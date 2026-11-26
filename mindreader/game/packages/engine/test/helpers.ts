import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { answer, cell, DisplayItem, GameState, KB, loadKB, Manifest, newGame, advance, respondToGuess, rng } from "../src";

export function loadSeed(): KB {
  const dir = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "data", "seed");
  const manifest = JSON.parse(readFileSync(join(dir, "manifest.json"), "utf8")) as Manifest;
  const bin = readFileSync(join(dir, "arrays.bin"));
  const buffer = bin.buffer.slice(bin.byteOffset, bin.byteOffset + bin.byteLength);
  const display = JSON.parse(readFileSync(join(dir, "display.json"), "utf8")) as DisplayItem[];
  return loadKB(manifest, buffer, display);
}

/** A simulated player thinking of character index `target`. */
export function playerAnswer(kb: KB, qi: number, target: number, noise: number, rand: () => number): number {
  const p = cell(kb, qi, target) / 255;
  if (p > 0.3 && p < 0.7) return [0, 1, 2, 3, 4][Math.floor(rand() * 5)];
  const yes = p >= 0.7;
  if (rand() < noise) return yes ? 4 : 0;
  if (rand() < 0.1) return yes ? 1 : 3;
  return yes ? 0 : 4;
}

export interface GameResult {
  won: boolean;
  questions: number;
  guesses: number;
}

export function playGame(kb: KB, target: number, noise: number, seed: number): GameResult {
  const rand = rng(seed * 7919 + 13);
  let s: GameState = advance(kb, newGame(seed));
  let guesses = 0;
  for (let steps = 0; steps < 200; steps++) {
    if (s.status === "asking") {
      const qi = kb.questionIndex.get(s.current!)!;
      s = answer(kb, s, s.current!, playerAnswer(kb, qi, target, noise, rand));
    } else if (s.status === "guessing") {
      guesses++;
      s = respondToGuess(kb, s, s.guess === kb.ids[target]);
    } else {
      return { won: s.status === "won", questions: s.answers.length, guesses };
    }
  }
  throw new Error("game did not finish");
}
