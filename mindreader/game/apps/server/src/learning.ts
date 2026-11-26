// Where finished games, new-character submissions and takedown requests go.
// * JsonlSink: appends to a file. Used with the seed snapshot and in development.
// * PostgresSink: writes the `games`, `evidence`, `devices`, `submissions` and
//   `takedown_requests` tables from pipeline/schema/001_init.sql. The nightly job folds
//   evidence into the next snapshot.

import { appendFile, mkdir } from "node:fs/promises";
import { dirname } from "node:path";
import { createHmac } from "node:crypto";
import pg from "pg";
import { ANSWER_VALUE, cell, KB } from "@mindreader/engine";

export interface FinishRecord {
  gid: string;
  startedAt: number;
  finishedAt: number;
  kbVersion: number;
  kbSource: string;
  lang: string;
  outcome: "won" | "lost" | "abandoned";
  answers: [number, number][];
  guesses: number[]; // every entity the game guessed, in order
  trueEntityId: number | null;
  newCharacter: { name: string; description: string | null } | null;
  deviceHash: string | null;
  reliability: number | null;
  flagged: string | null;
  country: string | null;
  deviceClass: number | null;
}

export interface TakedownRecord {
  kind: "image" | "likeness" | "data" | "other";
  entityId: number | null;
  url: string | null;
  name: string;
  email: string;
  details: string;
}

export interface Sink {
  finish(r: FinishRecord): Promise<"stored" | "duplicate">;
  takedown(t: TakedownRecord): Promise<void>;
  close(): Promise<void>;
}

// ------------------------------------------------------------------ moderation checks

