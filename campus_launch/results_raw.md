# Campus Launch blueprint: stress-test output

## A. Reproduce the blueprint (must match before any other test counts)

| Check | Blueprint | Recomputed | Result |
|---|---|---|---|
| Base, 60 boxes, demand 90 | 3,966 | 3,966.0 | match |
| Base, 120 boxes, demand 90 | 3,249 | 3,249.0 | match |
| 35 orders, 60 boxes | 64 | 63.5 | match |
| 130 orders, 120 boxes | 7,932 | 7,932.0 | match |
| 85% COD, 130 orders, 120 boxes: contribution | 5,420 | 5,420.4 | match |
| 85% COD fast payout: minimum cash | 21,200 | 21,200.0 | match |
| 85% COD late payout: minimum cash, 120 boxes | 5,570 | 5,569.6 | match |
| 85% COD late payout: minimum cash, 60 boxes | 10,785 | 10,784.8 | match |
| 60% COD failure, 85% COD, trial | -1,278 | -1,278.0 | match |
| Unit cost 170, trial | -834 | -834.0 | match |
| Year 1 contribution, 24 drops | 95,184 | 95,184.0 | match |
| Year 3 contribution, 72 drops | 285,552 | 285,552.0 | match |

| Decision row | Blueprint batch | Recomputed | Result |
|---|---|---|---|
| Base demand 90 | 60 | 60 | match |
| 35 orders | 60 | 60 | match |
| 130 orders | 120 | 120 | match |
| 85% COD, 130, fast | 120 | 120 | match |
| 85% COD, 130, late | 60 | 60 | match |
| 60% fail, 85% COD | 0 | 0 | match |
| Unit cost 170 | 0 | 0 | match |
| Zero demand | 0 | 0 | match |
| Opening cash below reserve | review | review | match |

All figures and all nine decisions reproduce.

## B. One drop is a gamble, not an expected value

200,000 simulated drops per seed, 3 seeds. COD mix and failures drawn at random.

| Demand | Batch | Blueprint EV | Sim mean | Std dev | P(loss) | Worst 5% | P(reserve breach), late payout |
|---|---|---|---|---|---|---|---|
| 35 | 60 | 64 | 62 | 458 | 48.6% | -730 | 0.0% |
| 35 | 120 | -5,336 | -5,338 | 458 | 100.0% | -6,130 | 100.0% |
| 60 | 60 | 3,966 | 3,964 | 600 | 0.0% | 3,000 | 0.0% |
| 60 | 120 | -1,434 | -1,436 | 600 | 99.8% | -2,400 | 54.9% |
| 90 | 60 | 3,966 | 3,964 | 600 | 0.0% | 3,000 | 0.0% |
| 90 | 120 | 3,249 | 3,250 | 734 | 0.0% | 2,030 | 1.3% |
| 130 | 60 | 3,966 | 3,964 | 600 | 0.0% | 3,000 | 0.0% |
| 130 | 120 | 7,932 | 7,933 | 848 | 0.0% | 6,460 | 0.0% |

Largest gap between seeds on any probability: 0.32 percentage points.

## B2. Exact cross-check of the simulation (no random numbers)

Demand 35, batch 60. Exact binomial: mean 63.5, P(loss) 48.45%. Simulation P(loss): 48.57%.
Simulation agrees with the exact calculation to within 1 percentage point.

## C. The 60 vs 120 choice under forecast error

120 boxes beats 60 only when actual demand is 95 or more.
If you order 120 and demand is 60: -1,434. If you order 60: 3,966.

| Forecast MAE | Forecast | Batch chosen | Mean contribution | P(loss) | P(wrong batch) | Money left on table |
|---|---|---|---|---|---|---|
| 6.7 | 70 | 60 | 3,890 | 0.0% | 0.2% | 1 |
| 6.7 | 85 | 60 | 3,965 | 0.0% | 12.9% | 83 |
| 6.7 | 95 | 120 | 4,026 | 0.3% | 47.7% | 494 |
| 6.7 | 105 | 120 | 5,569 | 0.0% | 10.6% | 68 |
| 6.7 | 120 | 120 | 7,408 | 0.0% | 0.1% | 0 |
| 9.3 | 70 | 60 | 3,768 | 0.2% | 1.9% | 12 |
| 9.3 | 85 | 60 | 3,955 | 0.0% | 20.7% | 209 |
| 9.3 | 95 | 120 | 4,015 | 1.9% | 48.4% | 696 |
| 9.3 | 105 | 120 | 5,502 | 0.2% | 18.5% | 186 |
| 9.3 | 120 | 120 | 7,204 | 0.0% | 1.4% | 9 |
| 25.0 | 70 | 60 | 2,714 | 13.1% | 34.6% | 784 |
| 25.0 | 85 | 60 | 3,378 | 5.5% | 43.3% | 1,073 |
| 25.0 | 95 | 120 | 3,433 | 20.8% | 49.5% | 1,648 |
| 25.0 | 105 | 120 | 4,583 | 13.0% | 36.9% | 1,104 |
| 25.0 | 120 | 120 | 5,976 | 5.4% | 20.9% | 531 |

