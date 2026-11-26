// Bayesian guessing engine: posterior over all characters, next question by expected
// information gain over the top-K candidates, guess rules, undo. Pure functions over a
// serialisable GameState, so the game service can stay stateless.

import { cell, fillColumn, KB, Q_HALF } from "./kb";

export type Answer = "yes" | "probably" | "dont_know" | "probably_not" | "no";
export const ANSWERS: Answer[] = ["yes", "probably", "dont_know", "probably_not", "no"];
/** How strongly each answer means "yes". null = no information. */
export const ANSWER_VALUE: (number | null)[] = [1, 0.75, null, 0.25, 0];

export const RULES = {
  noise: 0.12, // share of answers assumed to be mistakes: one wrong answer never eliminates anyone
  topK: 2000,
  guessConfidence: 0.7, // tuned by simulation: about 2.5 fewer questions than 0.85 for a small accuracy cost
  leadGuess: { minQuestions: 8, minP: 0.5, ratio: 4 }, // also guess when far ahead of the runner-up
  firstForcedGuess: 16, // then at 28 and 40
  forcedGuessEvery: 12,
  maxQuestions: 40,
  maxGuesses: 3,
  minGapAfterWrongGuess: 2,
  sameTopicPenalty: [0.8, 0.5], // gain multiplier when the last one / last two questions had the same topic
  minUsefulGain: 0.002, // nats
  nearBest: 0.95, // pick randomly among questions within 5% of the best gain (variety)
  maxCandidatesQuestions: 4000,
};

export type Status = "asking" | "guessing" | "won" | "lost";

export interface GameState {
  v: 1;
  seed: number;
  /** [question id, answer code 0..4] */
  answers: [number, number][];
  /** entity ids the player rejected */
  wrong: number[];
  lastGuessAt: number; // number of answers when the last guess was made, -1 if none
  status: Status;
  current: number | null; // question id
  guess: number | null; // entity id
}

// ---------------------------------------------------------------- likelihood tables

function makeTables() {
  const ll: Float64Array[] = []; // ll[code][q8] = log P(answer | p)
  const lyes = new Float64Array(256);
  const llyes = new Float64Array(256);
  for (let code = 0; code < 5; code++) {
    const v = ANSWER_VALUE[code];
    const t = new Float64Array(256);
    for (let q = 0; q < 256; q++) {
      if (v === null) continue;
      const p = Math.min(0.99, Math.max(0.01, q / 255));
      const clean = v * p + (1 - v) * (1 - p);
      t[q] = Math.log((1 - RULES.noise) * clean + RULES.noise / 2);
    }
    ll.push(t);
  }
  for (let q = 0; q < 256; q++) {
    const p = Math.min(0.99, Math.max(0.01, q / 255));
    lyes[q] = (1 - RULES.noise) * p + RULES.noise / 2;
    llyes[q] = Math.log(lyes[q]);
  }
  const lno = new Float64Array(256);
  const llno = new Float64Array(256);
  for (let q = 0; q < 256; q++) {
    lno[q] = 1 - lyes[q];
    llno[q] = Math.log(lno[q]);
  }
  return { ll, lyes, llyes, lno, llno };
}
const T = makeTables();

// ---------------------------------------------------------------- random

export function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function stepSeed(state: GameState): number {
  return (state.seed ^ Math.imul(state.answers.length + 1, 2654435761) ^ Math.imul(state.wrong.length + 1, 40503)) >>> 0;
}

// ---------------------------------------------------------------- posterior

const scratch = new Map<number, Uint8Array>();
function column(kb: KB): Uint8Array {
  let buf = scratch.get(kb.n);
  if (!buf) {
    buf = new Uint8Array(kb.n);
    scratch.set(kb.n, buf);
  }
  return buf;
}

/** Normalised posterior over all characters (index order). Rejected guesses get 0. */
export function posterior(kb: KB, state: Pick<GameState, "answers" | "wrong">): Float64Array {
  const n = kb.n;
  const logp = new Float64Array(n);
  for (let i = 0; i < n; i++) logp[i] = kb.prior[i];
  const col = column(kb);
  for (const [qid, code] of state.answers) {
    const qi = kb.questionIndex.get(qid);
    if (qi === undefined || ANSWER_VALUE[code] === null || ANSWER_VALUE[code] === undefined) continue;
    fillColumn(kb, qi, col);
    const table = T.ll[code];
    for (let i = 0; i < n; i++) logp[i] += table[col[i]];
  }
  for (const id of state.wrong) {
    const i = kb.entityIndex.get(id);
    if (i !== undefined) logp[i] = -Infinity;
  }
  let max = -Infinity;
  for (let i = 0; i < n; i++) if (logp[i] > max) max = logp[i];
  const out = new Float64Array(n);
  if (max === -Infinity) return out;
  let z = 0;
  for (let i = 0; i < n; i++) {
    const v = Math.exp(logp[i] - max);
    out[i] = v;
    z += v;
  }
  for (let i = 0; i < n; i++) out[i] /= z;
  return out;
}