const BLOCKED = /(https?:\/\/|www\.|\.(com|net|org|io)\b|fuck|shit|bitch|cunt|nigg|fagg|porn|xxx|rape|nazi|hitler|kill yourself)/i;
const ALLOWED = /^[\p{L}\p{M}\p{N} .,'&()\-!?:·]+$/u;

export function checkName(name: string): { ok: boolean; reason?: string; clean: string } {
  const clean = name.replace(/\s+/g, " ").trim();
  if (clean.length < 2 || clean.length > 60) return { ok: false, reason: "length", clean };
  if (!/\p{L}/u.test(clean)) return { ok: false, reason: "no_letters", clean };
  if (!ALLOWED.test(clean)) return { ok: false, reason: "characters", clean };
  if (BLOCKED.test(clean)) return { ok: false, reason: "blocked_word", clean };
  return { ok: true, clean };
}

export function checkText(text: string | null | undefined, max: number): string | null {
  if (!text) return null;
  const clean = text.replace(/\s+/g, " ").trim().slice(0, max);
  return BLOCKED.test(clean) ? null : clean || null;
}

export function hashDevice(deviceId: unknown, secret: string): string | null {
  if (typeof deviceId !== "string" || !/^[A-Za-z0-9_-]{16,64}$/.test(deviceId)) return null;
  return createHmac("sha256", secret).update(`device:${deviceId}`).digest("hex");
}

/** How well this game's answers agree with what the data says about the true character.
 *  Returns a weight for the game's answers, and a flag when they contradict most confident facts. */
export function reliability(kb: KB, entityId: number, answers: [number, number][]): { weight: number; flagged: string | null } {
  const e = kb.entityIndex.get(entityId);
  if (e === undefined) return { weight: 0.5, flagged: null };
  let agree = 0;
  let disagree = 0;
  for (const [qid, code] of answers) {
    const qi = kb.questionIndex.get(qid);
    const v = ANSWER_VALUE[code];
    if (qi === undefined || v === null || v === undefined) continue;
    const p = cell(kb, qi, e) / 255;
    if (p < 0.85 && p > 0.15) continue;
    if (Math.abs(v - p) > 0.6) disagree++;
    else agree++;
  }
  const confident = agree + disagree;
  if (confident >= 6 && disagree / confident > 0.5) {
    return { weight: 0, flagged: `answers contradicted ${disagree} of ${confident} confident facts` };
  }
  return { weight: Math.round(((agree + 1) / (confident + 2)) * 1000) / 1000, flagged: null };
}

// ------------------------------------------------------------------ sinks

export class JsonlSink implements Sink {
  private seen = new Set<string>();
  constructor(private path: string) {}

  private async write(kind: string, data: unknown) {
    await mkdir(dirname(this.path), { recursive: true });
    await appendFile(this.path, JSON.stringify({ kind, at: new Date().toISOString(), ...(data as object) }) + "\n");
  }

  async finish(r: FinishRecord) {
    if (this.seen.has(r.gid)) return "duplicate" as const;
    this.seen.add(r.gid);
    if (this.seen.size > 200_000) this.seen.clear();
    await this.write("game", r);
    return "stored" as const;
  }

  async takedown(t: TakedownRecord) {
    await this.write("takedown", t);
  }

  async close() {}
}

const CODE_TO_SMALLINT = [0, 1, 2, 3, 4];

export class PostgresSink implements Sink {
  private pool: pg.Pool;
  constructor(url: string, private kbSourceForEvidence = "wikidata") {
    this.pool = new pg.Pool({ connectionString: url, max: 5 });
  }

  async finish(r: FinishRecord) {
    const client = await this.pool.connect();
    try {
      await client.query("BEGIN");
      if (r.deviceHash) {
        await client.query(
          `INSERT INTO devices (device_hash, games, reliability) VALUES (decode($1, 'hex'), 1, $2)
           ON CONFLICT (device_hash) DO UPDATE SET games = devices.games + 1,
             reliability = (devices.reliability * devices.games + EXCLUDED.reliability) / (devices.games + 1),
             updated_at = now()`,
          [r.deviceHash, r.reliability ?? 0.5],
        );
      }
      const inserted = await client.query(
        `INSERT INTO games (id, started_at, finished_at, snapshot_version, lang, outcome, n_questions, n_guesses,
                            guessed_entity_id, true_entity_id, answers, device_hash, reliability, device_class, country, flagged)
         VALUES ($1, to_timestamp($2 / 1000.0), to_timestamp($3 / 1000.0), $4, $5, $6, $7, $8, $9, $10, $11,
                 CASE WHEN $12::text IS NULL THEN NULL ELSE decode($12, 'hex') END, $13, $14, $15, $16)
         ON CONFLICT (id) DO NOTHING`,
        [r.gid, r.startedAt, r.finishedAt, r.kbVersion, r.lang, r.outcome, r.answers.length, r.guesses.length,
          r.guesses.at(-1) ?? null, r.trueEntityId, JSON.stringify(r.answers), r.deviceHash, r.reliability,
          r.deviceClass, r.country, r.flagged],
      );
      if (inserted.rowCount === 0) {
        await client.query("ROLLBACK");
        return "duplicate" as const;
      }
      const learnable = r.trueEntityId !== null && !r.flagged && r.kbSource === this.kbSourceForEvidence && (r.reliability ?? 0) > 0;
      if (learnable) {
        const rows = r.answers.filter(([, code]) => ANSWER_VALUE[code] !== null);
        if (rows.length) {
          const values: unknown[] = [];
          const tuples = rows.map(([qid, code], i) => {
            values.push(r.gid, r.trueEntityId, qid, CODE_TO_SMALLINT[code], r.reliability);
            const b = i * 5;
            return `($${b + 1}, $${b + 2}, $${b + 3}, $${b + 4}, $${b + 5})`;
          });
          await client.query(
            `INSERT INTO evidence (game_id, entity_id, question_id, answer, weight)
             SELECT v.g::uuid, v.e::bigint, v.q::int, v.a::smallint, v.w::real
             FROM (VALUES ${tuples.join(", ")}) AS v(g, e, q, a, w)
             WHERE EXISTS (SELECT 1 FROM entities WHERE id = v.e::bigint)
               AND EXISTS (SELECT 1 FROM questions WHERE id = v.q::int)
             ON CONFLICT DO NOTHING`,
            values,
          );
        }
      }
      if (r.newCharacter) {
        const name = checkName(r.newCharacter.name);
        await client.query(
          `INSERT INTO submissions (game_id, name, description, lang, status, auto_checks, reject_reason)
           VALUES ($1, $2, $3, $4, $5, $6, $7)`,
          [r.gid, name.clean.slice(0, 80), r.newCharacter.description, r.lang, name.ok ? "pending" : "rejected",
            JSON.stringify({ name: name.ok ? "ok" : name.reason }), name.ok ? null : `automatic: ${name.reason}`],
        );
      }
      await client.query("COMMIT");
      return "stored" as const;
    } catch (err) {
      await client.query("ROLLBACK");
      throw err;
    } finally {
      client.release();
    }
  }

  async takedown(t: TakedownRecord) {
    await this.pool.query(
      `INSERT INTO takedown_requests (kind, entity_id, url, requester_name, requester_email, details)
       VALUES ($1, (SELECT id FROM entities WHERE id = $2), $3, $4, $5, $6)`,
      [t.kind, t.entityId, t.url, t.name, t.email, t.details],
    );
  }

  async close() {
    await this.pool.end();
  }
}
