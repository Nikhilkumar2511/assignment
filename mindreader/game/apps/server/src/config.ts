import { randomBytes } from "node:crypto";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const gameRoot = resolve(here, "..", "..", "..");

function env(name: string, fallback: string): string {
  const v = process.env[name];
  return v === undefined || v === "" ? fallback : v;
}

const secret = process.env.TOKEN_SECRET;
if (!secret && process.env.NODE_ENV === "production") {
  throw new Error("TOKEN_SECRET must be set in production (32+ random bytes, e.g. `openssl rand -hex 32`).");
}

export const config = {
  port: Number(env("PORT", "8080")),
  host: env("HOST", "0.0.0.0"),
  snapshotDir: resolve(env("SNAPSHOT_DIR", join(gameRoot, "data", "seed"))),
  webDir: resolve(env("WEB_DIR", join(gameRoot, "apps", "web", "out"))),
  imagesDir: process.env.IMAGES_DIR ? resolve(process.env.IMAGES_DIR) : null,
  imageBaseUrl: env("IMAGE_BASE_URL", "/img/"), // CDN base for thumbnails, ends with "/"
  tokenSecrets: (secret ?? randomBytes(32).toString("hex")).split(",").map((s) => s.trim()), // first signs, all verify
  databaseUrl: process.env.DATABASE_URL || null,
  learningLog: resolve(env("LEARNING_LOG", join(gameRoot, "data", "learning.jsonl"))),
  trustProxy: env("TRUST_PROXY", "true") === "true",
  rateLimitPerMinute: Number(env("RATE_LIMIT_PER_MINUTE", "240")),
  newGamesPerMinute: Number(env("NEW_GAMES_PER_MINUTE", "30")),
  submissionsPerHour: Number(env("SUBMISSIONS_PER_HOUR", "20")),
  autoApproveAfter: Number(env("AUTO_APPROVE_AFTER", "3")),
};
