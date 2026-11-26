// What the client receives after every move.

import { confidence, DisplayItem, GameState, KB, Lang, RULES } from "@mindreader/engine";

export const LANGS: Lang[] = ["en", "hi", "es", "pt", "ja", "fr", "ar"];

export function pickLang(input: unknown): Lang {
  return LANGS.includes(input as Lang) ? (input as Lang) : "en";
}

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

export function card(kb: KB, id: number, lang: Lang, imageBase: string): CharacterCard | null {
  const i = kb.entityIndex.get(id);
  if (i === undefined || !kb.display) return null;
  return cardFromDisplay(kb.display[i], lang, imageBase, kb.source);
}

export function cardFromDisplay(d: DisplayItem, lang: Lang, imageBase: string, source: string): CharacterCard {
  const img = d.img;
  const url = (size: number, ext: string) => `${imageBase}${img!.p.replace(/^img\//, "")}-${size}.${ext}`;
  return {
    id: d.id,
    name: d.n[lang] ?? d.n.en ?? Object.values(d.n)[0] ?? "?",
    description: d.d[lang] ?? d.d.en ?? "",
    kind: d.k,
    theme: d.t ?? null,
    image: img
      ? {
          avif: { 256: url(256, "avif"), 512: url(512, "avif") },
          webp: { 256: url(256, "webp"), 512: url(512, "webp") },
          author: img.a ?? null,
          license: img.l ?? null,
          licenseUrl: img.lu ?? null,
          creditUrl: img.c ?? null,
        }
      : null,
    wikidataUrl: source === "wikidata" ? `https://www.wikidata.org/wiki/Q${d.id}` : null,
  };
}

export interface GameView {
  token: string;
  status: GameState["status"];
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

export function gameView(kb: KB, s: GameState, token: string, lang: Lang, imageBase: string): GameView {
  let question: GameView["question"] = null;
  if (s.status === "asking" && s.current !== null) {
    const qi = kb.questionIndex.get(s.current);
    const q = qi === undefined ? null : kb.questions[qi];
    question = { id: s.current, text: q ? q.text[lang] ?? q.text.en ?? "" : "" };
  }
  return {
    token,
    status: s.status,
    step: s.answers.length + (s.status === "asking" ? 1 : 0),
    question,
    guess: s.status === "guessing" && s.guess !== null ? card(kb, s.guess, lang, imageBase) : null,
    confidence: s.status === "asking" || s.status === "guessing" ? Math.round(confidence(kb, s) * 1000) / 1000 : 0,
    questionsAsked: s.answers.length,
    wrongGuesses: s.wrong.length,
    maxGuesses: RULES.maxGuesses,
    maxQuestions: RULES.maxQuestions,
    canUndo: (s.status === "asking" || s.status === "guessing") && s.answers.length > 0,
  };
}
