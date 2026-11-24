"""Business financial health diagnosis and investment appraisal.

Rule-based on purpose: every ratio, threshold and finding can be traced and audited.
A metric is reported only when its inputs were supplied. Missing inputs are listed, never guessed.
"""
from __future__ import annotations

from .student import InputError

# (poor, good) per metric. Lower-is-better metrics have poor > good. Defaults are general rules of
# thumb and differ by industry; pass "thresholds" in the request to override any of them.
DEFAULT_THRESHOLDS = {
    "gross_margin": (0.10, 0.40), "operating_margin": (0.00, 0.20), "net_margin": (0.00, 0.10),
    "current_ratio": (1.0, 2.0), "quick_ratio": (0.5, 1.0), "cash_cover_months": (1.0, 3.0),
    "debt_to_equity": (2.0, 0.5), "interest_coverage": (1.5, 5.0),
    "receivable_days": (90, 30), "inventory_days": (120, 45), "cash_conversion_cycle": (90, 30),
}
AREAS = {
    "Profitability": (0.30, ["gross_margin", "operating_margin", "net_margin"]),
    "Liquidity": (0.30, ["current_ratio", "quick_ratio", "cash_cover_months"]),
    "Solvency": (0.20, ["debt_to_equity", "interest_coverage"]),
    "Efficiency": (0.20, ["receivable_days", "inventory_days", "cash_conversion_cycle"]),
}
NUMERIC_FIELDS = ["revenue", "cogs", "operating_expenses", "depreciation", "interest", "tax", "total_costs",
                  "net_profit", "cash", "receivables", "inventory", "other_current_assets", "payables",
                  "short_term_debt", "other_current_liabilities", "long_term_debt", "equity"]
MAY_BE_NEGATIVE = {"net_profit", "equity"}
UNITS = {"gross_margin": "share", "operating_margin": "share", "net_margin": "share", "current_ratio": "times",
         "quick_ratio": "times", "cash_cover_months": "months", "debt_to_equity": "times",
         "interest_coverage": "times", "receivable_days": "days", "inventory_days": "days",
         "payable_days": "days", "cash_conversion_cycle": "days", "working_capital": "currency"}


def _score(value: float, poor: float, good: float) -> float:
    if good == poor:
        return 50.0
    return float(max(0.0, min(100.0, 100.0 * (value - poor) / (good - poor))))


def _clean(data: dict, quality: list, label: str = "") -> dict:
    out = {}
    for key in NUMERIC_FIELDS:
        v = data.get(key)
        if v is None:
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise InputError(f"{label}{key} must be a number")
        if v < 0 and key not in MAY_BE_NEGATIVE:
            raise InputError(f"{label}{key} cannot be negative")
        out[key] = float(v)
    unknown = sorted(set(data) - set(NUMERIC_FIELDS) - {"period_months", "prior", "thresholds", "currency", "name"})
    if unknown:
        quality.append(f"Ignored unknown fields: {', '.join(unknown)}.")
    return out


def _metrics(d: dict, period_days: float, assumptions: list) -> dict:
    """Compute every metric whose inputs exist. Returns {name: value}."""
    m = {}
    rev = d.get("revenue")
    has = lambda *keys: all(k in d for k in keys)

    def opt(key):                         # optional cost lines count as zero, and we say so
        if key not in d:
            assumptions.append(f"{key} was not provided and is treated as zero.")
            return 0.0
        return d[key]

    ebit = None
    if rev and has("cogs"):
        m["gross_margin"] = (rev - d["cogs"]) / rev
    if rev and has("cogs", "operating_expenses"):
        ebitda = rev - d["cogs"] - d["operating_expenses"]
        m["operating_margin"] = ebitda / rev
        ebit = ebitda - opt("depreciation")
    net = None
    if "net_profit" in d:
        net = d["net_profit"]
    elif rev is not None and "total_costs" in d:
        net = rev - d["total_costs"]
    elif ebit is not None:
        net = ebit - opt("interest") - opt("tax")
    if rev and net is not None:
        m["net_margin"] = net / rev
        m["_net_profit"] = net
    if ebit is not None and d.get("interest", 0) > 0:
        m["interest_coverage"] = ebit / d["interest"]
        m["_ebit"] = ebit

    if has("cash", "receivables", "payables"):
        ca = d["cash"] + d["receivables"] + d.get("inventory", 0.0) + d.get("other_current_assets", 0.0)
        cl = d["payables"] + d.get("short_term_debt", 0.0) + d.get("other_current_liabilities", 0.0)
        for k in ("inventory", "short_term_debt"):
            if k not in d:
                assumptions.append(f"{k} was not provided and is treated as zero in the liquidity ratios.")
        m["working_capital"] = ca - cl
        if cl > 0:
            m["current_ratio"] = ca / cl
            m["quick_ratio"] = (d["cash"] + d["receivables"]) / cl
    monthly_cost = None
    if has("cogs", "operating_expenses"):
        monthly_cost = (d["cogs"] + d["operating_expenses"] + d.get("interest", 0.0)) / (period_days / 30)
    elif "total_costs" in d:
        monthly_cost = d["total_costs"] / (period_days / 30)
    if "cash" in d and monthly_cost:
        m["cash_cover_months"] = d["cash"] / monthly_cost

    if has("equity") and ("long_term_debt" in d or "short_term_debt" in d) and d["equity"] > 0:
        m["debt_to_equity"] = (d.get("long_term_debt", 0.0) + d.get("short_term_debt", 0.0)) / d["equity"]

    if rev and "receivables" in d:
        m["receivable_days"] = d["receivables"] / rev * period_days
    if d.get("cogs") and "inventory" in d:
        m["inventory_days"] = d["inventory"] / d["cogs"] * period_days
    if d.get("cogs") and "payables" in d:
        m["payable_days"] = d["payables"] / d["cogs"] * period_days
    if {"receivable_days", "inventory_days", "payable_days"} <= set(m):
        m["cash_conversion_cycle"] = m["receivable_days"] + m["inventory_days"] - m["payable_days"]
    return m


