import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import type { FastifyInstance } from "fastify";
import { cell } from "@mindreader/engine";
import { buildApp } from "../src/app";
import { config } from "../src/config";
import { JsonlSink } from "../src/learning";
import { SnapshotHolder } from "../src/snapshot";

process.env.NODE_ENV = "test";
const dir = mkdtempSync(join(tmpdir(), "mr-"));
const cfg = { ...config, webDir: join(dir, "no-web"), learningLog: join(dir, "learning.jsonl"), tokenSecrets: ["test-secret"],
  newGamesPerMinute: 1000, rateLimitPerMinute: 10000, submissionsPerHour: 1000 };
const holder = new SnapshotHolder(config.snapshotDir);
let app: FastifyInstance;

beforeAll(async () => {
  await holder.reload();
  app = await buildApp(cfg, holder, new JsonlSink(cfg.learningLog));
});
afterAll(async () => app.close());

const post = async (url: string, payload: object) => {
  const res = await app.inject({ method: "POST", url, payload });
  return { status: res.statusCode, body: res.json() };
};

/** Plays as someone thinking of `name`, answering from the data. */
async function playAs(name: string) {
  const kb = holder.kb;
  const target = kb.display!.findIndex((d) => d.n.en === name);
  let g = (await post("/v1/games", { lang: "en" })).body;
  for (let i = 0; i < 60 && g.status === "asking"; i++) {
    const p = cell(kb, kb.questionIndex.get(g.question.id)!, target) / 255;
    const answer = p > 0.6 ? "yes" : p < 0.4 ? "no" : "dont_know";
    g = (await post("/v1/games/answer", { token: g.token, questionId: g.question.id, answer })).body;
  }
  return g;
}

describe("game API", () => {
  it("plays a full game and wins", async () => {
    const g = await playAs("Virat Kohli");
    expect(g.status).toBe("guessing");
    expect(g.guess.name).toBe("Virat Kohli");
    expect(g.guess.description).toMatch(/cricket/i);
    const won = await post("/v1/games/guess", { token: g.token, correct: true });
    expect(won.body.status).toBe("won");
    const fin = await post("/v1/games/finish", { token: won.body.token, deviceId: "abcdefghijklmnop1234" });
    expect(fin.body).toMatchObject({ ok: true, duplicate: false, character: { name: "Virat Kohli" } });
    const again = await post("/v1/games/finish", { token: won.body.token });
    expect(again.body.duplicate).toBe(true);
    const log = readFileSync(cfg.learningLog, "utf8").trim().split("\n").map((l) => JSON.parse(l));
    const rec = log.find((r) => r.kind === "game" && r.outcome === "won");
    expect(rec.reliability).toBeGreaterThan(0.8);
    expect(rec.deviceHash).toMatch(/^[0-9a-f]{64}$/);
    expect(JSON.stringify(rec)).not.toContain("abcdefghijklmnop1234"); // raw device id never stored
  });

  it("rejects tampered tokens", async () => {
    const g = (await post("/v1/games", {})).body;
    const [payload, mac] = g.token.split(".");
    const forged = Buffer.from(JSON.stringify({ ...JSON.parse(Buffer.from(payload, "base64url").toString()), s: { status: "won" } }))
      .toString("base64url");
    const res = await post("/v1/games/answer", { token: `${forged}.${mac}`, questionId: g.question.id, answer: "yes" });
    expect(res.status).toBe(400);
  });

  it("undo returns the previous question; stale answers are refused", async () => {
    const g0 = (await post("/v1/games", {})).body;
    const g1 = (await post("/v1/games/answer", { token: g0.token, questionId: g0.question.id, answer: "no" })).body;
    const back = (await post("/v1/games/undo", { token: g1.token })).body;
    expect(back.question.id).toBe(g0.question.id);
    expect(back.step).toBe(1);
    const stale = await post("/v1/games/answer", { token: g1.token, questionId: g0.question.id, answer: "yes" });
    expect(stale.status).toBe(409);
  });

  it("loses after three wrong guesses and accepts a new character for moderation", async () => {
    let g = (await post("/v1/games", {})).body;
    for (let i = 0; i < 80 && g.status !== "lost"; i++) {
      g = g.status === "asking"
        ? (await post("/v1/games/answer", { token: g.token, questionId: g.question.id, answer: "dont_know" })).body
        : (await post("/v1/games/guess", { token: g.token, correct: false })).body;
    }
    expect(g.status).toBe("lost");
    expect(g.questionsAsked).toBeLessThanOrEqual(40);
    const bad = await post("/v1/games/finish", { token: g.token, newCharacter: { name: "visit www.spam.com" } });
    expect(bad.status).toBe(400);
    const ok = await post("/v1/games/finish", { token: g.token, newCharacter: { name: "Detective Conan", description: "Boy detective" } });
    expect(ok.body).toMatchObject({ ok: true, submitted: true });
  });

  it("searches names", async () => {
    const res = await app.inject({ method: "GET", url: "/v1/search?q=kohli" });
    expect(res.json().results[0].name).toBe("Virat Kohli");
    const short = await app.inject({ method: "GET", url: "/v1/search?q=k" });
    expect(short.json().results).toEqual([]);
  });

  it("validates takedown requests", async () => {
    expect((await post("/v1/takedown", { kind: "image" })).status).toBe(400);
    const ok = await post("/v1/takedown", { kind: "image", name: "Jane Doe", email: "jane@example.org",
      details: "This photo of me is used without permission.", entityId: 1 });
    expect(ok.status).toBe(201);
  });

  it("reports health", async () => {
    const res = await app.inject({ method: "GET", url: "/v1/health" });
    expect(res.json().snapshot.source).toBe("seed");
    expect(res.json().snapshot.characters).toBeGreaterThan(300);
  });
});