Largest gap between seeds on any probability: 0.33 percentage points.

## D. Is 0/60/120 the right menu? (newsvendor check)

Net cash per dispatched box before purchase cost: 156.1

| Leftover value recovered | Profit per box sold | Loss per box unsold | Order up to this demand percentile |
|---|---|---|---|
| 0.0% | 66.1 | 90.0 | 0.42 |
| 50.0% | 66.1 | 45.0 | 0.59 |
| 80.0% | 66.1 | 18.0 | 0.79 |

| Forecast (sd 12) | Leftover recovered | Best batch (steps of 10) | Its contribution | 60 boxes | 120 boxes |
|---|---|---|---|---|---|
| 90 | 0.0% | 90 | 5,200 | 3,962 | 3,241 |
| 90 | 50.0% | 90 | 5,914 | 4,314 | 5,120 |
| 90 | 80.0% | 100 | 6,482 | 4,525 | 6,247 |
| 110 | 0.0% | 110 | 6,522 | 3,966 | 6,155 |
| 110 | 50.0% | 110 | 7,353 | 4,317 | 7,303 |
| 110 | 80.0% | 120 | 7,992 | 4,528 | 7,992 |

## E. Cost and price sensitivity (60-box sell-out drop, 24 drops, overhead 60,000)

| Case | Contribution per drop | Year 1 surplus |
|---|---|---|
| Blueprint base | 3,966 | 35,184 |
| Price 190 (down 9.5%) | 2,922 | 10,128 |
| Price 180 (down 14%) | 2,400 | -2,400 |
| Unit cost 100 (packaging +10) | 3,366 | 20,784 |
| Unit cost 115 | 2,466 | -816 |
| Gateway fee 2% on prepaid | 3,840 | 32,160 |
| COD failure 10% | 5,070 | 61,680 |
| COD failure 40% | 3,000 | 12,000 |
| COD share 80% | 2,890 | 9,350 |
| COD share 20% | 5,042 | 61,018 |
| Packaging +10 and gateway 2% | 3,240 | 17,760 |
| Packaging +10, gateway 2%, price 190 | 2,208 | -7,008 |

Year 1 surplus hits zero at: price 181.9, unit cost 114.4, COD failure 47.2%.
Year 1 surplus per founder per month, six founders: 489.

## F. Year 1 if some weeks are weak (blueprint assumes every drop sells out)

Analytic break-even: Year 1 loses money once more than 37.6% of drops are weak (9 of 24 is the last safe count).

| Share of weak weeks (35 orders) | Mean Year 1 surplus | P(Year 1 loss) | Worst 5% |
|---|---|---|---|
| 0.0% | 35,163 | 0.0% | 30,323 |
| 10.0% | 25,800 | 0.0% | 14,603 |
| 20.0% | 16,447 | 2.7% | 2,460 |
| 30.0% | 7,085 | 21.8% | -8,390 |
| 40.0% | -2,264 | 58.7% | -18,260 |
| 50.0% | -11,588 | 87.6% | -27,960 |

Largest gap between seeds on P(loss): 0.92 percentage points.

## G. Redesign test: forecast-then-buy versus prepay-then-buy

Same 2% gateway fee on prepaid receipts in every design. Actual demand = forecast with sd 12.
V1 = blueprint (courier, 50% COD, 26% failure, COD paid after the bill).
V1b = blueprint rule with hand delivery on campus (10% no-show on pay-at-pickup, no failure fee, cash at handover).
V2 = prepaid UPI pre-order, buy to the paid count in packs of 10, minimum 60, run only at 30+ paid orders.