def diagnose_business(payload: dict) -> dict:
    quality, assumptions = [], []
    period_months = payload.get("period_months", 1)
    if not isinstance(period_months, (int, float)) or period_months <= 0:
        raise InputError("period_months must be above zero")
    period_days = 30.0 * period_months
    d = _clean(payload, quality)
    if "revenue" not in d:
        raise InputError("revenue is required")
    thresholds = dict(DEFAULT_THRESHOLDS)
    for k, v in (payload.get("thresholds") or {}).items():
        if k not in thresholds or not isinstance(v, (list, tuple)) or len(v) != 2:
            raise InputError(f"thresholds.{k} must be a known metric with [poor, good]")
        thresholds[k] = (float(v[0]), float(v[1]))

    m = _metrics(d, period_days, assumptions)
    net_profit, ebit = m.pop("_net_profit", None), m.pop("_ebit", None)

    metrics_out, areas_out, weighted, weight_sum = [], [], 0.0, 0.0
    scores = {}
    for name, value in m.items():
        entry = {"metric": name, "value": round(value, 4), "unit": UNITS.get(name, "")}
        if name in thresholds:
            poor, good = thresholds[name]
            s = _score(value, poor, good)
            scores[name] = s
            entry.update({"score": round(s, 1), "band": "good" if s >= 70 else "watch" if s >= 40 else "poor",
                          "poor_at": poor, "good_at": good})
        metrics_out.append(entry)
    missing_by_area = {}
    for area, (weight, names) in AREAS.items():
        have = [scores[n] for n in names if n in scores]
        missing = [n for n in names if n not in scores]
        if missing:
            missing_by_area[area] = missing
        if have:
            a = sum(have) / len(have)
            areas_out.append({"area": area, "score": round(a, 1), "metrics_used": len(have), "metrics_missing": missing})
            weighted += weight * a; weight_sum += weight
        else:
            areas_out.append({"area": area, "score": None, "metrics_used": 0, "metrics_missing": missing})

    enough = sum(1 for a in areas_out if a["score"] is not None) >= 2
    overall = round(weighted / weight_sum, 1) if enough else None
    status = "Insufficient evidence" if overall is None else "Healthy" if overall >= 70 else "Watch" if overall >= 45 else "At risk"

    f = []
    g = m.get
    margin, cover, quick, current = g("net_margin"), g("cash_cover_months"), g("quick_ratio"), g("current_ratio")
    cash_poor = (cover is not None and cover < 1) or (quick is not None and quick < 0.5) or (current is not None and current < 1)
    if margin is not None and margin < 0:
        f.append({"area": "Profitability", "priority": "Urgent action", "title": "The business is making a loss",
                  "evidence": {"net_margin": round(margin, 4), "net_profit": round(net_profit, 2)},
                  "rationale": "Costs are higher than revenue for this period.",
                  "next_step": "Split costs into avoidable and unavoidable, and check contribution margin by product before cutting."})
    if margin is not None and margin > 0 and cash_poor:
        ev = {"net_margin": round(margin, 4)}
        for k in ("cash_cover_months", "quick_ratio", "current_ratio", "receivable_days"):
            if g(k) is not None:
                ev[k] = round(g(k), 2)
        f.append({"area": "Liquidity", "priority": "Urgent action", "title": "Profitable on paper but short of cash",
                  "evidence": ev,
                  "rationale": "Profit is positive, yet cash on hand does not cover near-term payments. Profit is not cash.",
                  "next_step": "Review receivable ageing, chase the oldest invoices, and line up payment dates against cash."})
    elif cash_poor:
        f.append({"area": "Liquidity", "priority": "Urgent action", "title": "Cash does not cover near-term payments",
                  "evidence": {k: round(g(k), 2) for k in ("cash_cover_months", "quick_ratio", "current_ratio") if g(k) is not None},
                  "rationale": "Liquid assets are low against current liabilities or monthly costs.",
                  "next_step": "Build a week-by-week cash plan before committing to new spending."})

    prior = payload.get("prior")
    if isinstance(prior, dict):
        p = _clean(prior, quality, "prior.")
        pm = _metrics(p, period_days, [])
        if p.get("revenue") and d["revenue"] > p["revenue"]:
            growth = d["revenue"] / p["revenue"] - 1
            for key, label in (("gross_margin", "gross margin"), ("net_margin", "net margin")):
                if key in m and key in pm and pm[key] - m[key] >= 0.02:
                    ev = {"revenue_growth": round(growth, 4), f"{key}_now": round(m[key], 4), f"{key}_before": round(pm[key], 4)}
                    if "cogs" in d and p.get("cogs"):
                        ev["cogs_growth"] = round(d["cogs"] / p["cogs"] - 1, 4)
                    if "operating_expenses" in d and p.get("operating_expenses"):
                        ev["operating_expense_growth"] = round(d["operating_expenses"] / p["operating_expenses"] - 1, 4)
                    f.append({"area": "Profitability", "priority": "Investigate and improve",
                              "title": f"Sales are growing but {label} is falling", "evidence": ev,
                              "rationale": f"Revenue rose {100 * growth:.1f}% while {label} fell "
                                           f"{100 * (pm[key] - m[key]):.1f} points, so costs grew faster than sales.",
                              "next_step": "Compare cost growth with sales growth line by line, and check discounts and product mix."})
                    break

    de, cov = g("debt_to_equity"), g("interest_coverage")
    if (de is not None and de > 2) or (cov is not None and cov < 1.5):
        ev = {k: round(g(k), 2) for k in ("debt_to_equity", "interest_coverage") if g(k) is not None}
        if cov is not None and ebit is not None:
            ev["interest_coverage_if_ebit_falls_20pct"] = round(0.8 * ebit / d["interest"], 2)
        f.append({"area": "Solvency", "priority": "Urgent action" if cov is not None and cov < 1.5 else "Investigate and improve",
                  "title": "Debt is putting pressure on the business", "evidence": ev,
                  "rationale": "Borrowing is high against equity, or earnings cover interest only narrowly.",
                  "next_step": "Map repayment dates against expected cash, and avoid new borrowing until coverage improves."})
    rd = g("receivable_days")
    if rd is not None and rd > 60:
        locked = (rd - 45) * d["revenue"] / period_days
        f.append({"area": "Efficiency", "priority": "Investigate and improve", "title": "Customers are slow to pay",
                  "evidence": {"receivable_days": round(rd, 1), "cash_released_at_45_days": round(locked, 2)},
                  "rationale": f"Collecting in 45 days instead of {rd:.0f} would release about {locked:,.0f} of cash.",
                  "next_step": "Age the receivables and agree payment terms with the largest overdue customers."})
    inv = g("inventory_days")
    if inv is not None and inv > 90:
        f.append({"area": "Efficiency", "priority": "Investigate and improve", "title": "Stock is moving slowly",
                  "evidence": {"inventory_days": round(inv, 1)},
                  "rationale": "Stock on hand covers more than three months of sales at cost.",
                  "next_step": "List the slowest items and decide whether to discount, bundle or stop reordering them."})
    if not cash_poor and (cover or 0) >= 3 and (current or 0) >= 1.5 and (margin or 0) >= 0.05:
        f.append({"area": "Investment", "priority": "Evaluate investment", "title": "The business has room to consider investing",
                  "evidence": {"cash_cover_months": round(cover, 2), "current_ratio": round(current, 2), "net_margin": round(margin, 4)},
                  "rationale": "Margins are positive and cash covers at least three months of costs.",
                  "next_step": "Compare options on NPV, IRR and payback with the investment appraisal, keeping the cash reserve intact."})
    strengths = [e["metric"] for e in metrics_out if e.get("band") == "good"]
    if strengths:
        f.append({"area": "Overall", "priority": "Monitor", "title": "Strengths to keep watching",
                  "evidence": {e["metric"]: e["value"] for e in metrics_out if e.get("band") == "good"},
                  "rationale": "These measures are in the healthy range under the thresholds used.",
                  "next_step": "Track them each period so a decline shows early."})
    if missing_by_area:
        f.append({"area": "Data", "priority": "Insufficient evidence", "title": "Some measures could not be calculated",
                  "evidence": missing_by_area,
                  "rationale": "The inputs for these measures were not supplied, so no value is shown for them.",
                  "next_step": "Add the missing balance sheet or cost figures and run the diagnosis again."})
    order = ["Urgent action", "Investigate and improve", "Evaluate investment", "Monitor", "Insufficient evidence"]
    f.sort(key=lambda x: order.index(x["priority"]))

    # A strong average must not hide a critical weakness: any urgent finding caps the score.
    health = {"score": overall, "status": status}
    if overall is not None and overall > 44 and any(x["priority"] == "Urgent action" for x in f):
        health = {"score": 44.0, "status": "At risk", "score_before_cap": overall,
                  "note": "Capped at 44 because at least one finding needs urgent action."}

    return {"mode": "business", "summary": {"revenue": d["revenue"], "net_profit": None if net_profit is None else round(net_profit, 2),
                                            "period_months": period_months},
            "health": health, "areas": areas_out, "metrics": metrics_out,
            "findings": f, "assumptions": sorted(set(assumptions)), "data_quality": quality,
            "thresholds_note": "Default thresholds are general rules of thumb. They vary by industry and can be overridden."}


