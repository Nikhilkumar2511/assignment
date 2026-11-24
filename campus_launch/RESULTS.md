# Campus Launch blueprint: flaws, redesign and test results

Tested on 24 November 2026. Every rupee figure is illustrative. Inputs come from the blueprint
or from assumptions stated beside each test. No real personal or company data was used.

Rerun everything with `python3 stress_test.py`. Full tables are in `results_raw.md`.

## How the testing was done

1. The blueprint's ledger was rebuilt in code. All 12 figures and all 9 batch decisions on
   pages 4 and 5 reproduce to the rupee (test A). Nothing else counts until that passes.
2. Each simulation ran 200,000 drops on three different random seeds. The largest gap between
   seeds on any probability was 1.9 percentage points, and under 1 point for single-drop tests.
3. One simulated result was checked against an exact binomial calculation with no random
   numbers: 48.45% exact against 48.57% simulated (test B2).

## Flaws found

| # | Flaw | Evidence from the tests |
|---|---|---|
| 1 | The venture and the numbers do not match. The idea is a hostel drop, but the 26% failed-delivery rate and the late COD payout come from national courier e-commerce. | Swap in campus terms (hand delivery, 10% no-show, cash at handover) and contribution at a forecast of 90 rises from 3,836 to 5,000. The headline result, "late payout flips 120 boxes to 60", depends on a courier the venture may never use. |
| 2 | The forecasting problem is self-inflicted. The design collects "interest" and then predicts orders. | Collect payment in the ordering window and buy to the paid count: the chance of a loss falls to 0% at every demand level tested (test G). |
| 3 | The decision rule looks only at expected values. | At 35 orders the blueprint shows +64. The exact chance of a loss on that drop is 48.5%. At a forecast of 95 the rule orders 120 boxes and is wrong 48% of the time. With a 25-box forecast error, that order loses money 21% of the time. |
| 4 | The 0/60/120 menu is too coarse. | At demand of 90 (sd 12) a 90-box batch earns 5,200. The menu's best choice, 60 boxes, earns 3,962. That is 31% left behind. |
| 5 | Leftover boxes are valued at zero, although the product is shelf-stable. | With zero recovery you should order to the 42nd percentile of demand. At 50% recovery it is the 59th, at 80% the 79th. The assumption changes the batch. |
| 6 | Margins are thin. | Year 1 surplus reaches zero at a price of 181.9 (13% lower) or a unit cost of 114.4 (27% higher). Packaging of 10 per box, a 2% gateway fee and a price of 190 together give a Year 1 loss of 7,008. The base surplus is 489 per founder per month. |
| 7 | The three-year table assumes all 141 drops sell out. | Year 1 turns to a loss once more than 37.6% of weeks are weak (9 of 24 is the last safe count). With variable demand averaging 90 orders, Year 1 surplus is 22,851, not 35,184. Break-even is about 64 orders per drop. |
| 8 | The forecast evidence cannot rank the methods. | The blueprint reports a gap of 127 over 20 weeks on one seed. Across 300 seeds of a comparable generator, the gap ranges from -2,754 to +4,684 when exam and promotion effects are weak. The three-input model earns more in 54% to 94% of seeds, depending only on how strong the generator makes those effects. |
| 9 | Scale and scope gaps. | Year 1 sales are 2.63 lakh. Year 3 needs 72 drops, more than 52 weeks, so it needs two or three campuses, and no expansion cost is modelled. The box weight in grams is never stated, so price per 100 g cannot be compared with quick-commerce. |
| 10 | Page 4 wording. | "Full batch falls to 5,570. Trial stays at 10,785" are minimum cash balances, printed under a contribution figure of 5,420. |

## The modified idea

1. **Pick one delivery model.** For a hostel venture, hand over boxes at a collection point on
   campus. Drop the courier, the failed-delivery fee and the COD settlement delay.
2. **Prepaid UPI pre-order.** Students pay inside the ordering window. Place the purchase order
   after the window closes, for the paid count, rounded up to the supplier's pack size.
3. **A go/no-go threshold.** With a 60-box minimum, run the drop only at 30 or more paid orders.
   Below that, refund and skip the week.
4. **Pay-at-pickup from spare stock only.** Add a 20% buffer only if fewer than about 60% of
   interested students prepay. At 80% prepay, a buffer lowers contribution.
5. **Ask the supplier for packs of 10.** Fixing the menu alone is worth about 1,240 per drop at
   demand of 90, even in the original design.
6. **Keep the dated cash-reserve test** as the governance rule, and add two risk limits: chance
   of a loss and chance of a reserve breach.
7. **Add the missing cost lines:** gateway fee, packaging, food registration, and leftover value.
8. **Give the AI a job it can win.** Run the simple rule as the default. Use a richer model only
   after it earns more across many seeds or real weeks, not one 20-week holdout.

## Redesign test results

Mean contribution per drop. Actual demand varies around the forecast with a standard deviation
of 12. A 2% gateway fee applies in every design.

| Forecast | V1 blueprint | V1b hand delivery | Modified, 80% prepay | Modified, 60% prepay + 20% buffer |
|---|---|---|---|---|
| 60 | 3,100 | 4,172 | 4,133 | 3,013 |
| 90 | 3,836 | 5,000 | 6,969 | 6,171 |
| 130 | 7,470 | 9,772 | 9,951 | 8,925 |
| Chance of a loss | up to 2.3% | up to 37.5% at low demand | 0% | 0% |

Year 1 mean surplus with uncertain demand (lognormal, 35% variation, exam weeks at 70%):

| Mean orders per drop | V1 always 60 boxes | Prepaid, 80% still buy | Prepaid, 60% still buy |
|---|---|---|---|
| 50 | -26,440 | -19,300 | -44,388 |
| 60 | -6,074 | 4,376 | -30,060 |
| 70 | 7,934 | 27,876 | -13,227 |
| 90 | 22,851 | 70,438 | 22,001 |
| 110 | 28,639 | 108,454 | 55,277 |

The three-year test used strict prepay with no walk-up sales, so the 60% column is the
pessimistic case. The hybrid with a buffer was tested per drop only.

## What the tests do not prove

- **Prepay share is the deciding unknown.** The redesign wins when roughly 60% to 80% of
  interested students still buy when asked to pay first. Below that, V1b can earn more. The
  team has to measure this with a survey or a one-week pilot, using aggregate counts only.
- **Three inputs are my assumptions:** 10% no-show at pickup, half of non-prepayers turning up
  as walk-ups, and the demand spread. Change them in `stress_test.py` and rerun.
- **All demand data is synthetic.** These tests show how the mechanics behave. They say nothing
  about whether hostel students want the box at 210.
- **The blueprint's notebook was not supplied.** Test H uses a separate generator.

## Facts to verify before the pitch

- Food business registration with FSSAI is required. The basic registration fee is reported as
  100 per year. Sources disagree on whether the turnover limit is still 12 lakh or was raised
  to 1.5 crore from 1 April 2026.
- GST registration threshold for goods in Uttarakhand is reported as 20 lakh by most sources,
  40 lakh by some. Planned sales of 2.63 to 7.89 lakh are below both.
- GST on packaged namkeen is reported as 5% from 22 September 2025. Confirm whether the
  supplier's 90 includes it.
