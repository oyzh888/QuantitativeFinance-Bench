# Finance-Bench Dashboard

*Updated: 2026-04-22 08:00 UTC | Total results: 1037 (includes docker-fix reruns)*

## Leaderboard

| # | Model | Agent | N | Mean Reward | Success (>0) | Perfect (=1.0) |
|---|-------|-------|---|-------------|--------------|----------------|
| 1 | **codex-gpt-5.4** | codex-cli | 91 | 0.538 | 72/91 (79%) | 24/91 (26%) |
| 2 | **cc-opus-4-6** | claude-code | 188 | 0.472 | 99/188 (53%) | 77/188 (41%) |
| 3 | **gemcli-2.5-pro** | gemini-cli | 48 | 0.319 | 25/48 (52%) | 7/48 (15%) |
| 4 | **cc-sonnet-4-5** | claude-code | 258 | 0.293 | 94/258 (36%) | 62/258 (24%) |
| 5 | **cc-haiku-4-5-br** | claude-code | 189 | 0.269 | 67/189 (35%) | 40/189 (21%) |
| 6 | **gemcli-2.5-flash** | gemini-cli | 58 | 0.041 | 3/58 (5%) | 1/58 (2%) |
| 7 | **fz-gpt-5** | finance-zero | 144 | 0.000 | 0/144 (0%) | 0/144 (0%) |
| 8 | **fz-gemini-2.5-pro** | finance-zero | 48 | 0.000 | 0/48 (0%) | 0/48 (0%) |

## Per-Task Heatmap (Best Score Across Rounds)

