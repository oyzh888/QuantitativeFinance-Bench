# QFBench Task Calibration Progress

_Last updated: 2026-03-22_

---

## Active Task: kalman-pairs-trading

**Category:** statistical-arbitrage  
**Difficulty target:** hard (sonnet passes ~50%, haiku fails)  
**Branch:** `dev/kalman-pairs-trading`

### Calibration History

| Version | DI Items | Oracle | Haiku | Sonnet | Status |
|---------|----------|--------|-------|--------|--------|
| v1_base | DI-01 only | ✅ 1.000 | ❌ 1.000 (too easy) | — | ESCALATED |
| v2_tc   | DI-01 + DI-02 | ✅ 1.000 | 🔄 running... | — | CALIBRATING |

### DI Items Tracking

- **DI-01** (Kalman Filter core): ✅ stable — verified oracle passes
- **DI-02** (transaction costs): ✅ deployed — 0.05%/side, deducted from P&L + all metrics
  - v1 instruction had full pseudocode → haiku trivially copy-pasted
  - v2 instruction: math equations only, no code, no step-by-step algorithm
  - New test `test_transaction_costs_reflected` verifies costs are applied
  - Oracle: `job_id=2026-03-22__05-12-50`, reward=1.000 ✅

### Next Actions

1. [x] ~~Steve writes v2 instruction~~ → CTO rewrote: removed pseudocode, added tx cost
2. [x] ~~Oracle v2 confirmed~~ → ✅ reward=1.000
3. [ ] **WAITING**: Haiku calibration result (PID 180064, log: `/tmp/haiku-v2-cal.log`)
4. [ ] If haiku still passes → add DI-03 (e.g., stale P₀ vs convergence trick, or require Z-score EWMA)
5. [ ] If haiku fails → run sonnet (target 30–60% pass rate)
6. [ ] When haiku fails + sonnet reasonable → commit/push + merge PR

---

## Task Pipeline Overview

| Task | Category | Difficulty | Oracle | Haiku | Status |
|------|----------|------------|--------|-------|--------|
| kalman-pairs-trading | stat-arb | hard | ✅ | too easy (v1) | calibrating v2 |
| american-option-fd-new | derivatives | hard | ? | ? | untested |
| barrier-garch-var | cross-domain | hard | ? | ? | untested |
| bollinger-backtest-aapl | backtesting | medium | ? | ? | untested |
| cta-basel-capital | cross-domain | hard | ? | ? | untested |
| fama-french-factor-model-new | factor | easy | ? | ? | untested |
| hull-white-swaption | IR deriv | very_hard | ? | ? | untested |
| kelly-var-sizing | cross-domain | hard | ? | ? | untested |
| mc-greek-surface-1 | derivatives | hard | ? | ? | untested |
| mc-greeks-surface | derivatives | hard | ? | ? | untested |
| momentum-backtest | backtesting | easy | ? | ? | untested |
| regime-cta-vol-target | cross-domain | hard | ? | ? | untested |
| regime-riskparity-cvar | cross-domain | hard | ? | ? | untested |
| sentiment-factor-alpha | cross-domain | hard | ? | ? | untested |
| stochvol-implied-surface-new | derivatives | hard | ? | ? | untested |
| structured-note-risk | cross-domain | hard | ? | ? | untested |

---

## Notes & Decisions

- **v1 instruction too explicit**: Gave step-by-step pseudocode with exact formulas → haiku solved trivially
- **v2 direction**: Remove pseudocode, only describe *what* to compute (not how), force agent to know Kalman math
- **Calibration target**: haiku reward ~0, sonnet reward 0.3–0.6, only strong models can solve
- **DI-02 idea**: Add regime detection sub-task or require agent to infer Kalman parameters from docs (no given delta/R formula)
