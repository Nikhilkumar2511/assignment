// HTTP API (v1). Every game move returns a new signed token; the server keeps no session.

import { existsSync } from "node:fs";
import { join } from "node:path";
import { randomInt } from "node:crypto";
import Fastify, { FastifyInstance, FastifyReply } from "fastify";
import rateLimit from "@fastify/rate-limit";
import fastifyStatic from "@fastify/static";
import { advance, answer, ANSWERS, GameError, GameState, newGame, respondToGuess, undo } from "@mindreader/engine";
import { config as defaultConfig } from "./config";
import { checkName, checkText, FinishRecord, hashDevice, reliability, Sink } from "./learning";
import { NameIndex } from "./search";
import { SnapshotHolder } from "./snapshot";
import { decodeToken, encodeToken, newGameId, TokenData } from "./token";
import { card, gameView, pickLang } from "./view";

type Config = typeof defaultConfig;

const ANSWER_CODES: Record<string, number> = Object.fromEntries(ANSWERS.map((a, i) => [a, i]));

function answerCode(input: unknown): number | null {
  if (typeof input === "number" && Number.isInteger(input) && input >= 0 && input <= 4) return input;
  if (typeof input === "string" && input in ANSWER_CODES) return ANSWER_CODES[input];
  return null;
}

export async function buildApp(cfg: Config, holder: SnapshotHolder, sink: Sink): Promise<FastifyInstance> {
  const app = Fastify({
    trustProxy: cfg.trustProxy,
    bodyLimit: 16 * 1024,
    logger: process.env.NODE_ENV === "test" ? false : { level: process.env.LOG_LEVEL ?? "info" },
  });
  let names = new NameIndex(holder.kb);

  await app.register(rateLimit, { global: true, max: cfg.rateLimitPerMinute, timeWindow: "1 minute" });

  // sendBeacon posts text/plain; accept it as JSON.
  app.addContentTypeParser("text/plain", { parseAs: "string" }, (_req, body, done) => {
    try {
      done(null, JSON.parse(body as string));
    } catch {
      done(null, {});
    }
  });

  const respond = (reply: FastifyReply, data: TokenData) => {
    const kb = holder.kb;
    const token = encodeToken(data, cfg.tokenSecrets);
    return reply.send(gameView(kb, data.s, token, pickLang(data.lang), cfg.imageBaseUrl));
  };

  const load = (token: unknown, reply: FastifyReply): TokenData | null => {
    const data = decodeToken(token, cfg.tokenSecrets);
    if (!data) {
      reply.code(400).send({ error: "bad_token", message: "This game could not be read. Start a new one." });
      return null;
    }
    return data;
  };

  const move = (reply: FastifyReply, data: TokenData, fn: (s: GameState) => GameState) => {
    try {
      return respond(reply, { ...data, s: fn(data.s) });
    } catch (err) {
      if (err instanceof GameError) return reply.code(409).send({ error: err.code, message: err.message });
      throw err;
    }
  };

  // ---------------------------------------------------------------- game

  app.post("/v1/games", { config: { rateLimit: { max: cfg.newGamesPerMinute, timeWindow: "1 minute" } } },
    async (req, reply) => {
      const body = (req.body ?? {}) as { lang?: string };
      const kb = holder.kb;
      const data: TokenData = {
        gid: newGameId(), t0: Date.now(), kbv: kb.version, lang: pickLang(body.lang),
        s: advance(kb, newGame(randomInt(0, 2 ** 31))),
      };
      reply.code(201);
      return respond(reply, data);
    });

  app.post("/v1/games/answer", async (req, reply) => {
    const body = (req.body ?? {}) as { token?: string; questionId?: number; answer?: unknown };
    const data = load(body.token, reply);
    if (!data) return reply;
    const code = answerCode(body.answer);
    if (code === null || typeof body.questionId !== "number") {
      return reply.code(400).send({ error: "bad_request", message: "questionId and answer are required." });
    }
    return move(reply, data, (s) => answer(holder.kb, s, body.questionId!, code));
  });

  app.post("/v1/games/guess", async (req, reply) => {
    const body = (req.body ?? {}) as { token?: string; correct?: boolean };
    const data = load(body.token, reply);
    if (!data) return reply;
    if (typeof body.correct !== "boolean") return reply.code(400).send({ error: "bad_request", message: "correct is required." });
    return move(reply, data, (s) => respondToGuess(holder.kb, s, body.correct!));
  });

  app.post("/v1/games/undo", async (req, reply) => {
    const body = (req.body ?? {}) as { token?: string };
    const data = load(body.token, reply);
    if (!data) return reply;
    return move(reply, data, (s) => undo(holder.kb, s));
  });

  // Called once per finished game: confirms the answer, teaches a new character, or both.
  app.post("/v1/games/finish", { config: { rateLimit: { max: cfg.submissionsPerHour * 3, timeWindow: "1 hour" } } },
    async (req, reply) => {
      const body = (req.body ?? {}) as {
        token?: string; entityId?: number; newCharacter?: { name?: string; description?: string };
        deviceId?: string; deviceClass?: number;
      };
      const data = load(body.token, reply);
      if (!data) return reply;
      const s = data.s;
      if (s.status !== "won" && s.status !== "lost") {
        return reply.code(409).send({ error: "not_finished", message: "The game is still running." });
      }
      const kb = holder.kb;
      let trueId: number | null = s.status === "won" ? s.guess : null;
      let newCharacter: FinishRecord["newCharacter"] = null;
      if (s.status === "lost") {
        if (typeof body.entityId === "number" && kb.entityIndex.has(body.entityId)) trueId = body.entityId;
        else if (body.newCharacter?.name) {
          const name = checkName(body.newCharacter.name);
          if (!name.ok) return reply.code(400).send({ error: "bad_name", message: "That name cannot be used." });
          newCharacter = { name: name.clean, description: checkText(body.newCharacter.description, 140) };
        }
      }
      const rel = trueId !== null ? reliability(kb, trueId, s.answers) : { weight: null, flagged: null };
      const guesses = [...s.wrong, ...(s.status === "won" && s.guess !== null ? [s.guess] : [])];
      const result = await sink.finish({
        gid: data.gid, startedAt: data.t0, finishedAt: Date.now(), kbVersion: data.kbv, kbSource: kb.source,
        lang: data.lang, outcome: s.status, answers: s.answers, guesses, trueEntityId: trueId, newCharacter,
        deviceHash: hashDevice(body.deviceId, cfg.tokenSecrets[0]), reliability: rel.weight, flagged: rel.flagged,
        country: typeof req.headers["cf-ipcountry"] === "string" ? req.headers["cf-ipcountry"].slice(0, 2) : null,
        deviceClass: typeof body.deviceClass === "number" ? Math.max(0, Math.min(2, Math.round(body.deviceClass))) : null,
      });
      return reply.send({
        ok: true,
        duplicate: result === "duplicate",
        character: trueId !== null ? card(kb, trueId, pickLang(data.lang), cfg.imageBaseUrl) : null,
        submitted: newCharacter !== null,
      });
    });

  // sendBeacon from the page when a player leaves mid-game: counts drop-off per question.
  app.post("/v1/games/abandon", async (req, reply) => {
    const body = (req.body ?? {}) as { token?: string };
    const data = decodeToken(body.token, cfg.tokenSecrets);
    if (data && (data.s.status === "asking" || data.s.status === "guessing") && data.s.answers.length > 0) {
      await sink.finish({
        gid: data.gid, startedAt: data.t0, finishedAt: Date.now(), kbVersion: data.kbv, kbSource: holder.kb.source,
        lang: data.lang, outcome: "abandoned", answers: data.s.answers, guesses: data.s.wrong, trueEntityId: null,
        newCharacter: null, deviceHash: null, reliability: null, flagged: null, country: null, deviceClass: null,
      });
    }
    return reply.code(204).send();
  });

  // ---------------------------------------------------------------- lookups

  app.get("/v1/search", async (req, reply) => {
    const q = req.query as { q?: string; lang?: string; limit?: string };
    const limit = Math.max(1, Math.min(20, Number(q.limit ?? 8) || 8));
    reply.header("cache-control", "public, max-age=300");
    return { results: names.search(String(q.q ?? "").slice(0, 60), pickLang(q.lang), limit, cfg.imageBaseUrl) };
  });

  app.post("/v1/takedown", { config: { rateLimit: { max: 5, timeWindow: "1 hour" } } }, async (req, reply) => {
    const b = (req.body ?? {}) as Record<string, unknown>;
    const kind = ["image", "likeness", "data", "other"].includes(String(b.kind)) ? (b.kind as "image") : null;
    const email = typeof b.email === "string" && /^[^\s@]{1,64}@[^\s@]{1,190}\.[^\s@]{2,}$/.test(b.email) ? b.email : null;
    const name = typeof b.name === "string" ? b.name.trim().slice(0, 120) : "";
    const details = typeof b.details === "string" ? b.details.trim().slice(0, 4000) : "";
    if (!kind || !email || name.length < 2 || details.length < 10) {
      return reply.code(400).send({ error: "bad_request", message: "Please fill in every field." });
    }
    await sink.takedown({
      kind, email, name, details,
      entityId: typeof b.entityId === "number" ? b.entityId : null,
      url: typeof b.url === "string" ? b.url.slice(0, 500) : null,
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

  // ---------------------------------------------------------------- static web app and images

  if (cfg.imagesDir && existsSync(cfg.imagesDir)) {
    await app.register(fastifyStatic, {
      root: cfg.imagesDir, prefix: "/img/", decorateReply: false, immutable: true, maxAge: "365d",
    });
  }
  if (existsSync(cfg.webDir)) {
    await app.register(fastifyStatic, {
      root: cfg.webDir,
      prefix: "/",
      extensions: ["html"],
      cacheControl: false, // headers are set below per file type
      setHeaders: (res, path) => {
        if (path.includes(`${join("_next", "static")}`)) res.setHeader("cache-control", "public, max-age=31536000, immutable");
        else if (path.endsWith("sw.js") || path.endsWith(".html") || path.endsWith(".webmanifest")) res.setHeader("cache-control", "no-cache");
        else res.setHeader("cache-control", "public, max-age=86400");
      },
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