| Task | codex-gpt-5.4 | cc-opus-4-6 | gemcli-2.5-pro | cc-sonnet-4-5 | cc-haiku-4-5-br | gemcli-2.5-flash |
|------|---:|---:|---:|---:|---:|---:|
| 13f-amendment-aware-crowding | - | 0.00 | - | 0.00 | 0.00 | - |
| alpha-hedge-strategy | - | **1.00** | - | **1.00** | 0.64 | - |
| american-binomial-tree | - | **1.00** | - | **1.00** | **1.00** | - |
| american-option-fd-new | **1.00** | **1.00** | 0.00 | **1.00** | 0.00 | 0.00 |
| amortization-schedule | - | **1.00** | - | **1.00** | **1.00** | - |
| asian-option-levy-curran | - | **1.00** | - | 0.00 | 0.00 | - |
| asian-option-pricing | - | **1.00** | - | **1.00** | **1.00** | - |
| barra-cne6-risk | - | 0.27 | - | 0.31 | 0.23 | - |
| barrier-garch-var | 0.62 | 0.70 | 0.57 | 0.53 | 0.38 | 0.42 |
| barrier-gbm-analytics | - | 0.00 | - | 0.00 | 0.00 | - |
| barrier-option-mc | - | **1.00** | - | **1.00** | 0.00 | - |
| beta-hedging | - | **1.00** | - | **1.00** | **1.00** | - |
| binance-btc-participation-tca | - | 0.00 | - | 0.00 | 0.00 | - |
| binary-option-pricing | - | **1.00** | - | **1.00** | **1.00** | - |
| bl-regime-hmm | - | 0.92 | - | 0.58 | 0.50 | - |
| black-litterman-allocation | - | 0.00 | - | 0.00 | **1.00** ★ | - |
| black-scholes-pricing | - | **1.00** | - | **1.00** | **1.00** | - |
| bollinger-backtest-aapl | **1.00** | **1.00** | 0.00 | **1.00** | **1.00** | 0.00 |
| bond-callable-pricing | - | 0.00 | - | 0.00 | 0.00 | - |
| bond-convexity | - | **1.00** | - | **1.00** | **1.00** | - |
| bond-portfolio-analytics | - | **1.00** | - | **1.00** | **1.00** | - |
| bond-yield-curve | - | **1.00** | - | 0.00 | **1.00** | - |
| brinson-sector-attribution | - | **1.00** | - | 0.00 | 0.00 | - |
| bs-greeks-pde | - | **1.00** | - | **1.00** | 0.00 | - |
| cap-floor-black-pricing | - | 0.00 | - | 0.00 | 0.00 | - |
| carry-trade-fx | - | 0.00 | - | 0.00 | 0.00 | - |
| cds-curve-stripping | - | 0.00 | - | 0.00 | 0.00 | - |
| cds-pricing | - | **1.00** | - | **1.00** | **1.00** | - |
| cev-option-pricing | - | 0.00 | - | 0.00 | 0.00 | - |
| cheapest-ETF-creation-basket | - | 0.00 | - | **1.00** | 0.00 | - |
| chooser-option-pricing | - | 0.00 | - | 0.00 | 0.00 | - |
| cir-bond-pricing | - | **1.00** | - | **1.00** | **1.00** | - |
| cliquet-ratchet-pricing | - | **1.00** | - | 0.00 | 0.00 | - |
| cme-hdd-option-pricing | - | **1.00** | - | **1.00** | 0.00 | - |
| compound-option-geske | - | 0.00 | - | 0.00 | **1.00** | - |
| corporate-action-adjustment | - | **1.00** | - | **1.00** | **1.00** | - |
| credit-migration-matrix | - | 0.00 | - | 0.00 | 0.00 | - |
| credit-portfolio-var-cvar | - | **1.00** | - | 0.00 | 0.00 | - |
| credit-spread-decomposition | - | **1.00** | - | **1.00** | 0.00 | - |
| cross-sectional-momentum | - | **1.00** | - | **1.00** | **1.00** | - |
| crypto-funding-rate-basis-carry | - | 0.00 | - | 0.00 | 0.00 | - |
| cta-basel-capital | 0.25 | 0.54 | 0.46 | 0.33 | 0.17 | 0.00 |
| cta-ewma-cvar | - | 0.00 | - | 0.00 | 0.00 | - |
| data-cleaning | - | **1.00** | - | **1.00** | **1.00** | - |
| dcc-garch-portfolio-var | - | 0.00 | - | 0.00 | 0.00 | - |
| delta-hedging-pnl-simulation | - | **1.00** | - | **1.00** | 0.00 | - |
| digital-barrier-options | - | **1.00** | - | **1.00** | 0.00 | - |
| dirty-gap-momentum-aapl | - | **1.00** | - | **1.00** | **1.00** | - |
| double-sort | - | 0.00 | - | 0.00 | 0.00 | - |
| earnings-news-event-alpha | - | 0.00 | - | 0.00 | 0.00 | - |
| earnings-surprise-calculator | - | **1.00** | - | **1.00** | **1.00** | - |
| equity-vendor-restatement-break-audit | - | 0.00 | - | 0.00 | 0.00 | - |
| etf-cross-asset-lead-lag | - | 0.00 | - | 0.00 | 0.00 | - |
| etf-overlap-redemption-pressure | - | 0.00 | - | 0.00 | 0.00 | - |
| event-study-earnings | - | 0.00 | - | 0.00 | 0.00 | - |
| evt-pot-var | - | **1.00** | - | 0.92 | 0.71 | - |
| ewma-portfolio-risk-decomposition | - | **1.00** | - | **1.00** | 0.00 | - |
| execution-is-vwap | - | 0.00 | - | 0.00 | 0.00 | - |
| execution-ledger-pnl-reconciliation | - | **1.00** | - | **1.00** | **1.00** | - |
| factor-momentum-spanning | - | 0.00 | - | 0.00 | 0.00 | - |
| fama-french-factor-model-new | **1.00** | **1.00** | **1.00** | **1.00** | **1.00** | **1.00** |
| fama-macbeth-risk-premia | - | 0.00 | - | 0.00 | 0.00 | - |
| fixed-income-market-stress | - | 0.00 | - | **1.00** | **1.00** | - |
| fomc-tone-event-study | - | **1.00** | - | 0.00 | 0.00 | - |
| form4-cross-sectional-sale-pressure | - | 0.00 | - | 0.00 | 0.00 | - |
| futures-carry-repair | - | 0.00 | - | 0.00 | 0.00 | - |
| fx-carry-forward-hedge | - | 0.00 | - | 0.00 | 0.00 | - |
| fx-carry-trade-backtest | - | 0.00 | - | 0.00 | 0.00 | - |
| fx-forward-cross-rate | - | 0.00 | - | **1.00** | 0.00 | - |
| garch-vecm-cointegration | - | 0.00 | - | **1.00** | **1.00** | - |
| geometric-mean-reverting-jd | - | **1.00** | - | 0.00 | 0.00 | - |
| historical-var-data-prep | - | **1.00** | - | **1.00** | **1.00** | - |
| hull-white-swaption | 0.00 | **1.00** | 0.00 | 0.00 | 0.00 | 0.00 |
| implied-vol-approximations | - | 0.00 | - | 0.00 | 0.00 | - |
| insider-buy-clusters | - | 0.00 | - | 0.00 | 0.00 | - |
| interest-rate-cap-floor | - | **1.00** | - | **1.00** | 0.00 | - |
| intraday-volume-fitting-and-execution-scheduling | - | **1.00** | - | **1.00** | 0.00 | - |
| ipca-latent-factors | - | 0.69 | - | 0.29 | 0.33 | - |
| kelly-var-sizing | 0.93 | **1.00** | 0.93 | 0.89 | 0.89 | 0.93 |
| kou-double-exponential | - | 0.00 | - | 0.00 | 0.00 | - |
| ledoit-wolf-shrinkage | - | **1.00** | - | 0.00 | **1.00** | - |
| liquidity-var-backtest | - | 0.00 | - | 0.00 | 0.00 | - |
| lmm-markov-representation | - | 0.00 | - | 0.00 | 0.00 | - |
| lob-pc-signal | - | 0.00 | - | 0.00 | 0.00 | - |
| localvol-barrier | - | 0.00 | - | 0.00 | 0.00 | - |
| lookback-options | - | **1.00** | - | **1.00** | 0.00 | - |
| markowitz-efficient-frontier | - | **1.00** | - | 0.00 | 0.00 | - |
| mc-greek-surface-1 | **1.00** | **1.00** | 0.00 | **1.00** | 0.00 | 0.00 |
| mc-greeks-surface | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| merton-cds-copula | - | 0.90 | - | 0.90 | 0.90 | - |
| minimum-cost-equity-etf-hedger | - | **1.00** | - | **1.00** | **1.00** | - |
| ml-credit-scoring-fairness | - | **1.00** | - | 0.00 | 0.00 | - |
| momentum-backtest | **1.00** | **1.00** | **1.00** | **1.00** | **1.00** | 0.00 |
| mtm-xccy-basis-desk | - | 0.00 | - | 0.00 | 0.00 | - |
| multimodal-alpha-fusion-edgar-cot-gdelt | - | 0.00 | - | 0.00 | 0.00 | - |
| nelson-siegel-yield-curve-fit | - | 0.00 | - | 0.00 | 0.00 | - |
| option-put-call-parity-forward-audit | - | 0.00 | - | 0.00 | **1.00** ★ | - |
| ou-jump-commodity | - | **1.00** | - | 0.00 | **1.00** | - |
| pairs-cointegration-kalman | - | 0.79 | - | 0.71 | 0.38 | - |
| pairs-trading-cointegration | - | 0.00 | - | 0.00 | 0.00 | - |
| pca-factor-portfolio | - | **1.00** | - | **1.00** | **1.00** | - |
| perpetual-funding-ledger-reconciliation | - | 0.00 | - | 0.00 | 0.00 | - |
| polars-api-migration | - | 0.00 | - | 0.00 | 0.00 | - |
| portfolio-risk-attribution | - | 0.00 | - | 0.00 | 0.00 | - |
| post-earnings-drift | - | 0.00 | - | 0.00 | 0.00 | - |
| prediction-markets-cross-venue-dislocation | - | 0.00 | - | 0.00 | 0.00 | - |
| qfbench/barone-adesi-whaley | - | **1.00** | - | **1.00** | 0.00 | - |
| qfbench/double-barrier-options | - | **1.00** | - | 0.00 | 0.00 | - |
| qfbench/dupire-local-vol | - | 0.00 | - | 0.00 | 0.00 | - |
| qfbench/first-passage-time | - | **1.00** | - | **1.00** | 0.00 | - |
| qfbench/fx-quanto-options | - | 0.00 | - | 0.00 | 0.00 | - |
| qfbench/heston-cf-pricing | - | 0.00 | - | 0.00 | 0.00 | - |
| qfbench/power-options | - | 0.00 | - | 0.00 | 0.00 | - |
| quantamental-earnings-jumpfilter-committee | - | 0.00 | - | 0.00 | 0.00 | - |
| rainbow-option-pricing | - | 0.00 | - | 0.00 | 0.00 | - |
| realized-vol-estimators | - | 0.00 | - | 0.00 | **1.00** | - |
| regime-cta-vol-target | 0.78 | 0.81 | 0.74 | 0.55 | 0.36 | 0.00 |
| regime-riskparity-cvar | 0.40 | 0.48 | 0.28 | 0.52 | 0.28 | 0.00 |
| residual-momentum | - | **1.00** | - | **1.00** | 0.00 | - |
| sec-10k-report-long | - | 0.00 | - | 0.00 | 0.00 | - |
| sec-8k-event-alpha | - | **1.00** | - | 0.54 | 0.96 | - |
| sector-neutral-residual-momentum | - | 0.00 | - | 0.00 | 0.00 | - |
| sentiment-factor-alpha | 0.86 | 0.71 | 0.40 | 0.30 | 0.29 | 0.00 |
| shrinkage-meanvar-portfolio | - | 0.00 | - | 0.00 | 0.00 | - |
| sma-crossover-spy | **1.00** | **1.00** | **1.00** | **1.00** | **1.00** | 0.00 |
| spread-option-kirk-margrabe | - | **1.00** | - | **1.00** | 0.00 | - |
| stable-residual | - | 0.00 | - | 0.00 | 0.00 | - |
| stochvol-implied-surface-new | **1.00** | **1.00** | 0.00 | 0.00 | 0.00 | 0.00 |
| structured-note-risk | 0.00 | 0.72 | 0.00 | 0.00 | 0.39 | 0.00 |
| swap-curve-bootstrap-ois | - | **1.00** | - | **1.00** | 0.00 | - |
| trace-rate-flow-analysis | - | **1.00** | - | 0.00 | **1.00** | - |
| treasury-curve-pca-butterfly | - | 0.00 | - | 0.00 | 0.00 | - |
| ust-carry-roll-down-attribution | - | **1.00** | - | **1.00** | 0.00 | - |
| var-ebacktest-coverage | - | 0.00 | - | 0.00 | 0.00 | - |
| variance-swap-pricing | - | 0.00 | - | **1.00** | **1.00** | - |
| variance-swap-replication | - | **1.00** | - | **1.00** | **1.00** | - |
| yield-curve-bond-immunization | - | 0.00 | - | 0.00 | 0.00 | - |
| yield-curve-bootstrap-immunization | - | **1.00** | - | **1.00** | 0.00 | - |
| yield-curve-pca-dynamics | - | **1.00** | - | 0.00 | **1.00** | - |
| zero-coupon-bootstrapping | - | **1.00** | - | **1.00** | **1.00** | - |

