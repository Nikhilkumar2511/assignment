#!/usr/bin/env python3
"""Train and evaluate the student early-warning model. Synthetic data only.

Writes model/student_warning_model.json and model/evaluation.md.
Run:  python3 train_model.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from finpulse_engine.warning_model import (FEATURES, MODEL_PATH, WarningModel, auc, build_features,
                                           fit_logistic, metrics, simulate)

TRAIN_SEED, VALID_SEED = 101, 202
TEST_SEEDS = (11, 23, 47)
N_TRAIN, N_TEST = 120_000, 50_000
CHECK_DAYS = range(5, 21)
OUT = Path(__file__).resolve().parent / "model"


def dataset(seed: int, n: int, **sim):
    """One random check day per synthetic student. Students already under the floor are dropped."""
    rng = np.random.default_rng(seed)
    flexible, fixed, label = simulate(rng, n, **sim)
    days = rng.integers(min(CHECK_DAYS), max(CHECK_DAYS) + 1, n)
    xs, ys = [], []
    for day in CHECK_DAYS:
        pick = days == day
        x, live = build_features(flexible[pick], fixed[pick], day, 10_000)
        xs.append(x[live]); ys.append(label[pick][live])
    return np.vstack(xs), np.concatenate(ys)


def at_day(seed: int, day: int, **sim):
    rng = np.random.default_rng(seed)
    flexible, fixed, label = simulate(rng, N_TEST, **sim)
    x, live = build_features(flexible, fixed, day, 10_000)
    return x[live], label[live]


def main():
    lines = ["# Student early-warning model: evaluation", "",
             "Synthetic student-months only. These numbers show how the model behaves on the generator",
             "it was trained on. They are not evidence about real students.", ""]

    x_train, y_train = dataset(TRAIN_SEED, N_TRAIN)
    mean, std, weights, bias = fit_logistic(x_train, y_train)
    spec = {"version": "0.1-synthetic", "features": FEATURES, "mean": mean.tolist(), "std": std.tolist(),
            "weights": weights.tolist(), "bias": float(bias), "threshold": 0.5,
            "trained_on": f"{len(y_train):,} synthetic student-months, seed {TRAIN_SEED}",
            "label": "balance under 5% of the allowance on or before five days from month end"}
    model = WarningModel(spec)

    # choose the alert threshold on separate validation data: best F1 with recall of at least 80%
    x_val, y_val = dataset(VALID_SEED, N_TRAIN)
    p_val = model.predict_proba(x_val)
    best = None
    for t in np.arange(0.20, 0.71, 0.01):
        m = metrics(p_val >= t, y_val)
        if m["recall"] >= 0.80 and (best is None or m["f1"] > best[1]):
            best = (float(t), m["f1"])
    spec["threshold"] = round(best[0], 2)
    model = WarningModel(spec)
    OUT.mkdir(exist_ok=True)
    MODEL_PATH.write_text(json.dumps(spec, indent=2))

    lines += [f"Training rows: {len(y_train):,}. Share that run short: {100 * y_train.mean():.1f}%.",
              f"Alert threshold chosen on validation data: {spec['threshold']:.2f} (best F1 with recall of at least 80%).", "",
              "## Weights (standardised features)", "", "| Feature | Weight |", "|---|---|"]
    lines += [f"| {name} | {w:+.2f} |" for name, w in zip(FEATURES, weights)]
    lines += [f"| bias | {bias:+.2f} |", ""]

    def block(title: str, **sim):
        out = [f"## {title}", "",
               "| Check day | Method | Precision | Recall | F1 | Students flagged | AUC | Seed spread (F1) |",
               "|---|---|---|---|---|---|---|---|"]
        for day in (7, 10, 15):
            rows = {"Trained model": [], "Rule C (pace so far, fixed bills removed)": [], "Rule A (pro-rata share)": []}
            for seed in TEST_SEEDS:
                x, y = at_day(seed, day, **sim)
                p = model.predict_proba(x)
                for name, flag, score in (("Trained model", p >= model.threshold, p),
                                          ("Rule C (pace so far, fixed bills removed)", x[:, 2] > 1, x[:, 2]),
                                          ("Rule A (pro-rata share)", x[:, 0] > x[:, 1], x[:, 0] - x[:, 1])):
                    m = metrics(flag, y); m["auc"] = auc(score, y)
                    rows[name].append([m["precision"], m["recall"], m["f1"], m["flagged"], m["auc"]])
            for name, vals in rows.items():
                a = np.array(vals); m = a.mean(axis=0); spread = a[:, 2].max() - a[:, 2].min()
                out.append(f"| {day} | {name} | {100*m[0]:.1f}% | {100*m[1]:.1f}% | {m[2]:.3f} | {100*m[3]:.1f}% | {m[4]:.3f} | {spread:.3f} |")
        return out + [""]

    lines += block(f"Held-out test, same kind of students ({N_TEST:,} per seed, seeds {TEST_SEEDS})")
    lines += block("Drift test: students spend 25% more and 60% front-load", base_range=(88, 338), front_share=0.60)
    lines += block("Drift test: thriftier students, fewer large one-off spends", base_range=(50, 200), big_prob=0.02)

    # calibration on held-out data, all check days
    x_cal, y_cal = dataset(TEST_SEEDS[0], N_TRAIN)
    p_cal = model.predict_proba(x_cal)
    lines += ["## Calibration (held-out, all check days)", "",
              "| Predicted probability | Students | Share that actually ran short |", "|---|---|---|"]
    for lo in np.arange(0, 1.0, 0.2):
        pick = (p_cal >= lo) & (p_cal < lo + 0.2 + (1e-9 if lo > 0.79 else 0))
        if pick.sum():
            lines.append(f"| {lo:.1f} to {lo + 0.2:.1f} | {int(pick.sum()):,} | {100 * y_cal[pick].mean():.1f}% |")
    brier = float(np.mean((p_cal - y_cal) ** 2))
    lines += ["", f"Brier score: {brier:.4f} (0 is perfect; always guessing the base rate scores {y_cal.mean() * (1 - y_cal.mean()):.4f}).", ""]

    # scale check: a 20,000 allowance with doubled spending must give the same probabilities
    rng = np.random.default_rng(5)
    flexible, fixed, _ = simulate(rng, 2_000)
    a, _ = build_features(flexible, fixed, 10, 10_000)
    b, _ = build_features(flexible * 2, fixed * 2, 10, 20_000)
    gap = float(np.abs(model.predict_proba(a) - model.predict_proba(b)).max())
    lines += ["## Scale check", "", f"Doubling the allowance and every spend changes the probability by at most {gap:.2e}.", ""]
    assert gap < 1e-9

    (OUT / "evaluation.md").write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
