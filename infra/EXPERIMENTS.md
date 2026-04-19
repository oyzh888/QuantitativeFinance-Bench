# Experiment Log

Manual log of Harbor benchmark runs with links to raw logs.

For the full experiment grid, see [TRACKER.md](TRACKER.md).

## Runs

| Date | Trial | Task | Agent | Model | Provider | Tokens (in/out) | Tests | Reward | Duration | Infra | Logs |
|------|-------|------|-------|-------|----------|-----------------|-------|--------|----------|-------|------|
| 2026-04-19 | fb-v3 | american-option-fd-new | claude-code 2.1.114 | claude-sonnet-4 | Bedrock | 904K / 12.8K | 41/54 (75.9%) | 0.0 | 5m56s | c6id.24xlarge CPU | [result](logs/fb-v3-american-option-fd-new/result.json) · [tests](logs/fb-v3-american-option-fd-new/verifier/test-stdout.txt) · [trajectory](logs/fb-v3-american-option-fd-new/agent/claude-code.txt) · [session](logs/fb-v3-american-option-fd-new/agent/sessions/projects/-app/) |
| 2026-04-19 | fb-claude-s4 | american-option-fd-new | claude-code 2.1.114 | claude-sonnet-4 | Bedrock | ~1.6M / ~31K | N/A (verifier hung) | N/A | ~23m | c6id.24xlarge CPU | [trajectory](logs/fb-claude-s4-american-option-fd-new/agent/claude-code.txt) · [session](logs/fb-claude-s4-american-option-fd-new/agent/sessions/) |
| 2026-04-19 | fb-sonnet4-barrier | barrier-garch-var | claude-code | claude-sonnet-4 | Bedrock | 336K / 8.7K | 0/1 | 0.175 | ~6m | c6id.24xlarge CPU | [result](logs/fb-sonnet4-barrier/result.json) · [tests](logs/fb-sonnet4-barrier/verifier/test-stdout.txt) · [trajectory](logs/fb-sonnet4-barrier/agent/claude-code.txt) |
| 2026-04-19 | fb-haiku45-option | american-option-fd-new | claude-code | claude-haiku-4.5 | Bedrock | 1.6M / 25.5K | 41/54 (75.9%) | 0.0 | ~20m | c6id.24xlarge CPU | [result](logs/fb-haiku45-option/result.json) · [tests](logs/fb-haiku45-option/verifier/test-stdout.txt) · [trajectory](logs/fb-haiku45-option/agent/claude-code.txt) |
| 2026-04-19 | fb-sonnet45-sma | sma-crossover-spy | claude-code | claude-sonnet-4.5 | Bedrock | 99K / 3.2K | 20/20 (100%) | **1.0** | ~4m | c6id.24xlarge CPU | [result](logs/fb-sonnet45-sma/result.json) · [tests](logs/fb-sonnet45-sma/verifier/test-stdout.txt) · [trajectory](logs/fb-sonnet45-sma/agent/claude-code.txt) |
| 2026-04-19 | fb-haiku45-hull | hull-white-swaption | claude-code | claude-haiku-4.5 | Bedrock | 1.9M / 35.6K | 0/43 (0%) | 0.0 | ~22m | c6id.24xlarge CPU | [result](logs/fb-haiku45-hull/result.json) · [tests](logs/fb-haiku45-hull/verifier/test-stdout.txt) · [trajectory](logs/fb-haiku45-hull/agent/claude-code.txt) |
| 2026-04-19 | fb-sonnet4-momentum | momentum-backtest | claude-code | claude-sonnet-4 | Bedrock | 186K / 4.2K | 26/26 (100%) | **1.0** | ~5m | c6id.24xlarge CPU | [result](logs/fb-sonnet4-momentum/result.json) · [tests](logs/fb-sonnet4-momentum/verifier/test-stdout.txt) · [trajectory](logs/fb-sonnet4-momentum/agent/claude-code.txt) |

## Results Summary

| Model | Tasks Attempted | Full Pass (reward=1) | Partial | Fail | Avg Tokens In |
|-------|----------------|---------------------|---------|------|---------------|
| Claude Sonnet 4 | 3 | 1 (momentum) | 1 (barrier 0.175) | 1 (option 75.9%) | 309K |
| Claude Sonnet 4.5 | 1 | **1** (sma 100%) | 0 | 0 | 99K |
| Claude Haiku 4.5 | 2 | 0 | 1 (option 75.9%) | 1 (hull 0%) | 1.8M |

**Key observations:**
- **Sonnet 4.5** is the most token-efficient: solved sma-crossover-spy with only 99K input tokens
- **Haiku 4.5** uses 5-10x more tokens (1.6-1.9M) due to more conversation turns, and still fails on harder tasks
- **Sonnet 4** shows consistent mid-tier performance across diverse tasks
- Tasks vary widely in difficulty: momentum-backtest and sma-crossover are easier; hull-white-swaption and barrier-garch-var are significantly harder

## Failed Tests (fb-v3)

| Test Category | Test Name | Status |
|---------------|-----------|--------|
| OptionValues | test_european_put_range | FAIL |
| OptionValues | test_european_call_range | FAIL |
| OptionValues | test_american_put_range | FAIL |
| OptionValues | test_american_call_range | FAIL |
| NoDividend | test_no_div_american_call_equals_european_call | FAIL |
| NoDividend | test_dividends_increase_put_value | FAIL |
| NoDividend | test_dividends_decrease_call_value | FAIL |
| EarlyExerciseBoundary | test_boundary_at_maturity | FAIL |
| EarlyExerciseBoundary | test_boundary_put_delta_near_minus_one | FAIL |
| Greeks | test_european_put_delta_range | FAIL |
| AmericanPutGrid | test_grid_at_S0_interpolated_matches_price | FAIL |
| Summary | test_summary_no_div_call_diff | FAIL |
| Summary | test_summary_boundary_at_T | FAIL |

## Quick Links

- [Infra README](README.md) — Setup and usage guide
- [Experiment Tracker](TRACKER.md) — Full experiment grid
- [Init script](../init_harbor_dind.sh) — DinD bootstrap
- [Harbor docs](https://harborframework.com/)