## Key Findings

### Task Difficulty Tiers (140 tasks, all batches)

| Tier | Count | Description | Example Tasks |
|------|-------|-------------|---------------|
| 🟢 Easy | ~50 | Haiku solves (reward > 0) | fama-french, sma-crossover, bond-convexity |
| 🟡 Medium | ~21 | Haiku fails, Sonnet/Opus solves | barrier-option-mc, lookback-options, cliquet-ratchet |
| 🔴 Hard | ~11 | Only Opus solves | hull-white-swaption, markowitz-efficient-frontier, geometric-mean-reverting-jd |
| ⚫ All-Fail | ~58 | All 3 Claude models score 0 | Needs investigation — broken or very hard |

### Docker-Fix Rerun Summary (2026-04-22)

15 PR tasks had broken Dockerfiles (wrong sandbox image name). Fixed and re-ran with Haiku:
- ✅ **2 passed** (★ in heatmap): `black-litterman-allocation`, `option-put-call-parity-forward-audit`
- ❌ **10 reward=0**: Tasks run but Haiku couldn't solve
- 💥 **3 Docker errors**: `futures-carry-repair`, `insider-buy-clusters`, `post-earnings-drift` (NFS symlink + Docker compose issue)

### Notable Observations

1. **Codex GPT-5.4 leads** on the original 16 tasks with highest mean reward (0.538)
2. **Opus 4.6 has highest perfect score rate** (41%) across all tasks including Batch 2 PR tasks
3. **Gemini-2.5-Pro** achieves 0.319 mean via NODE_OPTIONS auth hack — competitive on some tasks (kelly: 0.93, regime-cta: 0.74)
4. **Gemini-2.5-Flash** essentially fails on agentic tasks (0.041 mean)
5. **Finance-zero baselines** (non-agentic single-call) score 0.0 on everything — confirms tasks require multi-step reasoning
6. **mc-greeks-surface** had OUTPUT_DIR bug (fixed); **structured-note-risk** needs custom Docker image
7. **hull-white-swaption** is a strong differentiator: only Opus solves it (codex generates wrong row count)
8. **All-or-nothing scoring** inflates failure rate — many tasks pass 90%+ of tests but get reward=0

### Open Issues

| Issue | Impact | Fix |
|-------|--------|-----|
| 58 all-fail tasks | Unknown quality | Sample 5-10, check if tests/specs are reasonable |
| 3 NFS symlink Docker errors | 3 tasks untested | Copy task dirs locally instead of symlink |
| 2 tasks missing test.sh | Can't verify | Need task author to add verifier |
| All-or-nothing scoring | Hides partial success | Consider partial reward (% tests passed) |

## Data Sources

- Results: `infra/results/all_results_snapshot.json` + docker-fix trials
- Tracker: `python3 infra/scripts/tracker.py status`
- Trials: `/sensei-fs-3/users/zouyang/fb-harbor/trials/`
- Docker-fix logs: `/sensei-fs-3/users/zouyang/fb-harbor/machine-logs/docker-fix-v8/`
