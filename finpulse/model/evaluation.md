# Student early-warning model: evaluation

Synthetic student-months only. These numbers show how the model behaves on the generator
it was trained on. They are not evidence about real students.

Training rows: 113,813. Share that run short: 33.4%.
Alert threshold chosen on validation data: 0.32 (best F1 with recall of at least 80%).

## Weights (standardised features)

| Feature | Weight |
|---|---|
| spent_share | +2.83 |
| time_share | -1.89 |
| need_ratio_tagged | +0.87 |
| need_ratio_recent | +0.07 |
| fixed_share | -0.28 |
| largest_spend_share | -0.89 |
| bias | -1.05 |

## Held-out test, same kind of students (50,000 per seed, seeds (11, 23, 47))

| Check day | Method | Precision | Recall | F1 | Students flagged | AUC | Seed spread (F1) |
|---|---|---|---|---|---|---|---|
| 7 | Trained model | 64.1% | 80.6% | 0.714 | 46.2% | 0.862 | 0.005 |
| 7 | Rule C (pace so far, fixed bills removed) | 65.1% | 73.9% | 0.692 | 41.7% | 0.843 | 0.002 |
| 7 | Rule A (pro-rata share) | 38.3% | 99.8% | 0.554 | 95.7% | 0.840 | 0.002 |
| 10 | Trained model | 68.8% | 80.4% | 0.741 | 42.4% | 0.888 | 0.003 |
| 10 | Rule C (pace so far, fixed bills removed) | 67.7% | 77.6% | 0.724 | 41.6% | 0.875 | 0.002 |
| 10 | Rule A (pro-rata share) | 42.6% | 99.0% | 0.595 | 84.3% | 0.875 | 0.004 |
| 15 | Trained model | 71.2% | 82.6% | 0.765 | 37.9% | 0.921 | 0.004 |
| 15 | Rule C (pace so far, fixed bills removed) | 71.6% | 80.9% | 0.760 | 36.9% | 0.915 | 0.003 |
| 15 | Rule A (pro-rata share) | 46.4% | 97.9% | 0.629 | 69.0% | 0.915 | 0.005 |

## Drift test: students spend 25% more and 60% front-load

| Check day | Method | Precision | Recall | F1 | Students flagged | AUC | Seed spread (F1) |
|---|---|---|---|---|---|---|---|
| 7 | Trained model | 78.2% | 90.6% | 0.840 | 67.2% | 0.896 | 0.003 |
| 7 | Rule C (pace so far, fixed bills removed) | 80.7% | 85.6% | 0.831 | 61.5% | 0.880 | 0.004 |
| 7 | Rule A (pro-rata share) | 58.8% | 100.0% | 0.740 | 98.6% | 0.875 | 0.003 |
| 10 | Trained model | 80.0% | 90.7% | 0.850 | 64.2% | 0.916 | 0.002 |
| 10 | Rule C (pace so far, fixed bills removed) | 81.0% | 87.1% | 0.839 | 61.0% | 0.903 | 0.003 |
| 10 | Rule A (pro-rata share) | 60.7% | 99.6% | 0.755 | 93.0% | 0.902 | 0.003 |
| 15 | Trained model | 79.7% | 90.8% | 0.849 | 56.2% | 0.939 | 0.003 |
| 15 | Rule C (pace so far, fixed bills removed) | 81.3% | 88.2% | 0.846 | 53.6% | 0.931 | 0.004 |
| 15 | Rule A (pro-rata share) | 60.4% | 99.0% | 0.750 | 80.9% | 0.930 | 0.005 |

## Drift test: thriftier students, fewer large one-off spends

| Check day | Method | Precision | Recall | F1 | Students flagged | AUC | Seed spread (F1) |
|---|---|---|---|---|---|---|---|
| 7 | Trained model | 25.9% | 75.2% | 0.386 | 21.7% | 0.876 | 0.006 |
| 7 | Rule C (pace so far, fixed bills removed) | 26.9% | 68.0% | 0.385 | 18.9% | 0.863 | 0.008 |
| 7 | Rule A (pro-rata share) | 8.4% | 99.7% | 0.154 | 88.9% | 0.861 | 0.007 |
| 10 | Trained model | 31.4% | 75.1% | 0.443 | 17.7% | 0.902 | 0.012 |
| 10 | Rule C (pace so far, fixed bills removed) | 30.8% | 72.9% | 0.433 | 17.6% | 0.894 | 0.004 |
| 10 | Rule A (pro-rata share) | 11.2% | 98.2% | 0.201 | 65.2% | 0.895 | 0.009 |
| 15 | Trained model | 41.7% | 74.1% | 0.534 | 12.4% | 0.935 | 0.011 |
| 15 | Rule C (pace so far, fixed bills removed) | 41.5% | 74.7% | 0.534 | 12.6% | 0.934 | 0.007 |
| 15 | Rule A (pro-rata share) | 16.6% | 96.5% | 0.283 | 40.7% | 0.935 | 0.014 |

## Calibration (held-out, all check days)

| Predicted probability | Students | Share that actually ran short |
|---|---|---|
| 0.0 to 0.2 | 56,743 | 7.2% |
| 0.2 to 0.4 | 18,826 | 29.8% |
| 0.4 to 0.6 | 11,112 | 48.3% |
| 0.6 to 0.8 | 9,120 | 68.3% |
| 0.8 to 1.0 | 18,120 | 93.6% |

Brier score: 0.1159 (0 is perfect; always guessing the base rate scores 0.2231).

## Scale check

Doubling the allowance and every spend changes the probability by at most 0.00e+00.
