// Stateless game sessions: the whole game state travels in an HMAC-signed token.
// A tampered token fails verification; an old token simply replays the game from that
// point (the same as undo), so there is nothing to protect beyond integrity.

import { createHmac, randomUUID, timingSafeEqual } from "node:crypto";
import type { GameState } from "@mindreader/engine";

export interface TokenData {
  gid: string; // game id (uuid), used once by /finish
  t0: number; // start time, ms
  kbv: number; // snapshot version the game started on
  lang: string;
  s: GameState;
}

const MAX_TOKEN_LENGTH = 6000;

function b64(buf: Buffer): string {
  return buf.toString("base64url");
}

function sign(payload: string, secret: string): string {
  return b64(createHmac("sha256", secret).update(payload).digest());
}

export function encodeToken(data: TokenData, secrets: string[]): string {
  const payload = b64(Buffer.from(JSON.stringify(data)));
  return `${payload}.${sign(payload, secrets[0])}`;
}

export function decodeToken(token: unknown, secrets: string[]): TokenData | null {
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
    const data = JSON.parse(Buffer.from(payload, "base64url").toString("utf8")) as TokenData;
    if (!data || typeof data.gid !== "string" || !data.s || !Array.isArray(data.s.answers)) return null;
    return data;
  } catch {
    return null;
  }
}

export function newGameId(): string {
  return randomUUID();
}