/** Indices of the k most likely characters (unordered). */
export function topK(post: Float64Array, k: number): Int32Array {
  const n = post.length;
  const live: number[] = [];
  for (let i = 0; i < n; i++) if (post[i] > 0) live.push(i);
  if (live.length <= k) return Int32Array.from(live);
  // quickselect for the k-th largest value
  const vals = Float64Array.from(live, (i) => post[i]);
  let lo = 0;
  let hi = vals.length - 1;
  const target = k - 1;
  while (lo < hi) {
    const pivot = vals[(lo + hi) >> 1];
    let i = lo;
    let j = hi;
    while (i <= j) {
      while (vals[i] > pivot) i++;
      while (vals[j] < pivot) j--;
      if (i <= j) {
        const t = vals[i];
        vals[i] = vals[j];
        vals[j] = t;
        i++;
        j--;
      }
    }
    if (target <= j) hi = j;
    else if (target >= i) lo = i;
    else break;
  }
  const threshold = vals[target];
  const out: number[] = [];
  for (const i of live) if (post[i] > threshold) out.push(i);
  for (const i of live) {
    if (out.length >= k) break;
    if (post[i] === threshold) out.push(i);
  }
  return Int32Array.from(out);
}

// ---------------------------------------------------------------- question choice

export interface Choice {
  questionIndex: number | null;
  gain: number;
}

function candidateQuestions(kb: KB, rows: Int32Array, state: GameState): number[] {
  const asked = new Set<number>();
  const askedDup = new Set<number>();
  for (const [qid] of state.answers) {
    const qi = kb.questionIndex.get(qid);
    if (qi === undefined) continue;
    asked.add(qi);
    const dup = kb.questions[qi].dup;
    if (dup !== null && dup !== undefined) askedDup.add(dup);
  }
  const ok = (qi: number) => {
    if (asked.has(qi)) return false;
    const dup = kb.questions[qi].dup;
    return dup === null || dup === undefined || !askedDup.has(dup);
  };
  if (kb.questions.length <= RULES.maxCandidatesQuestions) {
    const all: number[] = [];
    for (const q of kb.questions) if (ok(q.index) && (q.kind === "cells" || (q.group !== null && kb.groups.has(q.group)))) all.push(q.index);
    return all;
  }
  // Large question banks: only questions about values that the likely characters have.
  const set = new Set<number>(kb.alwaysCandidates.filter(ok));
  for (const g of kb.groups.values()) {
    for (const r of rows) {
      for (let k = g.ptr[r]; k < g.ptr[r + 1]; k++) {
        const list = kb.valueQuestions.get(`${g.id}:${g.val[k]}`);
        if (list) for (const qi of list) if (ok(qi)) set.add(qi);
      }
    }
  }
  return [...set];
}

