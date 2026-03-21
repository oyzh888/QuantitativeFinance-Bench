# Novita Agent Sandbox — Integration Notes for QFBench

## Overview

We're evaluating [Novita Agent Sandbox](https://novita.ai/docs/guides/sandbox-overview) as an execution backend for QFBench tasks, replacing the current DigitalOcean droplet + Docker setup.

**Key motivation:** Current setup is serial (1 task at a time on a single VM). Novita supports up to 100 concurrent sandboxes, which would cut a full 100-task × 3-model benchmark sweep from ~8 hours down to ~15 minutes.

---

## Test 1: Hello World (2026-03-21)

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

# Test run_code
result = sandbox.run_code("print('hello from novita sandbox!')")
print(result.logs)  # stdout: ['hello from novita sandbox!\n']

# Test shell command
result2 = sandbox.commands.run('echo "shell works!" && python3 --version')
print(result2.stdout)  # shell works! / Python 3.12.11

sandbox.kill()
```

### Result

```
Sandbox created: irxdmbwh61swyd6tqtxzm-c81df28e
run_code result: Logs(stdout: ['hello from novita sandbox!\n'], stderr: [])
commands.run result: CommandResult(stderr='', stdout='shell works!\nPython 3.12.11\n', exit_code=0, error='')
```

**Sandbox cold-start: ~1.2s. API works exactly as documented.**

---

## Test 2: Full QFBench Task — `bollinger-backtest-aapl` (2026-03-21)

Tested the complete pipeline: upload data → run oracle → run verifier → read reward.

### Test Script

```python
import os, time
os.environ['NOVITA_API_KEY'] = 'sk_...'

from novita_sandbox.code_interpreter import Sandbox
from novita_sandbox.core.sandbox.filesystem.filesystem import WriteEntry

TASK_DIR = "./tasks/bollinger-backtest-aapl"

# 1. Create sandbox
sandbox = Sandbox.create()

# 2. Upload task files (use user="root" for system paths)
sandbox.files.write_files([
    WriteEntry(path="/app/aapl_prices.csv", data=open(f"{TASK_DIR}/environment/data/aapl_prices.csv", "rb").read()),
    WriteEntry(path="/app/solve.sh",        data=open(f"{TASK_DIR}/solution/solve.sh", "rb").read()),
    WriteEntry(path="/tests/test.sh",       data=open(f"{TASK_DIR}/tests/test.sh", "rb").read()),
    WriteEntry(path="/tests/test_outputs.py", data=open(f"{TASK_DIR}/tests/test_outputs.py", "rb").read()),
], user="root")

# Create required directories
sandbox.commands.run("mkdir -p /app/output /logs/verifier", user="root")

# 3. Run oracle
result = sandbox.commands.run("cd /app && bash /app/solve.sh", timeout=300, user="root")
print(f"oracle exit_code: {result.exit_code}")

# 4. Run verifier
verify = sandbox.commands.run("cd /app && bash /tests/test.sh", timeout=300, user="root")
print(f"verifier exit_code: {verify.exit_code}")

# 5. Read reward
reward = float(sandbox.files.read("/logs/verifier/reward.txt").strip())
print(f"reward: {reward}")  # 1.0 = PASS

# 6. Cleanup
sandbox.kill()
```

### ⚠️ API Gotchas

| Issue | Solution |
|-------|----------|
| `ImportError: cannot import name 'SandboxFile'` | Use `WriteEntry` from `novita_sandbox.core.sandbox.filesystem.filesystem` |
| `mkdir: cannot create directory '/logs': Permission denied` | Add `user="root"` to all `commands.run()` and `files.write_files()` calls that touch system paths |

### Results

```
============================================================
SUMMARY
============================================================
  Task:          bollinger-backtest-aapl
  Reward:        1.0
  Total time:    32.8s (0.5 min)
    - sandbox create: 0.6s
    - file upload:    5.1s
    - oracle run:     12.9s
    - verifier run:   13.3s
  Estimated cost: $0.00106
============================================================
```

**✅ 35/35 tests passed. Oracle reward = 1.0. Full pipeline works.**

---

## Performance & Cost Summary

### Timing Breakdown (bollinger-backtest-aapl oracle run)

| Step | Time |
|------|------|
| `Sandbox.create()` | 0.6s |
| File upload (4 files, ~155KB total) | 5.1s |
| Oracle (`solve.sh`, Python compute) | 12.9s |
| Verifier (`test.sh`, pytest 35 tests) | 13.3s |
| **Total** | **~33s** |

### Cost

| Run | Duration | Estimated Cost |
|-----|----------|----------------|
| Hello World | 3.9s | $0.000044 |
| bollinger-backtest-aapl oracle | 32.8s | $0.00106 |

Spec used: 2 vCPU (`$0.0000196/s`) + 4GB RAM (`$0.0000128/s`) = `$0.0000324/s`

### Projected Cost: Full Benchmark Sweep

| Scenario | Per-task | 100 tasks × 3 models |
|----------|----------|----------------------|
| Fast (3 min) | ~$0.006 | ~$1.80 |
| Typical (5 min) | ~$0.010 | ~$3.00 |
| Slow (8 min) | ~$0.016 | ~$4.80 |

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
| `solution/solve.sh` (oracle) | `sandbox.commands.run('bash /app/solve.sh', user='root')` |
| `tests/test.sh` | `sandbox.commands.run('bash /tests/test.sh', user='root')` |
| `reward.txt` | `sandbox.files.read('/logs/verifier/reward.txt')` |

---

## Next Steps

- [ ] Build custom Novita template with the finance-bench-sandbox Python stack (numpy, pandas, scipy, ta-lib, etc.) — currently using base sandbox which doesn't have TA-Lib
- [ ] Test a task that requires TA-Lib (e.g. `rsi-signal-backtest`)
- [ ] Implement parallel task runner with `asyncio` + semaphore for concurrent dispatch
- [ ] Benchmark: compare timing/cost vs current DO droplet serial run
- [ ] Wire up LLM agent (claude-haiku/sonnet) as the solver instead of oracle

---

## Account Info

- **Account:** aitist.dev@gmail.com
- **User ID:** 5918c2f7-3988-4efe-954c-6b025bb8d203
