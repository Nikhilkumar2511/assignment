"""Student money module: diagnosis, early warning and next-month budget.

Every figure is computed here with plain arithmetic. The warning probability comes from the
trained model in warning_model.py. Nothing is estimated when data is missing.
"""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

from .warning_model import WarningModel, build_features, floor_of, horizon_of

ESSENTIAL_WORDS = ("food", "mess", "grocer", "meal", "travel", "transport", "bus", "study", "book",
                   "health", "medic", "rent", "phone", "recharge", "data", "fee")
_MODEL = None


def _model() -> WarningModel:
    global _MODEL
    if _MODEL is None:
        _MODEL = WarningModel.load()
    return _MODEL


class InputError(ValueError):
    """Raised when the request cannot be analysed. The message is safe to show to the user."""


def _is_essential(category: str) -> bool:
    name = category.lower()
    return any(word in name for word in ESSENTIAL_WORDS)


def _round50(x: float) -> int:
    return int(round(x / 50.0)) * 50


def diagnose_student(payload: dict) -> dict:
    allowance = payload.get("allowance")
    month_days = int(payload.get("month_days", 30))
    today = payload.get("today")
    if not isinstance(allowance, (int, float)) or allowance <= 0:
        raise InputError("allowance must be a number above zero")
    if not 28 <= month_days <= 31:
        raise InputError("month_days must be between 28 and 31")
    if not isinstance(today, int) or not 1 <= today <= month_days:
        raise InputError(f"today must be a whole day between 1 and {month_days}")

    flexible = np.zeros((1, month_days)); fixed = np.zeros((1, month_days))
    by_cat = defaultdict(lambda: {"amount": 0.0, "fixed_amount": 0.0})
    quality = []
    for i, t in enumerate(payload.get("transactions") or [], start=1):
        day, amount = t.get("day"), t.get("amount")
        if not isinstance(day, int) or not isinstance(amount, (int, float)):
            raise InputError(f"transaction {i}: day and amount are required numbers")
        if amount < 0:
            raise InputError(f"transaction {i}: amount cannot be negative")
        if not 1 <= day <= today:
            raise InputError(f"transaction {i}: day {day} is outside 1 to {today} (no future spending)")
        category = (t.get("category") or "").strip() or "Uncategorised"
        is_fixed = bool(t.get("fixed", False))
        (fixed if is_fixed else flexible)[0, day - 1] += amount
        by_cat[category]["amount"] += amount
        if is_fixed:
            by_cat[category]["fixed_amount"] += amount

    upcoming = 0.0
    for i, u in enumerate(payload.get("upcoming_fixed") or [], start=1):
        if not isinstance(u.get("amount"), (int, float)) or u["amount"] < 0:
            raise InputError(f"upcoming_fixed {i}: amount must be zero or more")
        upcoming += u["amount"]
        cat = (u.get("category") or "").strip() or "Upcoming bills"
        by_cat[cat]["upcoming"] = by_cat[cat].get("upcoming", 0.0) + u["amount"]

    spent = float(flexible.sum() + fixed.sum())
    spent_fixed = float(fixed.sum())
    balance = allowance - spent
    days_left = month_days - today
    floor = floor_of(allowance)
    result = {
        "mode": "student",
        "summary": {"allowance": allowance, "today": today, "month_days": month_days, "spent": round(spent, 2),
                    "balance": round(balance, 2), "days_left": days_left,
                    "spent_share": round(spent / allowance, 4), "time_share": round(today / month_days, 4)},
        "data_quality": quality, "findings": [],
    }

    if spent == 0:
        result["health"] = {"score": None, "status": "Insufficient evidence"}
        result["findings"].append({
            "priority": "Insufficient evidence", "title": "No spending recorded yet",
            "evidence": {"transactions": 0},
            "rationale": "A diagnosis needs at least a few days of recorded spending.",
            "next_step": "Record each spend with a day, an amount and a category, then run the diagnosis again."})
        return result
    if balance < 0:
        quality.append("Recorded spending is higher than the allowance. Check for a duplicate or a mistyped amount.")

    pace = spent / today
    pace_flex = float(flexible.sum()) / today
    window = min(7, today)
    pace_recent = float((flexible[0, today - window:today] + fixed[0, today - window:today]).sum()) / window
    lasts = pace == 0 or balance / pace >= days_left
    run_out_day = None if lasts or balance <= 0 else today + int(balance // pace) + 1
    if balance <= 0:
        run_out_day = today
    available = balance - upcoming
    safe = available / days_left if days_left > 0 else available
    shortfall = max(0.0, pace * days_left + upcoming - balance)
    result["pace"] = {"per_day": round(pace, 2), "per_day_excluding_fixed": round(pace_flex, 2),
                      "last_7_days_per_day": round(pace_recent, 2)}
    result["run_out"] = {"day": run_out_day, "safe_to_spend_per_day": round(max(safe, 0.0), 2),
                         "shortfall_at_current_pace": round(shortfall, 2), "upcoming_fixed": round(upcoming, 2)}

    # ---- early warning
    model = _model()
    horizon = horizon_of(month_days)
    if balance < floor:
        prob, basis = 1.0, "fact: the balance is already under 5% of the allowance"
    elif today >= horizon:
        prob, basis = 0.0, "fact: the warning window has passed with the balance above the floor"
    else:
        x, _ = build_features(flexible, fixed, today, allowance, month_days)
        prob, basis = float(model.predict_proba(x)[0]), f"model {model.version}"
    rule_c = balance >= floor and today < horizon and pace_flex * (horizon - today) > balance - floor
    flag = prob >= model.threshold
    result["warning"] = {"probability": round(prob, 3), "flag": bool(flag), "threshold": model.threshold,
                         "simple_rule_flag": bool(rule_c), "basis": basis,
                         "meaning": f"Chance that the balance falls under {floor:,.0f} on or before day {horizon}."}
    score = int(round(100 * (1 - prob)))
    result["health"] = {"score": score, "status": "On track" if score >= 70 else "Watch" if score >= 40 else "At risk"}

    # ---- categories
    cats = []
    for name, v in by_cat.items():
        if v["amount"] == 0:
            continue
        cats.append({"category": name, "amount": round(v["amount"], 2), "share": round(v["amount"] / spent, 4),
                     "fixed": v["fixed_amount"] == v["amount"], "essential": _is_essential(name)})
    cats.sort(key=lambda c: -c["amount"])
    result["categories"] = cats
    flex_cats = [c for c in cats if not c["fixed"]]

    # ---- findings
    f = result["findings"]
    if flag or run_out_day is not None:
        when = f"on day {run_out_day}" if run_out_day else f"before day {horizon}"
        f.append({"priority": "Urgent action", "title": f"Money is on course to run out {when}",
                  "evidence": {"balance": round(balance, 2), "pace_per_day": round(pace, 2), "days_left": days_left,
                               "warning_probability": round(prob, 3)},
                  "rationale": f"At {pace:,.0f} a day the balance of {balance:,.0f} does not cover the {days_left} days left.",
                  "next_step": f"Hold spending to {math.floor(max(safe, 0)):,} a day for the rest of the month."})
    if len(flex_cats) >= 1:
        top = flex_cats[:2]
        total_top = sum(c["amount"] for c in top)
        names = " and ".join(c["category"] for c in top)
        f.append({"priority": "Investigate and improve" if (flag or run_out_day) else "Monitor",
                  "title": f"{names} take {100 * total_top / spent:.0f}% of spending",
                  "evidence": {c["category"]: c["amount"] for c in top},
                  "rationale": "These are the largest flexible categories, so a cut here moves the result most.",
                  "next_step": "Set a weekly limit for each and check it every Sunday."})
    loose = sum(c["amount"] for c in cats if c["category"].lower() in ("uncategorised", "other", "misc", "miscellaneous"))
    if loose / spent > 0.15:
        f.append({"priority": "Investigate and improve", "title": f"{100 * loose / spent:.0f}% of spending has no clear category",
                  "evidence": {"uncategorised_amount": round(loose, 2)},
                  "rationale": "Money you cannot name is money you cannot plan.",
                  "next_step": "Tag each spend when you make it."})
    if not flag and run_out_day is None:
        projected_end = balance - pace * days_left - upcoming
        f.append({"priority": "Monitor", "title": "Spending is on pace to last the month",
                  "evidence": {"projected_month_end_balance": round(projected_end, 2)},
                  "rationale": f"At {pace:,.0f} a day about {max(projected_end, 0):,.0f} remains at month end.",
                  "next_step": "Move part of the expected surplus to savings on the day the next allowance arrives."})

    result["next_month_budget"] = _budget(payload, allowance, month_days, today, cats, by_cat, f)
    return result


def _budget(payload, allowance, month_days, today, cats, by_cat, findings) -> dict:
    """Fixed bills first, then buffer and savings, then flexible categories scaled to fit."""
    fixed_lines = [{"line": c["category"], "amount": c["amount"] + by_cat[c["category"]].get("upcoming", 0.0), "type": "fixed"}
                   for c in cats if c["fixed"]]
    fixed_lines += [{"line": name, "amount": v["upcoming"], "type": "fixed"}
                    for name, v in by_cat.items() if v["amount"] == 0 and v.get("upcoming")]
    fixed_total = sum(l["amount"] for l in fixed_lines)
    savings = float(payload.get("savings_goal", 0.05 * allowance))
    buffer = float(payload.get("buffer_share", 0.10)) * allowance
    if fixed_total + savings + buffer > allowance:
        over = fixed_total + savings + buffer - allowance
        cut_s = min(savings, over); savings -= cut_s; buffer = max(0.0, buffer - (over - cut_s))
        findings.append({"priority": "Investigate and improve", "title": "Fixed bills leave little room for savings",
                         "evidence": {"fixed_bills": round(fixed_total, 2), "allowance": allowance},
                         "rationale": "Fixed bills, the buffer and the savings goal together exceed the allowance.",
                         "next_step": "Review recurring bills and subscriptions first."})
    pool = max(0.0, allowance - fixed_total - savings - buffer)
    flex = [c for c in cats if not c["fixed"]]
    projected = {c["category"]: c["amount"] / today * month_days for c in flex}
    need = sum(projected.values()) - pool
    alloc = dict(projected)
    if need > 0:
        weight = {c["category"]: (0.5 if c["essential"] else 1.0) * projected[c["category"]] for c in flex}
        remaining, active = need, set(alloc)
        while remaining > 1e-6 and active:                   # share the cut, never below zero
            total_w = sum(weight[k] for k in active)
            spill = 0.0
            for k in list(active):
                cut = remaining * weight[k] / total_w
                if cut >= alloc[k]:
                    spill += cut - alloc[k]; alloc[k] = 0.0; active.discard(k)
                else:
                    alloc[k] -= cut
            remaining = spill
    lines = [{"line": l["line"], "amount": _round50(l["amount"]), "type": "fixed"} for l in fixed_lines]
    lines += [{"line": k, "amount": _round50(v), "type": "flexible",
               "change_vs_current_pace": _round50(v - projected[k])} for k, v in alloc.items()]
    lines.append({"line": "Emergency buffer", "amount": _round50(buffer), "type": "buffer"})
    extra = 0.0 if need > 0 else -need                        # unspent room goes to savings
    lines.append({"line": "Savings", "amount": _round50(savings + extra), "type": "savings"})
    drift = allowance - sum(l["amount"] for l in lines)       # absorb rounding in one line
    target = next((l for l in sorted(lines, key=lambda l: -l["amount"]) if l["type"] == "flexible"), lines[-1])
    target["amount"] += drift
    flexible_total = sum(l["amount"] for l in lines if l["type"] == "flexible")
    return {"lines": lines, "total": sum(l["amount"] for l in lines),
            "flexible_per_day": round(flexible_total / month_days, 2),
            "flexible_per_week": round(flexible_total / month_days * 7, 2),
            "method": "Fixed bills are kept. A buffer and savings are set aside. Flexible categories start from "
                      "this month's pace and are cut to fit, with essential categories cut at half the rate of the rest."}


def savings_scenarios(monthly: float, months: int, annual_rates=(0.0, 0.06, 0.12)) -> dict:
    """Hypothetical future values of a monthly saving. Rates are illustrations, never forecasts."""
    if monthly < 0 or months <= 0:
        raise InputError("monthly saving must be zero or more and months must be above zero")
    out = []
    for annual in annual_rates:
        r = annual / 12
        value = monthly * months if r == 0 else monthly * ((1 + r) ** months - 1) / r
        out.append({"annual_rate": annual, "value": round(value, 2)})
    return {"paid_in": round(monthly * months, 2), "scenarios": out,
            "note": "Hypothetical rates with end-of-month deposits. Not a forecast and not investment advice."}


__all__ = ["diagnose_student", "savings_scenarios", "InputError", "math"]
