"""Bayesian guessing engine. Pure NumPy: it knows nothing about the database or HTTP.

The knowledge base is a matrix P where P[e, q] is the probability that a player
thinking of character e answers "yes" to question q.

After each answer the engine multiplies every character's score by how likely that
answer is for that character (a Bayes update). The next question is the one with the
highest expected information gain: the one that, on average, shrinks the uncertainty
over characters the most.

A small noise term keeps every likelihood above zero, so one wrong answer lowers the
right character's score instead of removing it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# Answer -> how strongly it means "yes". None means the answer carries no information.
ANSWER_VALUES: dict[str, float | None] = {
    "yes": 1.0,
    "probably": 0.75,
    "dont_know": None,
    "probably_not": 0.25,
    "no": 0.0,
}

NOISE = 0.12            # share of answers we assume are random mistakes
TOP_K = 300             # question scoring only looks at the K most likely characters
GUESS_CONFIDENCE = 0.85 # guess as soon as one character reaches this probability
MIN_GAP_BETWEEN_GUESSES = 3   # questions to ask after a wrong guess before guessing again
FORCED_GUESS_AT = 20    # guess at question 20 even if unsure, then every 10 questions
FORCED_GUESS_EVERY = 10
MAX_GUESSES = 3         # after this many wrong guesses the game is lost
MIN_USEFUL_GAIN = 0.005 # bits; below this the remaining questions are not worth asking


@dataclass
class KnowledgeBase:
    entity_ids: list[int]
    entity_names: list[str]
    entity_descriptions: list[str]
    question_ids: list[int]
    question_texts: list[str]
    P: np.ndarray                 # shape (N, M), values in (0, 1)
    log_prior: np.ndarray         # shape (N,)
    version: int = 0
    eidx: dict[int, int] = field(init=False)
    qidx: dict[int, int] = field(init=False)

    def __post_init__(self) -> None:
        self.P = np.clip(np.asarray(self.P, dtype=np.float64), 0.01, 0.99)
        self.log_prior = np.asarray(self.log_prior, dtype=np.float64)
        self.eidx = {e: i for i, e in enumerate(self.entity_ids)}
        self.qidx = {q: j for j, q in enumerate(self.question_ids)}

    @property
    def n_entities(self) -> int:
        return len(self.entity_ids)

    @property
    def n_questions(self) -> int:
        return len(self.question_ids)


def likelihood(p: np.ndarray, value: float) -> np.ndarray:
    """P(answer | character) for an answer of strength `value` (1 = yes, 0 = no)."""
    clean = value * p + (1.0 - value) * (1.0 - p)
    return (1.0 - NOISE) * clean + NOISE * 0.5


def posterior(kb: KnowledgeBase, answers: list[tuple[int, str]], excluded: set[int] | frozenset = frozenset()) -> np.ndarray:
    """Probability of each character given the answers so far. Sums to 1."""
    logp = kb.log_prior.copy()
    for qid, answer in answers:
        value = ANSWER_VALUES.get(answer)
        col = kb.qidx.get(qid)
        if value is None or col is None:
            continue
        logp += np.log(likelihood(kb.P[:, col], value))
    for eid in excluded:
        row = kb.eidx.get(eid)
        if row is not None:
            logp[row] = -np.inf
    if not np.isfinite(logp).any():
        return np.zeros_like(logp)
    logp -= logp[np.isfinite(logp)].max()
    probs = np.exp(logp)
    return probs / probs.sum()


def _entropy(p: np.ndarray, axis: int = 0) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        terms = np.where(p > 0, p * np.log2(p), 0.0)
    return -terms.sum(axis=axis)


def question_gains(kb: KnowledgeBase, post: np.ndarray, asked: set[int]) -> tuple[np.ndarray, np.ndarray]:
    """Expected information gain (bits) of every unasked question.

    Returns (question_ids, gains). Only the TOP_K most likely characters are scored,
    which keeps a turn under a few milliseconds even with thousands of characters.
    """
    cols = np.array([j for j, q in enumerate(kb.question_ids) if q not in asked], dtype=int)
    if cols.size == 0 or post.sum() <= 0:
        return np.array([], dtype=int), np.array([])
    k = min(TOP_K, int((post > 0).sum()))
    rows = np.argpartition(-post, k - 1)[:k] if k < post.size else np.flatnonzero(post > 0)
    pi = post[rows] / post[rows].sum()

    Psub = kb.P[np.ix_(rows, cols)]                   # (K, Mq)
    L_yes = (1 - NOISE) * Psub + NOISE * 0.5
    L_no = 1.0 - L_yes
    h_now = _entropy(pi)
    expected_h = np.zeros(cols.size)
    for L in (L_yes, L_no):
        joint = pi[:, None] * L                        # P(character, answer)
        p_answer = joint.sum(axis=0)                   # P(answer) per question
        cond = joint / np.where(p_answer > 0, p_answer, 1.0)
        expected_h += p_answer * _entropy(cond, axis=0)
    gains = h_now - expected_h
    return np.array(kb.question_ids)[cols], gains


def choose_question(kb: KnowledgeBase, post: np.ndarray, asked: set[int], rng: np.random.Generator) -> tuple[int | None, float]:
    """Pick the next question. Adds a little variety: picks at random among the
    questions within 5% of the best gain, so games do not always open the same way."""
    qids, gains = question_gains(kb, post, asked)
    if gains.size == 0:
        return None, 0.0
    best = gains.max()
    near_best = np.flatnonzero(gains >= best * 0.95)
    if near_best.size > 3:
        near_best = near_best[np.argsort(-gains[near_best])[:3]]
    pick = int(rng.choice(near_best))
    return int(qids[pick]), float(gains[pick])


# --------------------------------------------------------------------------- game rules

def new_state(seed: int) -> dict:
    return {"answers": [], "current_q": None, "wrong_guesses": [], "pending_guess": None,
            "last_guess_at": None, "status": "asking", "seed": int(seed)}


def _rng(state: dict) -> np.random.Generator:
    # Deterministic per step, so a replayed or undone step shows the same question.
    return np.random.default_rng([state["seed"], len(state["answers"]), len(state["wrong_guesses"])])


def advance(kb: KnowledgeBase, state: dict) -> dict:
    """Decide what happens next: ask a question, make a guess, or give up."""
    answers = [(q, a) for q, a in state["answers"]]
    excluded = set(state["wrong_guesses"])
    post = posterior(kb, answers, excluded)
    n_asked = len(answers)
    n_wrong = len(state["wrong_guesses"])

    if post.sum() <= 0 or n_wrong >= MAX_GUESSES:
        state.update(status="lost", current_q=None, pending_guess=None)
        return state

    top = int(np.argmax(post))
    top_p = float(post[top])
    asked = {q for q, _ in answers}
    qid, gain = choose_question(kb, post, asked, _rng(state))

    since_last = n_asked - state["last_guess_at"] if state["last_guess_at"] is not None else n_asked
    forced_at = FORCED_GUESS_AT + FORCED_GUESS_EVERY * n_wrong
    should_guess = (
        (top_p >= GUESS_CONFIDENCE and since_last >= MIN_GAP_BETWEEN_GUESSES)
        or n_asked >= forced_at
        or qid is None
        or gain < MIN_USEFUL_GAIN
    )
    if should_guess:
        state.update(status="guessing", current_q=None, pending_guess=kb.entity_ids[top], last_guess_at=n_asked)
    else:
        state.update(status="asking", current_q=qid, pending_guess=None)
    return state


def apply_answer(kb: KnowledgeBase, state: dict, qid: int, answer: str) -> dict:
    if state["status"] != "asking":
        raise ValueError("The game is not waiting for an answer.")
    if answer not in ANSWER_VALUES:
        raise ValueError(f"Unknown answer: {answer}")
    if qid != state["current_q"]:
        raise ValueError("That is not the current question.")
    state["answers"].append([qid, answer])
    return advance(kb, state)


def apply_guess_response(kb: KnowledgeBase, state: dict, correct: bool) -> dict:
    if state["status"] != "guessing":
        raise ValueError("The game has not made a guess.")
    if correct:
        state.update(status="won", current_q=None)
        return state
    state["wrong_guesses"].append(state["pending_guess"])
    state["pending_guess"] = None
    return advance(kb, state)


def undo(kb: KnowledgeBase, state: dict) -> dict:
    """Take back the last answer and show that question again."""
    if state["status"] not in ("asking", "guessing") or not state["answers"]:
        raise ValueError("Nothing to undo.")
    qid, _ = state["answers"].pop()
    if state["last_guess_at"] is not None and state["last_guess_at"] > len(state["answers"]):
        state["last_guess_at"] = None
    state.update(status="asking", current_q=qid, pending_guess=None)
    return state


def confidence(kb: KnowledgeBase, state: dict) -> float:
    post = posterior(kb, [(q, a) for q, a in state["answers"]], set(state["wrong_guesses"]))
    return float(post.max()) if post.size and post.sum() > 0 else 0.0
