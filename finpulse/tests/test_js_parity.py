"""The website runs a JavaScript port of the engines. These tests fail if the two versions disagree.

Needs Node.js. Skipped when it is not installed. Run:  python3 -m pytest -q tests/test_js_parity.py
"""
import json
import random
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from finpulse_engine.business import appraise_investments, diagnose_business  # noqa: E402
from finpulse_engine.explain import template_explanation  # noqa: E402
from finpulse_engine.student import InputError, diagnose_student, savings_scenarios  # noqa: E402

ENGINE = ROOT / "site" / "finpulse-engine.js"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")

RUNNER = """
const E = require(process.argv[1]);
const cases = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const fn = {student: E.diagnoseStudent, business: E.diagnoseBusiness, invest: E.appraiseInvestments,
            savings: p => E.savingsScenarios(p.monthly, p.months)};
console.log(JSON.stringify(cases.map(c => {
  try { const r = fn[c.kind](c.payload); return {ok: r, text: E.explain(r)}; }
  catch (e) { if (e instanceof E.InputError) return {error: e.message}; throw e; }
})));
"""


def run_js(cases):
    out = subprocess.run(["node", "-e", RUNNER, str(ENGINE)], input=json.dumps(cases), capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def run_py(case):
    fn = {"student": diagnose_student, "business": diagnose_business, "invest": appraise_investments,
          "savings": lambda p: savings_scenarios(p["monthly"], p["months"])}[case["kind"]]
    try:
        result = fn(json.loads(json.dumps(case["payload"])))
    except InputError as error:
        return {"error": str(error)}
    return {"ok": json.loads(json.dumps(result)), "text": template_explanation(result)}


def differences(a, b, path=""):
    """Every place two JSON values differ. Numbers may differ by floating-point noise only."""
    if isinstance(a, bool) or isinstance(b, bool) or a is None or b is None or isinstance(a, str) or isinstance(b, str):
        return [] if a == b else [f"{path}: {a!r} != {b!r}"]
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return [] if abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b)) else [f"{path}: {a!r} != {b!r}"]
    if isinstance(a, dict) and isinstance(b, dict):
        out = [f"{path}: keys {sorted(set(a) ^ set(b))}"] if set(a) != set(b) else []
        return out + [d for k in a if k in b for d in differences(a[k], b[k], f"{path}.{k}")]
    if isinstance(a, list) and isinstance(b, list):
        out = [f"{path}: length {len(a)} != {len(b)}"] if len(a) != len(b) else []
        return out + [d for i, (x, y) in enumerate(zip(a, b)) for d in differences(x, y, f"{path}[{i}]")]
    return [f"{path}: {a!r} != {b!r}"]


def sample(name):
    return json.loads((ROOT / "samples" / f"{name}_sample.json").read_text())


