// The engine running in the browser on the built-in seed snapshot. Loaded on demand, so it
// is not part of the first page load. Same GameView shape as the game service.

import {
  advance, answer, confidence, DisplayItem, GameState, KB, loadKB, Manifest, newGame, respondToGuess, RULES, undo,
} from "@mindreader/engine";
import type { CharacterCard, FinishResult, GameClient, GameView } from "./client";
import type { Lang } from "./i18n";

function toCard(d: DisplayItem, lang: Lang): CharacterCard {
  return {
    id: d.id,
    name: d.n[lang] ?? d.n.en ?? "?",
    description: d.d[lang] ?? d.d.en ?? "",
    kind: d.k,
    theme: d.t ?? null,
    image: null,
    wikidataUrl: null,
  };
}

function norm(s: string) {
  return s.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^\p{L}\p{M}\p{N}]+/gu, " ").trim();
}

export class LocalGame implements GameClient {
  mode = "offline" as const;
  characters: number;
  private lang: Lang = "en";

  private constructor(private kb: KB) {
    this.characters = kb.n;
  }

  static async load(): Promise<LocalGame> {
    const [m, b, d] = await Promise.all([
      fetch("/offline/manifest.json").then((r) => r.json()),
      fetch("/offline/arrays.bin").then((r) => r.arrayBuffer()),
      fetch("/offline/display.json").then((r) => r.json()),
    ]);
    return new LocalGame(loadKB(m as Manifest, b, d as DisplayItem[]));
  }

  private view(s: GameState): GameView {
    const kb = this.kb;
    let question = null;
    if (s.status === "asking" && s.current !== null) {
      const q = kb.questions[kb.questionIndex.get(s.current)!];
      question = { id: s.current, text: q.text[this.lang] ?? q.text.en ?? "" };
    }
    const guessIdx = s.guess !== null ? kb.entityIndex.get(s.guess) : undefined;
    return {
      token: JSON.stringify(s),
      status: s.status,
      step: s.answers.length + (s.status === "asking" ? 1 : 0),
      question,
      guess: s.status === "guessing" && guessIdx !== undefined ? toCard(kb.display![guessIdx], this.lang) : null,
      confidence: s.status === "asking" || s.status === "guessing" ? confidence(kb, s) : 0,
      questionsAsked: s.answers.length,
      wrongGuesses: s.wrong.length,
      maxGuesses: RULES.maxGuesses,
      maxQuestions: RULES.maxQuestions,
      canUndo: (s.status === "asking" || s.status === "guessing") && s.answers.length > 0,
    };
  }

  private state(v: GameView): GameState {
    return JSON.parse(v.token) as GameState;
  }

  async start(lang: Lang) {
    this.lang = lang;
    const seed = crypto.getRandomValues(new Uint32Array(1))[0];
    return this.view(advance(this.kb, newGame(seed)));
  }
  async answer(v: GameView, code: number) {
    const s = this.state(v);
    return this.view(answer(this.kb, s, s.current!, code));
  }
  async guess(v: GameView, correct: boolean) {
    return this.view(respondToGuess(this.kb, this.state(v), correct));
  }
  async undo(v: GameView) {
    return this.view(undo(this.kb, this.state(v)));
  }
  async finish(v: GameView, opts: { entityId?: number; newCharacter?: { name: string; description: string } }): Promise<FinishResult> {
    const s = this.state(v);
    const id = s.status === "won" ? s.guess : opts.entityId ?? null;
    const idx = id !== null && id !== undefined ? this.kb.entityIndex.get(id) : undefined;
    return { ok: true, character: idx !== undefined ? toCard(this.kb.display![idx], this.lang) : null, submitted: false };
  }
  async search(q: string, lang: Lang) {
    const n = norm(q);
    if (n.length < 2) return [];
    const hits: { i: number; score: number }[] = [];
    this.kb.display!.forEach((d, i) => {
      for (const name of Object.values(d.n)) {
        const pos = norm(name ?? "").indexOf(n);
        if (pos >= 0) {
          hits.push({ i, score: pos === 0 ? 0 : 1 });
          break;
        }
      }
    });
    return hits
      .sort((a, b) => a.score - b.score || this.kb.prior[b.i] - this.kb.prior[a.i])
      .slice(0, 8)
      .map((h) => toCard(this.kb.display![h.i], lang));
  }
  abandon() {}
}
