# Task: Merton Structural Credit Model Calibration

You are given synthetic data for 10 companies:

- `/app/equity_prices.csv` — 252 daily observations of equity values for `COMP_01` through `COMP_10`
- `/app/balance_sheet.csv` — company-level debt and metadata

The balance-sheet file contains:

- `company_id`
- `total_debt`
- `equity_book_value`
- `industry`

Treat `total_debt` as the face value of debt due at horizon `T = 1` year.
Treat the observed equity series as the market equity value process for each
company, and use `equity_book_value` as the current observed equity value at
the horizon date. The data are internally consistent.

## Objective

For each company, calibrate the **Merton structural credit model** and compute:

- implied asset value `V_A`
- implied asset volatility `sigma_A`
- Distance-to-Default `DD`
- Probability of Default `PD`
- model-implied current equity value `equity_model_value`

Then compute:

- `portfolio_avg_pd` = simple average of company-level `PD`
- `portfolio_avg_dd` = simple average of company-level `DD`

## Model

Under the Merton model, equity is a call option on firm assets:

`E = V_A * N(d1) - D * exp(-rT) * N(d2)`

where

`d1 = [ln(V_A / D) + (r + 0.5 * sigma_A^2) * T] / (sigma_A * sqrt(T))`

`d2 = d1 - sigma_A * sqrt(T)`

Use:

- risk-free rate `r = 0.03`
- horizon `T = 1.0`

`N(.)` is the standard normal CDF.

## Calibration Requirements

For each company:

1. Estimate annualized equity volatility from the daily equity series using
   log returns and a 252-trading-day convention.
2. Calibrate `sigma_A` by fixed-point iteration:
   - for a candidate `sigma_A`, infer the implied asset value corresponding to
     each daily equity observation by solving the Merton equity equation
   - from the implied asset-value time series, compute a new annualized
     asset volatility
   - iterate until convergence
3. Use the final implied asset-value series to estimate annualized asset drift
   `mu` from the mean daily log return times 252.
4. Let `V_A` be the implied asset value on the final date.
5. Compute:

`DD = [ln(V_A / D) + (mu - 0.5 * sigma_A^2) * T] / (sigma_A * sqrt(T))`

`PD = N(-DD)`

6. Compute `equity_model_value` by plugging the final calibrated `V_A` and
   `sigma_A` back into the Merton equity formula.

## Numerical Requirements

- Use a nonlinear root solve for the asset value implied by the equity formula
- Use a convergence tolerance of `1e-6` or tighter for the fixed-point loop
- Use a robust stopping rule and avoid negative or zero volatilities
- The final model-implied equity value should match the observed current equity
  value to within `0.01` for every company

## Output Files

### 1. `/app/output/merton_output.csv`

Columns:

`company_id,V_A,sigma_A,DD,PD,equity_model_value`

One row per company.

### 2. `/app/output/results.json`

Use this structure:

```json
{
  "companies": [
    {
      "company_id": "COMP_01",
      "V_A": 0.0,
      "sigma_A": 0.0,
      "DD": 0.0,
      "PD": 0.0,
      "equity_model_value": 0.0
    }
  ],
  "portfolio_avg_pd": 0.0,
  "portfolio_avg_dd": 0.0
}
```

## Notes

- Use raw floats in the outputs, not percentages
- `PD` must be computed as `N(-DD)`
- Do not output extra files
- The company ordering in the CSV and JSON should match `balance_sheet.csv`
