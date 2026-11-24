# FINPULSE AI: new sections

Two sections to add to the blueprint after "03 / Personal". Every figure is illustrative and
comes from synthetic students. Reproduce them with `python3 student_module_test.py`.

---

## 03B / STUDENT

### Student money module

A campus student receives a fixed amount from home once a month and has no income. Many
spend most of it in the first three weeks and reach the last week with almost nothing.
FINPULSE AI shows the student, early in the month, when the money will run out and what to
change so it lasts.

This module is sold directly to the student, so it is the direct-to-consumer side of FINPULSE AI.

**Inputs:** monthly allowance and the date it arrives, fixed bills, daily spending by
category, and a savings goal. Entry is manual or from sample data.

### What the student sees

| Output | What it tells the student |
|---|---|
| Run-out date | The day the money finishes at the current pace. |
| Safe-to-spend | The daily amount that makes the balance last to month end. |
| Spending diagnosis | Where the money went, and the two categories that grew most. |
| Next-month budget | An allocation built from the student's own fixed bills and history. |
| Early warning | An alert near day 10 if the student is on course to run short. |
| Savings tracker | Progress toward a buffer and a goal. |

### Illustrative diagnosis

A student receives INR 10,000 on day 1. By day 18 the record looks like this.

| Category | Spent (INR) |
|---|---|
| Food beyond the mess | 3,200 |
| Outings | 1,900 |
| Shopping | 1,500 |
| Travel | 700 |
| Phone and subscriptions | 650 |
| Study material | 400 |
| Other | 300 |
| **Total** | **8,650** |

The balance is INR 1,350 with 12 days left. The pace so far is INR 481 per day, so the money
runs out on day 21. To reach month end the student can spend INR 112 per day. At the
current pace the shortfall is INR 4,417. Food beyond the mess and outings account for
INR 5,100, which is 59% of spending. That is where the student should cut first.

### Illustrative budget for the next month

| Allocation | Amount (INR) |
|---|---|
| Fixed bills (phone, study, travel) | 1,750 |
| Food beyond the mess | 3,900 |
| Outings | 1,450 |
| Shopping | 1,150 |
| Other | 250 |
| Emergency buffer | 1,000 |
| Savings | 500 |
| **Total** | **10,000** |

Flexible spending is INR 6,750, which is INR 225 per day or INR 1,575 per week. The tool
keeps the fixed bills, sets aside the buffer and savings, and cuts the flexible categories
from this month's pace to fit. Essential categories such as food are cut at half the rate of
the rest. It does not impose a fixed percentage rule.

### What the AI predicts, and how it was tested

The prediction is one question: will this student's balance fall below INR 500 on or before
day 25? Three rules were tested on 50,000 synthetic student-months, repeated on three random
seeds. In the simulation 36.9% of students ran short.

| Rule, checked on day 10 | Precision | Recall | Students flagged |
|---|---|---|---|
| A. Spent more than the pro-rata share | 42.6% | 98.9% | 84.3% |
| B. Last seven days' pace continues | 53.0% | 85.5% | 58.7% |
| C. Pace so far, with fixed bills tagged and removed | 67.8% | 77.4% | 41.5% |
| Trained model (logistic regression, six inputs) | 68.8% | 80.4% | 42.4% |

Rule A catches almost everyone, but it warns 84% of all students, so most would stop
reading the alert. The trained model is the default: it catches 80% of the students who run
short, and 69% of its warnings are correct. Its lead over Rule C is small, about 3 points of
recall, so the product shows both and records when they disagree. A missed warning costs a
student more than a false alarm, so the team should not push precision higher at the cost of
recall. Results moved by less than 0.6 percentage points between seeds. The model row comes
from a separate held-out run recorded in `model/evaluation.md`.

The language model only explains figures the calculation engine has already verified. It
never produces the numbers.

### Limits and safeguards

- Synthetic data shows that the rules work as designed. It does not show how real students spend.
- A student's spending record is personal data. The project uses synthetic students only.
- A live product needs clear consent, and it must never share a student's record with
  parents or the institution unless the student chooses to.

---

## 03C / INVESTMENT

### Savings and investment planning

This section serves students and businesses. It compares options, shows the risk and runs
scenarios. The user makes the decision.

### For students

The order matters more than the product:

1. Finish the month without running short.
2. Build an emergency buffer equal to half a month's allowance.
3. Save a fixed amount toward a named goal.
4. Learn the main saving and investment categories, with their risk and lock-in period.

| Monthly saving (INR) | Months | Paid in | Value at 6% a year | Value at 12% a year |
|---|---|---|---|---|
| 500 | 12 | 6,000 | 6,168 | 6,341 |
| 500 | 24 | 12,000 | 12,716 | 13,487 |
| 1,000 | 24 | 24,000 | 25,432 | 26,973 |

These rates are hypothetical, not forecasts. Over 24 months, doubling the assumed return
adds INR 771 to a saving of INR 500 a month. Doubling the monthly saving adds INR 12,716 at
the same 6% rate. For a student, the habit of saving is worth far more than the search for
a higher return, so the module spends its effort there.

### For businesses

The module ranks a company's own spending options. It first checks that the cash reserve
and upcoming payments are covered. It then compares each option on NPV, IRR, payback period
and sensitivity to its main assumption, and marks an option "Insufficient evidence" when
inputs are missing. Surplus cash is sorted by when the business will need it.

### Investment boundary

FINPULSE AI does not tell any user which share, fund or scheme to buy, and it never
promises a return. Under the SEBI (Investment Advisers) Regulations, 2013, a person may not
act as an investment adviser without registration. The module therefore gives education,
category comparisons and hypothetical scenarios only. A registered adviser would be needed
before any release that gives personal investment recommendations.
