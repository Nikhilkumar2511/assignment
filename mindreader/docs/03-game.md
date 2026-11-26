# MindReader: deliverables 3 to 7 in one build, the playable game

Code: `game/` (engine, game service, web app, Docker), `pipeline/mrpipe/apidump.py` and `pipeline/mrpipe/snapshot.py` (data to game).
How to run, configure and deploy: [`../game/README.md`](../game/README.md).

## 1. Assumptions

1. **One service, one image.** The game service serves both the API and the static web app, so a single container on Fly.io or Render is enough to start. A CDN goes in front later.
2. **No Redis** (your decision in deliverable 1). Game state travels in an HMAC-signed token; any instance can answer any request.
3. **Data.** The seed (247 hand-tagged characters, 108 questions) is built in and also powers offline play. The full Wikidata set is fetched with `apidump` from QLever, because this environment cannot download the 145 GB dump, then built by the deliverable 2 pipeline and exported as a snapshot.
4. **Wikidata has fewer fictional characters than the spec assumed.** Under the fictional, mythology, deity and Pokémon roots there are 132,980 items in total, only 58,209 of them with a Wikipedia article. To pass 500k characters, the split is about 433k real people (8 or more Wikipedia sitelinks) plus all of the roughly 133k fictional characters.
5. **Popularity uses sitelinks only for now.** The pageview dumps are on a host this environment cannot reach. The pipeline adds pageviews when you run it where `dumps.wikimedia.org` is reachable.
6. **Mascot.** An original orb character drawn in SVG ("Mira"), not a genie. You approved this in deliverable 1.
7. **Question text is English** for the seed and the first Wikidata build, until `mrpipe i18n` runs, which needs the API key you approved. The interface itself is fully translated into the 7 languages.
8. **Photos.** Real people get Commons photos after `mrpipe images` runs; Commons is reachable from this environment. Everyone else gets a generated card.

## 2. What the spec asked for, and where it is

| Spec item | Where | Status |
|---|---|---|
| Posterior from popularity prior, soft likelihoods | `packages/engine/src/engine.ts` `posterior` | Done. 12% noise floor: one wrong answer lowers a character by about 7x and never removes it. |
| Next question by expected information gain over top K = 2,000 | `questionGains` | Done. Exact bucket sums for value questions, per-row scoring for trait cells. |
| Skip near-duplicate questions | `candidateQuestions` (`dup` clusters) | Done. The nightly job fills `questions.dup_cluster`. |
| Guess at 0.85 or question 20; keep asking; max 3 guesses or 40 questions | `RULES`, `advance` | Done, tested. |
| Undo | `undo` + `POST /v1/games/undo` | Done, tested. |
| p95 under 150 ms per question | `npm run bench` | 105 to 132 ms p95 at 500,000 characters and 2,875 questions (single core). |
| Typeahead to pick the right character; submit a new one | `components/Teach.tsx`, `/v1/search`, `/v1/games/finish` | Done; new names go to `submissions` as pending, with automatic name checks. |
| Bayesian count updates, reliability weighting, rate limits | `apps/server/src/learning.ts`, `@fastify/rate-limit` | Evidence rows weighted by per-game reliability; contradicting games are flagged and not learned from. |
| WebGL nebula under 150 KB | `components/Nebula.tsx` | About 4 KB, raw WebGL2, no library. |
| 60 fps desktop, 30 fps low-end, static on reduced motion or low battery, paused when hidden | `Nebula.tsx` governor | Done. A frame-time watchdog lowers resolution, then stops the shader. |
| Mascot that thinks, smirks, gasps | `components/Mascot.tsx` + CSS | idle, thinking, confident (smirk), surprised (gasp), happy, sad |
| Reveal: card flip, glow burst, confetti, picture fades in | `Game.tsx` reveal + CSS `.flip`, `.glow-burst`, `lib/effects.ts` | Done. Confetti is skipped when motion is off. |
| Share card | `lib/effects.ts` `shareResult` | 1080 x 1350 PNG via the Web Share API; on desktop, copy plus download |
| Layouts 360 px, tablet portrait and landscape, desktop | `globals.css` | Screenshots checked at all four |
| WCAG 2.1 AA: keyboard, screen reader, high contrast | Keys 1 to 5, Y/N, U; `aria-live`, focus moves to each new question; high-contrast toggle, `prefers-contrast`, `forced-colors` | Done |
| PWA with offline shell | `public/manifest.webmanifest`, generated `sw.js` | Installable. Offline it plays the 247 built-in characters with the same engine. |
| Takedown form; credit Wikidata, Wikipedia, Wikimedia | `/takedown`, `/about`, footer, photo captions | Done |
| Analytics without personal data | `games` rows; `/v1/games/abandon` beacon for drop-off per question | No IP stored; the device id is stored only as a keyed hash |

## 3. Tests run, and their results

| Test | Result |
|---|---|
| Engine unit tests (`npm test -w @mindreader/engine`) | 13 passed: posterior, noise tolerance, group questions, top-K, duplicate skipping, undo, guess and loss rules, determinism |
| Seed, 247 characters, 5% wrong answers | 90% or more wins (test threshold) |
| Synthetic 1,000-character sample, 5% wrong answers | 80% or more of popular characters within 20 questions; 80% or more wins overall within 40 |
| API tests (`npm test -w @mindreader/server`) | 7 passed: full game, tampered token refused, undo, stale answer refused, loss plus moderated new name, search, takedown validation |
| Snapshot exporter, pipeline Postgres to engine | Fixture database exported and played. Kohli in 2 questions, Naruto in 9, Gandhi in 3. |
| Browser play-through (Playwright) | Won at 360 px (Shah Rukh Khan, 16 questions), 768 px (Naruto, 9), 1024 px (Messi, 11), 1366 px (Elsa, 9). No console errors. |
| Mid-range Android profile (4x CPU slowdown, 4G) | First paint 492 ms; Start usable at about 1.9 s (a tap before that is queued); answer round trip 184 ms |
| Arabic | Page switches to right to left; mixed-direction text renders correctly |
| High contrast + reduced motion | Shader off, static gradient, losing path, typeahead and teaching all work |
| Offline (static files only, no API) | Falls back to the built-in engine and guessed Messi in 11 questions |
| Production runtime (production dependencies only) | Refuses to start without `TOKEN_SECRET`; serves the app and API with it |

## 4. What you should test

1. `cd mindreader/game && npm ci && npm test && npm run build && npm start`, then open http://localhost:8080 on your phone, using your computer's LAN address.
2. Play 10 games each with real people and fictional characters you know. Note any question that reads oddly; question wording is data, and can be fixed in `question_texts`.
3. On a real mid-range Android phone over 4G, check that the Start button appears quickly, the background stays smooth, and turning on battery saver or reduced motion switches to the static gradient.
4. Install the PWA (browser menu, then Install), turn on airplane mode, reopen it, and play an offline game.
5. Use a screen reader (TalkBack or VoiceOver) for one full game, then play one using only the keyboard.
6. Deploy with `fly deploy` or the Render blueprint, set `TOKEN_SECRET`, and run `/v1/health`.
7. After the full Wikidata build: set `SNAPSHOT_DIR`, run `npm run bench -w @mindreader/engine`, and play 20 games with obscure characters.
