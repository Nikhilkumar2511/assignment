# Akinator-style guessing game: open-source implementations, tech stacks, LLM costs/latency, learning from players

Research date: 2026-11-25. Notes on access: GitHub repo data came from the `gh search repos` API, run on 2026-11-25. Star counts and "last updated" dates are from that run. Direct fetches of openai.com, developers.openai.com, ai.google.dev, groq.com and medium.com were blocked by this session's network allowlist. OpenAI, Gemini and Groq prices therefore come from search-result snippets and third-party aggregators, not the official pages, and are flagged as such. Claude prices come from Anthropic's bundled API reference, which says it was cached on 2026-11-03 and points to https://platform.claude.com/docs/en/about-claude/pricing as the live source.

## 1. Notable open-source Akinator clones, 20-questions engines and unofficial Akinator API wrappers

### Takeaway
No dominant, high-star open-source "Akinator clone" exists. The most useful references are small classic engines (allenai/twentyquestions, chrisspen/asklet modeled on 20Q, rouge8/20questions with entropy question selection, a T-SQL engine) and the Kaggle "LLM 20 Questions" solutions. Unofficial Akinator API wrappers (aki-api for Node, akinator.py/akipy for Python, Akiwrapper for Java) keep breaking: Akinator added Cloudflare protection around mid-2026, and current Python wrappers rely on cloudscraper or Playwright workarounds.

