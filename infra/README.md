# Infrastructure for Running Harbor Benchmarks

Run QuantitativeFinance-Bench (Harbor agent benchmarks) on Docker-in-Docker cloud instances.

## Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│  Cloud Instance (CPU or GPU, Docker-in-Docker enabled)             │
│                                                                    │
│  init_harbor_dind.sh (init script, auto-executed on instance)      │
│  ├── 1. Bootstrap pip (container may lack pip)                     │
│  ├── 2. Install Docker Compose V2 plugin                          │
│  ├── 3. Install uv + Python 3.12                                  │
│  ├── 4. Clone QuantitativeFinance-Bench repo                      │
│  ├── 5. Create venv, install Harbor + litellm + pytest            │
│  ├── 6. Build sandbox Docker image + patch network_mode: host     │
│  └── 7. Run Harbor benchmark                                      │
│      │                                                             │
│      ▼                                                             │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Harbor Docker Container (sandbox)                           │  │
│  │  ├── Claude Code CLI receives instruction.md                 │  │
│  │  ├── Agent writes code, executes, debugs (multi-turn)        │  │
│  │  ├── Outputs to /app/output/                                 │  │
│  │  └── Verifier: pytest validates outputs → reward 0 or 1      │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  Results → $SHARED_FS/trials/                                      │
└────────────────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Docker-in-Docker enabled instance (full-node allocation recommended)
- AWS Bedrock credentials (if using Bedrock models)

### One-time setup

```bash
# Save Bedrock credentials to shared filesystem
mkdir -p /path/to/shared-fs
echo "export AWS_BEARER_TOKEN_BEDROCK='${AWS_BEARER_TOKEN_BEDROCK}'" \
  > /path/to/shared-fs/.bedrock_env
chmod 600 /path/to/shared-fs/.bedrock_env
```

### Run a benchmark

```bash
# Set environment variables
export SHARED_FS=/path/to/shared-fs
export FB_TASK=tasks/american-option-fd-new   # or leave empty for all tasks
export FB_TRIAL_NAME=my-trial
export FB_MODEL=bedrock/us.anthropic.claude-sonnet-4-20250514-v1:0
export FB_AGENT=claude-code

# Run the init script
bash infra/init_harbor_dind.sh

# Monitor
tail -f /path/to/shared-fs/init-log.txt

# Check results
cat /path/to/shared-fs/trials/*/result.json | python3 -m json.tool
```

## Experiment Tracking

See [TRACKER.md](TRACKER.md) for the full experiment grid and results.

```bash
# Initialize experiment plan (12 models x 16 tasks x 3 rounds = 576 experiments)
python3 infra/scripts/tracker.py init

# Claim experiments for yourself
python3 infra/scripts/tracker.py claim --runner your-name --count 16 --model cc-sonnet-4

# Submit results from Harbor trials
python3 infra/scripts/tracker.py submit --runner your-name --trials-dir /path/to/trials/

# Regenerate TRACKER.md
python3 infra/scripts/tracker.py refresh

# Show summary
python3 infra/scripts/tracker.py status
```

## File Structure

```
infra/
├── README.md                  # This file
├── TRACKER.md                 # Experiment grid (auto-generated)
├── EXPERIMENTS.md             # Manual experiment log with links
├── experiments.jsonl          # Experiment plan data
├── schema/
│   └── fb-result-v1.json     # Result schema (JSON Schema)
├── scripts/
│   └── tracker.py             # Experiment tracker CLI
├── results/                   # Submitted result files (JSONL)
├── logs/                      # Raw Harbor logs (git LFS)
│   ├── fb-v3-american-option-fd-new/
│   └── fb-claude-s4-american-option-fd-new/
init_harbor_dind.sh            # DinD bootstrap script
```

## Key Technical Decisions

### 1. CPU-only by default

Harbor + Claude Code agent is purely API-call driven — no GPU needed. CPU instances
are cheaper and more available. GPU instances are only needed if the benchmark tasks
themselves require GPU computation.

### 2. Bedrock auth passthrough

The Bedrock token must reach three layers deep:
```
Host env → Harbor process → Harbor's inner Docker container → Claude Code
```

The init script loads credentials and passes them into the Harbor container via
`--ae AWS_BEARER_TOKEN_BEDROCK=$TOKEN`. Without `--ae`, the inner container has
no authentication and the agent fails.

### 3. Docker Compose V2 plugin

Some Docker installations don't include the Compose V2 plugin, but Harbor requires
`docker compose` (V2 syntax). The init script auto-downloads the binary if needed.

### 4. network_mode: host

k8s DinD pods can't use Docker's default bridge networking. The init script patches
Harbor's `docker-compose-base.yaml` to add `network_mode: host`.

### 5. Docker compose cp timeout

Harbor's `docker compose cp` operations (upload/download files) can hang indefinitely
in DinD environments. The init script patches Harbor's `docker.py` to add
`timeout_sec=300` to the 4 cp operations. Important: the general `exec()` method
is NOT patched — the agent needs unlimited execution time.

### 6. Extended thinking disabled

Bedrock has a multi-turn serialization bug with extended thinking — the second
API call fails because the agent strips thinking blocks from conversation history,
but Bedrock requires them. Fix: `--agent-kwarg max_thinking_tokens=0`.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `Docker not available` | Ensure Docker-in-Docker is enabled |
| `docker compose: unknown` | Init script auto-downloads; check network access |
| Agent exit code 1 | Check `--ae` flags — Bedrock token might not be passed through |
| `apiKeySource: "none"` | Normal for Bedrock; check `AWS_BEARER_TOKEN_BEDROCK` in `--ae` |
| Verifier hangs | Known DinD issue — init script patches cp timeout to fix this |

## Related Docs

- [Experiment Tracker](TRACKER.md) — Full experiment grid
- [Experiment Log](EXPERIMENTS.md) — Manual run log with log links
- [Harbor docs](https://harborframework.com/)