| Forecast | Design | Batch | Mean contribution | P(loss) | Worst 5% | P(reserve breach) |
|---|---|---|---|---|---|---|
| 35 | V1 blueprint | 0 | 0 | 0.0% | 0 | 0.0% |
| 35 | V1b hand delivery | 60 | 652 | 37.5% | -2,821 | 0.0% |
| 35 | V2 prepaid, 100% still buy | to count | 1,416 | 0.0% | 0 | 0.0% |
| 35 | V2 prepaid, 80% still buy | to count | 572 | 0.0% | 0 | 0.0% |
| 35 | V2 prepaid, 60% still buy | to count | 99 | 0.0% | 0 | 0.0% |
| 35 | V2 prepaid, 50% still buy | to count | 21 | 0.0% | 0 | 0.0% |
| 60 | V1 blueprint | 60 | 3,100 | 2.3% | 671 | 0.0% |
| 60 | V1b hand delivery | 60 | 4,172 | 0.8% | 1,536 | 0.0% |
| 60 | V2 prepaid, 100% still buy | to count | 4,857 | 0.0% | 1,872 | 0.0% |
| 60 | V2 prepaid, 80% still buy | to count | 3,234 | 0.0% | 418 | 0.0% |
| 60 | V2 prepaid, 60% still buy | to count | 1,321 | 0.0% | 0 | 0.0% |
| 60 | V2 prepaid, 50% still buy | to count | 545 | 0.0% | 0 | 0.0% |
| 90 | V1 blueprint | 60 | 3,836 | 0.0% | 2,870 | 0.0% |
| 90 | V1b hand delivery | 60 | 5,000 | 0.0% | 4,374 | 0.0% |
| 90 | V2 prepaid, 100% still buy | to count | 7,855 | 0.0% | 5,890 | 0.0% |
| 90 | V2 prepaid, 80% still buy | to count | 6,185 | 0.0% | 4,599 | 0.0% |
| 90 | V2 prepaid, 60% still buy | to count | 4,189 | 0.0% | 1,872 | 0.0% |
| 90 | V2 prepaid, 50% still buy | to count | 2,764 | 0.0% | 599 | 0.0% |
| 130 | V1 blueprint | 120 | 7,470 | 0.0% | 5,708 | 0.0% |
| 130 | V1b hand delivery | 120 | 9,772 | 0.0% | 8,197 | 0.0% |
| 130 | V2 prepaid, 100% still buy | to count | 11,527 | 0.0% | 9,562 | 0.0% |
| 130 | V2 prepaid, 80% still buy | to count | 9,139 | 0.0% | 7,544 | 0.0% |
| 130 | V2 prepaid, 60% still buy | to count | 6,753 | 0.0% | 5,335 | 0.0% |
| 130 | V2 prepaid, 50% still buy | to count | 5,526 | 0.0% | 4,054 | 0.0% |

Largest gap between seeds on any probability: 0.09 percentage points.

Share of interested buyers who must still pay upfront for V2 to match V1:

| Forecast | V1 mean contribution | V2 break-even retention |
|---|---|---|
| 60 | 3,100 | 79.0% |
| 90 | 3,836 | 58.0% |
| 130 | 7,470 | 66.0% |

## G2. Hybrid test: prepaid base plus a pay-at-pickup buffer

Half of the buyers who will not prepay still turn up at pickup if stock is there (assumption).
Buffer = extra boxes bought on top of the paid count. Unsold boxes are written off. 2% fee on all receipts.

| Forecast | Prepay share | Buffer | Mean contribution | P(loss) | Worst 5% |
|---|---|---|---|---|---|
| 60 | 60.0% | 0.0% | 3,000 | 0.0% | 0 |
| 60 | 60.0% | 20.0% | 3,013 | 0.0% | 0 |
| 60 | 60.0% | 40.0% | 2,872 | 0.0% | 0 |
| 60 | 80.0% | 0.0% | 4,133 | 0.0% | 1,145 |
| 60 | 80.0% | 20.0% | 3,883 | 0.0% | 1,145 |
| 60 | 80.0% | 40.0% | 3,207 | 0.0% | 1,145 |
| 90 | 60.0% | 0.0% | 5,627 | 0.0% | 4,599 |
| 90 | 60.0% | 20.0% | 6,171 | 0.0% | 4,599 |
| 90 | 60.0% | 40.0% | 5,812 | 0.0% | 4,063 |
| 90 | 80.0% | 0.0% | 6,969 | 0.0% | 5,508 |
| 90 | 80.0% | 20.0% | 6,512 | 0.0% | 4,799 |
| 90 | 80.0% | 40.0% | 5,211 | 0.0% | 3,726 |
| 130 | 60.0% | 0.0% | 7,573 | 0.0% | 6,426 |
| 130 | 60.0% | 20.0% | 8,925 | 0.0% | 7,344 |
| 130 | 60.0% | 40.0% | 8,581 | 0.0% | 6,826 |
| 130 | 80.0% | 0.0% | 9,951 | 0.0% | 8,262 |
| 130 | 80.0% | 20.0% | 9,603 | 0.0% | 7,907 |
| 130 | 80.0% | 40.0% | 7,739 | 0.0% | 6,128 |