### Cited Findings
**Classic, non-LLM engines and clones (stars as of 2026-11-25, from GitHub search):**
- **googlecreativelab/mystery-animal**: 80 stars, JavaScript. "A new spin on the classic 20-questions game." This is Google Creative Lab's voice game. — [GitHub](https://github.com/googlecreativelab/mystery-animal)
- **ukushu/AkinatorEngine**: 76 stars, C#, updated 2026-07. No description. — [GitHub](https://github.com/ukushu/AkinatorEngine)
- **YuriRDev/akinator.dev**: 66 stars, TypeScript, updated 2026-10. Described (in Portuguese) as "Akinator OpenSource! Create your own guessing game." — [GitHub](https://github.com/YuriRDev/akinator.dev)
- **rouge8/20questions**: 64 stars, Python. An AI course final project with a 20-questions player and a simple web app. Its entropy function is modeled on decision-tree entropy. It penalizes questions that get many "unsure" answers by weighting the score by the ratio of definite to unsure answers. — [GitHub](https://github.com/rouge8/20questions)
- **nesterovsky-bros/KB**: 42 stars, PLpgSQL/T-SQL. "KB is an Akinator like engine written in T-SQL." It is an example of keeping the whole engine inside the database. — [GitHub](https://github.com/nesterovsky-bros/KB)
- **leagerl1/Akinator**: 31 stars, C++. Akinator game using a binary decision tree. — [GitHub](https://github.com/leagerl1/Akinator)
- **chrisspen/asklet**: 19 stars, Python/Django. "A learning algorithm for the 20 questions game," inspired by Robin Burgener's 20Q (20q.net). The author wrote their own target-ranking method because Burgener's patent "doesn't completely describe how the target rank is calculated." It uses Django models (added to INSTALLED_APPS, then migrations) to store domains and record games. — [GitHub](https://github.com/chrisspen/asklet)
- **allenai/twentyquestions**: 19 stars, Python. "A web application for playing 20 Questions to crowdsource common sense." — [GitHub](https://github.com/allenai/twentyquestions)
- **evobyte-apps/open-20-questions**: 18 stars, Python. "The Open Source 20 Questions implementations by Evobyte and the Old School Coding YouTube channel." — [GitHub](https://github.com/evobyte-apps/open-20-questions)
- **face-hh/rustinator**: 8 stars. "Akinator clone in Rust with Tauri, written in 2 days." — [GitHub](https://github.com/face-hh/rustinator)
- **up-left/akinator**: 3 stars, Python. "Akinator clone: REST API and Single Page Application." — [GitHub](https://github.com/up-left/akinator)
- **hatimmangat/Movie-AkinatorAI**: 0 stars, Python, updated 2026-09. "An LLM-free, movie-guessing game powered by information theory (entropy), Bayesian belief updating" plus a FastAPI backend (description truncated). This is a reference for a modern Bayesian + FastAPI stack. — [GitHub](https://github.com/hatimmangat/Movie-AkinatorAI)
- The tutorial "Building Akinator with Python using Bayes Theorem" (Analytics Vidhya, Medium) builds a simple version with a Flask server and HTML front end. I could not fetch the full text (medium.com blocked). — [Medium](https://medium.com/analytics-vidhya/building-akinator-with-python-using-bayes-theorem-216253c98daa)

**LLM-based 20 questions:**
- **daveshap/TwentyQuestions**: 12 stars, Python. "Play 20 questions with GPT-3." — [GitHub](https://github.com/daveshap/TwentyQuestions)
- **Isaka-code/llm-20-questions**: 11 stars, Python. "9th Place Solution - LLM 20 Questions" (Kaggle competition). — [GitHub](https://github.com/Isaka-code/llm-20-questions)
- **vassiliphilippov/oxfordkaggleclub-20questions-keywords**: keyword generation for the Kaggle LLM 20 Questions competition. — [GitHub](https://github.com/vassiliphilippov/oxfordkaggleclub-20questions-keywords)
- **mindalyze-com/deep-20-bench** (updated 2026-11): "Deep20Bench uses the classic Twenty Questions game to test how well an AI can identify a hidden subject." — [GitHub](https://github.com/mindalyze-com/deep-20-bench)
- One Kaggle participant wrote that "most top entries employed complex methods, like using unigram-based approaches" rather than pure LLM prompting. Their own pure-prompting approach did not lead; it steered questions toward narrowing keyword categories and switched to guessing after a run of "no" answers. — [magsenche write-up](https://magsenche.vercel.app/projects/llm20)
- The "LLM + Akinator" repos found are tiny weekend projects with 0 stars (e.g. srivatsan0611/akinator-llm, "weekend fullstack project that replicates Akinator with an LLM"). — [GitHub](https://github.com/srivatsan0611/akinator-llm)
- Academic work on LLM question-asking uses expected information gain and Bayesian experimental design: BED-LLM ([arXiv 2508.21184](https://arxiv.org/pdf/2508.21184)), "Learning to Ask Informative Questions" with EIG + preference optimization ([arXiv 2406.17453](https://arxiv.org/pdf/2406.17453)), and "Chatbots as Problem Solvers: Playing Twenty Questions with Role Reversals" ([arXiv 2301.01743](https://arxiv.org/pdf/2301.01743)).

**Unofficial Akinator API wrappers (status):**
- **jgoralcz/aki-api**: 134 stars, TypeScript/Node, updated 2026-10-26. "An API for the Akinator in Node. Supports up to 15 languages." It has the most stars of any Akinator-related repo. — [GitHub](https://github.com/jgoralcz/aki-api)
- **Ombucha/akinator.py**: 28 stars, Python 3.9+, sync and async. According to its README, the original akinator.py "vanished from public repositories without notice." The Ombucha repo started as a mirror, then broke after Akinator changed its backend API. Its successor akipy broke when Cloudflare protection was added. This project restores function by swapping `requests` for `cloudscraper`. No releases are published, and the README carries no explicit "unofficial" disclaimer. — [GitHub](https://github.com/Ombucha/akinator.py)
- The PyPI `akinator` 2.1.0 listing says it uses cloudscraper to bypass Cloudflare's anti-bot measures, "restoring full functionality." This is the package's own claim and is untested here. — [PyPI](https://pypi.org/project/akinator/)
- **advnpzn/akipy**: 18 stars, updated 2026-11-08. A June 2026 issue reports Akinator.com "seems to have started using Cloudflare for detection." — [PyPI akipy](https://pypi.org/project/akipy); [issue](https://www.goodfirstissue.org/advnpzn/akipy/issues/10)
- Other wrappers: **markozajc/Akiwrapper** (Java, 34 stars) ([GitHub](https://github.com/markozajc/Akiwrapper)); **lgc2333/cooaki** (async, fully typed Python, uses Playwright or patchright for Cloudflare) ([PyPI](https://pypi.org/pypi/cooaki)); **Tom-the-Bomb/akinator-rs** (Rust, with Python bindings) ([GitHub](https://github.com/tom-the-bomb/akinator.py)); **janniksam/Akinator.Api.Net** (C#) ([GitHub](https://github.com/janniksam/Akinator.Api.Net)); **rynaki** (cloudscraper-based) ([PyPI](https://pypi.org/project/rynaki/)).
- A 2026 DEV post advertises a TypeScript "Akinator API that works in 2026 with retry and proxy support." This hints that proxies or retries are now needed. — [DEV Community](https://dev.to/lucas7x7/i-built-an-akinator-api-that-works-in-2026-with-typescript-retry-and-proxy-support-1nn6)

**How the original systems work:**
- Akinator is made by the French company Elokence (launched ~2007) and runs on its program "Limule." Answers are Yes / No / Probably / Probably not / Don't know. — [Wikipedia](https://en.wikipedia.org/wiki/Akinator)
- Akinator's official FAQ: "The algorithm we use is an original creation. How we created it is our little secret." — [akinator.com FAQ](https://en.akinator.com/content/6/everything-you-ve-always-wanted-to-know-about-akinator)
- 20Q (Robin Burgener) learns only from play. Each game's answers strengthen "synaptic connections." When it guesses wrong, the player types the correct object and it is added. One report says 1 million games produced 10 million associations. Answers are Yes / No / Unknown / Sometimes. Burgener's patent application is US 2006/0230008 ("Artificial neural network guessing method and game"), now discontinued. — [Wikipedia 20Q](https://en.wikipedia.org/wiki/20Q); [Mental Floss](https://mentalfloss.com/article/22269/how-electronic-20-questions-games-work)

### Inferences
- **Python reference code:** for a classic engine, rouge8/20questions (entropy selection) and asklet (20Q-style learning with Django persistence) are the most instructive. hatimmangat/Movie-AkinatorAI is the closest to a modern "Bayesian + entropy + FastAPI" layout, but it has no community validation (0 stars).
- **Don't build on unofficial wrappers:** a product built on Akinator wrappers would be fragile, legally exposed, and dependent on Cloudflare workarounds. Use them only for experiments or benchmarking.
- **Prefer a hybrid design:** Kaggle experience suggests pure LLM questioning underperforms structured candidate narrowing. A hybrid (structured candidate list + info-gain selection + LLM for phrasing and knowledge) is the better design.

### Gaps
- Per-repo license, data format and last-commit details could not be checked; `gh api repos/...` returned 403 for this session. Licenses need manual checking before reuse.
- No authoritative write-up of the Kaggle LLM 20 Questions winning solution was found.
- Star counts are low across the board, and some repos may be stale despite recent "updated" timestamps (pushes or stars can bump them).

## 2. Typical tech stacks (backend, storage, scoring, vector DBs, frontend)

### Takeaway
Existing projects use simple stacks: Python (Flask, Django or FastAPI) or Node, with a relational database holding the character × question answer counts. Scoring is a Bayesian update over the candidate set, with entropy or information gain to pick the next question. Vector databases, Redis and NumPy are reasonable engineering choices, but I found no cited open-source clone that uses them. Treat them as recommendations, not observed practice.

### Cited Findings
- **Django:** asklet stores domains and game records in Django models (relational DB via migrations). — [GitHub asklet](https://github.com/chrisspen/asklet)
- **Flask + HTML:** the Bayes-theorem Akinator tutorial uses a Flask web server and an HTML front end. — [Medium](https://medium.com/analytics-vidhya/building-akinator-with-python-using-bayes-theorem-216253c98daa)
- **FastAPI:** Movie-AkinatorAI combines entropy-based question selection and Bayesian belief updating with a FastAPI backend. — [GitHub](https://github.com/hatimmangat/Movie-AkinatorAI)
- **Engine inside the database:** KB implements the engine in SQL (PLpgSQL/T-SQL), keeping the probability tables and logic in the DB. — [GitHub](https://github.com/nesterovsky-bros/KB)
- **REST API + SPA:** up-left/akinator splits into a REST API and a single-page application. — [GitHub](https://github.com/up-left/akinator)
- **Desktop:** rustinator uses Rust + Tauri. — [GitHub](https://github.com/face-hh/rustinator)
- **Node:** aki-api is the main Node/TypeScript client, and Discord and Telegram bots are common front ends (abdulrahman1s/Akinator-Bot in JS, 49 stars; advnpzn/Akinator-Bot, a Telegram bot in Python, 45 stars). — [GitHub aki-api](https://github.com/jgoralcz/aki-api); [Akinator-Bot](https://github.com/abdulrahman1s/Akinator-Bot)
- **Entropy:** the formal definition and Python code for it are in Stanford CS109's information-theory lecture. — [Stanford CS109](https://web.stanford.edu/class/archive/cs/cs109/cs109.1262/lectures/18-InformationTheory/18-InformationTheory.pdf)

### Inferences
- **Recommended Python stack:** FastAPI (async; fits streaming LLM calls) + Postgres with `answer_counts(character_id, question_id, yes, no, prob_yes, prob_no, dont_know)` + Redis for in-progress game state (the candidate posterior vector plus the question/answer history, with a TTL of about 1 hour) + NumPy for scoring.
- **Scoring cost:** with C characters and Q questions, store P(answer | character, question) as a C×Q×5 float32 array in memory. A Bayesian update is one vectorized multiply over C. Question selection is expected-entropy over the top-K candidates, roughly O(K·Q). At 10k characters × 1k questions this is tens of MB and takes milliseconds, so server-side scoring is never the latency bottleneck.
- **Node stack:** a NestJS/Express + Postgres + Redis equivalent works. Numeric scoring is less ergonomic without NumPy, though typed arrays suffice.
- **Vector DBs:** pgvector (inside the same Postgres) or Qdrant are useful in two places. First, an LLM-hybrid design embeds character descriptions and retrieves a shortlist of candidates matching the answers so far. Second, they dedupe user-submitted characters and questions by semantic similarity ("Is it a mammal?" vs "Is your character a mammal?"). pgvector avoids running a second datastore.
- **Frontend:** Next.js/React for web. React Native or Flutter for mobile. Optimistic UI (pre-fetching the next question for each likely answer) helps with snappiness.

### Gaps
- I found no cited open-source clone that uses Redis, pgvector or Qdrant. Those suggestions are engineering inference, not observed practice.
- I found no benchmark for NumPy scoring speed in Akinator-like engines. The sizing above is a back-of-envelope estimate.

## 3. LLM API cost and latency per game (late-2026 prices)

### Takeaway
A 20-question game in which the LLM asks every question, resending the full history each turn, uses about 18k input tokens and 1k–6k output tokens. That works out to roughly $1–$7 per 1,000 games on small or cheap models (Claude Haiku 5.5, GPT-5 nano/mini, Gemini Flash-Lite, Groq gpt-oss/Llama), $15–$100 on mid-tier models (Claude Sonnet 5.5), and $30–$190 on Claude Opus 5.5. Prompt caching cuts input cost by about 60–70%. A hybrid Bayesian engine that calls an LLM only offline (to seed or expand the knowledge matrix) costs near-zero per game.

### Cited Findings
**Claude (Anthropic first-party API; the skill's model table is dated "cached: 2026-11-03"; live source is https://platform.claude.com/docs/en/about-claude/pricing):**
- Per 1M tokens, input/output:
  - Claude Haiku 5.5: $0.10 / $0.50. This applies to prompts up to 100K tokens; beyond that it is $0.50 / $2.50.
  - Claude Sonnet 5.5: $2 / $10.
  - Claude Opus 5.5: $4 / $20.
  - Claude Fable 5.2: $8 / $40.
  - Claude Haiku 4.5: $1 / $5.
  - Claude Sonnet 4.6: $3 / $15.
  — [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing)
- **Caching:** writes cost 1.25× base input for a 5-minute TTL and 2× for a 1-hour TTL. Reads cost about 0.1× base input in general, 0.05× on Opus 5.5 and Sonnet 5.5 (cache reads $0.20 and $0.10 per MTok), and 0.025× on Fable 5.2. The minimum cacheable prefix is 512 tokens on Opus 5.5, Sonnet 5.5 and Haiku 5.5. With a 5-minute TTL, two requests break even. — [Anthropic prompt caching docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- **Batches:** the Message Batches API runs asynchronously at 50% of standard cost. It suits offline knowledge-base seeding, not live turns. — [Anthropic batch processing](https://platform.claude.com/docs/en/build-with-claude/batch-processing)
- **Thinking:** Opus 5.5 cannot disable thinking; `effort` is the only control and defaults to `medium`. Haiku 5.5 thinks by default and can disable thinking only at effort `high` or below. This matters because reasoning tokens are billed as output. — [Anthropic models overview](https://platform.claude.com/docs/en/about-claude/models/overview)
- **Fast mode:** Opus 5.5 offers up to 2.5× higher output tokens per second at $8/$40 per MTok. — [Anthropic fast mode](https://platform.claude.com/docs/en/build-with-claude/fast-mode)

**OpenAI (official page not fetchable; figures from search snippets of developers.openai.com and aggregators, Nov 2026):**
- GPT-5 mini: $0.25 input / $0.025 cached input / $2.00 output per 1M; batch is half price. GPT-5 nano: $0.05 / $0.005 cached / $0.40; batch $0.025 / $0.20. — [OpenAI GPT-5 nano model page](https://developers.openai.com/docs/models/gpt-5-nano); [OpenAI GPT-5 mini model page](https://developers.openai.com/api/docs/models/gpt-5-mini)
- GPT-5.4 mini is reported at $2.50 input / $0.25 cached / $15.00 output. I treat this as unverified: it is suspiciously high for a "mini" model and comes only from a community thread. — [OpenAI community](https://community.openai.com/t/introducing-gpt-5-4-mini-and-nano-our-most-capable-small-models-yet/1377015/6)
- Third-party pages refer to newer "GPT-6" family models in 2026, but I could not check their prices against OpenAI. — [morphllm](https://morphllm.com/openai-api-pricing)

**Google Gemini (official page not fetchable; aggregator figures, which conflict):**
- Gemini 2.5 Flash-Lite: $0.10 input / $0.40 output per 1M; multiple sources agree.
- Gemini 3.1 Flash-Lite: $0.25 / $1.50 according to morphllm (Oct 2026), but $0.125 / $0.75 according to pricepertoken (Jul 2026). Vertex priority tier is $0.45 / $2.70.
- Gemini 3.5 Flash-Lite: $0.30 / $2.50 (morphllm).
- Google's page shows some Flash models at introductory rates that double on 2027-01-01 ("$0.75 through December 31, 2026. $1.50 starting January 1, 2027").
- Sources: [morphllm Gemini pricing (Oct 2026)](https://www.morphllm.com/gemini-api-pricing); [pricepertoken](https://pricepertoken.com/pricing-page/model/google-gemini-3.1-flash-lite); [Vertex AI pricing](https://cloud.google.com/vertex-ai/generative-ai/pricing); [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing)

**Groq (official page not fetchable; aggregator figures, Oct 2026):**
- **Prices** per 1M tokens, input/output:
  - gpt-oss-120b: $0.15 / $0.60.
  - gpt-oss-20b: $0.075 / $0.30. The 20B output price was cut from $0.50 in late 2025.
  - Llama 3.1 8B: $0.05 / $0.08.
  - Llama 3.3 70B: $0.59 / $0.79.

  — [morphllm Groq pricing](https://www.morphllm.com/groq-pricing); [pricingsaas Groq diff](https://pricingsaas.com/companies/groq/diffs/2025Q4)
- **Speed:** one tracker reports about 342 tok/s for gpt-oss-120b, 362 for 20B, 441 for Llama 3.1 8B and 235 for Llama 3.3 70B. Another reports about 1,000 tok/s for gpt-oss-20b. The sources conflict. — [Artificial Analysis – Groq](https://artificialanalysis.ai/providers/groq)

**Latency targets (UX):**
- Nielsen's limits: 0.1 s feels instantaneous, 1 s keeps the user's flow of thought, and past 10 s attention is lost. For delays over 1 s, show that the system is working. — [NN/g](https://www.nngroup.com/alertbox/timeframes.html); [NN/g video](https://www.nngroup.com/videos/3-response-time-limits-interaction-design/)

**Token and cost model (my estimate; see Inferences for assumptions):**

Cost per 1,000 games:

| Model (price date) | 1k out/game, no cache | 1k out/game, cached | 6k out/game (reasoning), no cache | 6k out/game, cached |
|---|---|---|---|---|
| Claude Haiku 5.5 (2026-11-03) | $2.33 | $0.82 | $4.83 | $3.32 |
| Claude Sonnet 5.5 (2026-11-03) | $46.60 | $14.71 | $96.60 | $64.71 |
| Claude Opus 5.5 (2026-11-03) | $93.20 | $29.42 | $193.20 | $129.42 |
| GPT-5 nano (aggregator, Nov 2026) | $1.31 | ~$0.55* | $3.31 | ~$2.55* |
| GPT-5 mini (aggregator, Nov 2026) | $6.58 | ~$2.73* | $16.57 | ~$12.73* |
| Gemini 2.5 Flash-Lite (aggregator) | $2.23 | n/a | $4.23 | n/a |
| Gemini 3.1 Flash-Lite at $0.25/$1.50 (Oct 2026 aggregator) | $6.07 | n/a | $13.58 | n/a |
| Groq gpt-oss-20b (Oct 2026 aggregator) | $1.67 | n/a | $3.17 | n/a |
| Groq gpt-oss-120b | $3.34 | n/a | $6.34 | n/a |
| Groq Llama 3.1 8B | $0.99 | n/a | $1.40 | n/a |

\*The OpenAI cached figures assume the whole prefix qualifies for caching. OpenAI's own minimum cacheable length could not be checked here, and a 600-token system prompt may not qualify on early turns.

**Offline cold-start seeding (estimate):** have an LLM fill a 2,000-character × 300-question answer matrix, 50 questions per call, which is about 12,000 calls at ~1.5k input and ~400 output tokens each. Cost at standard rates: about $4.20 on Haiku 5.5 ($2.10 with batch), $84 on Sonnet 5.5 ($42 with batch), and $14 on GPT-5 mini ($7 with batch).

### Inferences
- **Token assumptions:** the system prompt (rules, output JSON format, optional few-shot) is about 600 tokens. Each turn adds about 30 tokens of history (question plus answer). 20 turns, full history resent each turn: input = 20×600 + 30×(1+…+20) = 18,300 tokens per game. Visible output is about 50 tokens per turn (question plus small JSON with top guesses), giving about 1,000 per game. If the model reasons, budget about 300 output tokens per turn (6,000 per game). With caching on Claude, about 17,100 input tokens per game become cache reads and about 1,200 become cache writes.
- **Model choice:** for a consumer game, the cost driver is output and reasoning tokens, not input. Pick a small model, keep effort low or reasoning off, and constrain output to a short JSON (`{"question":..., "top_guesses":[...]}`).
- **Per-turn latency:** with ~50 output tokens at 300–1,000 tok/s (Groq-class), generation adds about 0.05–0.2 s on top of time-to-first-token. Hosted frontier models with reasoning add seconds per turn and would miss the 1 s "flow" target. Stream the question text, or keep the LLM off the per-turn critical path.
- **Hybrid design:** a Bayesian matrix engine answers each turn in single-digit milliseconds server-side, so the 0.1–1 s target is easy. The LLM is used only to (a) seed and expand the matrix offline via batch, (b) phrase questions, or (c) take a final "LLM guess" when the matrix posterior is flat. Per-game LLM cost is then fractions of a cent per 1,000 games, or zero.
- **Local inference** (Ollama or llama.cpp with 3–8B models) has zero marginal API cost. It moves cost to GPU hosting and gives variable latency on CPU-only machines, which makes it best for offline seeding or self-hosted prototypes.

### Gaps
- Official OpenAI, Gemini and Groq pricing pages could not be fetched (blocked by the network allowlist). Those numbers rest on search snippets and aggregators, and the Gemini 3.1 Flash-Lite price conflicts by 2× between sources. Verify before budgeting.
- No Together AI pricing was gathered.
- No measured time-to-first-token figures were found for Claude Haiku 5.5, GPT-5 nano/mini or Gemini Flash-Lite in late 2026.
- No Ollama or llama.cpp tokens/sec benchmarks were gathered.
- OpenAI and Gemini caching minimums and discounts were not verified.

## 4. Learning from players over time (count updates, new characters, moderation, trolls, cold start)

### Takeaway
The proven pattern, used by 20Q and described for Akinator, is to update answer statistics from every finished game and ask the player to name the character when the game loses. Moderation of submissions, troll detection and cold start are not documented by these projects, so the design recommendations below are inference.

### Cited Findings
- 20Q "learns only when it plays a game": no data is added except visitors' answers. When it guesses wrong, the player types the correct object, which becomes part of the network. — [Wikipedia 20Q](https://en.wikipedia.org/wiki/20Q); [Mental Floss](https://mentalfloss.com/article/22269/how-electronic-20-questions-games-work)
- 20Q accumulated about 10 million associations after about 1 million online games. — [Mental Floss](https://mentalfloss.com/article/22269/how-electronic-20-questions-games-work)
- If Akinator is wrong several times, it asks the user to enter the item's name, expanding its database. — [Wikipedia Akinator](https://en.wikipedia.org/wiki/Akinator)
- allenai/twentyquestions uses 20 Questions gameplay specifically to crowdsource commonsense knowledge. This is a precedent for treating game logs as a data-collection pipeline. — [GitHub](https://github.com/allenai/twentyquestions)
- rouge8/20questions down-weights questions that get many "unsure" answers. This is a simple data-quality signal for question usefulness. — [GitHub](https://github.com/rouge8/20questions)

### Inferences
- **Count updates:** when a game ends with a confirmed character, either because the guess was right or the user named it, increment `counts[character][question][answer]` for every question asked. Estimate P(answer | character, question) with Laplace or Dirichlet smoothing (add α to each of the 5 answer buckets). Map "probably" to soft counts, e.g. 0.75 yes and 0.25 no. Only update when the game reached a confirmed outcome.
- **New characters:** when the game loses, collect the name and search existing characters with fuzzy matching and embeddings to avoid duplicates. If it is new, create a pending character seeded from this game's answers, and optionally ask 3–5 extra discriminating questions. An LLM can pre-fill its answers to the top-N questions (see the cold-start costs in section 3), which players then refine.
- **Moderation:** put user-submitted names and new questions through a queue. Apply automated filters (profanity or an LLM moderation classifier, private-individual detection, and a rule against real private people and minors) and a promotion threshold (e.g. the same name submitted independently by N different users) before entering the public pool. Promoted entries get human review.
- **Troll and noise detection:** compute the log-likelihood of a game's answers under the final confirmed character's distribution. Down-weight or discard games that fall far below the norm, are internally contradictory, or show uniform or random answering patterns. Rate-limit per user, IP or device. Weight updates by user reputation. Freeze the counts of well-established characters, or cap the per-game contribution, so a brigade cannot rewrite them.
- **Cold start:** seed the character × question matrix from an LLM (batch API, low cost) or from structured sources such as Wikidata properties. Start with a narrow domain (e.g. Pokémon, as in ashbaldry/Pokemon_20Q, or animals, as in mystery-animal) to get dense data early. Show "probability of a correct guess" analytics to decide when to expand.
- **Exploration:** occasionally ask a low-information question about a top candidate so that sparse cells get filled (an exploration/exploitation trade-off).

### Gaps
- I found no public documentation of how Akinator or 20Q moderate submissions or detect trolls.
- I found no source quantifying how many games per character are needed before the probabilities stabilize.

## 5. Game design details (answers, undo, max questions, when to guess, multiple guesses, latency)

### Takeaway
The standard is Akinator's five answers (Yes, No, Don't know, Probably, Probably not), an undo or back option, and a guess when the posterior is concentrated. If wrong, keep playing for a few more questions, then try further guesses, and after several misses ask the player to name the character. The 20Q convention is 20 questions with a small overrun allowed. Keep each turn under about 1 s, ideally near 0.1 s.

### Cited Findings
- **Akinator answers:** Yes, No, Probably, Probably not, Don't know. — [Wikipedia Akinator](https://en.wikipedia.org/wiki/Akinator)
- **20Q answers:** Yes, No, Unknown, Sometimes. — [Mental Floss](https://mentalfloss.com/article/22269/how-electronic-20-questions-games-work)
- **Akinator multiple guesses:** after several wrong guesses it asks the user for the character's name. — [Wikipedia Akinator](https://en.wikipedia.org/wiki/Akinator)
- **Strategy:** ask questions that split the remaining possibilities roughly in half. — [MDPI analysis of Akinator](https://www.mdpi.com/2504-2289/7/1/26)
- **Kaggle LLM entry:** switched to guessing after a run of "no" answers. — [magsenche write-up](https://magsenche.vercel.app/projects/llm20)
- **Response-time limits:** 0.1 s, 1 s, 10 s. Show a progress indicator beyond 1 s. — [NN/g](https://www.nngroup.com/alertbox/timeframes.html); [Innovaccer design guidance](https://design.innovaccer.com/foundations/response-time)

### Inferences
- **When to guess:** guess when the top candidate's posterior is above a threshold (e.g. 0.8–0.9), or its ratio to the runner-up exceeds about 5×, or when expected information gain falls below a floor. Also force a guess at a hard cap, e.g. question 20, then allow 5 more questions per extra guess and up to 3 guesses total before asking "Who were you thinking of?".
- **Undo:** keep an immutable answer log in the Redis session and recompute the posterior from scratch on undo (cheap with NumPy). Never write to the learned counts until the game ends.
- **"Don't know" handling:** treat it as a weak or no update, and track it per question to detect ambiguous questions. "Probably" and "probably not" should be soft likelihoods.
- **Perceived speed:** pre-compute the next question for all 5 possible answers while the user reads, so the response is instant. Animate the avatar for 300–600 ms to mask any LLM latency. Stream LLM-phrased text.

### Gaps
- I found no published Akinator thresholds (when it decides to guess, maximum question count). The values above are design suggestions.

## 6. Legal note: the "Akinator" name and trademark

### Takeaway
"AKINATOR" is a registered trademark of Elokence (ELOKENCE.COM), with live US registrations in game, software and entertainment classes. A new product should not use "Akinator" in its name, branding, genie likeness or app-store keywords. "20 questions" is a generic game concept.

### Cited Findings
- US serial 79283171, Reg. No. 6430444, registered 2021-07-27, classes 9, 41 and 28, listed as a live trademark owned by ELOKENCE.COM. — [Markinton 79283171](https://markinton.com/trademark/akinator-79283171)
- US serial 79092974, Reg. No. 4100706, registered 2012-02-21, classes 9, 41 and 28. Aggregator status is inconsistent: it is shown as "live" and also with a 2019 cancellation date. — [Markinton 79092974](https://markinton.com/trademark/akinator-79092974)
- US serial 79237890, Reg. No. 5876238, registered 2019-10-08, class 42. One aggregator shows a 2026-04-24 cancellation date. — [Justia](https://trademarks.justia.com/792/37/akinator-79237890.html); [Markinton](https://markinton.com/trademark/akinator-79237890)
- Elokence's trademark portfolio, which includes a French INPI record. — [Justia owner page](https://trademarks.justia.com/owners/elokence-com-4687205); [INPI](https://data.inpi.fr/bopi/export/brands/FR4607104)
- Akinator's algorithm is proprietary: "How we created it is our little secret." — [akinator.com FAQ](https://en.akinator.com/content/6/everything-you-ve-always-wanted-to-know-about-akinator)
- The 20Q neural-network patent application (US 2006/0230008) is listed as discontinued. — [Wikipedia 20Q](https://en.wikipedia.org/wiki/20Q)

### Inferences
- **Naming and branding:** use an original name and mascot, and describe the game as "a 20-questions guessing game." "Akinator clone" in marketing or app-store listings risks trademark complaints and store takedowns.
- **Unofficial wrappers:** calling akinator.com through them likely conflicts with the site's terms, and Cloudflare bypassing is an explicit anti-bot circumvention. Avoid this in production.
- **Character names:** a game whose content is about real or copyrighted characters only names them as answers, which is generally lower risk. Still avoid using their images without a license.

### Gaps
- Official USPTO TSDR status was not checked; the aggregators conflict on cancellation dates.
- I did not review akinator.com's terms of service.
- This is not legal advice. Jurisdiction-specific counsel is needed.
