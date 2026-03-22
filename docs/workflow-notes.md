# QFBench Task Development Workflow Notes

_Last updated: 2026-03-22_

---

## Standard Task Development Loop

```
1. New worktree      → git worktree add worktrees/<task> dev/<task>
2. Codex --yolo      → 全自主开发 (reads DEVPLAN + ref task, writes all files, commits)
3. run_oracle.py     → Novita sandbox oracle 验证 (~20-40s)
4. Fix minor issues  → 通常只需加漏掉的依赖 (e.g., -w scipy in test.sh)
5. run_agent.py      → Novita sandbox haiku 校准 (target: pass_rate ≤ 20%)
6. If too easy       → Codex --yolo 收紧 instruction，goto 3
7. run_agent.py      → sonnet 校准 (target: pass_rate 30-60%)
8. commit + PR       → merge
```

---

## Codex Prompt Template

```bash
cd worktrees/<task-name>
codex --yolo "
You are building a QFBench benchmark task from scratch. Full autonomy.

## Context
Read first:
1. DEVPLAN.md — project rules
2. tasks/bollinger-backtest-aapl/instruction.md — reference instruction style
3. tasks/bollinger-backtest-aapl/solution/solve.sh — reference oracle style
4. tasks/bollinger-backtest-aapl/tests/test.sh + test_outputs.py — test harness pattern

## Task: <task-name>
Domain: <domain>
What agent must implement: <description>
Difficulty target: hard (haiku fails, sonnet ~50%)

## Files to create
tasks/<task-name>/
├── task.toml
├── instruction.md    (math equations only, NO code, NO step-by-step)
├── environment/data/ (generate synthetic data)
├── solution/solve.sh (oracle)
└── tests/test.sh + test_outputs.py

## Rules
- instruction.md: describe WHAT not HOW
- test.sh: copy bollinger pattern exactly, add all required -w packages
- Generate realistic synthetic data with numpy/random seed
- Design tests that ACTUALLY test understanding (not just schema)
- git add + git commit when done
- Notify: openclaw system event --text 'Done: <task> committed' --mode now
"
```

---

## Common Issues & Fixes

| Issue | Fix |
|-------|-----|
| `ModuleNotFoundError: scipy` in verifier | Add `-w scipy` to test.sh uvx command |
| `ModuleNotFoundError: ta-lib` | Add to Dockerfile instead |
| Oracle fails with edge case | Check synthetic data generation seed |
| Codex writes code in instruction.md | Re-run with explicit "NO code blocks" rule |
| sigma constraint direction wrong | Codex self-corrects in --yolo mode (noticed this) |

---

## Tasks Completed

| Task | Codex time | Oracle | Haiku | Notes |
|------|-----------|--------|-------|-------|
| kalman-pairs-trading v3 | — (manual) | ✅ 1.0 | ⏳ pending | MLE delta, DI-03 |
| merton-credit-model | ~10 min | ✅ 1.0 | ⏳ pending | Newton-Raphson, 13 tests |

---

## Execution Commands

```bash
# Create worktree
cd ~/workspace-cto/QuantitativeFinance-Bench
git branch dev/<task>
git worktree add ../worktrees/<task> dev/<task>

# Run Codex
cd ../worktrees/<task>
codex --yolo "$(cat /tmp/<task>-prompt.txt)"

# Verify oracle (from main repo)
cd ~/workspace-cto/QuantitativeFinance-Bench
python3 scripts/run_oracle.py <task>

# Check result
cat jobs/latest/artifacts/results.json

# Haiku calibration (once run_agent.py exists)
python3 scripts/run_agent.py <task> --model claude-haiku-4-5 --n 3
```

---

## Key Learnings

1. **--yolo is essential** — `--full-auto` stops to ask about every external command
2. **Codex reads DEVPLAN** — it follows the instruction.md style guide automatically
3. **Codex self-debugs** — caught and fixed its own sigma_A < sigma_E constraint error
4. **test.sh dependencies** — Codex often forgets to add scipy/other packages to uvx
5. **Novita sandbox** — 20-40s oracle run, $0.001/run, no Docker setup needed
6. **One fix after Codex** — usually just missing test dependency, not logic errors
