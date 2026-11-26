import { createRequire } from 'module'; const require = createRequire(import.meta.url);

// src/app.ts
import { existsSync } from "node:fs";
import { join } from "node:path";
import { randomInt } from "node:crypto";
import Fastify from "fastify";
import rateLimit from "@fastify/rate-limit";
import fastifyStatic from "@fastify/static";

// ../../packages/engine/src/kb.ts
var Q_HALF = 128;
function quantize(p) {
  return Math.max(0, Math.min(255, Math.round(p * 255)));
}
function view(buf, spec) {
  switch (spec.type) {
    case "f32":
      return new Float32Array(buf, spec.offset, spec.length);
    case "i32":
      return new Int32Array(buf, spec.offset, spec.length);
    case "u8":
      return new Uint8Array(buf, spec.offset, spec.length);
    default:
      throw new Error(`unknown array type ${spec.type}`);
  }
}
function loadKB(manifest, buffer, display = null) {
  if (manifest.format !== 1) throw new Error(`unsupported snapshot format ${manifest.format}`);
  const arr = (name) => {
    const spec = manifest.arrays[name];
    if (!spec) throw new Error(`snapshot is missing array ${name}`);
    return view(buffer, spec);
  };
  const n = manifest.entityCount;
  const ids = arr("ids");
  const groups = /* @__PURE__ */ new Map();
  for (const g of manifest.groups) {
    if (!manifest.arrays[`g${g.id}.ptr`]) continue;
    groups.set(g.id, {
      id: g.id,
      pMatch: quantize(g.pMatch),
      pOther: quantize(g.pOther),
      ptr: arr(`g${g.id}.ptr`),
      val: arr(`g${g.id}.val`)
    });
  }
  const questions = [];
  const questionIndex = /* @__PURE__ */ new Map();
  const valueQuestions = /* @__PURE__ */ new Map();
  const alwaysCandidates = [];
  manifest.questions.forEach((q, index) => {
    const usable = q.kind === "cells" || q.group !== null && groups.has(q.group);
    const question = {
      ...q,
      index,
      valueSet: q.kind === "group" && q.values ? new Set(q.values) : null
    };
    questions.push(question);
    questionIndex.set(q.id, index);
    if (!usable) return;
    if (q.kind === "group" && q.values && q.values.length === 1) {
      const key = `${q.group}:${q.values[0]}`;
      const list = valueQuestions.get(key) ?? [];
      list.push(index);
      valueQuestions.set(key, list);
    } else {
      alwaysCandidates.push(index);
    }
  });
  const entityIndex = /* @__PURE__ */ new Map();
  for (let i = 0; i < n; i++) entityIndex.set(ids[i], i);
  return {
    version: manifest.version,
    source: manifest.source,
    n,
    ids,
    prior: arr("prior"),
    kind: arr("kind"),
    questions,
    questionIndex,
    groups,
    cellPtr: arr("cells.ptr"),
    cellEnt: arr("cells.ent"),
    cellP: arr("cells.p"),
    entityIndex,
    valueQuestions,
    alwaysCandidates,
    display
  };
}
function fillColumn(kb, qi, out) {
  const q = kb.questions[qi];
  const g = q.kind === "group" && q.group !== null ? kb.groups.get(q.group) : void 0;
  if (g && q.valueSet && q.valueSet.size === 1) {
    const { ptr, val, pMatch, pOther } = g;
    const v = q.values[0];
    for (let e = 0; e < kb.n; e++) {
      const start = ptr[e];
      const end2 = ptr[e + 1];
      if (start === end2) {
        out[e] = Q_HALF;
        continue;
      }
      let hit = false;
      for (let k = start; k < end2; k++) {
        if (val[k] === v) {
          hit = true;
          break;
        }
      }
      out[e] = hit ? pMatch : pOther;
    }
  } else if (g && q.valueSet) {
    const { ptr, val, pMatch, pOther } = g;
    const set = q.valueSet;
    for (let e = 0; e < kb.n; e++) {
      const start = ptr[e];
      const end2 = ptr[e + 1];
      if (start === end2) {
        out[e] = Q_HALF;
        continue;
      }
      let hit = false;
      for (let k = start; k < end2; k++) {
        if (set.has(val[k])) {
          hit = true;
          break;
        }
      }
      out[e] = hit ? pMatch : pOther;
    }
  } else {
    out.fill(Q_HALF);
  }
  const end = kb.cellPtr[qi + 1];
  for (let k = kb.cellPtr[qi]; k < end; k++) out[kb.cellEnt[k]] = kb.cellP[k];
}
function cell(kb, qi, e) {
  let lo = kb.cellPtr[qi];
  let hi = kb.cellPtr[qi + 1] - 1;
  while (lo <= hi) {
    const mid = lo + hi >> 1;
    const v = kb.cellEnt[mid];
    if (v === e) return kb.cellP[mid];
    if (v < e) lo = mid + 1;
    else hi = mid - 1;
  }
  const q = kb.questions[qi];
  if (q.kind !== "group" || q.group === null || !q.valueSet) return Q_HALF;
  const g = kb.groups.get(q.group);
  if (!g) return Q_HALF;
  const start = g.ptr[e];
  const end = g.ptr[e + 1];
  if (start === end) return Q_HALF;
  for (let k = start; k < end; k++) if (q.valueSet.has(g.val[k])) return g.pMatch;
  return g.pOther;
}

