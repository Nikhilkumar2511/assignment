"""Play the game against simulated players to measure win rate and game length.

Each simulated player thinks of one character and answers from the seed data,
making a random mistake on a share of questions (--noise).

Caveat: the simulated players answer from the same data the engine uses, so these
numbers are an upper bound. Real players disagree with the data more often.

    python -m scripts.simulate --noise 0.1 --rounds 2
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import engine  # noqa: E402
from app.seed_data import build_kb_from_files  # noqa: E402


def player_answer(p: float, noise: float, rng: np.random.Generator) -> str:
    if 0.3 < p < 0.7:
        return str(rng.choice(["yes", "no", "dont_know", "probably", "probably_not"]))
    truth = "yes" if p >= 0.7 else "no"
    if rng.random() < noise:
        return "no" if truth == "yes" else "yes"
    if rng.random() < 0.1:                      # players sometimes hedge
        return "probably" if truth == "yes" else "probably_not"
    return truth


def play(kb, target_row: int, noise: float, rng: np.random.Generator) -> tuple[bool, int, int]:
    state = engine.advance(kb, engine.new_state(int(rng.integers(1 << 31))))
    target_id = kb.entity_ids[target_row]
    guesses = 0
    while True:
        if state["status"] == "asking":
            col = kb.qidx[state["current_q"]]
            ans = player_answer(kb.P[target_row, col], noise, rng)
            state = engine.apply_answer(kb, state, state["current_q"], ans)
        elif state["status"] == "guessing":
            guesses += 1
            state = engine.apply_guess_response(kb, state, state["pending_guess"] == target_id)
        else:
            return state["status"] == "won", len(state["answers"]), guesses


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--noise", type=float, default=0.1, help="share of answers that are wrong")
    ap.add_argument("--rounds", type=int, default=1, help="games per character")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    kb = build_kb_from_files()
    rng = np.random.default_rng(args.seed)
    wins, qs, first_try, losses = 0, [], 0, []
    for _ in range(args.rounds):
        for row in range(kb.n_entities):
            won, n_q, n_g = play(kb, row, args.noise, rng)
            wins += won
            qs.append(n_q)
            first_try += won and n_g == 1
            if not won:
                losses.append(kb.entity_names[row])
    total = kb.n_entities * args.rounds
    print(f"characters={kb.n_entities} questions={kb.n_questions} noise={args.noise}")
    print(f"win rate        {wins / total:.1%}  ({wins}/{total})")
    print(f"first-guess win {first_try / total:.1%}")
    print(f"questions/game  mean {np.mean(qs):.1f}, median {np.median(qs):.0f}, max {max(qs)}")
    if losses:
        print("lost on:", ", ".join(sorted(set(losses))[:40]))


if __name__ == "__main__":
    main()
