// Per-request latency at production scale: replay the answers, pick the next question.
// npm run bench -- 500000 8
import { advance, answer, GameState, newGame } from "../src";
import { synthetic } from "../test/synthetic";

const n = Number(process.argv[2] ?? 500000);
const scale = Number(process.argv[3] ?? 8);
let t0 = performance.now();
const kb = synthetic(n, 1, scale);
console.log(`built ${n.toLocaleString()} characters, ${kb.questions.length} questions in ${((performance.now() - t0) / 1000).toFixed(1)} s`);

const times: number[][] = [[], [], [], []]; // by answers replayed: 0-9, 10-19, 20-29, 30-39
for (let g = 0; g < 6; g++) {
  let s: GameState = advance(kb, newGame(g + 1));
  while (s.status === "asking" && s.answers.length < 39) {
    const code = [0, 4, 4, 2, 1][(s.answers.length + g) % 5];
    t0 = performance.now();
    s = answer(kb, s, s.current!, code);
    const dt = performance.now() - t0;
    times[Math.min(3, Math.floor(s.answers.length / 10))].push(dt);
    if (s.status === "guessing") s = { ...s, status: "asking", wrong: [...s.wrong], current: null } as GameState;
    if (s.status === "asking" && s.current === null) s = advance(kb, s);
  }
}
times.forEach((arr, i) => {
  if (!arr.length) return;
  arr.sort((a, b) => a - b);
  const p = (q: number) => arr[Math.min(arr.length - 1, Math.floor(q * arr.length))].toFixed(0);
  console.log(`answers ${i * 10}-${i * 10 + 9}: p50 ${p(0.5)} ms, p95 ${p(0.95)} ms, max ${p(1)} ms (${arr.length} requests)`);
});
