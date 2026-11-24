#!/usr/bin/env python3
"""Stress tests for the Campus Launch blueprint (snack tasting box, 0/60/120 batch decision).

All inputs are the illustrative figures printed in the blueprint, or assumptions stated
next to each test. Nothing here is real market data. Run:  python3 stress_test.py
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np

SEEDS = (11, 23, 47)          # every Monte Carlo test is repeated on these seeds
N = 200_000                   # simulated drops per seed for single-drop tests
BATCHES = (0, 60, 120)


@dataclass(frozen=True)
class Terms:
    price: float = 210
    unit_cost: float = 90
    freight: float = 24        # per dispatched box
    fail_fee: float = 20       # per failed delivery
    cod_share: float = 0.50
    cod_fail: float = 0.26
    open_cash: float = 32_000
    bill: float = 16_000       # existing bill due day 7
    reserve: float = 10_000
    cod_day: int = 5           # 5 = fast payout, 12 = payout after the bill
    gateway_fee: float = 0.0   # share of prepaid receipts kept by the payment gateway
    salvage: float = 0.0       # share of unit cost recovered on unsold or returned boxes


BASE = Terms()


# ----------------------------------------------------------------------------- core ledger
def ledger(batch, disp, prepaid, cod_ok, failed, t: Terms):
    """Contribution and lowest cash balance for one drop. Works on scalars or arrays."""
    pre_cash = prepaid * t.price * (1 - t.gateway_fee)
    cod_cash = cod_ok * t.price
    freight = disp * t.freight + failed * t.fail_fee
    purchase = batch * t.unit_cost
    salvage = t.salvage * t.unit_cost * (batch - disp + failed)
    contribution = pre_cash + cod_cash - purchase - freight + salvage
    steps = sorted(
        [(0, -purchase), (2, pre_cash), (3, -freight), (t.cod_day, cod_cash), (7, -t.bill + 0 * purchase)],
        key=lambda s: s[0],
    )
    bal, low = t.open_cash, None
    for _, amt in steps:
        bal = bal + amt
        low = bal if low is None else np.minimum(low, bal)
    return contribution, low


def ev(batch, demand, t: Terms = BASE):
    """Expected-value ledger, the way the blueprint computes it (fractional failures)."""
    disp = np.minimum(batch, demand)
    cod = disp * t.cod_share
    failed = cod * t.cod_fail
    return ledger(batch, disp, disp - cod, cod - failed, failed, t)


def mc(batch, demand, t: Terms, rng):
    """Random COD mix and random failed deliveries, one row per simulated drop."""
    disp = np.minimum(batch, demand).astype(int)
    cod = rng.binomial(disp, t.cod_share)
    failed = rng.binomial(cod, t.cod_fail)
    return ledger(batch, disp, disp - cod, cod - failed, failed, t)


def choose(demand, t: Terms = BASE, batches=BATCHES):
    """Blueprint rule: highest expected contribution among batches that keep the reserve."""
    if t.open_cash is None or t.open_cash < t.reserve:
        return "review", 0.0
    best = (0, 0.0)
    for b in batches:
        if b == 0:
            continue
        c, low = ev(b, demand, t)
        if low >= t.reserve and c > best[1]:
            best = (b, float(c))
    return best


def choose_vec(forecast, t: Terms, batches=BATCHES):
    """Vectorised version of choose() for arrays of forecasts."""
    forecast = np.asarray(forecast, dtype=float)
    best_b = np.zeros_like(forecast)
    best_c = np.zeros_like(forecast)
    for b in batches:
        if b == 0:
            continue
        c, low = ev(b, forecast, t)
        ok = (low >= t.reserve) & (c > best_c)
        best_b = np.where(ok, b, best_b)
        best_c = np.where(ok, c, best_c)
    return best_b


def seeds(fn):
    """Run fn(rng) on every seed. Returns (mean across seeds, max minus min across seeds)."""
    out = np.array([fn(np.random.default_rng(s)) for s in SEEDS], dtype=float)
    return out.mean(axis=0), out.max(axis=0) - out.min(axis=0)


def table(headers, rows):
    print("| " + " | ".join(headers) + " |")
    print("|" + "|".join(["---"] * len(headers)) + "|")
    for r in rows:
        print("| " + " | ".join(str(x) for x in r) + " |")
    print()


def rs(x):
    return f"{x:,.0f}"


def pct(x):
    return f"{100 * x:.1f}%"


# ----------------------------------------------------------------------------- A reproduce
def test_a():
    print("## A. Reproduce the blueprint (must match before any other test counts)\n")
    late = replace(BASE, cod_day=12)
    hi_cod = replace(BASE, cod_share=0.85)
    checks = [
        ("Base, 60 boxes, demand 90", ev(60, 90)[0], 3966),
        ("Base, 120 boxes, demand 90", ev(120, 90)[0], 3249),
        ("35 orders, 60 boxes", ev(60, 35)[0], 64),
        ("130 orders, 120 boxes", ev(120, 130)[0], 7932),
        ("85% COD, 130 orders, 120 boxes: contribution", ev(120, 130, hi_cod)[0], 5420),
        ("85% COD fast payout: minimum cash", ev(120, 130, hi_cod)[1], 21200),
        ("85% COD late payout: minimum cash, 120 boxes", ev(120, 130, replace(hi_cod, cod_day=12))[1], 5570),
        ("85% COD late payout: minimum cash, 60 boxes", ev(60, 130, replace(hi_cod, cod_day=12))[1], 10785),
        ("60% COD failure, 85% COD, trial", ev(60, 130, replace(hi_cod, cod_fail=0.60))[0], -1278),
        ("Unit cost 170, trial", ev(60, 130, replace(BASE, unit_cost=170))[0], -834),
        ("Year 1 contribution, 24 drops", 24 * ev(60, 60)[0], 95184),
        ("Year 3 contribution, 72 drops", 72 * ev(60, 60)[0], 285552),
    ]
    rows, ok = [], True
    for name, got, want in checks:
        match = abs(got - want) <= 1.0
        ok &= match
        rows.append((name, rs(want), f"{got:,.1f}", "match" if match else "MISMATCH"))
    table(["Check", "Blueprint", "Recomputed", "Result"], rows)
    decisions = [
        ("Base demand 90", choose(90)[0], 60),
        ("35 orders", choose(35)[0], 60),
        ("130 orders", choose(130)[0], 120),
        ("85% COD, 130, fast", choose(130, hi_cod)[0], 120),
        ("85% COD, 130, late", choose(130, replace(hi_cod, cod_day=12))[0], 60),
        ("60% fail, 85% COD", choose(130, replace(hi_cod, cod_fail=0.60))[0], 0),
        ("Unit cost 170", choose(130, replace(BASE, unit_cost=170))[0], 0),
        ("Zero demand", choose(0)[0], 0),
        ("Opening cash below reserve", choose(90, replace(BASE, open_cash=8000))[0], "review"),
    ]
    rows = []
    for name, got, want in decisions:
        ok &= got == want
        rows.append((name, want, got, "match" if got == want else "MISMATCH"))
    table(["Decision row", "Blueprint batch", "Recomputed", "Result"], rows)
    assert ok, "reproduction failed"
    _ = late
    print("All figures and all nine decisions reproduce.\n")


# ----------------------------------------------------------------------------- B single-drop risk
def test_b():
    print("## B. One drop is a gamble, not an expected value\n")
    print(f"{N:,} simulated drops per seed, {len(SEEDS)} seeds. COD mix and failures drawn at random.\n")
    rows, spread = [], 0.0
    for demand in (35, 60, 90, 130):
        for batch in (60, 120):
            def run(rng, demand=demand, batch=batch):
                c, _ = mc(batch, np.full(N, demand), BASE, rng)
                _, low_late = mc(batch, np.full(N, demand), replace(BASE, cod_day=12), rng)
                return [c.mean(), c.std(), (c < 0).mean(), np.percentile(c, 5), (low_late < BASE.reserve).mean()]
            m, s = seeds(run)
            spread = max(spread, s[2], s[4])
            rows.append((demand, batch, rs(ev(batch, demand)[0]), rs(m[0]), rs(m[1]), pct(m[2]), rs(m[3]), pct(m[4])))
    table(["Demand", "Batch", "Blueprint EV", "Sim mean", "Std dev", "P(loss)", "Worst 5%", "P(reserve breach), late payout"], rows)
    print(f"Largest gap between seeds on any probability: {100 * spread:.2f} percentage points.\n")


# ----------------------------------------------------------------------------- C forecast error
def test_c():
    print("## C. The 60 vs 120 choice under forecast error\n")
    d = np.arange(0, 200)
    c60, c120 = ev(60, d)[0], ev(120, d)[0]
    switch = int(d[np.argmax(c120 > c60)])
    print(f"120 boxes beats 60 only when actual demand is {switch} or more.")
    print(f"If you order 120 and demand is 60: {rs(ev(120, 60)[0])}. If you order 60: {rs(ev(60, 60)[0])}.\n")
    rows, spread = [], 0.0
    for mae in (6.7, 9.3, 25.0):
        sd = mae * math.sqrt(math.pi / 2)
        for f in (70, 85, 95, 105, 120):
            def run(rng, f=f, sd=sd):
                actual = np.clip(np.rint(rng.normal(f, sd, N)), 0, None)
                b = choose(f)[0]
                c, _ = mc(b, actual, BASE, rng)
                oracle = np.maximum(np.maximum(ev(60, actual)[0], ev(120, actual)[0]), 0)
                wrong = choose_vec(actual, BASE) != b
                return [b, c.mean(), (c < 0).mean(), wrong.mean(), (oracle - ev(b, actual)[0]).mean()]
            m, s = seeds(run)
            spread = max(spread, s[2], s[3])
            rows.append((mae, f, int(m[0]), rs(m[1]), pct(m[2]), pct(m[3]), rs(m[4])))
    table(["Forecast MAE", "Forecast", "Batch chosen", "Mean contribution", "P(loss)", "P(wrong batch)", "Money left on table"], rows)
    print(f"Largest gap between seeds on any probability: {100 * spread:.2f} percentage points.\n")


# ----------------------------------------------------------------------------- D newsvendor
def test_d():
    print("## D. Is 0/60/120 the right menu? (newsvendor check)\n")
    fail = BASE.cod_share * BASE.cod_fail
    per_disp = BASE.price * (1 - fail) - BASE.freight - fail * BASE.fail_fee
    rows = []
    for salv in (0.0, 0.5, 0.8):
        cu = per_disp - BASE.unit_cost
        co = BASE.unit_cost * (1 - salv)
        rows.append((pct(salv), f"{cu:.1f}", f"{co:.1f}", f"{cu / (cu + co):.2f}"))
    print(f"Net cash per dispatched box before purchase cost: {per_disp:.1f}\n")
    table(["Leftover value recovered", "Profit per box sold", "Loss per box unsold", "Order up to this demand percentile"], rows)
    rows = []
    for f in (90, 110):
        for salv in (0.0, 0.5, 0.8):
            t = replace(BASE, salvage=salv)
            def run(rng, f=f, t=t):
                actual = np.clip(np.rint(rng.normal(f, 12, N)), 0, None)
                return [ev(b, actual, t)[0].mean() for b in range(40, 151, 10)]
            m, _ = seeds(run)
            sizes = list(range(40, 151, 10))
            best = sizes[int(np.argmax(m))]
            rows.append((f, pct(salv), best, rs(m.max()), rs(m[sizes.index(60)]), rs(m[sizes.index(120)])))
    table(["Forecast (sd 12)", "Leftover recovered", "Best batch (steps of 10)", "Its contribution", "60 boxes", "120 boxes"], rows)


# ----------------------------------------------------------------------------- E sensitivity
def test_e():
    print("## E. Cost and price sensitivity (60-box sell-out drop, 24 drops, overhead 60,000)\n")
    def y1(t):
        return 24 * float(ev(60, 60, t)[0]) - 60_000
    cases = [
        ("Blueprint base", BASE),
        ("Price 190 (down 9.5%)", replace(BASE, price=190)),
        ("Price 180 (down 14%)", replace(BASE, price=180)),
        ("Unit cost 100 (packaging +10)", replace(BASE, unit_cost=100)),
        ("Unit cost 115", replace(BASE, unit_cost=115)),
        ("Gateway fee 2% on prepaid", replace(BASE, gateway_fee=0.02)),
        ("COD failure 10%", replace(BASE, cod_fail=0.10)),
        ("COD failure 40%", replace(BASE, cod_fail=0.40)),
        ("COD share 80%", replace(BASE, cod_share=0.80)),
        ("COD share 20%", replace(BASE, cod_share=0.20)),
        ("Packaging +10 and gateway 2%", replace(BASE, unit_cost=100, gateway_fee=0.02)),
        ("Packaging +10, gateway 2%, price 190", replace(BASE, unit_cost=100, gateway_fee=0.02, price=190)),
    ]
    table(["Case", "Contribution per drop", "Year 1 surplus"],
          [(n, rs(ev(60, 60, t)[0]), rs(y1(t))) for n, t in cases])

    def bisect(field, lo, hi):
        f = lambda v: y1(replace(BASE, **{field: v}))
        for _ in range(60):
            mid = (lo + hi) / 2
            if (f(lo) > 0) == (f(mid) > 0):
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2
    print(f"Year 1 surplus hits zero at: price {bisect('price', 100, 210):.1f}, "
          f"unit cost {bisect('unit_cost', 90, 200):.1f}, COD failure {100 * bisect('cod_fail', 0.26, 1.0):.1f}%.")
    print(f"Year 1 surplus per founder per month, six founders: {y1(BASE) / 6 / 12:.0f}.\n")


# ----------------------------------------------------------------------------- F weak weeks
def test_f():
    print("## F. Year 1 if some weeks are weak (blueprint assumes every drop sells out)\n")
    strong, weak = float(ev(60, 60)[0]), float(ev(60, 35)[0])
    p_star = (strong - 60_000 / 24) / (strong - weak)
    print(f"Analytic break-even: Year 1 loses money once more than {pct(p_star)} of drops are weak "
          f"({math.floor(p_star * 24)} of 24 is the last safe count).\n")
    rows, spread = [], 0.0
    paths = 20_000
    for p in (0.0, 0.1, 0.2, 0.3, 0.4, 0.5):
        def run(rng, p=p):
            demand = np.where(rng.random((paths, 24)) < p, 35, 60)
            c, _ = mc(60, demand, BASE, rng)
            surplus = c.sum(axis=1) - 60_000
            return [surplus.mean(), (surplus < 0).mean(), np.percentile(surplus, 5)]
        m, s = seeds(run)
        spread = max(spread, s[1])
        rows.append((pct(p), rs(m[0]), pct(m[1]), rs(m[2])))
    table(["Share of weak weeks (35 orders)", "Mean Year 1 surplus", "P(Year 1 loss)", "Worst 5%"], rows)
    print(f"Largest gap between seeds on P(loss): {100 * spread:.2f} percentage points.\n")


# ----------------------------------------------------------------------------- G redesign
def v2_drop(demand, retention, t: Terms, rng, moq=60, pack=10):
    """Prepaid pre-order: collect UPI payment in the window, then buy to the paid count."""
    net = t.price * (1 - t.gateway_fee) - t.freight
    go = math.ceil(moq * t.unit_cost * (1 - t.salvage) / (net - t.salvage * t.unit_cost))
    paid = rng.binomial(demand.astype(int), retention)
    run = paid >= go
    batch = np.where(run, np.maximum(moq, np.ceil(paid / pack) * pack), 0)
    disp = np.where(run, paid, 0)
    revenue = disp * t.price * (1 - t.gateway_fee)
    purchase = batch * t.unit_cost
    handling = disp * t.freight
    contribution = revenue - purchase - handling + t.salvage * t.unit_cost * (batch - disp)
    # conservative cash timing: supplier paid day 0, gateway settles day 2, handling day 3, bill day 7
    b0 = t.open_cash - purchase
    b3 = b0 + revenue - handling
    low = np.minimum(np.minimum(b0, b3), b3 - t.bill)
    return contribution, low, go


def test_g():
    print("## G. Redesign test: forecast-then-buy versus prepay-then-buy\n")
    fee = 0.02
    v1 = replace(BASE, gateway_fee=fee, cod_day=12)                       # blueprint, courier COD, late payout
    v1b = replace(BASE, gateway_fee=fee, cod_fail=0.10, fail_fee=0, cod_day=3, salvage=0.0)  # hand delivery, cash at handover
    v2 = replace(BASE, gateway_fee=fee)
    go = v2_drop(np.array([0]), 1.0, v2, np.random.default_rng(0))[2]
    print("Same 2% gateway fee on prepaid receipts in every design. Actual demand = forecast with sd 12.")
    print("V1 = blueprint (courier, 50% COD, 26% failure, COD paid after the bill).")
    print("V1b = blueprint rule with hand delivery on campus (10% no-show on pay-at-pickup, no failure fee, cash at handover).")
    print(f"V2 = prepaid UPI pre-order, buy to the paid count in packs of 10, minimum 60, run only at {go}+ paid orders.\n")
    rows, spread = [], 0.0
    for f in (35, 60, 90, 130):
        def actual(rng, f=f):
            return np.clip(np.rint(rng.normal(f, 12, N)), 0, None)
        def run_v1(rng, f=f, t=v1):
            a = actual(rng)
            c, low = mc(choose(f, t)[0], a, t, rng)
            return [c.mean(), (c < 0).mean(), np.percentile(c, 5), (low < t.reserve).mean()]
        for label, t in (("V1 blueprint", v1), ("V1b hand delivery", v1b)):
            m, s = seeds(lambda rng, t=t: run_v1(rng, t=t))
            spread = max(spread, s[1], s[3])
            rows.append((f, label, int(choose(f, t)[0]), rs(m[0]), pct(m[1]), rs(m[2]), pct(m[3])))
        for r in (1.0, 0.8, 0.6, 0.5):
            def run_v2(rng, r=r):
                c, low, _ = v2_drop(actual(rng), r, v2, rng)
                return [c.mean(), (c < 0).mean(), np.percentile(c, 5), (low < v2.reserve).mean()]
            m, s = seeds(run_v2)
            spread = max(spread, s[1], s[3])
            rows.append((f, f"V2 prepaid, {int(r * 100)}% still buy", "to count", rs(m[0]), pct(m[1]), rs(m[2]), pct(m[3])))
    table(["Forecast", "Design", "Batch", "Mean contribution", "P(loss)", "Worst 5%", "P(reserve breach)"], rows)
    print(f"Largest gap between seeds on any probability: {100 * spread:.2f} percentage points.\n")

    print("Share of interested buyers who must still pay upfront for V2 to match V1:\n")
    rows = []
    for f in (60, 90, 130):
        def v1_mean(rng, f=f):
            a = np.clip(np.rint(rng.normal(f, 12, N)), 0, None)
            return [mc(choose(f, v1)[0], a, v1, rng)[0].mean()]
        target = seeds(v1_mean)[0][0]
        found = None
        for r in np.arange(0.30, 1.001, 0.01):
            def v2_mean(rng, r=r, f=f):
                a = np.clip(np.rint(rng.normal(f, 12, N)), 0, None)
                return [v2_drop(a, r, v2, rng)[0].mean()]
            if seeds(v2_mean)[0][0] >= target:
                found = r
                break
        rows.append((f, rs(target), pct(found) if found else "never"))
    table(["Forecast", "V1 mean contribution", "V2 break-even retention"], rows)


# ----------------------------------------------------------------------------- B2 exact cross-check
def test_b2():
    print("## B2. Exact cross-check of the simulation (no random numbers)\n")
    # demand 35, batch 60: contribution = 210*(35-F) - 5400 - 35*24 - 20*F, F ~ Binomial(35, 0.5*0.26)
    q = BASE.cod_share * BASE.cod_fail
    pmf = [math.comb(35, k) * q ** k * (1 - q) ** (35 - k) for k in range(36)]
    contrib = [BASE.price * (35 - k) - 60 * BASE.unit_cost - 35 * BASE.freight - BASE.fail_fee * k for k in range(36)]
    p_loss = sum(p for p, c in zip(pmf, contrib) if c < 0)
    mean = sum(p * c for p, c in zip(pmf, contrib))
    sim = seeds(lambda rng: [(mc(60, np.full(N, 35), BASE, rng)[0] < 0).mean()])[0][0]
    print(f"Demand 35, batch 60. Exact binomial: mean {mean:.1f}, P(loss) {100 * p_loss:.2f}%. Simulation P(loss): {100 * sim:.2f}%.")
    assert abs(p_loss - sim) < 0.01 and abs(mean - 63.5) < 0.01
    print("Simulation agrees with the exact calculation to within 1 percentage point.\n")


# ----------------------------------------------------------------------------- G2 hybrid
def v3_drop(demand, retention, walk, buffer, t: Terms, rng, moq=60, pack=10):
    """Prepaid base plus a buffer for pay-at-pickup buyers. Unsold buffer is written off."""
    net = t.price * (1 - t.gateway_fee) - t.freight
    go = math.ceil(moq * t.unit_cost / net)
    demand = demand.astype(int)
    paid = rng.binomial(demand, retention)
    walkups = rng.binomial(demand - paid, walk)
    run = paid >= go
    batch = np.where(run, np.maximum(moq, np.ceil(paid * (1 + buffer) / pack) * pack), 0)
    sold_walk = np.where(run, np.minimum(walkups, batch - paid), 0)
    sold = np.where(run, paid, 0) + sold_walk
    contribution = sold * net - batch * t.unit_cost
    return contribution


def test_g2():
    print("## G2. Hybrid test: prepaid base plus a pay-at-pickup buffer\n")
    print("Half of the buyers who will not prepay still turn up at pickup if stock is there (assumption).")
    print("Buffer = extra boxes bought on top of the paid count. Unsold boxes are written off. 2% fee on all receipts.\n")
    t = replace(BASE, gateway_fee=0.02)
    rows, spread = [], 0.0
    for f in (60, 90, 130):
        for r in (0.6, 0.8):
            for buf in (0.0, 0.2, 0.4):
                def run(rng, f=f, r=r, buf=buf):
                    a = np.clip(np.rint(rng.normal(f, 12, N)), 0, None)
                    c = v3_drop(a, r, 0.5, buf, t, rng)
                    return [c.mean(), (c < 0).mean(), np.percentile(c, 5)]
                m, s = seeds(run)
                spread = max(spread, s[1])
                rows.append((f, pct(r), pct(buf), rs(m[0]), pct(m[1]), rs(m[2])))
    table(["Forecast", "Prepay share", "Buffer", "Mean contribution", "P(loss)", "Worst 5%"], rows)
    print(f"Largest gap between seeds on P(loss): {100 * spread:.2f} percentage points.\n")


# ----------------------------------------------------------------------------- H forecast replication
def test_h():
    print("## H. Can one 20-week holdout rank the forecasting methods?\n")
    print("My own synthetic generator (the blueprint's notebook was not supplied), 300 seeds per setting.")
    print("80 weeks, first 60 train, last 20 test, ridge on three standardised inputs, same decision rule.\n")
    rows = []
    for label, exam_mult, promo_mult in (("Weak exam/promo effect", 0.9, 1.1), ("Medium", 0.75, 1.25), ("Strong", 0.6, 1.4)):
        wins, ties, diffs, maes = 0, 0, [], []
        for seed in range(300):
            rng = np.random.default_rng(1000 + seed)
            interest = np.rint(150 * np.exp(0.25 * rng.standard_normal(80)))
            exam = (rng.random(80) < 0.20).astype(float)
            promo = (rng.random(80) < 0.25).astype(float)
            orders = np.rint(interest * 0.6 * np.where(exam == 1, exam_mult, 1) * np.where(promo == 1, promo_mult, 1)
                             * np.exp(0.12 * rng.standard_normal(80)))
            X = np.column_stack([interest, exam, promo])
            mu, sd = X[:60].mean(axis=0), X[:60].std(axis=0) + 1e-9
            Z = (X - mu) / sd
            ybar = orders[:60].mean()
            beta = np.linalg.solve(Z[:60].T @ Z[:60] + 1.0 * np.eye(3), Z[:60].T @ (orders[:60] - ybar))
            f_ai = Z[60:] @ beta + ybar
            slope, icpt = np.polyfit(interest[:60], orders[:60], 1)
            f_int = slope * interest[60:] + icpt
            f_avg = np.array([orders[w - 4:w].mean() for w in range(60, 80)])
            actual = orders[60:]
            def money(f):
                b = choose_vec(np.clip(f, 0, None), BASE)
                return float(np.sum(np.where(b > 0, ev(b, actual)[0], 0.0)))
            m_ai, m_int = money(f_ai), money(f_int)
            wins += m_ai > m_int
            ties += m_ai == m_int
            diffs.append(m_ai - m_int)
            maes.append([np.abs(f_ai - actual).mean(), np.abs(f_int - actual).mean(), np.abs(f_avg - actual).mean()])
        maes = np.mean(maes, axis=0)
        rows.append((label, f"{maes[0]:.1f}", f"{maes[1]:.1f}", f"{maes[2]:.1f}", pct(wins / 300), pct(ties / 300),
                     pct(1 - (wins + ties) / 300), rs(np.median(diffs)), f"{rs(np.percentile(diffs, 5))} to {rs(np.percentile(diffs, 95))}"))
    table(["Setting", "MAE three-input", "MAE interest only", "MAE 4-week avg", "Three-input earns more", "Tie",
           "Interest-only earns more", "Median gap over 20 drops", "5th to 95th percentile gap"], rows)


# ----------------------------------------------------------------------------- I three-year plan
def test_i():
    print("## I. Three-year plan with uncertain demand and a monthly cash check\n")
    drops_per_year = (24, 45, 72)
    overhead = (60_000, 100_000, 160_000)
    teaching = [m for m in range(12) if m not in (5, 6, 11)]      # nine teaching months, three break months
    paths = 4_000
    print("Each drop's demand is lognormal with the mean shown and a 35% coefficient of variation; one drop in five")
    print("falls in an exam week at 70% demand. Overhead is paid every month, drops happen only in nine teaching months.")
    print("Opening cash 32,000, existing bill 16,000 paid in month 1, reserve 10,000. Gateway fee 2% in both designs.\n")

    def simulate(rng, mean, design, retention=1.0):
        t = replace(BASE, gateway_fee=0.02)
        cash = np.full(paths, t.open_cash - t.bill, dtype=float)
        low = cash.copy()
        yearly = []
        for y in range(3):
            base, extra = divmod(drops_per_year[y], len(teaching))
            year_c = np.zeros(paths)
            for m in range(12):
                k = (base + (teaching.index(m) < extra)) if m in teaching else 0
                if k:
                    sigma = math.sqrt(math.log(1 + 0.35 ** 2))
                    d = mean * np.exp(sigma * rng.standard_normal((paths, k)) - sigma ** 2 / 2)
                    d = np.rint(d * np.where(rng.random((paths, k)) < 0.2, 0.7, 1.0))
                    if design == "v1":
                        c, _ = mc(60, d, t, rng)
                    else:
                        c, _, _ = v2_drop(d, retention, t, rng)
                    c = c.sum(axis=1)
                else:
                    c = np.zeros(paths)
                year_c += c
                cash += c - overhead[y] / 12
                low = np.minimum(low, cash)
            yearly.append(year_c - overhead[y])
        yearly = np.array(yearly)
        total = yearly.sum(axis=0)
        gap = np.maximum(0, t.reserve - low)
        return [yearly[0].mean(), yearly[1].mean(), yearly[2].mean(), (yearly[0] < 0).mean(), (total < 0).mean(),
                (low < t.reserve).mean(), np.percentile(gap, 95)]

    rows, spread = [], 0.0
    for mean in (50, 70, 90, 110):
        for label, design, r in (("V1 always 60 boxes", "v1", 1.0), ("V2 prepaid, 80% still buy", "v2", 0.8),
                                 ("V2 prepaid, 60% still buy", "v2", 0.6)):
            m, s = seeds(lambda rng, mean=mean, design=design, r=r: simulate(rng, mean, design, r))
            spread = max(spread, s[3], s[4], s[5])
            rows.append((mean, label, rs(m[0]), rs(m[1]), rs(m[2]), pct(m[3]), pct(m[4]), pct(m[5]), rs(m[6])))
    table(["Mean demand per drop", "Design", "Year 1 surplus", "Year 2", "Year 3", "P(Year 1 loss)",
           "P(3-year loss)", "P(cash below reserve)", "Funding gap, 95th percentile"], rows)
    print(f"Largest gap between seeds on any probability: {100 * spread:.2f} percentage points.")
    print("Blueprint table for comparison: 35,184 / 78,470 / 125,552 with every box sold and no gateway fee.\n")

    print("\nYear 1 mean surplus by mean demand per drop (same assumptions):\n")
    rows = []
    for mean in range(50, 96, 5):
        row = [mean]
        for design, r in (("v1", 1.0), ("v2", 0.8), ("v2", 0.6)):
            m, _ = seeds(lambda rng, mean=mean, design=design, r=r: simulate(rng, mean, design, r)[:1])
            row.append(rs(m[0]))
        rows.append(tuple(row))
    table(["Mean demand per drop", "V1 always 60", "V2, 80% prepay", "V2, 60% prepay"], rows)


if __name__ == "__main__":
    print("# Campus Launch blueprint: stress-test output\n")
    for test in (test_a, test_b, test_b2, test_c, test_d, test_e, test_f, test_g, test_g2, test_h, test_i):
        test()