/** Expected information gain (nats) of each candidate question over the top-K rows. */
export function questionGains(kb: KB, post: Float64Array, state: GameState): { qi: number[]; gain: Float64Array } {
  const rows = topK(post, RULES.topK);
  let mass = 0;
  for (const r of rows) mass += post[r];
  const pi = new Float64Array(rows.length);
  const logpi = new Float64Array(rows.length);
  let h0 = 0;
  for (let k = 0; k < rows.length; k++) {
    const p = post[rows[k]] / mass;
    pi[k] = p;
    logpi[k] = p > 0 ? Math.log(p) : 0;
    if (p > 0) h0 -= p * logpi[k];
  }
  const cands = candidateQuestions(kb, rows, state);
  const gain = new Float64Array(cands.length);
  const dense = kb.n <= 50000;
  const col = dense ? column(kb) : null;

  // Single-value group questions without explicit cells are scored from three bucket sums
  // (has the value / has another value / unknown), so one pass over the rows per group
  // covers every value question in that group.
  const aggregated = (qi: number) => {
    const q = kb.questions[qi];
    return !dense && q.kind === "group" && q.values?.length === 1 && q.group !== null && kb.groups.has(q.group)
      && kb.cellPtr[qi] === kb.cellPtr[qi + 1];
  };
  const aggs = new Map<number, { sK: number; tK: number; sU: number; tU: number; per: Map<number, number[]> }>();
  for (const qi of cands) {
    if (!aggregated(qi)) continue;
    const gid = kb.questions[qi].group!;
    if (aggs.has(gid)) continue;
    const g = kb.groups.get(gid)!;
    const a = { sK: 0, tK: 0, sU: 0, tU: 0, per: new Map<number, number[]>() };
    for (let k = 0; k < rows.length; k++) {
      const p = pi[k];
      if (p === 0) continue;
      const t = p * logpi[k];
      const r = rows[k];
      const start = g.ptr[r];
      const end = g.ptr[r + 1];
      if (start === end) {
        a.sU += p;
        a.tU += t;
        continue;
      }
      a.sK += p;
      a.tK += t;
      for (let j = start; j < end; j++) {
        const v = g.val[j];
        let dup = false;
        for (let x = start; x < j; x++) if (g.val[x] === v) dup = true;
        if (dup) continue;
        const cur = a.per.get(v);
        if (cur) {
          cur[0] += p;
          cur[1] += t;
        } else a.per.set(v, [p, t]);
      }
    }
    aggs.set(gid, a);
  }
  const bucketGain = (buckets: [number, number, number][]) => {
    let sY = 0, tY = 0, sN = 0, tN = 0;
    for (const [s, t, q8] of buckets) {
      if (s === 0) continue;
      sY += s * T.lyes[q8];
      tY += T.lyes[q8] * (t + s * T.llyes[q8]);
      sN += s * T.lno[q8];
      tN += T.lno[q8] * (t + s * T.llno[q8]);
    }
    return h0 - ((sY > 0 ? sY * Math.log(sY) : 0) - tY + (sN > 0 ? sN * Math.log(sN) : 0) - tN);
  };

  for (let c = 0; c < cands.length; c++) {
    const qi = cands[c];
    if (aggregated(qi)) {
      const q = kb.questions[qi];
      const g = kb.groups.get(q.group!)!;
      const a = aggs.get(q.group!)!;
      const m = a.per.get(q.values![0]) ?? [0, 0];
      gain[c] = bucketGain([[m[0], m[1], g.pMatch], [a.sK - m[0], a.tK - m[1], g.pOther], [a.sU, a.tU, Q_HALF]]);
      continue;
    }
    if (col) fillColumn(kb, qi, col);
    let sY = 0;
    let tY = 0;
    let sN = 0;
    let tN = 0;
    for (let k = 0; k < rows.length; k++) {
      const p = pi[k];
      if (p === 0) continue;
      const q8 = col ? col[rows[k]] : cell(kb, qi, rows[k]);
      const y = p * T.lyes[q8];
      const nn = p * T.lno[q8];
      sY += y;
      tY += y * (logpi[k] + T.llyes[q8]);
      sN += nn;
      tN += nn * (logpi[k] + T.llno[q8]);
    }
    const eh = (sY > 0 ? sY * Math.log(sY) : 0) - tY + (sN > 0 ? sN * Math.log(sN) : 0) - tN;
    gain[c] = h0 - eh;
  }
  return { qi: cands, gain };
}

function topicOf(kb: KB, qi: number): string | null {
  const q = kb.questions[qi];
  return q.topic ?? (q.group !== null ? `g${q.group}` : null);
}

export function chooseQuestion(kb: KB, post: Float64Array, state: GameState): Choice {
  const { qi, gain } = questionGains(kb, post, state);
  if (qi.length === 0) return { questionIndex: null, gain: 0 };
  // Variety: a third "Is your character from <country>?" in a row is boring even when it is
  // slightly more informative, so recent topics are discounted.
  const recent = state.answers.slice(-2).map(([qid]) => {
    const i = kb.questionIndex.get(qid);
    return i === undefined ? null : topicOf(kb, i);
  });
  const last = recent[recent.length - 1] ?? null;
  const both = recent.length === 2 && recent[0] !== null && recent[0] === recent[1] ? recent[0] : null;
  const raw = Float64Array.from(gain);
  for (let c = 0; c < qi.length; c++) {
    const t = topicOf(kb, qi[c]);
    if (t === null) continue;
    if (both !== null && t === both) gain[c] *= RULES.sameTopicPenalty[1];
    else if (t === last) gain[c] *= RULES.sameTopicPenalty[0];
  }
  let best = -Infinity;
  for (const g of gain) if (g > best) best = g;
  const near: number[] = [];
  for (let c = 0; c < qi.length; c++) if (gain[c] >= best * RULES.nearBest) near.push(c);
  near.sort((a, b) => gain[b] - gain[a]);
  const pool = near.slice(0, 3);
  const pick = pool[Math.floor(rng(stepSeed(state))() * pool.length)];
  return { questionIndex: qi[pick], gain: raw[pick] };
}

