# Harbor on Pluto — Infrastructure for Running Benchmarks

Run QuantitativeFinance-Bench (Harbor agent benchmarks) on Adobe Pluto cluster.

## Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│  Pluto Pod (c6id.24xlarge CPU or A10G GPU, Docker-in-Docker)      │
│                                                                    │
│  init_harbor_dind.sh (init script, auto-executed on pod start)     │
│  ├── 1. Bootstrap pip (container has no pip)                       │
│  ├── 2. Install Docker Compose V2 plugin (from shared FS)         │
│  ├── 3. Install uv + Python 3.12                                  │
│  ├── 4. Clone QuantitativeFinance-Bench repo                      │
│  ├── 5. Create venv, install Harbor + litellm + pytest             │
│  ├── 6. Build sandbox Docker image + patch network_mode: host      │
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
│  Results → /sensei-fs-3/users/zouyang/fb-harbor/trials/            │
└────────────────────────────────────────────────────────────────────┘
```

## Quick Start

### One-time setup (from any Pluto machine with Docker)

```bash
# 1. Copy Docker Compose V2 plugin to shared FS
mkdir -p /sensei-fs-3/users/zouyang/fb-harbor
cp /usr/libexec/docker/cli-plugins/docker-compose \
   /sensei-fs-3/users/zouyang/fb-harbor/docker-compose-plugin

# 2. Save Bedrock credentials
echo "export AWS_BEARER_TOKEN_BEDROCK='${AWS_BEARER_TOKEN_BEDROCK}'" \
  > /sensei-fs-3/users/zouyang/fb-harbor/.bedrock_env
chmod 600 /sensei-fs-3/users/zouyang/fb-harbor/.bedrock_env
```

### Launch a benchmark run

```bash
cd infra/pluto

# Quick test: single task (auto-picks cheapest available allocation)
python3 launch.py --name fb-test --task tasks/american-option-fd-new

# Full benchmark: all tasks
python3 launch.py --name fb-full

# Force GPU nodes
python3 launch.py --name fb-gpu --strategy gpu

# Check status
python3 launch.py --status <job_id>

# Stop
python3 launch.py --stop <job_id>
```

### Monitor

```bash
# Live logs
tail -f /sensei-fs-3/users/zouyang/fb-harbor/init-log.txt

# Results
ls /sensei-fs-3/users/zouyang/fb-harbor/trials/
cat /sensei-fs-3/users/zouyang/fb-harbor/trials/*/result.json | python3 -m json.tool
```

## Allocation Strategy

`launch.py` uses a tiered fallback strategy to minimize cost:

| Tier | Instance | Priority | Cost | Notes |
|------|----------|----------|------|-------|
| 1 (default) | c6id.24xlarge CPU | P2 preemptible | Free | 720 quota in GAI-415 |
| 2 | c6id.24xlarge CPU | P0 guaranteed | Quota-charged | Guaranteed allocation |
| 3 | g5.12xlarge A10G | P2 preemptible | Free | Smallest GPU full-node |

**Why full-node?** Docker-in-Docker (`enable_docker=True`) on Pluto requires
privileged mode, which requires full-node allocation. CPU nodes are preferred
since Harbor/agents don't need GPU.

If a tier gets `INSUFFICIENT_RESOURCES` for >60 seconds, it automatically
falls back to the next tier. Override with `--strategy`:
- `default` — CPU preemptible → CPU guaranteed → GPU preemptible
- `gpu` — GPU preemptible → GPU guaranteed
- `guaranteed` — CPU non-preemptible only

## File Structure

```
infra/
├── README.md              # This file
├── pluto/
│   ├── launch.py          # One-command launcher with fallback
│   ├── pluto_client.py    # Pluto gRPC job management SDK
│   └── manage.py          # Low-level job CLI (create/start/stop/status/resources)
init_harbor_dind.sh        # DinD pod init script (auto-runs on pod start)
```

## Key Technical Decisions

### 1. CPU-only is the default

Harbor + Claude Code agent is purely API-call driven — no GPU needed. Using
c6id.24xlarge saves GPU resources for actual training workloads. The preemptible
(P2) tier is quota-free, making benchmark runs essentially free.

### 2. Bedrock auth passthrough

The Bedrock token must reach three layers deep:
```
Pluto pod env → Harbor process → Harbor's inner Docker container → Claude Code
```

The init script sources the token from shared FS, and passes it into the Harbor
container via `--ae AWS_BEARER_TOKEN_BEDROCK=$TOKEN`. Without `--ae`, the
inner container sees `apiKeySource: "none"` and Claude Code fails.

### 3. Docker Compose V2 plugin

Pluto's Ubuntu Docker 28.2.2 package doesn't include the Compose V2 plugin,
but Harbor requires `docker compose` (V2 syntax). We pre-copy the 74MB binary
to shared FS and install it in the init script.

### 4. network_mode: host

k8s DinD pods can't use Docker's default bridge networking. The init script
patches Harbor's `docker-compose-base.yaml` to add `network_mode: host`.

### 5. Extended thinking disabled

Bedrock has a multi-turn serialization bug with extended thinking — the second
API call fails because Claude Code strips thinking blocks from conversation
history, but Bedrock requires them. Fix: `--agent-kwarg max_thinking_tokens=0`.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `INSUFFICIENT_RESOURCES` | Use `--strategy default` (tries multiple tiers) |
| `Docker not available` | Ensure job was created with `--enable-docker` |
| `docker compose: unknown` | Check that `docker-compose-plugin` exists on shared FS |
| Agent exit code 1 | Check `--ae` flags — Bedrock token might not be passed through |
| `apiKeySource: "none"` | Normal for Bedrock; check that `AWS_BEARER_TOKEN_BEDROCK` is in `--ae` |
| Verifier hangs | Known issue with `network_mode: host`; agent results are still valid |
| Preempted mid-run | Use `--strategy guaranteed` for important runs |
