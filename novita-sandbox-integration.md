# Novita Agent Sandbox — Integration Notes for QFBench

## Overview

We're evaluating [Novita Agent Sandbox](https://novita.ai/docs/guides/sandbox-overview) as an execution backend for QFBench tasks, replacing the current DigitalOcean droplet + Docker setup.

**Key motivation:** Current setup is serial (1 task at a time on a single VM). Novita supports up to 100 concurrent sandboxes, which would cut a full 100-task × 3-model benchmark sweep from ~8 hours down to ~15 minutes.

---

## Hello World Test (2026-03-21)

### Setup

```bash
pip install novita-sandbox
```

```python
import os
os.environ['NOVITA_API_KEY'] = 'sk_...'  # from novita.ai > Key Management

from novita_sandbox.code_interpreter import Sandbox

sandbox = Sandbox.create()
print(f"Sandbox created: {sandbox.sandbox_id}")
```

### Test Script (`/tmp/novita_test.py`)

```python
import os
os.environ['NOVITA_API_KEY'] = 'sk_RlPbM...'

from novita_sandbox.code_interpreter import Sandbox

print("Creating sandbox...")
sandbox = Sandbox.create()
print(f"Sandbox created: {sandbox.sandbox_id}")

# Test 1: run Python code directly
result = sandbox.run_code("print('hello from novita sandbox!')")
print("run_code result:", result.logs)

# Test 2: run shell command
result2 = sandbox.commands.run('echo "shell works!" && python3 --version')
print("commands.run result:", result2)

sandbox.kill()
print("Done!")
```

### Results

```
Creating sandbox...
Sandbox created: irxdmbwh61swyd6tqtxzm-c81df28e
run_code result: Logs(stdout: ['hello from novita sandbox!\n'], stderr: [])
commands.run result: CommandResult(stderr='', stdout='shell works!\nPython 3.12.11\n', exit_code=0, error='')
Done!
```

**Everything works as documented. API is straightforward.**

---

## Performance & Cost

### Timing (second run with warm SDK)

| Step | Time |
|------|------|
| `Sandbox.create()` | 1.2s |
| `run_code()` | 1.8s |
| `commands.run()` | 0.4s |
| `sandbox.kill()` | ~0.1s |
| **Total** | **~3.9s** |

Sandbox cold-start is **~1.2 seconds** — fast enough for parallel task orchestration.

### Cost for Hello World Run

- Sandbox was alive for ~3.9 seconds
- Default spec: 1 vCPU + 512MiB RAM
- CPU: `$0.0000098/s × 3.9s = $0.0000382`
- RAM: `$0.0000016/s × 3.9s = $0.0000062`
- **Total: ~$0.000044 (less than half a cent per thousand runs)**

### Projected Cost for Full QFBench Benchmark

Task spec from `task.toml`: 2 vCPU / 4GB RAM, agent timeout 900s, verifier timeout 300s

| Scenario | Per-task cost | 100 tasks × 3 models |
|----------|--------------|----------------------|
| Fast task (3 min) | ~$0.006 | ~$1.80 |
| Typical (5 min) | ~$0.010 | ~$3.00 |
| Slow task (8 min) | ~$0.016 | ~$4.80 |
| Worst case (15 min) | ~$0.029 | ~$8.70 |

**~$3–5 per complete benchmark sweep** (compute only; LLM token costs are separate and larger).

---

## Architecture Plan: QFBench on Novita

### Current (DigitalOcean droplet)
```
serial loop → harbor CLI → Docker build → Docker run → collect reward
~8 hours for 100 tasks × 3 models
```

### Target (Novita Sandbox)
```
parallel dispatch (100 concurrent) → Novita API → collect rewards
~15 minutes for 100 tasks × 3 models
```

### What maps to what

| QFBench concept | Novita equivalent |
|-----------------|-------------------|
| `environment/Dockerfile` | Custom template (pre-built once) |
| `environment/data/` | `sandbox.files.write_files()` |
| `solution/solve.sh` (oracle) | `sandbox.commands.run('bash /app/solve.sh')` |
| `tests/test.sh` | `sandbox.commands.run('bash /tests/test.sh')` |
| `reward.txt` | `sandbox.files.read('/logs/verifier/reward.txt')` |

### Key Novita API calls needed

```python
# 1. Create sandbox (with custom template for finance stack)
sandbox = Sandbox.create(template_id="finance-bench-v1")

# 2. Upload task data
sandbox.files.write_files([
    SandboxFile(path="/app/data.json", content=open("data.json").read()),
    SandboxFile(path="/tests/test_outputs.py", content=open("test_outputs.py").read()),
    SandboxFile(path="/tests/test.sh", content=open("test.sh").read()),
])

# 3. Run oracle / agent
result = sandbox.commands.run("bash /app/solve.sh", timeout=900)

# 4. Run verifier
verifier = sandbox.commands.run("bash /tests/test.sh", timeout=300)

# 5. Collect reward
reward_txt = sandbox.files.read("/logs/verifier/reward.txt")
reward = float(reward_txt.strip())

# 6. Cleanup
sandbox.kill()
```

---

## Next Steps

- [ ] Build custom Novita template with the finance-bench-sandbox Python stack (numpy, pandas, scipy, ta-lib, etc.)
- [ ] Test full task end-to-end: `black-scholes-pricing` (upload data → run oracle → run verifier → read reward)
- [ ] Implement parallel task runner with `asyncio` + semaphore for concurrent dispatch
- [ ] Benchmark: compare timing/cost of Novita vs current DO droplet

---

## Account Info

- **Account:** aitist.dev@gmail.com
- **User ID:** 5918c2f7-3988-4efe-954c-6b025bb8d203
- **API Key:** stored in `/tmp/novita_test.py` (do not commit key to repo)