// ---------------------------------------------------------------- game rules

export function newGame(seed: number): GameState {
  return { v: 1, seed: seed >>> 0, answers: [], wrong: [], lastGuessAt: -1, status: "asking", current: null, guess: null };
}

function topOf(post: Float64Array): { index: number; p: number; second: number } {
  let index = -1;
  let p = 0;
  let second = 0;
  for (let i = 0; i < post.length; i++) {
    if (post[i] > p) {
      second = p;
      p = post[i];
      index = i;
    } else if (post[i] > second) second = post[i];
  }
  return { index, p, second };
}

/** Decide what happens next: ask, guess, or give up. Returns a new state. */
export function advance(kb: KB, state: GameState): GameState {
  const s: GameState = { ...state, answers: [...state.answers], wrong: [...state.wrong] };
  const post = posterior(kb, s);
  const top = topOf(post);
  const n = s.answers.length;
  if (top.index < 0 || s.wrong.length >= RULES.maxGuesses || (n >= RULES.maxQuestions && s.lastGuessAt >= n)) {
    return { ...s, status: "lost", current: null, guess: null };
  }
  const choice = n >= RULES.maxQuestions ? { questionIndex: null, gain: 0 } : chooseQuestion(kb, post, s);
  const since = s.lastGuessAt < 0 ? Infinity : n - s.lastGuessAt;
  const forcedAt = Math.min(RULES.firstForcedGuess + RULES.forcedGuessEvery * s.wrong.length, RULES.maxQuestions);
  const shouldGuess =
    (top.p >= RULES.guessConfidence && since >= RULES.minGapAfterWrongGuess) ||
    (n >= RULES.leadGuess.minQuestions && top.p >= RULES.leadGuess.minP && top.p >= RULES.leadGuess.ratio * top.second &&
      since >= RULES.minGapAfterWrongGuess) ||
    (n >= forcedAt && s.lastGuessAt < n) ||
    choice.questionIndex === null ||
    (choice.gain < RULES.minUsefulGain && since > 0);
  if (shouldGuess) {
    return { ...s, status: "guessing", current: null, guess: kb.ids[top.index], lastGuessAt: n };
  }
  return { ...s, status: "asking", current: kb.questions[choice.questionIndex!].id, guess: null };
}

export function answer(kb: KB, state: GameState, questionId: number, code: number): GameState {
  if (state.status !== "asking") throw new GameError("not_asking", "The game is not waiting for an answer.");
  if (questionId !== state.current) throw new GameError("stale_question", "That is not the current question.");
  if (!Number.isInteger(code) || code < 0 || code > 4) throw new GameError("bad_answer", "Unknown answer.");
  return advance(kb, { ...state, answers: [...state.answers, [questionId, code]] });
}

export function respondToGuess(kb: KB, state: GameState, correct: boolean): GameState {
  if (state.status !== "guessing" || state.guess === null) throw new GameError("not_guessing", "There is no guess to answer.");
  if (correct) return { ...state, status: "won" };
  return advance(kb, { ...state, wrong: [...state.wrong, state.guess], guess: null });
}

export function undo(kb: KB, state: GameState): GameState {
  if ((state.status !== "asking" && state.status !== "guessing") || state.answers.length === 0) {
    throw new GameError("nothing_to_undo", "Nothing to undo.");
  }
  const answers = state.answers.slice(0, -1);
  const [qid] = state.answers[state.answers.length - 1];
  const lastGuessAt = state.lastGuessAt > answers.length ? -1 : state.lastGuessAt;
  return { ...state, answers, lastGuessAt, status: "asking", current: qid, guess: null };
}

export function confidence(kb: KB, state: GameState): number {
  return topOf(posterior(kb, state)).p;
}

export class GameError extends Error {
  constructor(public code: string, message: string) {
    super(message);
  }
}

export { Q_HALF };