def random_cases(seed=7, n=400):
    rng = random.Random(seed)
    cats = [("Food beyond the mess", False), ("Outings", False), ("Shopping", False), ("Travel", True), ("Phone", True),
            ("Study material", True), ("Other", False), ("", False), ("Gifts", False), ("Health", False)]
    fields = ["cogs", "operating_expenses", "depreciation", "interest", "tax", "cash", "receivables", "inventory",
              "payables", "short_term_debt", "long_term_debt", "equity", "total_costs", "net_profit", "other_current_assets"]
    cases = []
    for _ in range(n):
        month_days = rng.choice([28, 30, 31])
        today = rng.randint(1, month_days)
        allowance = rng.choice([3000, 6500, 10000, 12500.5, 25000])
        tx = []
        for _ in range(rng.randint(0, 40)):
            name, fixed = rng.choice(cats)
            amount = rng.choice([round(rng.uniform(5, allowance / 8), 2), rng.randint(10, 900), 0])
            tx.append({"day": rng.randint(1, today), "amount": amount, "category": name, "fixed": fixed and rng.random() < 0.8})
        s = {"allowance": allowance, "today": today, "month_days": month_days, "transactions": tx}
        if rng.random() < 0.5:
            s["savings_goal"] = rng.choice([0, 250, 500, allowance * 0.2])
        if rng.random() < 0.3:
            s["buffer_share"] = rng.choice([0, 0.05, 0.25])
        if rng.random() < 0.3:
            s["upcoming_fixed"] = [{"amount": rng.randint(50, 900), "category": rng.choice(["Phone", "Rent", ""])}]
        if rng.random() < 0.05:                        # a deliberately bad request
            s[rng.choice(["allowance", "today"])] = rng.choice([0, -5, 99])
        cases.append({"kind": "student", "payload": s})

        b = {"revenue": rng.choice([0, 250000, 1200000, 8765432.1]), "period_months": rng.choice([1, 3, 12])}
        for key in rng.sample(fields, rng.randint(0, len(fields))):
            b[key] = round(rng.uniform(0, 3000000), 2) if rng.random() < 0.9 else 0
        if "net_profit" in b and rng.random() < 0.5:
            b["net_profit"] = -b["net_profit"]
        if rng.random() < 0.5:
            b["prior"] = {"revenue": rng.choice([200000, 1000000, 9000000]), "cogs": round(rng.uniform(0, 900000), 2),
                          "operating_expenses": round(rng.uniform(0, 500000), 2)}
        if rng.random() < 0.15:
            b["thresholds"] = {"current_ratio": [1.2, 2.5]}
        if rng.random() < 0.05:
            b["cash"] = -1
        cases.append({"kind": "business", "payload": b})

        opts = [{"name": f"Project {i}", "initial_cost": rng.choice([50000, 400000, 812345.67]),
                 "cash_flows": [round(rng.uniform(-50000, 400000), 2) for _ in range(rng.randint(1, 6))]}
                for i in range(rng.randint(1, 4))]
        inv = {"discount_rate": rng.choice([0.0, 0.08, 0.12, 0.3]), "options": opts}
        if rng.random() < 0.6:
            inv.update({"cash": rng.choice([100000, 900000]), "reserve": rng.choice([0, 300000])})
        cases.append({"kind": "invest", "payload": inv})
        cases.append({"kind": "savings", "payload": {"monthly": rng.choice([0, 250, 500, 1234.5]), "months": rng.randint(1, 120)}})
    return cases


def test_model_weights_and_samples_in_the_js_file_match_the_python_files():
    out = subprocess.run(["node", "-e", "const E=require(process.argv[1]);console.log(JSON.stringify({m:E.MODEL,s:E.SAMPLES}))",
                          str(ENGINE)], capture_output=True, text=True, check=True)
    embedded = json.loads(out.stdout)
    assert embedded["m"] == json.loads((ROOT / "model" / "student_warning_model.json").read_text())
    assert embedded["s"] == {name: sample(name) for name in ("student", "business", "invest")}


def test_samples_give_identical_results_and_identical_explanations():
    cases = [{"kind": kind, "payload": sample(kind)} for kind in ("student", "business", "invest")]
    for case, js in zip(cases, run_js(cases)):
        py = run_py(case)
        assert differences(py["ok"], js["ok"]) == []
        assert py["text"] == js["text"]


def test_1600_random_requests_give_identical_results():
    cases = random_cases()
    js_results = run_js(cases)
    problems, errors = [], 0
    for i, (case, js) in enumerate(zip(cases, js_results)):
        py = run_py(case)
        if "error" in py or "error" in js:
            errors += 1
            if py.get("error") != js.get("error"):
                problems.append(f"case {i} ({case['kind']}): error {py.get('error')!r} != {js.get('error')!r}")
            continue
        diff = differences(py["ok"], js["ok"])
        if diff:
            problems.append(f"case {i} ({case['kind']}): " + "; ".join(diff[:3]))
        elif py["text"] != js["text"]:
            problems.append(f"case {i} ({case['kind']}): explanation differs")
    assert len(cases) == 1600 and errors > 10, "the random set should include bad requests too"
    assert problems == [], f"{len(problems)} of {len(cases)} differ, first: {problems[:5]}"
