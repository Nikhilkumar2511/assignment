"""Plain-language explanations of a diagnosis.

Default: a template built from the verified result. No data leaves the server.

Optional: a language model rewrites the same facts in friendlier words. It receives only the
computed result, and its answer is rejected if it contains a number that is not in that result.
Turn it on with ?explain=llm and credentials for the Anthropic API on the server.
"""
from __future__ import annotations

import json
import os
import re

from .student import inr

LLM_MODEL = os.environ.get("FINPULSE_LLM_MODEL", "claude-opus-5-5")
SYSTEM_PROMPT = """You explain a financial diagnosis to the person it is about.

You are given a JSON result that a calculation engine has already verified. Write a short
explanation in plain English: what the situation is, why, and what to do first.

Rules:
- Use only figures that appear in the JSON. Do not calculate new figures, estimate, or round
  differently from the JSON. If a figure is missing, say it is missing.
- Do not recommend any share, fund, scheme or other security, and do not promise any return.
- Write 4 to 6 sentences. No headings, no bullet points, no greeting.
- Address the reader as "you". Be direct and kind, never alarming."""


def template_explanation(result: dict) -> str:
    health = result.get("health", {})
    parts = []
    if result.get("mode") == "student":
        s = result["summary"]
        if health.get("score") is None:
            return "There is not enough recorded spending yet to give a diagnosis. Add your spends and try again."
        r, w = result["run_out"], result["warning"]
        parts.append(f"You have spent {inr(s['spent'])} of {inr(s['allowance'])} by day {s['today']}, "
                     f"which leaves {inr(s['balance'])} for {s['days_left']} days.")
        if r["day"]:
            parts.append(f"At your current pace of {inr(result['pace']['per_day'])} a day the money runs out on day {r['day']}.")
        else:
            parts.append(f"At your current pace of {inr(result['pace']['per_day'])} a day the money lasts the month.")
        parts.append(f"To reach month end you can spend {inr(int(r['safe_to_spend_per_day']))} a day.")
        parts.append(f"The chance of running short is {100 * w['probability']:.0f}%, so your status is {health['status']}.")
        flex = [c for c in result.get("categories", []) if not c["fixed"]][:2]
        if flex:
            parts.append("Your largest flexible spending is " + " and ".join(
                f"{c['category']} ({inr(c['amount'])})" for c in flex) + ", so start there.")
    elif result.get("mode") == "business":
        if health.get("score") is None:
            parts.append("There is not enough data for an overall health score.")
        else:
            parts.append(f"Overall financial health is {health['score']:.0f} out of 100, which is {health['status']}.")
        scored = [a for a in result.get("areas", []) if a["score"] is not None]
        if scored:
            parts.append("By area: " + ", ".join(f"{a['area']} {a['score']:.0f}" for a in scored) + ".")
        for finding in result.get("findings", [])[:3]:
            parts.append(f"{finding['priority']}: {finding['title']}. {finding['next_step']}")
    else:
        return ""
    return " ".join(parts)


def _numbers_in(obj, out: set):
    if isinstance(obj, bool) or obj is None:
        return
    if isinstance(obj, (int, float)):
        v = float(obj)
        for candidate in (v, v * 100):                       # shares are often read as percentages
            for digits in (0, 1, 2):
                out.add(round(abs(candidate), digits))
    elif isinstance(obj, dict):
        for value in obj.values():
            _numbers_in(value, out)
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            _numbers_in(value, out)
    elif isinstance(obj, str):
        for token in re.findall(r"\d+(?:,\d+)*(?:\.\d+)?", obj):
            try:
                out.add(round(float(token.replace(",", "")), 2))
            except ValueError:
                pass


def unsupported_numbers(text: str, result: dict) -> list:
    """Numbers in `text` that do not appear in `result`. Small counts (up to 12) are allowed."""
    allowed: set = set()
    _numbers_in(result, allowed)
    bad = []
    for token in re.findall(r"\d+(?:,\d+)*(?:\.\d+)?", text):
        value = float(token.replace(",", ""))
        if value <= 12 and value == int(value):
            continue
        if not any(abs(value - a) <= max(0.005 * a, 0.011) for a in allowed):
            bad.append(token)
    return bad


def llm_explanation(result: dict):
    """Returns (text, note). Falls back to the template whenever the model answer cannot be trusted."""
    fallback = template_explanation(result)
    try:
        import anthropic
    except ImportError:
        return fallback, "template: the anthropic package is not installed"
    client = anthropic.Anthropic()
    try:
        response = client.beta.messages.create(
            model=LLM_MODEL,
            max_tokens=8000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",                      # if the model declines, the API retries on a fallback model
            output_config={"effort": "low"},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": json.dumps(result, indent=1, default=str)}],
        )
    except anthropic.AuthenticationError:
        return fallback, "template: no valid Anthropic credentials on the server"
    except anthropic.RateLimitError:
        return fallback, "template: the language model is rate limited, try again later"
    except anthropic.APIStatusError as error:
        return fallback, f"template: the language model returned an error ({error.status_code})"
    except anthropic.APIConnectionError:
        return fallback, "template: could not reach the language model"
    except Exception as error:                        # missing credentials raise a plain error at call time
        return fallback, f"template: language model unavailable ({type(error).__name__})"
    if response.stop_reason == "refusal":
        return fallback, "template: the language model declined the request"
    text = " ".join(block.text for block in response.content if block.type == "text").strip()
    if not text:
        return fallback, "template: the language model returned no text"
    bad = unsupported_numbers(text, result)
    if bad:
        return fallback, f"template: the language model used figures that are not in the result ({', '.join(bad[:5])})"
    return text, f"language model {response.model}, figures checked against the result"
