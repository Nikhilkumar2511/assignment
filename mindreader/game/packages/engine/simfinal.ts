import { readFileSync } from "node:fs";
import { loadKB, DisplayItem, Manifest } from "./src";
import { playGame } from "./test/helpers";
const dir = "/home/user/data/snap30k";
const m = JSON.parse(readFileSync(dir + "/manifest.json", "utf8")) as Manifest;
const b = readFileSync(dir + "/arrays.bin");
const d = JSON.parse(readFileSync(dir + "/display.json", "utf8")) as DisplayItem[];
let t0 = performance.now();
const kb = loadKB(m, b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength), d);
console.log(`loaded ${kb.n} characters, ${kb.questions.length} questions in ${(performance.now() - t0).toFixed(0)} ms`);
const order = Array.from({ length: kb.n }, (_, i) => i).sort((a, b) => kb.prior[b] - kb.prior[a]);
const sets: [string, number[]][] = [
  ["top 200 most popular", order.slice(0, 200)],
  ["200 Indian (random)", (JSON.parse(readFileSync("/tmp/claude-0/-home-user-assignment/20e9514d-5db6-5bbd-a6ba-406394f9935d/scratchpad/indian_idx.json","utf8")) as number[]).filter((_, i, a) => i % Math.floor(a.length / 200) === 0).slice(0, 200)],
  ["300 random", Array.from({ length: 300 }, (_, i) => order[(i * 997) % kb.n])],
];
for (const [label, targets] of sets) {
  let wins = 0, qs = 0, first = 0, within20 = 0;
  t0 = performance.now();
  let steps = 0;
  for (const [i, t] of targets.entries()) {
    const r = playGame(kb, t, 0.05, i + 11);
    wins += +r.won; qs += r.questions; first += +(r.won && r.guesses === 1); within20 += +(r.won && r.questions <= 20);
    steps += r.questions + r.guesses;
  }
  const ms = (performance.now() - t0) / steps;
  console.log(`${label}: win ${(100 * wins / targets.length).toFixed(1)}% | first guess ${(100 * first / targets.length).toFixed(1)}% | won within 20 q ${(100 * within20 / targets.length).toFixed(1)}% | avg questions ${(qs / targets.length).toFixed(1)} | ${ms.toFixed(1)} ms per move`);
}
