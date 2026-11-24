# FINPULSE AI student module: test output

## 1. Worked example (one synthetic student, day 18 of 30)

Spent 8,650 in 18 days. Balance 1,350. Days left 12.
Burn rate 480.6 per day. Money lasts 2.8 more days, so it runs out on day 21.
Safe to spend 112.5 per day. Shortfall at the current pace 4,417.
Top two categories: Food beyond the mess and Outings = 5,100 (59% of spending).

Next-month plan adds up to 10,000. Flexible spending 6,750 = 225 per day, 1,575 per week.

## 2. Early-warning test: which students run short before day 25?

50,000 synthetic student-months per seed, 3 seeds. A student counts as near bankrupt when the balance
drops under 500 on or before day 25. Students already under 500 at the check day are left out.

| Check day | Rule | Precision | Recall | F1 | Flagged | Seed spread (recall) |
|---|---|---|---|---|---|---|
| 7 | A. Spent more than the pro-rata share | 38.4% | 99.8% | 0.55 | 95.7% | 0.06 pts |
| 7 | B. Last 7 days' pace continues | 40.9% | 99.0% | 0.58 | 89.2% | 0.16 pts |
| 7 | C. Pace so far, fixed bills tagged and removed | 65.4% | 74.1% | 0.69 | 41.7% | 0.58 pts |
| 10 | A. Spent more than the pro-rata share | 42.6% | 98.9% | 0.60 | 84.3% | 0.19 pts |
| 10 | B. Last 7 days' pace continues | 53.0% | 85.5% | 0.65 | 58.7% | 0.25 pts |
| 10 | C. Pace so far, fixed bills tagged and removed | 67.8% | 77.4% | 0.72 | 41.5% | 0.40 pts |
| 15 | A. Spent more than the pro-rata share | 46.7% | 98.0% | 0.63 | 69.0% | 0.05 pts |
| 15 | B. Last 7 days' pace continues | 72.6% | 75.4% | 0.74 | 34.1% | 0.14 pts |
| 15 | C. Pace so far, fixed bills tagged and removed | 72.1% | 81.1% | 0.76 | 37.0% | 0.27 pts |

Share of simulated students who end up near bankrupt: 36.9%.

## 3. Savings scenarios (hypothetical rates, not forecasts)

| Monthly saving | Months | Paid in | Value at 0% | Value at 6% a year | Value at 12% a year |
|---|---|---|---|---|---|
| 500 | 12 | 6,000 | 6,000 | 6,168 | 6,341 |
| 500 | 24 | 12,000 | 12,000 | 12,716 | 13,487 |
| 1,000 | 24 | 24,000 | 24,000 | 25,432 | 26,973 |

End-of-month deposits, monthly compounding.

