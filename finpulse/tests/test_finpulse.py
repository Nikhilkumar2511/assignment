"""Tests for the FINPULSE AI engines and API. Run:  python3 -m pytest -q"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from api import app  # noqa: E402
from finpulse_engine.business import appraise_investments, diagnose_business  # noqa: E402
from finpulse_engine.explain import template_explanation, unsupported_numbers  # noqa: E402
from finpulse_engine.student import InputError, diagnose_student, savings_scenarios  # noqa: E402

client = TestClient(app)
sample = lambda name: json.loads((ROOT / "samples" / f"{name}_sample.json").read_text())
titles = lambda result: " | ".join(f["title"] for f in result["findings"])
priorities = lambda result: [f["priority"] for f in result["findings"]]


# ------------------------------------------------------------------ student module
def test_student_worked_example_matches_the_blueprint_section():
    r = diagnose_student(sample("student"))
    assert r["summary"]["spent"] == 8650 and r["summary"]["balance"] == 1350 and r["summary"]["days_left"] == 12
    assert r["run_out"]["day"] == 21
    assert r["run_out"]["safe_to_spend_per_day"] == 112.5
    assert round(r["run_out"]["shortfall_at_current_pace"]) == 4417
    top = r["categories"][:2]
    assert [c["category"] for c in top] == ["Food beyond the mess", "Outings"]
    assert round(100 * sum(c["amount"] for c in top) / 8650) == 59
    assert r["warning"]["flag"] and r["health"]["status"] == "At risk"
    assert priorities(r)[0] == "Urgent action"


def test_student_budget_adds_up_and_keeps_fixed_bills():
    b = diagnose_student(sample("student"))["next_month_budget"]
    assert b["total"] == 10000 == sum(line["amount"] for line in b["lines"])
    amounts = {line["line"]: line["amount"] for line in b["lines"]}
    assert amounts["Travel"] == 700 and amounts["Phone and subscriptions"] == 650 and amounts["Study material"] == 400
    assert amounts["Emergency buffer"] == 1000 and amounts["Savings"] == 500
    assert all(line["amount"] >= 0 for line in b["lines"])
    food = next(l for l in b["lines"] if l["line"] == "Food beyond the mess")
    outings = next(l for l in b["lines"] if l["line"] == "Outings")
    # essential categories are cut at half the rate of the rest
    assert abs(food["change_vs_current_pace"]) / 5333 < abs(outings["change_vs_current_pace"]) / 3167


def test_student_on_track_is_not_flagged_and_surplus_goes_to_savings():
    tx = [{"day": d, "amount": 180, "category": "Food"} for d in range(1, 16)]
    r = diagnose_student({"allowance": 10000, "today": 15, "transactions": tx})
    assert not r["warning"]["flag"] and r["run_out"]["day"] is None and r["health"]["status"] == "On track"
    savings = next(l for l in r["next_month_budget"]["lines"] if l["line"] == "Savings")
    assert savings["amount"] > 500 and r["next_month_budget"]["total"] == 10000


def test_student_result_does_not_depend_on_the_size_of_the_allowance():
    base = sample("student")
    doubled = json.loads(json.dumps(base))
    doubled["allowance"] *= 2; doubled["savings_goal"] *= 2
    for t in doubled["transactions"]:
        t["amount"] *= 2
    a, b = diagnose_student(base), diagnose_student(doubled)
    assert a["warning"]["probability"] == b["warning"]["probability"]
    assert a["run_out"]["day"] == b["run_out"]["day"]


def test_student_already_broke_and_late_month_use_facts_not_the_model():
    broke = diagnose_student({"allowance": 10000, "today": 12, "transactions": [{"day": 5, "amount": 9800, "category": "Trip"}]})
    assert broke["warning"]["probability"] == 1.0 and broke["warning"]["basis"].startswith("fact")
    late = diagnose_student({"allowance": 10000, "today": 27, "transactions": [{"day": 5, "amount": 6000, "category": "Food"}]})
    assert late["warning"]["probability"] == 0.0 and late["warning"]["basis"].startswith("fact")


def test_student_no_records_gives_insufficient_evidence_and_no_invented_numbers():
    r = diagnose_student({"allowance": 10000, "today": 4, "transactions": []})
    assert r["health"] == {"score": None, "status": "Insufficient evidence"}
    assert "run_out" not in r and "next_month_budget" not in r


@pytest.mark.parametrize("payload, message", [
    ({"allowance": 0, "today": 5}, "allowance"),
    ({"allowance": 10000, "today": 40}, "today"),
    ({"allowance": 10000, "today": 5, "transactions": [{"day": 9, "amount": 100}]}, "future"),
    ({"allowance": 10000, "today": 5, "transactions": [{"day": 2, "amount": -5}]}, "negative"),
])
def test_student_bad_input_is_rejected(payload, message):
    with pytest.raises(InputError, match=message):
        diagnose_student(payload)


def test_savings_scenarios_match_the_blueprint_table():
    values = [s["value"] for s in savings_scenarios(500, 24)["scenarios"]]
    assert [round(v) for v in values] == [12000, 12716, 13487]


# ------------------------------------------------------------------ business module (blueprint page 7 scenarios)
def test_business_profitable_but_cash_poor():
    r = diagnose_business(sample("business"))
    assert "Profitable on paper but short of cash" in titles(r)
    assert r["health"]["status"] == "At risk" and r["health"]["score"] == 44.0 and r["health"]["score_before_cap"] > 44
    margin = next(m for m in r["metrics"] if m["metric"] == "net_margin")
    assert round(margin["value"], 4) == 0.0833          # the blueprint's 8.33%


def test_business_growing_sales_falling_margins():
    r = diagnose_business(sample("business"))
    finding = next(f for f in r["findings"] if "Sales are growing" in f["title"])
    assert finding["evidence"]["revenue_growth"] == 0.2
    assert finding["evidence"]["gross_margin_before"] == 0.44 and finding["evidence"]["gross_margin_now"] == 0.4


def test_business_high_debt_with_stress_case():
    r = diagnose_business({"revenue": 1000000, "cogs": 600000, "operating_expenses": 300000, "depreciation": 0,
                           "interest": 80000, "tax": 0, "short_term_debt": 500000, "long_term_debt": 3000000, "equity": 1000000})
    finding = next(f for f in r["findings"] if "Debt is putting pressure" in f["title"])
    assert finding["priority"] == "Urgent action"
    assert finding["evidence"]["debt_to_equity"] == 3.5 and finding["evidence"]["interest_coverage"] == 1.25
    assert finding["evidence"]["interest_coverage_if_ebit_falls_20pct"] == 1.0


def test_business_incomplete_records_never_invents_values():
    r = diagnose_business({"revenue": 1200000, "total_costs": 1100000})
    names = [m["metric"] for m in r["metrics"]]
    assert names == ["net_margin", "cash_cover_months"] or names == ["net_margin"]
    assert r["health"] == {"score": None, "status": "Insufficient evidence"}
    missing = next(f for f in r["findings"] if f["priority"] == "Insufficient evidence")
    assert "current_ratio" in missing["evidence"]["Liquidity"]
    assert "debt_to_equity" in missing["evidence"]["Solvency"]


def test_business_healthy_company_gets_no_urgent_finding():
    r = diagnose_business({"revenue": 1000000, "cogs": 550000, "operating_expenses": 250000, "depreciation": 20000,
                           "interest": 10000, "tax": 40000, "cash": 3000000, "receivables": 900000, "inventory": 600000,
                           "payables": 500000, "short_term_debt": 100000, "long_term_debt": 400000, "equity": 3000000})
    assert "Urgent action" not in priorities(r) and r["health"]["status"] == "Healthy"
    assert "room to consider investing" in titles(r)


def test_business_loss_is_urgent():
    r = diagnose_business({"revenue": 500000, "total_costs": 650000, "cash": 2000000})
    assert priorities(r)[0] == "Urgent action" and "making a loss" in titles(r)


@pytest.mark.parametrize("payload, message", [
    ({"cogs": 5}, "revenue is required"),
    ({"revenue": 100, "cogs": -1}, "cannot be negative"),
    ({"revenue": 100, "thresholds": {"made_up": [1, 2]}}, "thresholds"),
])
def test_business_bad_input_is_rejected(payload, message):
    with pytest.raises(InputError, match=message):
        diagnose_business(payload)


def test_investment_appraisal_figures_and_reserve_check():
    r = appraise_investments(sample("invest"))
    by = {o["name"]: o for o in r["options"]}
    line = by["Second packing line"]
    hand = -500000 + 180000 / 1.12 + 200000 / 1.12 ** 2 + 220000 / 1.12 ** 3 + 220000 / 1.12 ** 4
    assert abs(line["npv"] - hand) < 0.01 and line["payback_years"] == 2.55
    assert abs(sum(cf / (1 + line["irr"]) ** t for t, cf in enumerate([-500000, 180000, 200000, 220000, 220000]))) < 500
    assert by["Warehouse extension"]["keeps_reserve"] is False
    assert by["New delivery van"]["verdict"].startswith("Rejects")
    assert "not a recommendation to buy any security" in r["note"]


# ------------------------------------------------------------------ explanations
def test_template_explanation_uses_only_figures_from_the_result():
    for name, fn in (("student", diagnose_student), ("business", diagnose_business)):
        result = fn(sample(name))
        assert unsupported_numbers(template_explanation(result), result) == []


def test_number_check_catches_an_invented_figure():
    result = diagnose_student(sample("student"))
    assert unsupported_numbers("You can safely spend 345 a day and save 2,750.", result) == ["345", "2,750"]
    # known limit: the check proves a figure exists in the result, not that it is used for the right thing
    assert unsupported_numbers("You can safely spend 300 a day.", result) == []


# ------------------------------------------------------------------ API
def test_api_health_and_samples():
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["stores_data"] is False
    assert client.get("/api/samples/student").json()["allowance"] == 10000
    assert client.get("/").status_code == 200


def test_api_student_and_business_round_trip():
    s = client.post("/api/student/diagnose", json=sample("student"))
    assert s.status_code == 200 and s.json()["run_out"]["day"] == 21 and s.json()["explanation_source"] == "template"
    b = client.post("/api/business/diagnose?explain=none", json=sample("business"))
    assert b.status_code == 200 and "explanation" not in b.json() and b.json()["health"]["status"] == "At risk"
    i = client.post("/api/business/invest", json=sample("invest"))
    assert i.status_code == 200 and len(i.json()["options"]) == 3
    v = client.post("/api/student/savings", json={"monthly": 500, "months": 24})
    assert v.status_code == 200 and v.json()["paid_in"] == 12000


def test_api_rejects_bad_requests_with_a_readable_message():
    r = client.post("/api/student/diagnose", json={"allowance": 10000, "today": 5,
                                                   "transactions": [{"day": 9, "amount": 100}]})
    assert r.status_code == 422 and "future" in r.json()["detail"]
    assert client.post("/api/business/diagnose", json={"revenue": 100, "made_up_field": 1}).status_code == 422


def test_api_llm_explanation_falls_back_to_template_without_credentials(monkeypatch):
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    r = client.post("/api/student/diagnose?explain=llm", json=sample("student")).json()
    assert r["explanation_source"].startswith("template") and "runs out on day 21" in r["explanation"]
