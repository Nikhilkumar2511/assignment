# MindReader: the game

Think of a famous person or character; MindReader asks questions and guesses who it is.

| Part | Folder | What it is |
|---|---|---|
| Engine | `packages/engine` | TypeScript Bayesian engine: posterior over all characters, next question by expected information gain over the top 2,000, guess rules, undo |
| Game service | `apps/server` | Fastify API with stateless signed game tokens, learning, search, takedown form; also serves the web app |
| Web app | `apps/web` | Next.js static export, installable PWA: WebGL2 nebula, orb mascot, card-flip reveal, share card, 7 languages, offline play |
| Seed data | `data/seed` | 247 hand-tagged characters, 108 questions (also bundled in the app for offline play) |

The full Wikidata character set (about 550,000) is built by `../pipeline` and loaded as a snapshot (below).

## Run locally

```bash
cd mindreader/game
npm ci
npm run build                 # web app (static export) + game service bundle
npm start                     # http://localhost:8080  (seed data, learning log in data/learning.jsonl)
```

Development with hot reload: `npm run dev:server` (port 8080) and, in a second terminal,
`NEXT_PUBLIC_API_BASE=http://localhost:8080 npm run dev:web` (port 3000).

## Test

```bash
npm test                                          # engine (13 tests) + API (7 tests)
npm run bench -w @mindreader/engine -- 500000 8   # latency at 500k characters
```

## Configuration (game service)

| Variable | Default | Meaning |
|---|---|---|
| `TOKEN_SECRET` | random in development, **required in production** | HMAC key for game tokens. Comma-separate several to rotate: the first signs, all verify. |
| `SNAPSHOT_DIR` | `data/seed` | Folder with `manifest.json`, `arrays.bin`, `display.json` |
| `DATABASE_URL` | none | Postgres with `../pipeline/schema/001_init.sql`. Without it, games go to `LEARNING_LOG`. |
| `LEARNING_LOG` | `data/learning.jsonl` | Finished games, submissions and takedown requests when there is no database |
| `IMAGE_BASE_URL` | `/img/` | Where thumbnails are served from (your CDN or R2 bucket URL) |
| `IMAGES_DIR` | none | Serve thumbnails from this folder under `/img/` (when not on a CDN) |
| `ADMIN_TOKEN` | none | Enables `POST /v1/admin/reload` to load a new snapshot without a restart |
| `RATE_LIMIT_PER_MINUTE` | 240 | Requests per IP per minute; new games are limited to `NEW_GAMES_PER_MINUTE` (30) |
| `PORT`, `HOST`, `TRUST_PROXY` | 8080, 0.0.0.0, true | |

## Load the full character set

```bash
cd mindreader/pipeline
python -m mrpipe apidump --work work --out work/api-dump.json.gz   # or use the official dump (deliverable 2)
MR_TARGET_REAL=433000 MR_TARGET_FICTIONAL=135000 MR_TYPED_PREFILTER=0 \
  python -m mrpipe all --work work --dump work/api-dump.json.gz --dsn $DATABASE_URL
python -m mrpipe images --work work --dsn $DATABASE_URL                # optional: Commons photos
python -c "from mrpipe.snapshot import export_from_postgres as e; print(e('$DATABASE_URL', 'snapshot'))"
```

Point the service at it with `SNAPSHOT_DIR=/path/to/snapshot` and restart, or call `POST /v1/admin/reload`
with `Authorization: Bearer $ADMIN_TOKEN`. The snapshot needs about 400 MB of RAM at 550k characters.

## Deploy

One Docker image serves both the app and the API (`Dockerfile`). It runs as a non-root user and needs no disk except
the snapshot.

- **Fly.io**: `fly launch --no-deploy`, set secrets as in `fly.toml`, `fly deploy`.
- **Render**: New > Blueprint with `render.yaml`.
- Put a CDN (Cloudflare) in front: `/_next/static/*` is served `immutable` for a year, pages are `no-cache`.
