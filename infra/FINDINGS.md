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

## Recommended Approach

### Option A: Use A10G GPU Nodes for DinD (best availability)
- A10G has **5 free GPUs** with 58% utilization (lowest of all GPU types)
- Create preemptible A10G jobs with DinD enabled
- We waste the GPU but get Docker access reliably
- Cost: 1 GPU per benchmark run

### Option B: Use One Large DinD Node for Multiple Benchmarks
- Create **one** A10G or A100 preemptible DinD job
- SSH into it and run **multiple Harbor benchmarks in parallel** via Docker
- Most efficient: 1 node runs N benchmarks concurrently
- The Harbor tasks are CPU-bound (LLM inference is remote API calls)
- **This is the recommended approach**

### Option C: Run on Current Machine
- Current machine is H200 but **does NOT have DinD privileges**
- `dockerd` fails with iptables permission denied
- Would need to request DinD on the existing interactive job

## Experiment Results (Completed)

| Trial | Model | Task | Reward | Input Tokens | Output Tokens |
|-------|-------|------|--------|-------------|---------------|
| fb-sonnet45-sma | Sonnet 4.5 | sma-crossover-spy | **1.0** | 99,029 | 3,212 |
| fb-sonnet4-momentum | Sonnet 4 | momentum-backtest | **1.0** | 185,757 | 4,236 |
| fb-sonnet4-barrier | Sonnet 4 | bollinger-backtest-aapl | **0.175** | 335,885 | 8,659 |
| fb-haiku45-hull | Haiku 4.5 | hull-white-swaption | **0.0** | 1,891,785 | 35,643 |
| fb-haiku45-option | Haiku 4.5 | option-pricing | **0.0** | 1,627,004 | 25,538 |
| fb-v3 | Sonnet 4 | kelly-var-sizing | **0.0** | 904,640 | 12,853 |

### Key Observations
1. **Sonnet 4/4.5 solve simpler tasks** (momentum, SMA) with perfect scores and low token usage
2. **Haiku 4.5 burns 10-20x more tokens** on hard tasks and still fails — it thrashes
3. **Harder quant tasks** (hull-white, option-pricing, kelly) remain unsolved across all models
4. **Token efficiency varies wildly**: Sonnet 4.5 used 99K tokens for a perfect score vs Haiku's 1.9M for zero

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