// ../../packages/engine/src/engine.ts
var ANSWERS = ["yes", "probably", "dont_know", "probably_not", "no"];
var ANSWER_VALUE = [1, 0.75, null, 0.25, 0];
var RULES = {
  noise: 0.12,
  // share of answers assumed to be mistakes: one wrong answer never eliminates anyone
  topK: 2e3,
  guessConfidence: 0.85,
  firstForcedGuess: 20,
  // then every 10 questions
  forcedGuessEvery: 10,
  maxQuestions: 40,
  maxGuesses: 3,
  minGapAfterWrongGuess: 3,
  minUsefulGain: 2e-3,
  // nats
  nearBest: 0.95,
  // pick randomly among questions within 5% of the best gain (variety)
  maxCandidatesQuestions: 4e3
};
function makeTables() {
  const ll = [];
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
var T = makeTables();
function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a = a + 1831565813 >>> 0;
    let t = a;
    t = Math.imul(t ^ t >>> 15, t | 1);
    t ^= t + Math.imul(t ^ t >>> 7, t | 61);
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}
function stepSeed(state) {
  return (state.seed ^ Math.imul(state.answers.length + 1, 2654435761) ^ Math.imul(state.wrong.length + 1, 40503)) >>> 0;
}
var scratch = /* @__PURE__ */ new Map();
function column(kb) {
  let buf = scratch.get(kb.n);
  if (!buf) {
    buf = new Uint8Array(kb.n);
    scratch.set(kb.n, buf);
  }
  return buf;
}
function posterior(kb, state) {
  const n = kb.n;
  const logp = new Float64Array(n);
  for (let i = 0; i < n; i++) logp[i] = kb.prior[i];
  const col = column(kb);
  for (const [qid, code] of state.answers) {
    const qi = kb.questionIndex.get(qid);
    if (qi === void 0 || ANSWER_VALUE[code] === null || ANSWER_VALUE[code] === void 0) continue;
    fillColumn(kb, qi, col);
    const table = T.ll[code];
    for (let i = 0; i < n; i++) logp[i] += table[col[i]];
  }
  for (const id of state.wrong) {
    const i = kb.entityIndex.get(id);
    if (i !== void 0) logp[i] = -Infinity;
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
function topK(post, k) {
  const n = post.length;
  const live = [];
  for (let i = 0; i < n; i++) if (post[i] > 0) live.push(i);
  if (live.length <= k) return Int32Array.from(live);
  const vals = Float64Array.from(live, (i) => post[i]);
  let lo = 0;
  let hi = vals.length - 1;
  const target = k - 1;
  while (lo < hi) {
    const pivot = vals[lo + hi >> 1];
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
  const out = [];
  for (const i of live) if (post[i] > threshold) out.push(i);
  for (const i of live) {
    if (out.length >= k) break;
    if (post[i] === threshold) out.push(i);
  }
  return Int32Array.from(out);
}
function candidateQuestions(kb, rows, state) {
  const asked = /* @__PURE__ */ new Set();
  const askedDup = /* @__PURE__ */ new Set();
  for (const [qid] of state.answers) {
    const qi = kb.questionIndex.get(qid);
    if (qi === void 0) continue;
    asked.add(qi);
    const dup = kb.questions[qi].dup;
    if (dup !== null && dup !== void 0) askedDup.add(dup);
  }
  const ok = (qi) => {
    if (asked.has(qi)) return false;
    const dup = kb.questions[qi].dup;
    return dup === null || dup === void 0 || !askedDup.has(dup);
  };
  if (kb.questions.length <= RULES.maxCandidatesQuestions) {
    const all = [];
    for (const q of kb.questions) if (ok(q.index) && (q.kind === "cells" || q.group !== null && kb.groups.has(q.group))) all.push(q.index);
    return all;
  }
  const set = new Set(kb.alwaysCandidates.filter(ok));
  for (const g of kb.groups.values()) {
    for (const r of rows) {
      for (let k = g.ptr[r]; k < g.ptr[r + 1]; k++) {
        const list = kb.valueQuestions.get(`${g.id}:${g.val[k]}`);
        if (list) {
          for (const qi of list) if (ok(qi)) set.add(qi);
        }
      }
    }
  }
  return [...set];
}
function questionGains(kb, post, state) {
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
  const dense = kb.n <= 5e4;
  const col = dense ? column(kb) : null;
  const aggregated = (qi) => {
    const q = kb.questions[qi];
    return !dense && q.kind === "group" && q.values?.length === 1 && q.group !== null && kb.groups.has(q.group) && kb.cellPtr[qi] === kb.cellPtr[qi + 1];
  };
  const aggs = /* @__PURE__ */ new Map();
  for (const qi of cands) {
    if (!aggregated(qi)) continue;
    const gid = kb.questions[qi].group;
    if (aggs.has(gid)) continue;
    const g = kb.groups.get(gid);
    const a = { sK: 0, tK: 0, sU: 0, tU: 0, per: /* @__PURE__ */ new Map() };
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
  const bucketGain = (buckets) => {
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
      const g = kb.groups.get(q.group);
      const a = aggs.get(q.group);
      const m = a.per.get(q.values[0]) ?? [0, 0];
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
function chooseQuestion(kb, post, state) {
  const { qi, gain } = questionGains(kb, post, state);
  if (qi.length === 0) return { questionIndex: null, gain: 0 };
  let best = -Infinity;
  for (const g of gain) if (g > best) best = g;
  const near = [];
  for (let c = 0; c < qi.length; c++) if (gain[c] >= best * RULES.nearBest) near.push(c);
  near.sort((a, b) => gain[b] - gain[a]);
  const pool = near.slice(0, 3);
  const pick = pool[Math.floor(rng(stepSeed(state))() * pool.length)];
  return { questionIndex: qi[pick], gain: gain[pick] };
}
function newGame(seed) {
  return { v: 1, seed: seed >>> 0, answers: [], wrong: [], lastGuessAt: -1, status: "asking", current: null, guess: null };
}
function topOf(post) {
  let index = -1;
  let p = 0;
  for (let i = 0; i < post.length; i++) {
    if (post[i] > p) {
      p = post[i];
      index = i;
    }
  }
  return { index, p };
}
function advance(kb, state) {
  const s = { ...state, answers: [...state.answers], wrong: [...state.wrong] };
  const post = posterior(kb, s);
  const top = topOf(post);
  const n = s.answers.length;
  if (top.index < 0 || s.wrong.length >= RULES.maxGuesses || n >= RULES.maxQuestions && s.lastGuessAt >= n) {
    return { ...s, status: "lost", current: null, guess: null };
  }
  const choice = n >= RULES.maxQuestions ? { questionIndex: null, gain: 0 } : chooseQuestion(kb, post, s);
  const since = s.lastGuessAt < 0 ? Infinity : n - s.lastGuessAt;
  const forcedAt = Math.min(RULES.firstForcedGuess + RULES.forcedGuessEvery * s.wrong.length, RULES.maxQuestions);
  const shouldGuess = top.p >= RULES.guessConfidence && since >= RULES.minGapAfterWrongGuess || n >= forcedAt && s.lastGuessAt < n || choice.questionIndex === null || choice.gain < RULES.minUsefulGain && since > 0;
  if (shouldGuess) {
    return { ...s, status: "guessing", current: null, guess: kb.ids[top.index], lastGuessAt: n };
  }
  return { ...s, status: "asking", current: kb.questions[choice.questionIndex].id, guess: null };
}
function answer(kb, state, questionId, code) {
  if (state.status !== "asking") throw new GameError("not_asking", "The game is not waiting for an answer.");
  if (questionId !== state.current) throw new GameError("stale_question", "That is not the current question.");
  if (!Number.isInteger(code) || code < 0 || code > 4) throw new GameError("bad_answer", "Unknown answer.");
  return advance(kb, { ...state, answers: [...state.answers, [questionId, code]] });
}
function respondToGuess(kb, state, correct) {
  if (state.status !== "guessing" || state.guess === null) throw new GameError("not_guessing", "There is no guess to answer.");
  if (correct) return { ...state, status: "won" };
  return advance(kb, { ...state, wrong: [...state.wrong, state.guess], guess: null });
}
function undo(kb, state) {
  if (state.status !== "asking" && state.status !== "guessing" || state.answers.length === 0) {
    throw new GameError("nothing_to_undo", "Nothing to undo.");
  }
  const answers = state.answers.slice(0, -1);
  const [qid] = state.answers[state.answers.length - 1];
  const lastGuessAt = state.lastGuessAt > answers.length ? -1 : state.lastGuessAt;
  return { ...state, answers, lastGuessAt, status: "asking", current: qid, guess: null };
}
function confidence(kb, state) {
  return topOf(posterior(kb, state)).p;
}
var GameError = class extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
  }
};

// src/learning.ts
import { appendFile, mkdir } from "node:fs/promises";
import { dirname } from "node:path";
import { createHmac } from "node:crypto";
import pg from "pg";
var BLOCKED = /(https?:\/\/|www\.|\.(com|net|org|io)\b|fuck|shit|bitch|cunt|nigg|fagg|porn|xxx|rape|nazi|hitler|kill yourself)/i;
var ALLOWED = /^[\p{L}\p{M}\p{N} .,'&()\-!?:·]+$/u;
function checkName(name) {
  const clean = name.replace(/\s+/g, " ").trim();
  if (clean.length < 2 || clean.length > 60) return { ok: false, reason: "length", clean };
  if (!new RegExp("\\p{L}", "u").test(clean)) return { ok: false, reason: "no_letters", clean };
  if (!ALLOWED.test(clean)) return { ok: false, reason: "characters", clean };
  if (BLOCKED.test(clean)) return { ok: false, reason: "blocked_word", clean };
  return { ok: true, clean };
}
function checkText(text, max) {
  if (!text) return null;
  const clean = text.replace(/\s+/g, " ").trim().slice(0, max);
  return BLOCKED.test(clean) ? null : clean || null;
}
function hashDevice(deviceId, secret2) {
  if (typeof deviceId !== "string" || !/^[A-Za-z0-9_-]{16,64}$/.test(deviceId)) return null;
  return createHmac("sha256", secret2).update(`device:${deviceId}`).digest("hex");
}
function reliability(kb, entityId, answers) {
  const e = kb.entityIndex.get(entityId);
  if (e === void 0) return { weight: 0.5, flagged: null };
  let agree = 0;
  let disagree = 0;
  for (const [qid, code] of answers) {
    const qi = kb.questionIndex.get(qid);
    const v = ANSWER_VALUE[code];
    if (qi === void 0 || v === null || v === void 0) continue;
    const p = cell(kb, qi, e) / 255;
    if (p < 0.85 && p > 0.15) continue;
    if (Math.abs(v - p) > 0.6) disagree++;
    else agree++;
  }
  const confident = agree + disagree;
  if (confident >= 6 && disagree / confident > 0.5) {
    return { weight: 0, flagged: `answers contradicted ${disagree} of ${confident} confident facts` };
  }
  return { weight: Math.round((agree + 1) / (confident + 2) * 1e3) / 1e3, flagged: null };
}
var JsonlSink = class {
  constructor(path) {
    this.path = path;
  }
  seen = /* @__PURE__ */ new Set();
  async write(kind, data) {
    await mkdir(dirname(this.path), { recursive: true });
    await appendFile(this.path, JSON.stringify({ kind, at: (/* @__PURE__ */ new Date()).toISOString(), ...data }) + "\n");
  }
  async finish(r) {
    if (this.seen.has(r.gid)) return "duplicate";
    this.seen.add(r.gid);
    if (this.seen.size > 2e5) this.seen.clear();
    await this.write("game", r);
    return "stored";
  }
  async takedown(t) {
    await this.write("takedown", t);
  }
  async close() {
  }
};
var CODE_TO_SMALLINT = [0, 1, 2, 3, 4];
var PostgresSink = class {
  constructor(url, kbSourceForEvidence = "wikidata") {
    this.kbSourceForEvidence = kbSourceForEvidence;
    this.pool = new pg.Pool({ connectionString: url, max: 5 });
  }
  pool;
  async finish(r) {
    const client = await this.pool.connect();
    try {
      await client.query("BEGIN");
      if (r.deviceHash) {
        await client.query(
          `INSERT INTO devices (device_hash, games, reliability) VALUES (decode($1, 'hex'), 1, $2)
           ON CONFLICT (device_hash) DO UPDATE SET games = devices.games + 1,
             reliability = (devices.reliability * devices.games + EXCLUDED.reliability) / (devices.games + 1),
             updated_at = now()`,
          [r.deviceHash, r.reliability ?? 0.5]
        );
      }
      const inserted = await client.query(
        `INSERT INTO games (id, started_at, finished_at, snapshot_version, lang, outcome, n_questions, n_guesses,
                            guessed_entity_id, true_entity_id, answers, device_hash, reliability, device_class, country, flagged)
         VALUES ($1, to_timestamp($2 / 1000.0), to_timestamp($3 / 1000.0), $4, $5, $6, $7, $8, $9, $10, $11,
                 CASE WHEN $12::text IS NULL THEN NULL ELSE decode($12, 'hex') END, $13, $14, $15, $16)
         ON CONFLICT (id) DO NOTHING`,
        [
          r.gid,
          r.startedAt,
          r.finishedAt,
          r.kbVersion,
          r.lang,
          r.outcome,
          r.answers.length,
          r.guesses.length,
          r.guesses.at(-1) ?? null,
          r.trueEntityId,
          JSON.stringify(r.answers),
          r.deviceHash,
          r.reliability,
          r.deviceClass,
          r.country,
          r.flagged
        ]
      );
      if (inserted.rowCount === 0) {
        await client.query("ROLLBACK");
        return "duplicate";
      }
      const learnable = r.trueEntityId !== null && !r.flagged && r.kbSource === this.kbSourceForEvidence && (r.reliability ?? 0) > 0;
      if (learnable) {
        const rows = r.answers.filter(([, code]) => ANSWER_VALUE[code] !== null);
        if (rows.length) {
          const values = [];
          const tuples = rows.map(([qid, code], i) => {
            values.push(r.gid, r.trueEntityId, qid, CODE_TO_SMALLINT[code], r.reliability);
            const b = i * 5;
            return `($${b + 1}, $${b + 2}, $${b + 3}, $${b + 4}, $${b + 5})`;
          });
          await client.query(
            `INSERT INTO evidence (game_id, entity_id, question_id, answer, weight)
             SELECT v.g::uuid, v.e::bigint, v.q::int, v.a::smallint, v.w::real
             FROM (VALUES ${tuples.join(", ")}) AS v(g, e, q, a, w)
             WHERE EXISTS (SELECT 1 FROM entities WHERE id = v.e::bigint)
               AND EXISTS (SELECT 1 FROM questions WHERE id = v.q::int)
             ON CONFLICT DO NOTHING`,
            values
          );
        }
      }
      if (r.newCharacter) {
        const name = checkName(r.newCharacter.name);
        await client.query(
          `INSERT INTO submissions (game_id, name, description, lang, status, auto_checks, reject_reason)
           VALUES ($1, $2, $3, $4, $5, $6, $7)`,
          [
            r.gid,
            name.clean.slice(0, 80),
            r.newCharacter.description,
            r.lang,
            name.ok ? "pending" : "rejected",
            JSON.stringify({ name: name.ok ? "ok" : name.reason }),
            name.ok ? null : `automatic: ${name.reason}`
          ]
        );
      }
      await client.query("COMMIT");
      return "stored";
    } catch (err) {
      await client.query("ROLLBACK");
      throw err;
    } finally {
      client.release();
    }
  }
  async takedown(t) {
    await this.pool.query(
      `INSERT INTO takedown_requests (kind, entity_id, url, requester_name, requester_email, details)
       VALUES ($1, (SELECT id FROM entities WHERE id = $2), $3, $4, $5, $6)`,
      [t.kind, t.entityId, t.url, t.name, t.email, t.details]
    );
  }
  async close() {
    await this.pool.end();
  }
};

// src/view.ts
var LANGS = ["en", "hi", "es", "pt", "ja", "fr", "ar"];
function pickLang(input) {
  return LANGS.includes(input) ? input : "en";
}
function card(kb, id, lang, imageBase) {
  const i = kb.entityIndex.get(id);
  if (i === void 0 || !kb.display) return null;
  return cardFromDisplay(kb.display[i], lang, imageBase, kb.source);
}
function cardFromDisplay(d, lang, imageBase, source) {
  const img = d.img;
  const url = (size, ext) => `${imageBase}${img.p.replace(/^img\//, "")}-${size}.${ext}`;
  return {
    id: d.id,
    name: d.n[lang] ?? d.n.en ?? Object.values(d.n)[0] ?? "?",
    description: d.d[lang] ?? d.d.en ?? "",
    kind: d.k,
    theme: d.t ?? null,
    image: img ? {
      avif: { 256: url(256, "avif"), 512: url(512, "avif") },
      webp: { 256: url(256, "webp"), 512: url(512, "webp") },
      author: img.a ?? null,
      license: img.l ?? null,
      licenseUrl: img.lu ?? null,
      creditUrl: img.c ?? null
    } : null,
    wikidataUrl: source === "wikidata" ? `https://www.wikidata.org/wiki/Q${d.id}` : null
  };
}
function gameView(kb, s, token, lang, imageBase) {
  let question = null;
  if (s.status === "asking" && s.current !== null) {
    const qi = kb.questionIndex.get(s.current);
    const q = qi === void 0 ? null : kb.questions[qi];
    question = { id: s.current, text: q ? q.text[lang] ?? q.text.en ?? "" : "" };
  }
  return {
    token,
    status: s.status,
    step: s.answers.length + (s.status === "asking" ? 1 : 0),
    question,
    guess: s.status === "guessing" && s.guess !== null ? card(kb, s.guess, lang, imageBase) : null,
    confidence: s.status === "asking" || s.status === "guessing" ? Math.round(confidence(kb, s) * 1e3) / 1e3 : 0,
    questionsAsked: s.answers.length,
    wrongGuesses: s.wrong.length,
    maxGuesses: RULES.maxGuesses,
    maxQuestions: RULES.maxQuestions,
    canUndo: (s.status === "asking" || s.status === "guessing") && s.answers.length > 0
  };
}

// src/search.ts
function normalize(s) {
  return s.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[\s!-/:-@[-`{-~¡-¿ -⁯　-〿・！-／]+/g, " ").trim();
}
var NameIndex = class {
  // popularity rank of each entity (0 = most popular)
  constructor(kb) {
    this.kb = kb;
    const names = [];
    const owner = [];
    kb.display?.forEach((d, i) => {
      const seen = /* @__PURE__ */ new Set();
      for (const n of Object.values(d.n)) {
        const norm = normalize(n ?? "");
        if (norm && !seen.has(norm)) {
          seen.add(norm);
          names.push(norm);
          owner.push(i);
        }
      }
    });
    this.names = names;
    this.owner = Int32Array.from(owner);
    const idx = Array.from({ length: kb.n }, (_, i) => i).sort((a, b) => kb.prior[b] - kb.prior[a]);
    this.rankOf = new Int32Array(kb.n);
    idx.forEach((e, r) => this.rankOf[e] = r);
  }
  names = [];
  owner = new Int32Array(0);
  rankOf = new Int32Array(0);
  search(query, lang, limit, imageBase) {
    const q = normalize(query);
    if (q.length < 2 || !this.kb.display) return [];
    const rank = /* @__PURE__ */ new Map();
    for (let k = 0; k < this.names.length; k++) {
      const name = this.names[k];
      const pos = name.indexOf(q);
      if (pos < 0) continue;
      const score = pos === 0 ? 0 : name[pos - 1] === " " ? 1 : 2;
      const e = this.owner[k];
      const cur = rank.get(e);
      if (cur === void 0 || score < cur) rank.set(e, score);
    }
    return [...rank.entries()].sort((a, b) => a[1] - b[1] || this.rankOf[a[0]] - this.rankOf[b[0]]).slice(0, limit).map(([e]) => cardFromDisplay(this.kb.display[e], lang, imageBase, this.kb.source));
  }
};

// src/token.ts
import { createHmac as createHmac2, randomUUID, timingSafeEqual } from "node:crypto";
var MAX_TOKEN_LENGTH = 6e3;
function b64(buf) {
  return buf.toString("base64url");
}
function sign(payload, secret2) {
  return b64(createHmac2("sha256", secret2).update(payload).digest());
}
function encodeToken(data, secrets) {
  const payload = b64(Buffer.from(JSON.stringify(data)));
  return `${payload}.${sign(payload, secrets[0])}`;
}
function decodeToken(token, secrets) {
  if (typeof token !== "string" || token.length > MAX_TOKEN_LENGTH) return null;
  const dot = token.indexOf(".");
  if (dot < 1) return null;
  const payload = token.slice(0, dot);
  const mac = Buffer.from(token.slice(dot + 1), "base64url");
  const ok = secrets.some((s) => {
    const expected = Buffer.from(sign(payload, s), "base64url");
    return expected.length === mac.length && timingSafeEqual(expected, mac);
  });
  if (!ok) return null;
  try {
    const data = JSON.parse(Buffer.from(payload, "base64url").toString("utf8"));
    if (!data || typeof data.gid !== "string" || !data.s || !Array.isArray(data.s.answers)) return null;
    return data;
  } catch {
    return null;
  }
}
function newGameId() {
  return randomUUID();
}

// src/app.ts
var ANSWER_CODES = Object.fromEntries(ANSWERS.map((a, i) => [a, i]));
function answerCode(input) {
  if (typeof input === "number" && Number.isInteger(input) && input >= 0 && input <= 4) return input;
  if (typeof input === "string" && input in ANSWER_CODES) return ANSWER_CODES[input];
  return null;
}
async function buildApp(cfg, holder, sink) {
  const app = Fastify({
    trustProxy: cfg.trustProxy,
    bodyLimit: 16 * 1024,
    logger: process.env.NODE_ENV === "test" ? false : { level: process.env.LOG_LEVEL ?? "info" }
  });
  let names = new NameIndex(holder.kb);
  await app.register(rateLimit, { global: true, max: cfg.rateLimitPerMinute, timeWindow: "1 minute" });
  app.addContentTypeParser("text/plain", { parseAs: "string" }, (_req, body, done) => {
    try {
      done(null, JSON.parse(body));
    } catch {
      done(null, {});
    }
  });
  const respond = (reply, data) => {
    const kb = holder.kb;
    const token = encodeToken(data, cfg.tokenSecrets);
    return reply.send(gameView(kb, data.s, token, pickLang(data.lang), cfg.imageBaseUrl));
  };
  const load = (token, reply) => {
    const data = decodeToken(token, cfg.tokenSecrets);
    if (!data) {
      reply.code(400).send({ error: "bad_token", message: "This game could not be read. Start a new one." });
      return null;
    }
    return data;
  };
  const move = (reply, data, fn) => {
    try {
      return respond(reply, { ...data, s: fn(data.s) });
    } catch (err) {
      if (err instanceof GameError) return reply.code(409).send({ error: err.code, message: err.message });
      throw err;
    }
  };
  app.post(
    "/v1/games",
    { config: { rateLimit: { max: cfg.newGamesPerMinute, timeWindow: "1 minute" } } },
    async (req, reply) => {
      const body = req.body ?? {};
      const kb = holder.kb;
      const data = {
        gid: newGameId(),
        t0: Date.now(),
        kbv: kb.version,
        lang: pickLang(body.lang),
        s: advance(kb, newGame(randomInt(0, 2 ** 31)))
      };
      reply.code(201);
      return respond(reply, data);
    }
  );
  app.post("/v1/games/answer", async (req, reply) => {
    const body = req.body ?? {};
    const data = load(body.token, reply);
    if (!data) return reply;
    const code = answerCode(body.answer);
    if (code === null || typeof body.questionId !== "number") {
      return reply.code(400).send({ error: "bad_request", message: "questionId and answer are required." });
    }
    return move(reply, data, (s) => answer(holder.kb, s, body.questionId, code));
  });
  app.post("/v1/games/guess", async (req, reply) => {
    const body = req.body ?? {};
    const data = load(body.token, reply);
    if (!data) return reply;
    if (typeof body.correct !== "boolean") return reply.code(400).send({ error: "bad_request", message: "correct is required." });
    return move(reply, data, (s) => respondToGuess(holder.kb, s, body.correct));
  });
  app.post("/v1/games/undo", async (req, reply) => {
    const body = req.body ?? {};
    const data = load(body.token, reply);
    if (!data) return reply;
    return move(reply, data, (s) => undo(holder.kb, s));
  });
  app.post(
    "/v1/games/finish",
    { config: { rateLimit: { max: cfg.submissionsPerHour * 3, timeWindow: "1 hour" } } },
    async (req, reply) => {
      const body = req.body ?? {};
      const data = load(body.token, reply);
      if (!data) return reply;
      const s = data.s;
      if (s.status !== "won" && s.status !== "lost") {
        return reply.code(409).send({ error: "not_finished", message: "The game is still running." });
      }
      const kb = holder.kb;
      let trueId = s.status === "won" ? s.guess : null;
      let newCharacter = null;
      if (s.status === "lost") {
        if (typeof body.entityId === "number" && kb.entityIndex.has(body.entityId)) trueId = body.entityId;
        else if (body.newCharacter?.name) {
          const name = checkName(body.newCharacter.name);
          if (!name.ok) return reply.code(400).send({ error: "bad_name", message: "That name cannot be used." });
          newCharacter = { name: name.clean, description: checkText(body.newCharacter.description, 140) };
        }
      }
      const rel = trueId !== null ? reliability(kb, trueId, s.answers) : { weight: null, flagged: null };
      const guesses = [...s.wrong, ...s.status === "won" && s.guess !== null ? [s.guess] : []];
      const result = await sink.finish({
        gid: data.gid,
        startedAt: data.t0,
        finishedAt: Date.now(),
        kbVersion: data.kbv,
        kbSource: kb.source,
        lang: data.lang,
        outcome: s.status,
        answers: s.answers,
        guesses,
        trueEntityId: trueId,
        newCharacter,
        deviceHash: hashDevice(body.deviceId, cfg.tokenSecrets[0]),
        reliability: rel.weight,
        flagged: rel.flagged,
        country: typeof req.headers["cf-ipcountry"] === "string" ? req.headers["cf-ipcountry"].slice(0, 2) : null,
        deviceClass: typeof body.deviceClass === "number" ? Math.max(0, Math.min(2, Math.round(body.deviceClass))) : null
      });
      return reply.send({
        ok: true,
        duplicate: result === "duplicate",
        character: trueId !== null ? card(kb, trueId, pickLang(data.lang), cfg.imageBaseUrl) : null,
        submitted: newCharacter !== null
      });
    }
  );
  app.post("/v1/games/abandon", async (req, reply) => {
    const body = req.body ?? {};
    const data = decodeToken(body.token, cfg.tokenSecrets);
    if (data && (data.s.status === "asking" || data.s.status === "guessing") && data.s.answers.length > 0) {
      await sink.finish({
        gid: data.gid,
        startedAt: data.t0,
        finishedAt: Date.now(),
        kbVersion: data.kbv,
        kbSource: holder.kb.source,
        lang: data.lang,
        outcome: "abandoned",
        answers: data.s.answers,
        guesses: data.s.wrong,
        trueEntityId: null,
        newCharacter: null,
        deviceHash: null,
        reliability: null,
        flagged: null,
        country: null,
        deviceClass: null
      });
    }
    return reply.code(204).send();
  });
  app.get("/v1/search", async (req, reply) => {
    const q = req.query;
    const limit = Math.max(1, Math.min(20, Number(q.limit ?? 8) || 8));
    reply.header("cache-control", "public, max-age=300");
    return { results: names.search(String(q.q ?? "").slice(0, 60), pickLang(q.lang), limit, cfg.imageBaseUrl) };
  });
  app.post("/v1/takedown", { config: { rateLimit: { max: 5, timeWindow: "1 hour" } } }, async (req, reply) => {
    const b = req.body ?? {};
    const kind = ["image", "likeness", "data", "other"].includes(String(b.kind)) ? b.kind : null;
    const email = typeof b.email === "string" && /^[^\s@]{1,64}@[^\s@]{1,190}\.[^\s@]{2,}$/.test(b.email) ? b.email : null;
    const name = typeof b.name === "string" ? b.name.trim().slice(0, 120) : "";
    const details = typeof b.details === "string" ? b.details.trim().slice(0, 4e3) : "";
    if (!kind || !email || name.length < 2 || details.length < 10) {
      return reply.code(400).send({ error: "bad_request", message: "Please fill in every field." });
    }
    await sink.takedown({
      kind,
      email,
      name,
      details,
      entityId: typeof b.entityId === "number" ? b.entityId : null,
      url: typeof b.url === "string" ? b.url.slice(0, 500) : null
    });
    return reply.code(201).send({ ok: true });
  });
  app.get("/v1/health", async () => {
    const kb = holder.kb;
    return { ok: true, snapshot: { version: kb.version, source: kb.source, characters: kb.n, questions: kb.questions.length } };
  });
  app.post("/v1/admin/reload", async (req, reply) => {
    const auth = req.headers.authorization ?? "";
    if (!process.env.ADMIN_TOKEN || auth !== `Bearer ${process.env.ADMIN_TOKEN}`) return reply.code(401).send({ error: "unauthorized" });
    await holder.reload();
    names = new NameIndex(holder.kb);
    return { ok: true, version: holder.kb.version, characters: holder.kb.n };
  });
  if (cfg.imagesDir && existsSync(cfg.imagesDir)) {
    await app.register(fastifyStatic, {
      root: cfg.imagesDir,
      prefix: "/img/",
      decorateReply: false,
      immutable: true,
      maxAge: "365d"
    });
  }
  if (existsSync(cfg.webDir)) {
    await app.register(fastifyStatic, {
      root: cfg.webDir,
      prefix: "/",
      extensions: ["html"],
      cacheControl: false,
      // headers are set below per file type
      setHeaders: (res, path) => {
        if (path.includes(`${join("_next", "static")}`)) res.setHeader("cache-control", "public, max-age=31536000, immutable");
        else if (path.endsWith("sw.js") || path.endsWith(".html") || path.endsWith(".webmanifest")) res.setHeader("cache-control", "no-cache");
        else res.setHeader("cache-control", "public, max-age=86400");
      }
    });
    app.setNotFoundHandler((req, reply) => {
      if (req.url.startsWith("/v1/")) return reply.code(404).send({ error: "not_found" });
      return reply.code(404).type("text/html").sendFile("404.html");
    });
  }
  app.addHook("onSend", async (_req, reply, payload) => {
    reply.header("x-content-type-options", "nosniff");
    reply.header("referrer-policy", "strict-origin-when-cross-origin");
    reply.header("permissions-policy", "camera=(), microphone=(), geolocation=()");
    return payload;
  });
  return app;
}

// src/config.ts
import { randomBytes } from "node:crypto";
import { dirname as dirname2, join as join2, resolve } from "node:path";
import { fileURLToPath } from "node:url";
var here = dirname2(fileURLToPath(import.meta.url));
var gameRoot = resolve(here, "..", "..", "..");
function env(name, fallback) {
  const v = process.env[name];
  return v === void 0 || v === "" ? fallback : v;
}
var secret = process.env.TOKEN_SECRET;
if (!secret && process.env.NODE_ENV === "production") {
  throw new Error("TOKEN_SECRET must be set in production (32+ random bytes, e.g. `openssl rand -hex 32`).");
}
var config = {
  port: Number(env("PORT", "8080")),
  host: env("HOST", "0.0.0.0"),
  snapshotDir: resolve(env("SNAPSHOT_DIR", join2(gameRoot, "data", "seed"))),
  webDir: resolve(env("WEB_DIR", join2(gameRoot, "apps", "web", "out"))),
  imagesDir: process.env.IMAGES_DIR ? resolve(process.env.IMAGES_DIR) : null,
  imageBaseUrl: env("IMAGE_BASE_URL", "/img/"),
  // CDN base for thumbnails, ends with "/"
  tokenSecrets: (secret ?? randomBytes(32).toString("hex")).split(",").map((s) => s.trim()),
  // first signs, all verify
  databaseUrl: process.env.DATABASE_URL || null,
  learningLog: resolve(env("LEARNING_LOG", join2(gameRoot, "data", "learning.jsonl"))),
  trustProxy: env("TRUST_PROXY", "true") === "true",
  rateLimitPerMinute: Number(env("RATE_LIMIT_PER_MINUTE", "240")),
  newGamesPerMinute: Number(env("NEW_GAMES_PER_MINUTE", "30")),
  submissionsPerHour: Number(env("SUBMISSIONS_PER_HOUR", "20")),
  autoApproveAfter: Number(env("AUTO_APPROVE_AFTER", "3"))
};

// src/snapshot.ts
import { readFile } from "node:fs/promises";
import { join as join3 } from "node:path";
async function loadSnapshot(dir) {
  const [manifestText, bin, displayText] = await Promise.all([
    readFile(join3(dir, "manifest.json"), "utf8"),
    readFile(join3(dir, "arrays.bin")),
    readFile(join3(dir, "display.json"), "utf8")
  ]);
  const manifest = JSON.parse(manifestText);
  const buffer = bin.buffer.slice(bin.byteOffset, bin.byteOffset + bin.byteLength);
  const display = JSON.parse(displayText);
  if (display.length !== manifest.entityCount) {
    throw new Error(`display.json has ${display.length} rows, manifest says ${manifest.entityCount}`);
  }
  return loadKB(manifest, buffer, display);
}
var SnapshotHolder = class {
  constructor(dir) {
    this.dir = dir;
  }
  kb;
  async reload() {
    this.kb = await loadSnapshot(this.dir);
    return this.kb;
  }
};

// src/index.ts
async function main() {
  const holder = new SnapshotHolder(config.snapshotDir);
  const kb = await holder.reload();
  const sink = config.databaseUrl ? new PostgresSink(config.databaseUrl) : new JsonlSink(config.learningLog);
  const app = await buildApp(config, holder, sink);
  app.log.info(
    { snapshot: config.snapshotDir, characters: kb.n, questions: kb.questions.length, source: kb.source },
    "snapshot loaded"
  );
  process.on("SIGHUP", () => {
    holder.reload().then(
      (k) => app.log.info({ version: k.version, characters: k.n }, "snapshot reloaded"),
      (err) => app.log.error(err, "snapshot reload failed; keeping the old one")
    );
  });
  const stop = async () => {
    await app.close();
    await sink.close();
    process.exit(0);
  };
  process.on("SIGTERM", stop);
  process.on("SIGINT", stop);
  await app.listen({ port: config.port, host: config.host });
}
main().catch((err) => {
  console.error(err);
  process.exit(1);
});
