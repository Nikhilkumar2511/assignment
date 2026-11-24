"""FINPULSE AI service. Your website calls these endpoints and shows the JSON it gets back.

Run locally:   uvicorn api:app --reload --port 8000
Docs page:     http://localhost:8000/docs
Demo page:     http://localhost:8000/

The service is stateless: it stores nothing. Each request is analysed and forgotten.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from finpulse_engine.business import appraise_investments, diagnose_business
from finpulse_engine.explain import llm_explanation, template_explanation
from finpulse_engine.student import InputError, diagnose_student, savings_scenarios
from finpulse_engine.warning_model import WarningModel

ROOT = Path(__file__).resolve().parent
app = FastAPI(title="FINPULSE AI", version="0.1.0",
              description="Financial health diagnosis for businesses and budget diagnosis for students.")
app.add_middleware(CORSMiddleware,
                   allow_origins=[o.strip() for o in os.environ.get("FINPULSE_ALLOWED_ORIGINS", "*").split(",")],
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
Explain = Literal["template", "llm", "none"]


class Transaction(BaseModel):
    day: int = Field(ge=1, le=31, description="Day of the month the money was spent")
    amount: float = Field(ge=0)
    category: Optional[str] = None
    fixed: bool = Field(False, description="True for a recurring bill such as a phone plan")


class UpcomingBill(BaseModel):
    amount: float = Field(ge=0)
    category: Optional[str] = None


class StudentRequest(BaseModel):
    allowance: float = Field(gt=0, description="Money received for the month")
    today: int = Field(ge=1, le=31, description="Day of the month the diagnosis is for")
    month_days: int = Field(30, ge=28, le=31)
    transactions: list[Transaction] = []
    upcoming_fixed: list[UpcomingBill] = []
    savings_goal: Optional[float] = Field(None, ge=0)
    buffer_share: Optional[float] = Field(None, ge=0, le=0.5)


class Financials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revenue: Optional[float] = None
    cogs: Optional[float] = None
    operating_expenses: Optional[float] = None
    depreciation: Optional[float] = None
    interest: Optional[float] = None
    tax: Optional[float] = None
    total_costs: Optional[float] = None
    net_profit: Optional[float] = None
    cash: Optional[float] = None
    receivables: Optional[float] = None
    inventory: Optional[float] = None
    other_current_assets: Optional[float] = None
    payables: Optional[float] = None
    short_term_debt: Optional[float] = None
    other_current_liabilities: Optional[float] = None
    long_term_debt: Optional[float] = None
    equity: Optional[float] = None


class BusinessRequest(Financials):
    revenue: float = Field(ge=0)
    period_months: float = Field(1, gt=0)
    prior: Optional[Financials] = Field(None, description="Same figures for the previous period, for trends")
    thresholds: Optional[dict[str, list[float]]] = None


class Option(BaseModel):
    name: Optional[str] = None
    initial_cost: float = Field(gt=0)
    cash_flows: list[float] = Field(min_length=1, description="Net cash inflow per year")


class InvestRequest(BaseModel):
    discount_rate: float = Field(gt=-0.5, lt=1, description="As a decimal, for example 0.12")
    options: list[Option] = Field(min_length=1)
    cash: Optional[float] = None
    reserve: float = 0.0


class SavingsRequest(BaseModel):
    monthly: float = Field(ge=0)
    months: int = Field(gt=0, le=600)


def _run(fn, payload: dict, explain: str) -> dict:
    try:
        result = fn(payload)
    except InputError as error:
        raise HTTPException(status_code=422, detail=str(error))
    if explain == "llm":
        result["explanation"], result["explanation_source"] = llm_explanation(result)
    elif explain == "template":
        result["explanation"], result["explanation_source"] = template_explanation(result), "template"
    return result


@app.get("/api/health")
def health():
    model = WarningModel.load()
    return {"status": "ok", "service": app.version, "warning_model": model.version, "stores_data": False}


@app.post("/api/student/diagnose")
def student_diagnose(body: StudentRequest, explain: Explain = Query("template")):
    """Run-out date, safe daily spend, early-warning probability, category diagnosis and next-month budget."""
    return _run(diagnose_student, body.model_dump(exclude_none=True), explain)


@app.post("/api/student/savings")
def student_savings(body: SavingsRequest):
    """Hypothetical values of a monthly saving at 0%, 6% and 12% a year. Illustration only."""
    try:
        return savings_scenarios(body.monthly, body.months)
    except InputError as error:
        raise HTTPException(status_code=422, detail=str(error))


@app.post("/api/business/diagnose")
def business_diagnose(body: BusinessRequest, explain: Explain = Query("template")):
    """Health score, ratios by area, and prioritised findings with evidence and next steps."""
    return _run(diagnose_business, body.model_dump(exclude_none=True), explain)


@app.post("/api/business/invest")
def business_invest(body: InvestRequest):
    """Rank the company's own project options on NPV, IRR and payback, with a cash-reserve check."""
    return _run(appraise_investments, body.model_dump(exclude_none=True), "none")


@app.get("/api/samples/{name}")
def sample(name: Literal["student", "business", "invest"]):
    """Synthetic sample requests for the demo page."""
    return json.loads((ROOT / "samples" / f"{name}_sample.json").read_text())


@app.get("/", include_in_schema=False)
def demo():
    return FileResponse(ROOT / "web" / "demo.html")
