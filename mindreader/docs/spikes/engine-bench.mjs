// Feasibility spike for deliverable 1: can a stateless Node.js service replay a game
// and pick the next question for 500,000 characters in under 150 ms (p95)?
//
// Data model under test ("virtual matrix"):
//   - Categorical attribute groups (country, occupation, franchise...). Each character
//     stores one value id per group (0 = unknown) in a Uint16Array.
//   - A question is (group, value): "Is your character from India?".
//     P(yes) = 0.95 if the character has that value, 0.05 if it has another known value,
//     0.5 if unknown. Nothing per cell is stored, so memory is N x groups x 2 bytes.
//   - Expected information gain for a categorical question needs only three bucket sums
//     (match / known-other / unknown) of pi and pi*log(pi), so it is computed exactly over
//     ALL characters, not just a top-K sample.
//
// Run: node engine-bench.mjs

const N = 500_000;
const GROUPS = [ // [name, cardinality, share of characters with a known value]
  ["real", 2, 1.0], ["gender", 3, 0.97], ["alive", 2, 0.9], ["century", 30, 0.8],
  ["continent", 7, 0.85], ["country", 200, 0.8], ["occupation", 300, 0.7], ["sport", 60, 0.15],
  ["team", 800, 0.08], ["franchise", 1500, 0.25], ["medium", 8, 0.3], ["creator", 300, 0.1],
  ["species", 50, 0.3], ["role", 3, 0.2], ["language", 60, 0.6],
];
const NOISE = 0.12;
const ANSWERS = 40;      // worst case: a 40-question game is replayed on every request
const RUNS = 200;

// Deterministic PRNG so runs are comparable.
let seed = 12345;
const rand = () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296);

// Zipf-like value choice: a few values are common (USA, actor), most are rare.
function zipf(card) { return 1 + Math.min(card - 1, Math.floor(Math.pow(rand(), 2.2) * card)); }

const attrs = GROUPS.map(([, card, known]) => {
  const a = new Uint16Array(N);
  for (let i = 0; i < N; i++) if (rand() < known) a[i] = zipf(card);
  return a;
});
const logPrior = new Float64Array(N);
for (let i = 0; i < N; i++) logPrior[i] = Math.log(1 + 50 * Math.pow(rand(), 8)); // long-tail popularity
const nQuestions = GROUPS.reduce((s, g) => s + g[1], 0);

const L = (p, v) => (1 - NOISE) * (v * p + (1 - v) * (1 - p)) + NOISE * 0.5;

// Naive replay: one pass over all characters per answer. Cost grows with game length.
function replayNaive(answers) {
  const logp = Float64Array.from(logPrior);
  for (const [g, val, v] of answers) {
    const a = attrs[g];
    const lm = Math.log(L(0.95, v)), lo = Math.log(L(0.05, v)), lu = Math.log(L(0.5, v));
    for (let i = 0; i < N; i++) {
      const x = a[i];
      logp[i] += x === 0 ? lu : (x === val ? lm : lo);
    }
  }
  return normalize(logp);
}

// Folded replay: an answer about group g only depends on the character's value in g,
// so all answers about g collapse into one lookup table indexed by value.
// Cost: one branch-free pass per answered group (at most 15), whatever the game length.
function replay(answers) {
  const tables = new Map();
  for (const [g, val, v] of answers) {
    const card = GROUPS[g][1];
    let t = tables.get(g);
    if (!t) { t = new Float64Array(card + 1); tables.set(g, t); }
    const lm = Math.log(L(0.95, v)), lo = Math.log(L(0.05, v)), lu = Math.log(L(0.5, v));
    t[0] += lu;
    for (let x = 1; x <= card; x++) t[x] += x === val ? lm : lo;
  }
  const logp = Float64Array.from(logPrior);
  for (const [g, t] of tables) {
    const a = attrs[g];
    for (let i = 0; i < N; i++) logp[i] += t[a[i]];
  }
  return normalize(logp);
}

