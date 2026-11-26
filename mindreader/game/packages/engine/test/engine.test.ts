import { describe, expect, it } from "vitest";
import {
  advance, answer, buildKB, confidence, GameError, newGame, posterior, respondToGuess, RULES, topK, undo,
} from "../src";
import { loadSeed, playGame } from "./helpers";

const tiny = () =>
  buildKB({
    ids: [11, 12, 13, 14],
    prior: [0, 0, 0, 0],
    kind: ["real", "real", "fictional", "fictional"],
    groups: [],
    questions: [
      { id: 1, key: "a", kind: "cells", group: null, values: null, scope: "all", dup: null,
        cells: [[0, 0.95], [1, 0.95], [2, 0.05], [3, 0.05]] },
      { id: 2, key: "b", kind: "cells", group: null, values: null, scope: "all", dup: null,
        cells: [[0, 0.95], [1, 0.05], [2, 0.95], [3, 0.05]] },
      { id: 3, key: "b-again", kind: "cells", group: null, values: null, scope: "all", dup: 7,
        cells: [[0, 0.95], [1, 0.05], [2, 0.95], [3, 0.05]] },
      { id: 4, key: "b-dup", kind: "cells", group: null, values: null, scope: "all", dup: 7,
        cells: [[0, 0.96], [1, 0.04], [2, 0.96], [3, 0.04]] },
    ],
  });

describe("posterior", () => {
  it("moves toward consistent characters and never eliminates anyone", () => {
    const kb = tiny();
    const p = posterior(kb, { answers: [[1, 0], [2, 0]], wrong: [] });
    expect(p.indexOf(Math.max(...p))).toBe(0);
    expect(p[0]).toBeGreaterThan(0.7);
    const contradicted = posterior(kb, { answers: [[1, 4], [2, 0]], wrong: [] });
    expect(contradicted[0]).toBeGreaterThan(0.01); // one wrong answer only lowers the right character
  });

  it("ignores don't know and removes rejected guesses", () => {
    const kb = tiny();
    const p = posterior(kb, { answers: [[1, 2]], wrong: [12] });
    expect(p[1]).toBe(0);
    expect(p[0]).toBeCloseTo(1 / 3, 6);
  });

  it("uses the popularity prior", () => {
    const kb = buildKB({
      ids: [1, 2], prior: [Math.log(9), 0], kind: ["real", "real"], groups: [],
      questions: [{ id: 1, key: "x", kind: "cells", group: null, values: null, scope: "all", dup: null }],
    });
    expect(posterior(kb, { answers: [], wrong: [] })[0]).toBeCloseTo(0.9, 6);
  });
});

describe("group questions", () => {
  it("uses p_match, p_other and 0.5 for unknown, with explicit cells overriding", () => {
    const kb = buildKB({
      ids: [1, 2, 3], prior: [0, 0, 0], kind: ["real", "real", "real"],
      groups: [{ id: 6, key: "country", pMatch: 0.93, pOther: 0.08, values: [[668], [30], []] }],
      questions: [{ id: 9, key: "eq:country:Q668", kind: "group", group: 6, values: [668], scope: "all", dup: null,
        cells: [[1, 0.6]] }],
    });
    const p = posterior(kb, { answers: [[9, 0]], wrong: [] });
    expect(p[0]).toBeGreaterThan(p[2]);
    expect(p[2]).toBeGreaterThan(p[1] * 0.5); // unknown sits between match and the 0.6 override
    expect(p[1]).toBeGreaterThan(0.1);
  });
});

describe("topK", () => {
  it("returns exactly the k largest", () => {
    const post = Float64Array.from([0.1, 0.4, 0.05, 0.3, 0.15, 0]);
    expect([...topK(post, 3)].sort()).toEqual([1, 3, 4]);
    expect([...topK(post, 10)].sort()).toEqual([0, 1, 2, 3, 4]);
  });
});

describe("game rules", () => {
  it("skips near-duplicate questions once one of the cluster is asked", () => {
    const kb = tiny();
    let s = advance(kb, newGame(1));
    const seen = new Set<number>();
    while (s.status === "asking") {
      seen.add(s.current!);
      s = answer(kb, s, s.current!, 2);
    }
    expect(seen.has(3) && seen.has(4)).toBe(false);
  });

  it("rejects stale answers and supports undo", () => {
    const kb = loadSeed();
    const s0 = advance(kb, newGame(5));
    const q1 = s0.current!;
    expect(() => answer(kb, s0, q1 + 100000, 0)).toThrow(GameError);
    const s1 = answer(kb, s0, q1, 0);
    const back = undo(kb, s1);
    expect(back.current).toBe(q1);
    expect(back.answers).toEqual([]);
    expect(() => undo(kb, back)).toThrow(GameError);
  });

  it("guesses at question 20 at the latest, and loses after three wrong guesses or 40 questions", () => {
    const kb = loadSeed();
    let s = advance(kb, newGame(3));
    let firstGuessAt = -1;
    while (s.status !== "lost") {
      if (s.status === "asking") s = answer(kb, s, s.current!, 2);
      else {
        if (firstGuessAt < 0) firstGuessAt = s.answers.length;
        s = respondToGuess(kb, s, false);
      }
    }
    expect(firstGuessAt).toBeLessThanOrEqual(RULES.firstForcedGuess);
    expect(s.wrong.length === RULES.maxGuesses || s.answers.length >= RULES.maxQuestions).toBe(true);
    expect(s.answers.length).toBeLessThanOrEqual(RULES.maxQuestions);
  });

  it("is deterministic for a given seed (needed for stateless replay)", () => {
    const kb = loadSeed();
    const a = advance(kb, newGame(42));
    const b = advance(kb, newGame(42));
    expect(a.current).toBe(b.current);
  });

  it("reports confidence", () => {
    const kb = loadSeed();
    const s = advance(kb, newGame(9));
    const c = confidence(kb, s);
    expect(c).toBeGreaterThan(0);
    expect(c).toBeLessThan(0.5);
  });
});

describe("seed knowledge base (247 characters)", () => {
  it("wins at least 90% of games with 5% wrong answers", () => {
    const kb = loadSeed();
    let wins = 0;
    let total = 0;
    for (let t = 0; t < kb.n; t += 2) {
      const r = playGame(kb, t, 0.05, t + 1);
      wins += r.won ? 1 : 0;
      total++;
    }
    expect(wins / total).toBeGreaterThanOrEqual(0.9);
  });
});
