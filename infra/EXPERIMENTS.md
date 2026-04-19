# Experiment Tracker

All Harbor benchmark runs on Pluto cluster.

## Runs

| Date | Trial | Task | Agent | Model | Provider | Tokens (in/out) | Tests | Reward | Duration | Infra | Logs |
|------|-------|------|-------|-------|----------|-----------------|-------|--------|----------|-------|------|
| 2026-04-19 | fb-v3 | american-option-fd-new | claude-code 2.1.114 | claude-sonnet-4 | Bedrock | 904K / 12.8K | 41/54 (75.9%) | 0.0 | 5m56s | c6id.24xlarge CPU preemptible | [result](logs/fb-v3-american-option-fd-new/result.json) · [tests](logs/fb-v3-american-option-fd-new/verifier/test-stdout.txt) · [trajectory](logs/fb-v3-american-option-fd-new/agent/claude-code.txt) · [session](logs/fb-v3-american-option-fd-new/agent/sessions/projects/-app/) |
| 2026-04-19 | fb-claude-s4 | american-option-fd-new | claude-code 2.1.114 | claude-sonnet-4 | Bedrock | ~1.6M / ~31K | N/A (verifier hung) | N/A | ~23m | c6id.24xlarge CPU preemptible | [trajectory](logs/fb-claude-s4-american-option-fd-new/agent/claude-code.txt) · [session](logs/fb-claude-s4-american-option-fd-new/agent/sessions/) |

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

## Infrastructure

- **Cluster**: Pluto (colligo-laser02-prod-uw2)
- **Instance**: c6id.24xlarge CPU, 80 cores, preemptible (P2 quota-free)
- **Docker**: Docker-in-Docker, full-node allocation
- **Shared FS**: `/sensei-fs-3/users/zouyang/fb-harbor/`
- **Launcher**: `infra/pluto/launch.py` with tiered fallback

## Quick Links

- [Infra README](README.md) — Setup and usage guide
- [Launch script](pluto/launch.py) — One-command launcher
- [Init script](init_harbor_dind.sh) — DinD pod bootstrap
- [Harbor docs](https://harborframework.com/)