# ----------------------------------------------------------------------------- investment appraisal
def _npv(rate: float, flows: list) -> float:
    return sum(cf / (1 + rate) ** t for t, cf in enumerate(flows))


def _irr(flows: list):
    lo, hi = -0.99, 10.0
    if _npv(lo, flows) * _npv(hi, flows) > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        if _npv(lo, flows) * _npv(mid, flows) <= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def _payback(cost: float, inflows: list):
    total = 0.0
    for year, cf in enumerate(inflows, start=1):
        if cf > 0 and total + cf >= cost:
            return year - 1 + (cost - total) / cf
        total += cf
    return None


def appraise_investments(payload: dict) -> dict:
    """Rank a company's own spending options. This compares projects; it does not pick securities."""
    rate = payload.get("discount_rate")
    options = payload.get("options") or []
    cash, reserve = payload.get("cash"), payload.get("reserve", 0.0)
    if not isinstance(rate, (int, float)) or not -0.5 < rate < 1:
        raise InputError("discount_rate is required, as a decimal such as 0.12")
    if not options:
        raise InputError("at least one option is required")
    out = []
    for i, o in enumerate(options, start=1):
        cost, inflows = o.get("initial_cost"), o.get("cash_flows")
        if not isinstance(cost, (int, float)) or cost <= 0 or not isinstance(inflows, list) or not inflows:
            raise InputError(f"option {i}: initial_cost above zero and a list of yearly cash_flows are required")
        if not all(isinstance(c, (int, float)) and not isinstance(c, bool) for c in inflows):
            raise InputError(f"option {i}: cash_flows must be numbers")
        flows = [-cost] + list(inflows)
        npv, irr = _npv(rate, flows), _irr(flows)
        entry = {"name": o.get("name") or f"Option {i}", "initial_cost": cost, "npv": round(npv, 2),
                 "irr": None if irr is None else round(irr, 4),
                 "payback_years": None if _payback(cost, inflows) is None else round(_payback(cost, inflows), 2),
                 "profitability_index": round((npv + cost) / cost, 3),
                 "npv_if_cash_flows_20pct_lower": round(_npv(rate, [-cost] + [0.8 * c for c in inflows]), 2)}
        if isinstance(cash, (int, float)):
            entry["cash_after"] = round(cash - cost, 2)
            entry["keeps_reserve"] = cash - cost >= reserve
        entry["verdict"] = ("Does not keep the cash reserve" if entry.get("keeps_reserve") is False
                            else "Rejects: negative NPV" if npv <= 0
                            else "Fragile: NPV turns negative if cash flows are 20% lower" if entry["npv_if_cash_flows_20pct_lower"] <= 0
                            else "Worth evaluating further")
        out.append(entry)
    out.sort(key=lambda e: (e["verdict"] != "Worth evaluating further", -e["npv"]))
    return {"mode": "investment", "discount_rate": rate, "options": out,
            "cash_check": "applied" if isinstance(cash, (int, float)) else "not applied: cash was not provided",
            "note": "This ranks the company's own project options on the cash flows supplied. "
                    "It is decision support, not a recommendation to buy any security."}
