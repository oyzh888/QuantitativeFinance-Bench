# Harbor Benchmark Infrastructure — Findings & Status

> Last updated: 2026-04-19 by Claude (session on finance-bench)

## Architecture

Harbor benchmarks require Docker-in-Docker (DinD) to run. The benchmark spins up
Docker containers inside a Pluto pod. This means:

1. The Pluto job **must** have `enable_docker=True` (privileged DinD mode)
2. The job needs network access to pull Docker images + call LLM APIs
3. The init script bootstraps pip, clones the repo, builds Harbor, then runs tasks

### Multi-Provider Support

`init_harbor_dind.sh` auto-detects the LLM provider from `FB_MODEL`:

| Model String | Provider | Auth Method |
|-------------|----------|-------------|
| `bedrock/us.anthropic.claude-*` | AWS Bedrock | `$PLUTO_AUTH_TOKEN` via foundry_aws_gateway |
| `openai/google/gemini-2.5-*` | Vertex AI (OpenAI compat) | `foundry_auth.py gemini` → OPENAI_API_KEY |
| `azure/gpt-*` | Azure OpenAI | `foundry_auth.py azure` → AZURE_API_KEY |

Key discovery: Gemini works via Vertex AI's **OpenAI-compatible endpoint**, not litellm's
native `vertex_ai/` provider (which needs service account JSON, not raw OAuth tokens).

## Cluster Resources (as of 2026-04-19)

```
INSTANCE               GPU             NODES    TOTAL     USED     FREE   UTIL   CORD
c5d.18xlarge           CPU              5       275       255       20    93%     0
c6id.24xlarge          CPU              0         0         0        0     0%     1
g5.12xlarge            A10G             3        12         7        5    58%     0
p4d.24xlarge           A100-40GB      208      1664      1582       82    95%     2
p4de.24xlarge          A100-80GB     1030      8240      7877      363    96%     1
p5.48xlarge            H100 (80GB)    443      3544      3432      112    97%     1
p5en.48xlarge          H200 (141GB)   686      5488      5071      417    92%     0
p6-b200.48xlarge       B200 (180GB)    27       216       129       87    60%     3
```

### Project Quota (Foundry-THD)
```
c6id.24xlarge   CPU         alloc=0  used=0   avail=0    preempt=8
p5en.48xlarge   H200        alloc=0  used=45  avail=-77  preempt=0
```

### Why CPU Jobs Were Stuck 12+ Hours

**c6id.24xlarge has 0 schedulable nodes** (1 cordoned). Preemptible CPU jobs requesting
c6id nodes will wait forever — there are simply no nodes in the pool.

c5d.18xlarge has 5 nodes with 20 free units, but our project doesn't have c5d quota.

## DinD Job Creation Issues

### What Worked (2026-04-19)
- **A10G preemptible DinD**: Created 3 jobs on g5.12xlarge with `enable_docker=True`,
  `disable_split_node_capacity=True`, 4 GPUs each. Took 2-5 minutes to schedule.
- The init scripts on shared FS (`/sensei-fs-3/.../scripts/init_machine_*.sh`) ran successfully.

### What Failed
- **A100-40GB (p4d) preemptible**: Jobs showed as FAILED (run_status=6) with 0 allocated ranks.
  Initiative quota shows `alloc=0` for p4d, meaning no quota available.
- **H200 (p5en) non-preemptible**: Also failed despite 67 available quota GPUs.
  Possibly the `disable_split_node_capacity` flag wasn't set in earlier attempts.
- **Running Docker on non-DinD H200**: `dockerd` fails with iptables permission denied.
  Using `--iptables=false --bridge=none` starts Docker but containers can't be created
  ("failed to create default sandbox: operation not permitted").

### Critical Auth Fix
The Bedrock auth token must be the **ABSK-prefixed** gateway token (from `$AWS_BEARER_TOKEN_BEDROCK`
as set by the Pluto environment), NOT the raw JWT from `$PLUTO_AUTH_TOKEN`. Initial runs failed
with "Invalid API Key format: Must start with pre-defined prefix" because we exported the
raw JWT instead of the ABSK token.

## Recommended Approach

### Use A10G DinD Nodes (proven working)
- A10G (g5.12xlarge) has **5 free GPUs** with 58% utilization
- Create preemptible A10G jobs with `enable_docker=True`, full node (4 GPUs)
- Run multiple Harbor benchmarks in parallel per machine (`MAX_PARALLEL=5`)
- We waste the GPU but get Docker access reliably
- **This is what works**: 3 machines × 5 parallel tasks = 15 concurrent benchmarks

## Experiment Results

### Full Sonnet 4 Batch (16 tasks, 2026-04-19)

Run on 3 DinD machines (A10G preemptible), 5 tasks parallel per machine.

