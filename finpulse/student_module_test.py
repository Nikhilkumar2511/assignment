#!/usr/bin/env python3
"""Checks for the FINPULSE AI student money module. Synthetic students only, no real data.

Part 1 verifies the worked example used in the blueprint section.
Part 2 tests three early-warning rules on simulated months: who runs out before month end?
Part 3 verifies the savings scenarios in the investment section.
Run:  python3 student_module_test.py
"""
import numpy as np

ALLOWANCE, DAYS, FLOOR, HORIZON = 10_000, 30, 500, 25   # "near bankrupt" = balance under 500 by day 25
SEEDS, N = (11, 23, 47), 50_000


def part1():
    print("## 1. Worked example (one synthetic student, day 18 of 30)\n")
    spent = {"Food beyond the mess": 3200, "Outings": 1900, "Shopping": 1500, "Travel": 700,
             "Phone and subscriptions": 650, "Study material": 400, "Other": 300}
    day, total = 18, sum(spent.values())
    balance, left = ALLOWANCE - total, DAYS - day
    burn = total / day
    print(f"Spent {total:,} in {day} days. Balance {balance:,}. Days left {left}.")
    print(f"Burn rate {burn:.1f} per day. Money lasts {balance / burn:.1f} more days, so it runs out on day {day + int(balance // burn) + 1}.")
    print(f"Safe to spend {balance / left:.1f} per day. Shortfall at the current pace {burn * left - balance:,.0f}.")
    top = sorted(spent.items(), key=lambda kv: -kv[1])[:2]
    print(f"Top two categories: {top[0][0]} and {top[1][0]} = {top[0][1] + top[1][1]:,} ({100 * (top[0][1] + top[1][1]) / total:.0f}% of spending).\n")
    plan = {"Fixed bills (phone, study, travel)": 1750, "Food beyond the mess": 3600, "Outings": 1500, "Shopping": 1000,
            "Other": 650, "Emergency buffer": 1000, "Savings": 500}
    assert sum(plan.values()) == ALLOWANCE
    flexible = plan["Food beyond the mess"] + plan["Outings"] + plan["Shopping"] + plan["Other"]
    print(f"Next-month plan adds up to {sum(plan.values()):,}. Flexible spending {flexible:,} = {flexible / DAYS:.0f} per day, {flexible / DAYS * 7:,.0f} per week.\n")


def simulate(rng, n=N):
    base = rng.uniform(70, 270, n)                      # typical daily spend differs by student
    front = rng.random(n) < 0.40                        # 40% spend faster in the first 10 days after money arrives
    fixed_day = rng.integers(0, 5, n)                   # one fixed bill in the first five days
    fixed_amt = rng.uniform(1200, 2600, n)
    spend = np.zeros((n, DAYS))
    for d in range(DAYS):
        weekend = 1.5 if d % 7 in (5, 6) else 1.0
        early = np.where(front & (d < 10), 1.6, 1.0)
        big = (rng.random(n) < 0.04) * rng.uniform(800, 2500, n)   # trip, shopping, birthday
        spend[:, d] = base * weekend * early * rng.lognormal(-0.125, 0.5, n) + big
    spend[np.arange(n), fixed_day] += fixed_amt
    balance = ALLOWANCE - spend.cumsum(axis=1)
    label = (balance[:, :HORIZON] < FLOOR).any(axis=1)
    return spend, balance, label, fixed_amt


def part2():
    print("## 2. Early-warning test: which students run short before day 25?\n")
    print(f"{N:,} synthetic student-months per seed, {len(SEEDS)} seeds. A student counts as near bankrupt when the balance")
    print(f"drops under {FLOOR} on or before day {HORIZON}. Students already under {FLOOR} at the check day are left out.\n")
    names = ["A. Spent more than the pro-rata share", "B. Last 7 days' pace continues", "C. Pace so far, fixed bills tagged and removed"]
    print("| Check day | Rule | Precision | Recall | F1 | Flagged | Seed spread (recall) |")
    print("|---|---|---|---|---|---|---|")
    rates = []
    for c in (7, 10, 15):
        res = {k: [] for k in range(3)}
        for s in SEEDS:
            spend, balance, label, fixed_amt = simulate(np.random.default_rng(s))
            rates.append(label.mean())
            live = balance[:, c - 1] >= FLOOR
            bal, room, togo = balance[:, c - 1], balance[:, c - 1] - FLOOR, HORIZON - c
            spent = ALLOWANCE - bal
            flags = [spent > ALLOWANCE * c / DAYS,
                     spend[:, c - 7:c].mean(axis=1) * togo > room,
                     (spent - fixed_amt) / c * togo > room]
            for k, f in enumerate(flags):
                tp = (f & label & live).sum(); fp = (f & ~label & live).sum(); fn = (~f & label & live).sum()
                p, r = tp / max(tp + fp, 1), tp / max(tp + fn, 1)
                res[k].append([p, r, 2 * p * r / max(p + r, 1e-9), (f & live).sum() / live.sum()])
        for k in range(3):
            a = np.array(res[k]); m = a.mean(axis=0); sp = a[:, 1].max() - a[:, 1].min()
            print(f"| {c} | {names[k]} | {100*m[0]:.1f}% | {100*m[1]:.1f}% | {m[2]:.2f} | {100*m[3]:.1f}% | {100*sp:.2f} pts |")
    print(f"\nShare of simulated students who end up near bankrupt: {100 * np.mean(rates):.1f}%.\n")


def part3():
    print("## 3. Savings scenarios (hypothetical rates, not forecasts)\n")
    print("| Monthly saving | Months | Paid in | Value at 0% | Value at 6% a year | Value at 12% a year |")
    print("|---|---|---|---|---|---|")
    for pm, months in ((500, 12), (500, 24), (1000, 24)):
        row = []
        for annual in (0.0, 0.06, 0.12):
            r = annual / 12
            row.append(pm * months if r == 0 else pm * ((1 + r) ** months - 1) / r)
        print(f"| {pm:,} | {months} | {pm * months:,} | {row[0]:,.0f} | {row[1]:,.0f} | {row[2]:,.0f} |")
    print("\nEnd-of-month deposits, monthly compounding.\n")


if __name__ == "__main__":
    print("# FINPULSE AI student module: test output\n")
    part1(); part2(); part3()
