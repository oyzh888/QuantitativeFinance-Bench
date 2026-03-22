# QFBench Task Calibration Progress

_Last updated: 2026-03-22 06:30 UTC_

---

## Active Task: kalman-pairs-trading

**Category:** statistical-arbitrage  
**Difficulty target:** hard — haiku pass rate < 20%, sonnet 30–60%  
**Branch:** `dev/kalman-pairs-trading`  
**Worktree:** `/home/node/.openclaw/workspace-cto/worktrees/kalman-pairs-trading`

---

## Calibration History

| Version | DI Items | Oracle | Haiku | Sonnet | Status |
|---------|----------|--------|-------|--------|--------|
| v1_base | DI-01 | ✅ 1.000 | ❌ pass_rate=1.0 | — | ESCALATED — too easy |
| v2_tc | DI-01, DI-02 | ✅ 1.000 | ❌ pass_rate=1.0 | — | ESCALATED — still too easy |
| **v3_mle** | DI-01, DI-02, DI-03 | **✅ 1.000** | ⏳ pending | ⏳ pending | **CURRENT — awaiting calibration** |

---

## DI Items

| ID | Description | Status |
|----|-------------|--------|
| DI-01 | Kalman Filter core (state-space model, predict/update) | ✅ stable |
| DI-02 | Transaction costs: 0.05%/side deducted from P&L and all metrics | ✅ deployed v2 |
| DI-03 | MLE delta calibration: agent must find optimal `delta ∈ [1e-6, 1e-2]` via Kalman log-likelihood on first 250 days | ✅ deployed v3 |

---

## v3 Oracle Results (job: 2026-03-22__06-29-38)

```
delta* found by MLE: 4.997308e-06   (vs hardcoded 1e-4 in v1/v2)
avg_beta:        1.3242
avg_spread_std:  0.2980   (was 0.119 in v2 — much larger, filter more stable)
total_return:    0.045478
num_trades:      16
sharpe_ratio:    3.4179
win_rate:        1.0
Tests:           12/12 ✅
Time:            19.8s (Novita sandbox)
```

---

## Why Each Version Failed

| Version | Root cause |
|---------|-----------|
| v1 | Full pseudocode + exact Python formulas → haiku copied line-for-line |
| v2 | Added tx cost but kept `delta=1e-4` explicit → haiku still pattern-matched |
| v3 | `delta` removed; requires MLE over log-likelihood — needs real understanding |

---

## Next Actions

- [ ] Run haiku calibration on v3 (target: pass_rate ≤ 0.20)
- [ ] Run sonnet calibration (target: pass_rate 0.30–0.60)
- [ ] Update this file with results
- [ ] Commit + push + merge PR when calibrated

---

## How to Run Calibration

```bash
# Oracle (verify task correctness)
cd /home/node/.openclaw/workspace-cto/QuantitativeFinance-Bench
python3 scripts/run_oracle.py kalman-pairs-trading

# Haiku agent calibration (run_agent.py — TODO: build this script)
python3 scripts/run_agent.py kalman-pairs-trading --model claude-haiku-4-5 --n 3

# Results land in:
ls jobs/latest/
```

---

## Task Pipeline Overview

| Task | Category | Oracle | Haiku | Status |
|------|----------|--------|-------|--------|
| **kalman-pairs-trading** | stat-arb | ✅ v3 | ⏳ pending | **CALIBRATING v3** |
| bollinger-backtest-aapl | backtesting | ✅ (server) | 0.0 (server) | needs Novita migration |
| american-option-fd-new | derivatives | ? | ? | untested |
| barrier-garch-var | cross-domain | ? | ? | untested |
| cta-basel-capital | cross-domain | ? | ? | untested |
| fama-french-factor-model-new | factor | ? | ? | untested |
| hull-white-swaption | IR deriv | ? | ? | untested |
| kelly-var-sizing | cross-domain | ? | ? | untested |
| mc-greek-surface-1 | derivatives | ? | ? | untested |
| momentum-backtest | backtesting | ? | ? | untested |
| regime-cta-vol-target | cross-domain | ? | ? | untested |
| regime-riskparity-cvar | cross-domain | ? | ? | untested |
| sentiment-factor-alpha | cross-domain | ? | ? | untested |
| stochvol-implied-surface-new | derivatives | ? | ? | untested |
| structured-note-risk | cross-domain | ? | ? | untested |