function normalize(logp) {
  let mx = -Infinity;
  for (let i = 0; i < N; i++) if (logp[i] > mx) mx = logp[i];
  let z = 0;
  const pi = new Float64Array(N);
  for (let i = 0; i < N; i++) { pi[i] = Math.exp(logp[i] - mx); z += pi[i]; }
  for (let i = 0; i < N; i++) pi[i] /= z;
  return pi;
}

// Exact expected information gain of every (group, value) question over all N characters.
function bestQuestion(pi, asked) {
  let H0 = 0;
  const plogp = new Float64Array(N);
  for (let i = 0; i < N; i++) { const p = pi[i]; if (p > 0) { plogp[i] = p * Math.log(p); H0 -= plogp[i]; } }
  const ly = [L(0.95, 1), L(0.05, 1), L(0.5, 1)];
  const ln = [L(0.95, 0), L(0.05, 0), L(0.5, 0)];
  let best = { gain: -1 };
  for (let g = 0; g < GROUPS.length; g++) {
    const card = GROUPS[g][1], a = attrs[g];
    const S = new Float64Array(card + 1), T = new Float64Array(card + 1);
    for (let i = 0; i < N; i++) { const x = a[i]; S[x] += pi[i]; T[x] += plogp[i]; }
    let Sk = 0, Tk = 0;
    for (let v = 1; v <= card; v++) { Sk += S[v]; Tk += T[v]; }
    for (let v = 1; v <= card; v++) {
      if (asked.has(g * 10000 + v) || S[v] === 0) continue;
      // buckets: match, known-other, unknown
      const s = [S[v], Sk - S[v], S[0]], t = [T[v], Tk - T[v], T[0]];
      let EH = 0;
      for (const lik of [ly, ln]) {
        let Z = 0, A = 0;
        for (let b = 0; b < 3; b++) { Z += lik[b] * s[b]; A += lik[b] * (t[b] + s[b] * Math.log(lik[b])); }
        if (Z > 0) EH += Z * (Math.log(Z) - A / Z); // P(answer) * H(posterior | answer)
      }
      const gain = H0 - EH;
      if (gain > best.gain) best = { gain, g, v };
    }
  }
  return best;
}

function makeAnswers(k) {
  const out = [];
  for (let j = 0; j < k; j++) {
    const g = Math.floor(rand() * GROUPS.length);
    out.push([g, zipf(GROUPS[g][1]), [1, 0, 0.75, 0.25][Math.floor(rand() * 4)]]);
  }
  return out;
}

const mem = process.memoryUsage();
console.log(`characters=${N.toLocaleString()} questions=${nQuestions} attribute memory=${(attrs.reduce((s, a) => s + a.byteLength, 0) / 1e6).toFixed(1)} MB heap=${(mem.heapUsed / 1e6).toFixed(0)} MB`);

// Both replays must agree before timing means anything.
{
  const answers = makeAnswers(ANSWERS);
  const a = replayNaive(answers), b = replay(answers);
  let maxDiff = 0;
  for (let i = 0; i < N; i++) maxDiff = Math.max(maxDiff, Math.abs(a[i] - b[i]));
  console.log(`folded vs naive replay, max probability difference: ${maxDiff.toExponential(1)}`);
}

for (const [label, fn] of [["naive ", replayNaive], ["folded", replay]])
for (const k of [0, 10, 20, ANSWERS]) {
  const times = [];
  for (let r = 0; r < (k === ANSWERS ? RUNS : 50); r++) {
    const answers = makeAnswers(k);
    const asked = new Set(answers.map(([g, v]) => g * 10000 + v));
    const t0 = performance.now();
    const pi = fn(answers);
    bestQuestion(pi, asked);
    times.push(performance.now() - t0);
  }
  times.sort((a, b) => a - b);
  const pct = (q) => times[Math.min(times.length - 1, Math.floor(q * times.length))].toFixed(1);
  console.log(`${label} answers replayed=${String(k).padStart(2)}  p50=${pct(0.5)} ms  p95=${pct(0.95)} ms  max=${pct(1)} ms`);
}
