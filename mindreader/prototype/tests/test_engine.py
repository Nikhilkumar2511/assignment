import numpy as np
import pytest

from app import engine
from app.seed_data import build_kb_from_files, load_entities, load_questions, parse_entity_line


@pytest.fixture(scope="module")
def kb():
    return build_kb_from_files()


def tiny_kb():
    # 4 characters x 2 questions, uniform prior.
    P = np.array([[0.95, 0.95], [0.95, 0.05], [0.05, 0.95], [0.05, 0.05]])
    return engine.KnowledgeBase([1, 2, 3, 4], list("ABCD"), [""] * 4, [10, 20], ["q1", "q2"],
                                P=P, log_prior=np.zeros(4))


def test_data_files_parse():
    qs = load_questions()
    ents = load_entities(qs)
    assert len(qs) >= 100 and len(ents) >= 240


def test_implications_and_scope():
    qs = load_questions()
    e = parse_entity_line("Test Hero | 50 | x | marvel male human", qs)
    assert e.yes["from_comic"] == 0.95 and e.yes["american"] == 0.95
    assert e.yes["alive"] == 0.5          # real-only question is unknown for fictional characters
    r = parse_entity_line("Test Person | 50 | x | real female dead", qs)
    assert r.yes["alive"] == 0.08 and r.yes["human"] == 0.95
    assert r.yes["from_book"] == 0.5      # fictional-only question is unknown for real people


def test_unknown_tag_rejected():
    with pytest.raises(ValueError):
        parse_entity_line("X | 50 | x | real banana", load_questions())


def test_posterior_update_and_noise_tolerance():
    kb = tiny_kb()
    post = engine.posterior(kb, [(10, "yes"), (20, "yes")])
    assert np.argmax(post) == 0 and post[0] > 0.7
    # One answer against the truth lowers A but does not eliminate it.
    post = engine.posterior(kb, [(10, "no"), (20, "yes")])
    assert post[0] > 0.01


def test_dont_know_changes_nothing():
    kb = tiny_kb()
    np.testing.assert_allclose(engine.posterior(kb, [(10, "dont_know")]), np.full(4, 0.25))


def test_information_gain_prefers_balanced_question():
    P = np.array([[0.95, 0.95], [0.95, 0.05], [0.05, 0.05], [0.05, 0.05]])
    kb = engine.KnowledgeBase([1, 2, 3, 4], list("ABCD"), [""] * 4, [10, 20], ["even split", "1 vs 3"],
                              P=P, log_prior=np.zeros(4))
    qids, gains = engine.question_gains(kb, np.full(4, 0.25), set())
    assert qids[np.argmax(gains)] == 10


def test_game_flow_reaches_guess(kb):
    target = kb.entity_names.index("Spider-Man")
    state = engine.advance(kb, engine.new_state(1))
    for _ in range(60):
        if state["status"] != "asking":
            break
        p = kb.P[target, kb.qidx[state["current_q"]]]
        state = engine.apply_answer(kb, state, state["current_q"], "yes" if p > 0.5 else "no")
    assert state["status"] == "guessing"
    assert state["pending_guess"] == kb.entity_ids[target]


def test_undo_restores_question(kb):
    state = engine.advance(kb, engine.new_state(5))
    q1 = state["current_q"]
    state = engine.apply_answer(kb, state, q1, "yes")
    state = engine.undo(kb, state)
    assert state["current_q"] == q1 and state["answers"] == []


def test_three_wrong_guesses_lose(kb):
    state = engine.advance(kb, engine.new_state(3))
    while state["status"] != "lost":
        if state["status"] == "asking":
            state = engine.apply_answer(kb, state, state["current_q"], "dont_know")
        else:
            state = engine.apply_guess_response(kb, state, False)
    assert len(state["wrong_guesses"]) == engine.MAX_GUESSES


def test_simulated_win_rate(kb):
    """Regression guard: with 5% wrong answers the engine should win at least 90% of games."""
    from scripts.simulate import play
    rng = np.random.default_rng(0)
    rows = rng.choice(kb.n_entities, size=80, replace=False)
    wins = sum(play(kb, int(r), 0.05, rng)[0] for r in rows)
    assert wins / len(rows) >= 0.9
