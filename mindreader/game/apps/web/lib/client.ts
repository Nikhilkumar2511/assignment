// Two ways to play, behind one interface:
// * RemoteGame: the game service (full character set, learning).
// * LocalGame: the same engine in the browser with the built-in seed (offline / demo).

import type { Lang } from "./i18n";

export interface CharacterCard {
  id: number;
  name: string;
  description: string;
  kind: "real" | "fictional";
  theme: string | null;
  image: {
    avif: { 256: string; 512: string };
    webp: { 256: string; 512: string };
    author: string | null;
    license: string | null;
    licenseUrl: string | null;
    creditUrl: string | null;
  } | null;
  wikidataUrl: string | null;
}

export interface GameView {
  token: string;
  status: "asking" | "guessing" | "won" | "lost";
  step: number;
  question: { id: number; text: string } | null;
  guess: CharacterCard | null;
  confidence: number;
  questionsAsked: number;
  wrongGuesses: number;
  maxGuesses: number;
  maxQuestions: number;
  canUndo: boolean;
}

export interface FinishResult {
  ok: boolean;
  character: CharacterCard | null;
  submitted: boolean;
}

export interface GameClient {
  mode: "online" | "offline";
  characters: number;
  start(lang: Lang): Promise<GameView>;
  answer(view: GameView, code: number): Promise<GameView>;
  guess(view: GameView, correct: boolean): Promise<GameView>;
  undo(view: GameView): Promise<GameView>;
  finish(view: GameView, opts: { entityId?: number; newCharacter?: { name: string; description: string } }): Promise<FinishResult>;
  search(q: string, lang: Lang): Promise<CharacterCard[]>;
  abandon(view: GameView): void;
}

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

const API = process.env.NEXT_PUBLIC_API_BASE ?? "";

async function call<T>(path: string, body?: unknown, timeoutMs = 8000): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${API}${path}`, {
      method: body === undefined ? "GET" : "POST",
      headers: body === undefined ? undefined : { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: ctrl.signal,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new ApiError(res.status, data.error ?? "error", data.message ?? "Request failed");
    return data as T;
  } finally {
    clearTimeout(timer);
  }
}

export class RemoteGame implements GameClient {
  mode = "online" as const;
  constructor(public characters: number, private device: string, private deviceClass: number) {}
  start(lang: Lang) {
    return call<GameView>("/v1/games", { lang });
  }
  answer(v: GameView, code: number) {
    return call<GameView>("/v1/games/answer", { token: v.token, questionId: v.question!.id, answer: code });
  }
  guess(v: GameView, correct: boolean) {
    return call<GameView>("/v1/games/guess", { token: v.token, correct });
  }
  undo(v: GameView) {
    return call<GameView>("/v1/games/undo", { token: v.token });
  }
  finish(v: GameView, opts: { entityId?: number; newCharacter?: { name: string; description: string } }) {
    return call<FinishResult>("/v1/games/finish", { token: v.token, ...opts, deviceId: this.device, deviceClass: this.deviceClass });
  }
  async search(q: string, lang: Lang) {
    const r = await call<{ results: CharacterCard[] }>(`/v1/search?q=${encodeURIComponent(q)}&lang=${lang}`);
    return r.results;
  }
  abandon(v: GameView) {
    if (typeof navigator !== "undefined" && navigator.sendBeacon) {
      navigator.sendBeacon(`${API}/v1/games/abandon`, JSON.stringify({ token: v.token }));
    }
  }
}

/** Connects to the game service, or falls back to the built-in seed when it cannot. */
export async function connect(device: string, deviceClass: number): Promise<GameClient> {
  if (process.env.NEXT_PUBLIC_MODE !== "local") {
    try {
      const h = await call<{ snapshot: { characters: number } }>("/v1/health", undefined, 4000);
      return new RemoteGame(h.snapshot.characters, device, deviceClass);
    } catch {
      /* fall through to offline play */
    }
  }
  const { LocalGame } = await import("./local");
  return LocalGame.load();
}