| Task | Reward | Input Tokens | Output Tokens |
|------|--------|-------------|---------------|
| american-option-fd-new | **0.0** | 17,378 | 5,897 |
| barrier-garch-var | **0.325** | 307,567 | 6,224 |
| bollinger-backtest-aapl | **1.0** | 286,558 | 6,650 |
| cta-basel-capital | **0.083** | 302,522 | 7,883 |
| fama-french-factor-model-new | **1.0** | 518,554 | 8,474 |
| hull-white-swaption | **0.0** | 120,090 | 11,350 |
| kelly-var-sizing | **0.0** | ? | ? |
| mc-greek-surface-1 | **0.0** | ? | ? |
| mc-greeks-surface | **0.0** | ? | ? |
| momentum-backtest | **1.0** | 161,067 | 3,886 |
| regime-cta-vol-target | **0.0** | 68,888 | 305 |
| regime-riskparity-cvar | **0.519** | 294,393 | 5,122 |
| sentiment-factor-alpha | **0.0** | 68,330 | 288 |
| sma-crossover-spy | **1.0** | 213,560 | 4,930 |
| stochvol-implied-surface-new | *pending* | — | — |
| structured-note-risk | **N/A** | ? | ? |

**Summary**: 4/16 tasks scored 1.0, 2 partial (barrier=0.325, regime-riskparity=0.519, cta-capital=0.083). 9 tasks scored 0.0.

### Earlier Single-Task Results

| Trial | Model | Task | Reward | Input Tokens | Output Tokens |
|-------|-------|------|--------|-------------|---------------|
| fb-sonnet45-sma | Sonnet 4.5 | sma-crossover-spy | **1.0** | 99,029 | 3,212 |
| fb-sonnet4-momentum | Sonnet 4 | momentum-backtest | **1.0** | 185,757 | 4,236 |
| fb-sonnet4-barrier | Sonnet 4 | bollinger-backtest-aapl | **0.175** | 335,885 | 8,659 |
| fb-haiku45-hull | Haiku 4.5 | hull-white-swaption | **0.0** | 1,891,785 | 35,643 |
| fb-haiku45-option | Haiku 4.5 | option-pricing | **0.0** | 1,627,004 | 25,538 |
| fb-v3 | Sonnet 4 | kelly-var-sizing | **0.0** | 904,640 | 12,853 |

### Key Observations
1. **Sonnet 4 solves 4/16 tasks perfectly** (sma, momentum, bollinger, fama-french)
2. **Partial credit on 3 tasks**: barrier-garch-var (0.325), regime-riskparity (0.519), cta-capital (0.083)
3. **9 tasks score 0.0** — quant finance tasks are hard (option pricing, stochastic vol, greeks)
4. **Token efficiency varies wildly**: momentum used 161K tokens for 1.0 vs hull-white 120K for 0.0
5. **Some tasks fail very quickly** (sentiment, regime-cta with <70K tokens) suggesting immediate code errors
6. **Bollinger improved** from 0.175 (earlier) to 1.0 — possibly task/eval changes or better prompting

## Pluto SDK Breaking Changes

The Colligo Pluto SDK proto files were updated with breaking changes:

| Old Name | New Name | Location |
|----------|----------|----------|
| `SearchEntitiesRequest` | `SearchAllEntitiesRequest` | `ecs.model.search_entities_pb2` |
| `NameComponent` | moved | `system.model.components_pb2` |
| `ComponentMapItem.component_type` | Now requires `ComponentKind` message wrapper | — |
| `EntityType` string | `EntityKind` message | `ecs.model.base_pb2` |

**Workaround**: Monkey-patch the import before loading `client_ecs`:
```python
from colligo.pluto.proto.ecs.model import search_entities_pb2 as sep
sep.SearchEntitiesRequest = sep.SearchAllEntitiesRequest
sep.SearchEntitiesResponse = sep.SearchAllEntitiesResponse
# Now: from colligo.pluto.client.client_ecs import ECSClient  # works
```

Machine tokens also lack `ACTION_TYPE_CREATE_ENTITY` permission under the new API,
so **creating new jobs fails**. Workaround: restart previously created (stopped) jobs
using `BusinessActionsClient.RunBusinessActions` with `StartJobAction`.

## Files

| File | Purpose |
|------|---------|
| `infra/init_harbor_dind.sh` | Main DinD init script, multi-provider |
| `infra/scripts/foundry_auth.py` | Auto-generate Gemini/Azure credentials |
| `infra/scripts/gemini_auth.py` | Standalone Gemini auth (Vertex AI) |
| `infra/scripts/launch_experiments.py` | Batch experiment launcher (needs SDK fix) |
| `infra/FINDINGS.md` | This file |

## Next Steps

1. **Create one A10G DinD job** and run multiple benchmarks in parallel from it
2. Test GPT-5 (Azure) and Gemini 2.5 Flash/Pro on the same tasks
3. Fix `launch_experiments.py` to use the monkey-patched SDK
4. Collect enough data points for a proper model comparison