Largest gap between seeds on P(loss): 0.00 percentage points.

## H. Can one 20-week holdout rank the forecasting methods?

My own synthetic generator (the blueprint's notebook was not supplied), 300 seeds per setting.
80 weeks, first 60 train, last 20 test, ridge on three standardised inputs, same decision rule.

| Setting | MAE three-input | MAE interest only | MAE 4-week avg | Three-input earns more | Tie | Interest-only earns more | Median gap over 20 drops | 5th to 95th percentile gap |
|---|---|---|---|---|---|---|---|---|
| Weak exam/promo effect | 9.3 | 10.2 | 23.8 | 54.3% | 20.7% | 25.0% | 390 | -2,754 to 4,684 |
| Medium | 9.8 | 14.4 | 26.4 | 85.3% | 2.7% | 12.0% | 4,059 | -1,508 to 10,873 |
| Strong | 10.6 | 19.7 | 30.7 | 94.3% | 0.7% | 5.0% | 8,551 | -12 to 18,714 |

## I. Three-year plan with uncertain demand and a monthly cash check

Each drop's demand is lognormal with the mean shown and a 35% coefficient of variation; one drop in five
falls in an exam week at 70% demand. Overhead is paid every month, drops happen only in nine teaching months.
Opening cash 32,000, existing bill 16,000 paid in month 1, reserve 10,000. Gateway fee 2% in both designs.

| Mean demand per drop | Design | Year 1 surplus | Year 2 | Year 3 | P(Year 1 loss) | P(3-year loss) | P(cash below reserve) | Funding gap, 95th percentile |
|---|---|---|---|---|---|---|---|---|
| 50 | V1 always 60 boxes | -26,440 | -36,938 | -58,943 | 99.7% | 100.0% | 100.0% | 155,328 |
| 50 | V2 prepaid, 80% still buy | -19,300 | -23,324 | -37,431 | 97.5% | 99.9% | 100.0% | 110,858 |
| 50 | V2 prepaid, 60% still buy | -44,388 | -70,640 | -112,805 | 100.0% | 100.0% | 100.0% | 244,754 |
| 70 | V1 always 60 boxes | 7,934 | 27,513 | 43,979 | 14.6% | 0.0% | 5.2% | 201 |
| 70 | V2 prepaid, 80% still buy | 27,876 | 65,120 | 104,251 | 1.1% | 0.0% | 0.5% | 0 |
| 70 | V2 prepaid, 60% still buy | -13,227 | -11,930 | -19,432 | 90.0% | 96.2% | 98.6% | 78,918 |
| 90 | V1 always 60 boxes | 22,851 | 55,500 | 88,583 | 0.0% | 0.0% | 0.0% | 0 |
| 90 | V2 prepaid, 80% still buy | 70,438 | 145,204 | 232,386 | 0.0% | 0.0% | 0.0% | 0 |
| 90 | V2 prepaid, 60% still buy | 22,001 | 54,239 | 86,781 | 3.3% | 0.0% | 1.7% | 0 |
| 110 | V1 always 60 boxes | 28,639 | 66,329 | 105,850 | 0.0% | 0.0% | 0.0% | 0 |
| 110 | V2 prepaid, 80% still buy | 108,454 | 216,283 | 346,309 | 0.0% | 0.0% | 0.0% | 0 |
| 110 | V2 prepaid, 60% still buy | 55,277 | 116,137 | 185,744 | 0.0% | 0.0% | 0.0% | 0 |

Largest gap between seeds on any probability: 1.87 percentage points.
Blueprint table for comparison: 35,184 / 78,470 / 125,552 with every box sold and no gateway fee.


Year 1 mean surplus by mean demand per drop (same assumptions):

| Mean demand per drop | V1 always 60 | V2, 80% prepay | V2, 60% prepay |
|---|---|---|---|
| 50 | -26,440 | -19,300 | -44,388 |
| 55 | -15,400 | -7,558 | -37,716 |
| 60 | -6,074 | 4,376 | -30,060 |
| 65 | 1,646 | 16,276 | -21,898 |
| 70 | 7,934 | 27,876 | -13,227 |
| 75 | 13,009 | 39,067 | -4,543 |
| 80 | 17,074 | 49,961 | 4,636 |
| 85 | 20,306 | 60,415 | 13,398 |
| 90 | 22,851 | 70,438 | 22,001 |
| 95 | 24,859 | 80,174 | 30,716 |

