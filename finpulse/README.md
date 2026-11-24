# FINPULSE AI: diagnosis service

A small service your website calls. It returns a financial health diagnosis for a business,
and a budget diagnosis for a student. Everything here runs on synthetic sample data.

## What is inside

| Part | File | What it is |
|---|---|---|
| Student engine | `finpulse_engine/student.py` | Run-out date, safe daily spend, category diagnosis, next-month budget |
| Early-warning model | `finpulse_engine/warning_model.py`, `model/student_warning_model.json` | A trained model: will this student run short before month end? |
| Business engine | `finpulse_engine/business.py` | 13 ratios, a health score, prioritised findings, investment appraisal |
| Explanations | `finpulse_engine/explain.py` | Plain-language summary of a result |
| API | `api.py` | The endpoints your website calls |
| Demo page | `web/demo.html` | A working page that uses the API |
| Tests | `tests/test_finpulse.py` | 27 tests |

## Which part is "AI"

Be precise about this in your report. The service has three layers.

1. **Rules and formulas.** All ratios, dates, budgets and findings are fixed calculations. They
   are predictable and you can point to the rule behind every output. The business diagnosis
   is entirely this layer, because no labelled data on business failures was available to
   train on.
2. **A trained model.** The student early warning is a logistic regression with six inputs,
   trained on 113,813 synthetic student-months. Its weights are in a readable JSON file.
3. **An optional language model.** It rewrites a verified result in friendlier words. It is
   off by default and never produces a figure.

## Run it

```bash
pip install -r requirements.txt
python3 train_model.py            # optional: retrains the model and rewrites model/evaluation.md
python3 -m pytest -q              # 27 tests
uvicorn api:app --port 8000
```

Open `http://localhost:8000/` for the demo and `http://localhost:8000/docs` for the API reference.

## Endpoints

| Method and path | Purpose |
|---|---|
| `POST /api/student/diagnose` | Student diagnosis, warning and next-month budget |
| `POST /api/student/savings` | Hypothetical values of a monthly saving |
| `POST /api/business/diagnose` | Business health score, ratios and findings |
| `POST /api/business/invest` | Rank the company's own project options |
| `GET /api/samples/{student,business,invest}` | Synthetic sample requests |
| `GET /api/health` | Service and model version |

Add `?explain=template` (default), `?explain=llm` or `?explain=none` to the two diagnose endpoints.

## Call it from your website

```js
const response = await fetch("https://YOUR-API-HOST/api/student/diagnose", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    allowance: 10000,
    today: 18,
    month_days: 30,
    savings_goal: 500,
    transactions: [
      { day: 1, amount: 700, category: "Travel", fixed: true },
      { day: 1, amount: 180, category: "Food beyond the mess" }
    ]
  })
});
const result = await response.json();   // result.health, result.run_out, result.findings, result.next_month_budget
```

A bad request returns status 422 with a readable `detail` message. Before you go live, set
`FINPULSE_ALLOWED_ORIGINS` to your website's address so other sites cannot call the service
from a browser. The default allows any origin, which suits a local demo only.

## How the model performed

Held-out synthetic students, checked on day 10, mean of three seeds. Full tables, drift tests
and calibration are in `model/evaluation.md`.

| Method | Precision | Recall | F1 | Students flagged |
|---|---|---|---|---|
| Trained model | 68.8% | 80.4% | 0.741 | 42.4% |
| Simple rule (pace so far, fixed bills removed) | 67.7% | 77.6% | 0.724 | 41.6% |
| Naive rule (spent more than the pro-rata share) | 42.6% | 99.0% | 0.595 | 84.3% |

The trained model beats the simple rule by a small margin, about 3 points of recall at similar
precision. The API returns both, so you can show when they disagree. On a thriftier group of
students, precision fell to about 31% for the model and the simple rule alike. That is the
drift risk to monitor.

## Limits you must state

- **Synthetic data only.** The model learned a simulator, so its accuracy on real students is
  unknown. Collect real, consented, anonymised months before claiming it works.
- **Business thresholds are general rules of thumb.** They differ by industry. Pass
  `thresholds` in the request to change them.
- **A critical weakness caps the score.** Any "Urgent action" finding caps the business score
  at 44, so a strong average cannot hide a cash shortage. The uncapped score is also returned.
- **No investment advice.** The service compares a company's own projects and shows savings
  scenarios at hypothetical rates. It never names a security and never promises a return.
- **Missing inputs are never guessed.** A measure without its inputs is left out and listed
  under "Insufficient evidence". Optional cost lines treated as zero are listed under `assumptions`.

## Privacy

The service stores nothing. Each request is analysed and discarded. A student's spending and a
company's accounts are still sensitive, so use sample data for the project, serve the API over
HTTPS, and get clear consent before any real use.

## The optional language model layer

`?explain=llm` sends the computed result to the Claude API and asks for a short explanation.

- It needs Anthropic credentials on the server, for example the `ANTHROPIC_API_KEY`
  environment variable. Never put a key in website code.
- It uses `claude-opus-5-5` by default. Set `FINPULSE_LLM_MODEL` to change it.
- It turns on the API's server-side fallback, so a declined request is retried on a fallback model.
- Every figure in the answer is checked against the result. If any figure is not found, or the
  call fails for any reason, the service returns the template explanation and says why in
  `explanation_source`.
- The check proves a figure exists in the result. It cannot prove the figure is used for the
  right thing, so a person should still read the wording before a real launch.
- **Not tested against the live API.** No credentials were available where this was built. The
  fallback path without credentials is covered by a test.
- Turning it on sends the diagnosis figures to an outside service. Keep it off for real personal data.

## Putting it online

The service is a standard Python web app. Any host that runs `uvicorn api:app` will do. Your
website and this API can live on different hosts: the website calls the API address with `fetch`.
