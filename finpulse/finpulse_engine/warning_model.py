"""Early-warning model: will a student's balance fall below the floor before the horizon?

A small logistic regression, trained on synthetic student-months only. The weights live in a
JSON file, so the model is easy to read, audit and port to another language.

Definitions (all relative, so any allowance size works):
    floor   = 5% of the monthly allowance
    horizon = five days before the end of the month
    label   = 1 if the balance drops under the floor on or before the horizon
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

FEATURES = [
    "spent_share",            # share of the allowance already spent
    "time_share",             # share of the month already gone
    "need_ratio_tagged",      # pace so far (fixed bills removed) x days to horizon / money above the floor
    "need_ratio_recent",      # last 7 days' pace x days to horizon / money above the floor
    "fixed_share",            # share of the allowance spent on fixed bills
    "largest_spend_share",    # largest single day of flexible spending / allowance
]
FLOOR_SHARE = 0.05
HORIZON_GAP = 5
MODEL_PATH = Path(__file__).resolve().parent.parent / "model" / "student_warning_model.json"


def floor_of(allowance: float) -> float:
    return FLOOR_SHARE * allowance


def horizon_of(month_days: int) -> int:
    return month_days - HORIZON_GAP


def build_features(flexible: np.ndarray, fixed: np.ndarray, day: int, allowance: float, month_days: int = 30):
    """Features after `day` has ended. Inputs are (students, month_days) arrays of daily spending.

    Returns (features, live). `live` is False where the balance is already under the floor,
    because no warning is possible there.
    """
    flexible = np.atleast_2d(np.asarray(flexible, dtype=float))
    fixed = np.atleast_2d(np.asarray(fixed, dtype=float))
    spent_flex = flexible[:, :day].sum(axis=1)
    spent_fixed = fixed[:, :day].sum(axis=1)
    balance = allowance - spent_flex - spent_fixed
    room = balance - floor_of(allowance)
    togo = max(horizon_of(month_days) - day, 0)
    window = min(7, day)
    recent = (flexible[:, day - window:day] + fixed[:, day - window:day]).sum(axis=1) / window
    safe_room = np.maximum(room, 1e-9 * allowance + 1e-9)
    need_tagged = np.clip(spent_flex / day * togo / safe_room, 0, 5)
    need_recent = np.clip(recent * togo / safe_room, 0, 5)
    x = np.column_stack([
        (spent_flex + spent_fixed) / allowance,
        np.full(len(balance), day / month_days),
        need_tagged,
        need_recent,
        spent_fixed / allowance,
        flexible[:, :day].max(axis=1) / allowance,
    ])
    return x, room >= 0


def simulate(rng, n: int, allowance: float = 10_000, month_days: int = 30,
             base_range=(70, 270), front_share: float = 0.40, big_prob: float = 0.04):
    """Synthetic student-months. Returns (flexible, fixed, label)."""
    scale = allowance / 10_000
    base = rng.uniform(*base_range, n) * scale
    front = rng.random(n) < front_share              # spend faster in the first 10 days after money arrives
    flexible = np.zeros((n, month_days))
    for d in range(month_days):
        weekend = 1.5 if d % 7 in (5, 6) else 1.0
        early = np.where(front & (d < 10), 1.6, 1.0)
        big = (rng.random(n) < big_prob) * rng.uniform(800, 2500, n) * scale   # trip, shopping, birthday
        flexible[:, d] = base * weekend * early * rng.lognormal(-0.125, 0.5, n) + big
    fixed = np.zeros((n, month_days))
    fixed[np.arange(n), rng.integers(0, 5, n)] = rng.uniform(1200, 2600, n) * scale   # one bill in the first five days
    balance = allowance - (flexible + fixed).cumsum(axis=1)
    label = (balance[:, :horizon_of(month_days)] < floor_of(allowance)).any(axis=1)
    return flexible, fixed, label


def fit_logistic(x: np.ndarray, y: np.ndarray, l2: float = 1.0, steps: int = 25):
    """L2-regularised logistic regression by Newton's method. Returns (mean, std, weights, bias)."""
    mean, std = x.mean(axis=0), x.std(axis=0) + 1e-12
    z = np.column_stack([(x - mean) / std, np.ones(len(x))])
    w = np.zeros(z.shape[1])
    penalty = np.eye(z.shape[1]) * l2
    penalty[-1, -1] = 0.0                               # do not shrink the bias
    for _ in range(steps):
        p = 1 / (1 + np.exp(-np.clip(z @ w, -30, 30)))
        grad = z.T @ (p - y) + penalty @ w
        hess = (z * (p * (1 - p))[:, None]).T @ z + penalty
        step = np.linalg.solve(hess, grad)
        w -= step
        if np.abs(step).max() < 1e-8:
            break
    return mean, std, w[:-1], w[-1]


class WarningModel:
    def __init__(self, spec: dict):
        self.spec = spec
        self.mean = np.array(spec["mean"])
        self.std = np.array(spec["std"])
        self.weights = np.array(spec["weights"])
        self.bias = float(spec["bias"])
        self.threshold = float(spec["threshold"])
        self.version = spec.get("version", "unknown")

    @classmethod
    def load(cls, path: Path = MODEL_PATH) -> "WarningModel":
        return cls(json.loads(Path(path).read_text()))

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        z = (np.atleast_2d(x) - self.mean) / self.std
        return 1 / (1 + np.exp(-np.clip(z @ self.weights + self.bias, -30, 30)))


def metrics(flag: np.ndarray, label: np.ndarray) -> dict:
    tp = int((flag & label).sum()); fp = int((flag & ~label).sum()); fn = int((~flag & label).sum())
    precision = tp / max(tp + fp, 1); recall = tp / max(tp + fn, 1)
    return {"precision": precision, "recall": recall,
            "f1": 2 * precision * recall / max(precision + recall, 1e-12), "flagged": float(flag.mean())}


def auc(score: np.ndarray, label: np.ndarray) -> float:
    order = np.argsort(score)
    ranks = np.empty(len(score)); ranks[order] = np.arange(1, len(score) + 1)
    pos = label.sum(); neg = len(label) - pos
    return float((ranks[label].sum() - pos * (pos + 1) / 2) / max(pos * neg, 1))
