# Build Akinator-style games on Bayesian information gain

You can build a strong Akinator-style game without running any AI model during play. The recipe has three parts: a table of answer probabilities for every candidate and question, a Bayesian posterior over candidates that you update after each answer, and a rule that asks whichever question has the highest expected information gain. The 20Q patent describes this kind of design, and Akinator's public behavior fits it, although Elokence has never published its algorithm. Large language models do their most useful work offline. A small model can fill a 5,000-by-500 knowledge base for about $5 at batch prices. At play time, plain prompting performs poorly: GPT-4 solved only 31% of open "Things" games in Apple's 20-questions benchmark. When researchers wrap an LLM in explicit Bayesian experimental design, success rises to 88 to 95% on animal sets, which tells you the selection math matters more than the model. Your chosen stack (FastAPI, Postgres, a web frontend, a prebuilt knowledge base, no live LLM calls) matches the strongest evidence. Each turn takes milliseconds, the marginal cost per game is close to zero, and soft likelihoods let the engine survive a player's wrong answer. The weaknesses sit elsewhere. The engine can only guess characters that exist in its table, its accuracy depends on how well you fill the long tail, and you need a moderated loop to learn from players. The sections below cover each point and end with settings you can start from.

## Akinator and 20Q keep their algorithms secret, but their behavior points to Bayes

Elokence, the French company behind Akinator, says the game runs on its in-house engine Limule and that "how we created it is our little secret" ([Akinator FAQ](https://en.akinator.com/content/6/everything-you-ve-always-wanted-to-know-about-akinator)). The confirmed facts are few. Akinator launched in **August 2007**, makes its first guess **within 25 questions** on the web, and after several wrong guesses asks you to type the character's name so it can add it to its database ([Wikipedia: Akinator](https://en.wikipedia.org/wiki/Akinator)). A 2023 peer-reviewed paper says it has been played **billions of times** ([MDPI 2023](https://www.mdpi.com/2504-2289/7/1/26)). Its five answers are yes, no, don't know, probably and probably not ([Wikipedia: Akinator](https://en.wikipedia.org/wiki/Akinator)). Gizmodo puts the database at **more than 100,000 characters** ([Gizmodo](https://gizmodo.com/download/akinator)). Larger figures of 1.5 to 3 million come from uncited fan pages and conflict with each other. The claim that Limule is "close to a Bayesian model" comes from an outside French blog, not from Elokence ([PLKR](https://www.plkr.org/akinator-genie/)). Players can add characters, but only public figures, and when a submission resembles existing entries the site shows a list of close matches ([Akinator FAQ](https://en.akinator.com/content/6/everything-you-ve-always-wanted-to-know-about-akinator)).

20Q, Robin Burgener's game, is better documented because of a patent application. US 2006/0230008, now abandoned, describes a neural network organized as a **matrix of target objects by questions** that runs in two modes: answers go in and ranked objects come out, or the network ranks the next questions to ask ([Google Patents](https://patents.google.com/patent/US20060230008A1/en)). The online version had about **10 million connections** and the handheld about 250,000 ([Mavromatic](https://www.mavromatic.com/2005/11/20q-knows-what-you-are-thinking/)), and the handheld kept only 2,000 of the 10,000 most popular objects ([Coding Horror](https://blog.codinghorror.com/animal-vegetable-or-mineral/)). 20Q guessed right **80% of the time within 20 questions and 98% within 25**, and because it does not follow a binary decision tree, a wrong answer "will not throw it completely off" ([Scienceline](https://scienceline.org/2006/07/tech-schrock-20q/)). It learned only from play. By September 2006 it held more than 10,000 objects after more than 45 million games ([20Q.net Q&A](https://www.20q.net/flat/rbqanda.html)).

Taken together, the public behavior of both games rules out a strict decision tree. A tree that eliminates candidates could not accept "probably", recover from a wrong answer, keep playing after a wrong guess, or improve with use. A probabilistic classifier over a learned character-by-question table does all four. The 20Q matrix used in two modes works like a naive Bayes log-likelihood table: sum the weights for the given answers to score objects, then rank questions by how well they separate the top-scoring objects. That reading is an interpretation, since the patent excerpts available do not state the update rule. It is still the right mental model for your engine.

## Information gain picks the question and Bayes' rule keeps the score

### The core loop has four steps

Every serious design in the notes runs the same loop. You keep a posterior P(c | answers) over candidates, update it with Bayes' rule using learned likelihoods P(answer | candidate, question), ask the question with the largest expected information gain, and guess when one candidate dominates. In log space the update is a single addition per candidate: score(c) += log P(a | c, q). Information gain is the expected drop in entropy, IG(q) = H(C) minus the sum over answers of P(a) times H(C | a), the same quantity ID3 decision trees use to choose splits ([Temple CIS587](https://cis.temple.edu/~giorgio/cis587/readings/id3-c45.html)). Jedynak, Frazier and Sznitman proved that in noisy 20 questions the greedy policy, which minimizes expected posterior entropy one step at a time, is **Bayes-optimal**, so you do not need expensive multi-step lookahead ([Jedynak et al. 2011](https://people.orie.cornell.edu/pfrazier/pub/2011_JedynakFrazierSznitman_20questions.pdf)).

A small worked example shows how this plays out. Take four equally likely candidates and the question "Is your character female?", with P(yes) of 0.95, 0.90, 0.05 and 0.10. If the player says yes, the posterior becomes 0.475, 0.45, 0.025 and 0.05. The last two candidates lose weight but stay alive. This question is worth **0.622 bits**. A lopsided question that only the first candidate would answer yes to is worth 0.562 bits. The balanced split wins, and that is the formal version of the folk rule to "split the field roughly in half" ([Wikipedia: Twenty questions](https://en.wikipedia.org/wiki/Twenty_questions)).

The same math tells you how many questions to budget. With perfect yes/no answers, 5,000 candidates need about 12.3 bits and a million need 20. Players are not perfect. With a 5% error rate, each binary question carries at most about 0.71 bits, so a million candidates need about 28 questions. Classical lie-tolerant search gives a similar picture: if the player may lie once, a million candidates need at least 25 yes/no questions instead of 20. Rényi and Ulam framed this "noisy oracle" problem decades ago ([arXiv 1511.03144](https://arxiv.org/pdf/1511.03144)). These figures are derivations, not published Akinator data, but they line up with the 20Q figures above and with Akinator's 25-question budget.

Decision trees are the offline, noiseless special case. ID3 and C4.5 precompute a tree by greedy maximum-gain splits, which makes each game cheap, but **one wrong answer sends the player down the wrong branch for good**, the tree needs retraining whenever the data change, and "don't know" fits poorly. The online Bayesian loop recomputes gain each turn against a soft posterior, so new data take effect immediately. Hobbyist clones show the cost of skipping the gain step: one popular Python tutorial applies Bayes' rule correctly but picks the next question at random ([Medium/Analytics Vidhya](https://medium.com/analytics-vidhya/building-akinator-with-python-using-bayes-theorem-216253c98daa)).

### Soft likelihoods turn a wrong answer into a setback, not a loss

The single most important robustness rule is that no likelihood should ever equal zero. Store counts per cell and smooth them toward the question's global answer distribution. If players answered "Does Harry Potter wear glasses?" with 940 yes, 30 probably, 10 don't know, 5 probably not and 15 no, adding one pseudo-count per answer gives P(yes) of 0.936 and P(no) of 0.016. A wrong "no" then multiplies Harry Potter's odds by about 1/59, a loss of roughly 5.9 bits. Two or three strongly diagnostic answers later, he is back on top. Under hard elimination he would be gone for good.

An open-source hybrid makes the trade-off concrete. The ai-akinator project uses hard constraint filtering over 110 animals and 90 questions and won **330 of 330 games with truthful answers in an average of 7.11 questions**, but its README admits there is "no error rescue": one wrong answer loses the target ([ai-akinator](https://github.com/Mohammed-Darrige/ai-akinator)). That benchmark is in-sample, so treat it as an upper bound.

Three further adjustments help. Treat "don't know" as nearly uninformative, giving it roughly equal likelihood across candidates, as ai-akinator does by leaving the posterior unchanged. Raise likelihoods to a power below 1 (a temperature) because naive Bayes double-counts correlated questions such as "Is your character male?" and "Does your character have a beard?". After a rejected guess, multiply that candidate by a small factor instead of zero, in case the player misclicked. For data quality, the rouge8/20questions engine down-weights questions that draw many "unsure" answers ([rouge8/20questions](https://github.com/rouge8/20questions)).

### Pruning keeps each turn in the low milliseconds

The posterior update costs one operation per candidate. Question selection is the expensive step: a naive pass costs candidates times questions times answers, about **a billion operations** for 100,000 characters, 2,000 questions and five answers. The fix is to compute gain only over the top K candidates that hold 99 to 99.9% of the posterior mass (K of about 200 to 2,000), while the tail stays in the posterior and can come back. Using the form IG = H(predicted answer) minus the expected per-candidate answer entropy, with per-cell entropies precomputed, turns selection into one matrix-vector product. At 2,000 candidates by 5,000 questions by 5 answers, that is 50 million multiply-adds, roughly 10 ms on one CPU core with BLAS by back-of-envelope estimate. The first one to three questions are identical in every game, so you can cache them. Measured figures agree: ai-akinator selects a question in **4.96 ms on average** (p90 15.61 ms) even with a two-question lookahead ([ai-akinator](https://github.com/Mohammed-Darrige/ai-akinator)).

## Plain LLMs guess poorly; LLMs inside Bayesian design reach 88 to 95%

### Prompted LLMs lose most open-domain games

Apple's Entity-Deduction Arena gives the cleanest baseline: a guesser model asks questions, and a judge model that knows the entity answers yes, no or maybe, within 20 turns ([arXiv 2310.01468](https://arxiv.org/html/2310.01468v3)). The scores below come from the project's README and use mid-2023 models ([apple/ml-entity-deduction-arena](https://github.com/apple/ml-entity-deduction-arena)).

| Guesser model | Things: success | Things: avg turns | Celebrities: success | Celebrities: avg turns |
|---|---|---|---|---|
| GPT-4-0613 | 31% | 17.8 | 50% | 17.3 |
| GPT-3.5-turbo | 28% | 18.2 | 27% | 18.8 |
| Claude-2 | 21% | 18.4 | 31% | 17.6 |
| Vicuna-13B | 18% | 18.4 | 22% | 18.7 |
| Mistral-7B-Instruct | 13% | 18.9 | 22% | 18.2 |

Later work confirms the pattern. In the EMNLP 2025 GuessingGame study, LLaMA-3.3-70B won **32.1% of open-domain games with yes/no questions** ([arXiv 2509.19593](https://arxiv.org/html/2509.19593v1)). The failure modes are consistent across papers: the model forgets or contradicts earlier answers, repeats question types, guesses a specific entity too early, and sometimes hides a guess inside an attribute question ([arXiv 2310.01468](https://arxiv.org/html/2310.01468v3); [llm20questions](https://github.com/Maaz-R-Khan/llm20questions)). One 2026 study attributes such failures to "unreliable implicit state tracking rather than limitations in high-level reasoning" ([arXiv 2604.17819](https://arxiv.org/html/2604.17819v1)). An LLM acting as the answerer adds its own noise, since it can flip yes and no for the same question across samples ([arXiv 2401.05302](https://arxiv.org/pdf/2401.05302)).

Current frontier models are probably much better, but the evidence is thin. Deep20Bench reports leaders needing about 12 to 15 questions on average, yet the Hacker News claim (Claude Opus 5 at 12.34) and the leaderboard snippet (Claude Sonnet 5 at 14.74, rank 10) disagree, and its method could not be checked ([HN](https://news.ycombinator.com/item?id=49119862); [Deep20Bench](https://deep20bench.com/editions/1.0/results/)). No peer-reviewed results exist for GPT-5, Gemini 3 or Claude 4.x-era models on the Apple protocol.

### Explicit information gain lifts LLMs the most

The big gains come from moving the belief state out of the model and computing expected information gain in code. BED-LLM has the LLM propose hypotheses and questions, keeps an explicit belief over the hypotheses, filters those inconsistent with past answers, and picks the question with the highest expected gain. It raised success by **37.4 points on average**: Mistral-Large went from 33% to 95% on Animals and from 14 to 19% to 91% on Celebrities, and GPT-4o from 45% to 93% on Animals and 34% to 64% on Things ([arXiv 2508.21184](https://arxiv.org/pdf/2508.21184)). These figures come from search excerpts of the paper, so check them against the PDF before you quote them. Uncertainty of Thoughts (NeurIPS 2024) simulates yes/no splits over an LLM-generated candidate set and reports a **38.1% average relative gain** over direct prompting in its NeurIPS abstract and 57.8% in its repository ([UoT repo](https://github.com/zhiyuanhubj/UoT); [NeurIPS abstract](https://proceedings.neurips.cc/paper_files/paper/2024/hash/2b0e14abd8128e6bf98b6b0bec1cfcbf-Abstract.html)). Training helps less. DPO on information-gain preference pairs lifted LLaMA-2-7B from 44.4% to 51.1% success and cut average questions from 9.5 to 6.3 ([arXiv 2406.17453](https://arxiv.org/html/2406.17453v3)). Simple prompt rules also work: banning repeated question types raised LLaMA-3.3-70B from 39.4% to 80.0% in GuessingGame ([arXiv 2509.19593](https://arxiv.org/html/2509.19593v1)).

The lesson for your design is direct. The best LLM systems succeed by rebuilding the classic engine around the model: an explicit candidate set, explicit Bayesian updates, and information-gain selection. Your engine already has all three. What the LLM adds in those systems is an open-ended hypothesis space, so they can guess entities that no table contains. That is the one capability your design gives up.

### Per-game LLM cost is small, but per-turn latency is not

Under a simple token model (a 600-token system prompt, about 30 tokens of history per turn, 20 turns, full history resent each turn), a fully LLM-driven game uses about 18,300 input tokens and 1,000 output tokens, or 6,000 if the model reasons. The table applies current list prices to that estimate. Claude prices come from Anthropic's pricing page ([Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing)). OpenAI and Groq figures come from aggregator snippets, not official pages ([OpenAI GPT-5 nano](https://developers.openai.com/docs/models/gpt-5-nano); [morphllm Groq](https://www.morphllm.com/groq-pricing)).

| Model | Cost per 1,000 games, short output | Same, with prompt caching | Cost per 1,000 games, reasoning output |
|---|---|---|---|
| Claude Haiku 5.5 | $2.33 | $0.82 | $4.83 |
| Claude Sonnet 5.5 | $46.60 | $14.71 | $96.60 |
| Claude Opus 5.5 | $93.20 | $29.42 | $193.20 |
| GPT-5 nano (aggregator) | $1.31 | about $0.55 | $3.31 |
| Groq gpt-oss-20b (aggregator) | $1.67 | n/a | $3.17 |

Money is rarely the blocker for a small game; latency is. Nielsen's limits say 0.1 s feels instant, 1 s keeps a user's flow, and anything over 1 s needs a progress indicator ([NN/g](https://www.nngroup.com/alertbox/timeframes.html)). A fast host generating 50 tokens at 300 to 1,000 tokens per second adds 0.05 to 0.2 s on top of time to first token, but a hosted model that reasons adds seconds to every turn ([Artificial Analysis](https://artificialanalysis.ai/providers/groq)). BED-style and UoT-style methods multiply calls per turn by candidate questions, hypotheses and simulated answers, which can reach hundreds or thousands of calls per game unless you cache likelihoods. Neither paper's cost figures could be retrieved.

## Wikidata's CC0 license makes it the safe base for your knowledge base

### Licensing narrows your choices quickly

No public Akinator-scale table of people and characters by attributes exists, so you will build your own. Licensing decides most of the source list for a commercial product.

| Source | What it gives you | Terms |
|---|---|---|
| Wikidata | Entities and typed facts (occupation, gender, citizenship, birth date, "present in work") | Structured data is **CC0** ([Wikidata:Licensing](https://www.wikidata.org/wiki/Wikidata:Licensing)) |
| Wikipedia text, DBpedia abstracts | Descriptions for grounding prompts | CC BY-SA 3.0 and GFDL ([Wikimedia legal](https://download.wikipedia.com/legal.html)) |
| ConceptNet 5 | Commonsense facts for animals and objects | CC BY-SA 4.0 with required attribution ([conceptnet.io](https://conceptnet.io:443)) |
| Fandom wikis | Detailed fictional-character traits | Text CC BY-SA 3.0; images not covered ([Fandom Licensing](https://www.fandom.com/Licensing)) |
| IMDb datasets | Cast and character names | Personal, non-commercial use only; no building a database from them ([IMDb Help](https://help.imdb.com/article/imdb/general-information/can-i-use-imdb-data-in-my-software/G5JTRESSHJBBHTGX)) |
| TMDB API | Film and TV, popularity scores | Non-commercial only without a written agreement ([TMDB terms](https://themoviedb.org:443/api-terms-of-use)) |
| AniList API | Anime characters, favourite counts | Free below **$150 per month** of revenue ([AniList terms](https://anilist.gitbook.io/anilist-apiv2-docs/docs/guide/terms-of-use)) |
| MyAnimeList API | Anime characters | Separate commercial and non-commercial terms; access revocable ([MAL agreement](https://myanimelist.net/static/apiagreement.html)) |

Wikidata is the only source here with no legal friction. If you ship a matrix built substantially from CC BY-SA text, you may have to release that matrix under CC BY-SA too. Keeping the shipped table to Wikidata facts, your own LLM judgments and player data reduces that exposure, but a lawyer should confirm it. Use IMDb and TMDB only for internal checks unless you license them.

### Pull candidates by popularity, then map properties to questions

For practical pulls, the Wikidata Query Service enforces a **60-second query limit** ([WikidataQueryServiceR docs](https://mirror.linux.duke.edu/pub/cran/web/packages/WikidataQueryServiceR/WikidataQueryServiceR.pdf)). It requires a descriptive User-Agent ([Wikidata:Data access](https://www.wikidata.org/wiki/Wikidata:Data_access)) and has run on a split graph since 9 May 2025, with people and characters on the "main" graph ([WDQS graph split FAQ](https://meta.wikimedia.org/wiki/WikiCite/WDQS_graph_split)). Queries over sitelinks often time out ([Phabricator T288611](https://phabricator.wikimedia.org/T288611)), so loop over occupations (actor, singer, politician) or use the monthly JSON dump, about **147 GB compressed** as of July 2025 ([Phabricator T399544](https://phabricator.wikimedia.org/T399544)). The sitelink count is the standard popularity proxy ([Uni Freiburg cheat sheet](https://ad-wiki.informatik.uni-freiburg.de/research/HowTos/WikidataCheatSheet?action=raw)). Wikipedia pageviews from the Wikimedia Analytics API capture current fame ([AQS docs](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/documentation/getting-started.html)). Sitelinks favour Einstein and Napoleon, while pageviews favour this year's pop stars, so a blend of the logarithms of both suits an entertainment game. Wikidata covers fictional characters less consistently than real people, with gender, species and work links often missing, so plan an LLM backfill for them.

Turning facts into questions is mostly mechanical. "Instance of human" versus "fictional character" becomes "Is your character a real person?", which is worth close to a full bit as an opening question. Sex or gender (P21) becomes "Is your character female?". Occupation (P106) groups into 20 to 30 buckets such as music, film, sport and politics. Citizenship (P27) becomes continent and top-ten-country questions. Birth date (P569) becomes thresholds at quantiles of your candidate pool, and "present in work" (P1441) becomes medium questions such as "Is your character from an anime?". Knowledge graphs cannot express traits like "wears glasses" or "is known for being evil", so ask an LLM to propose questions that separate candidates your bank currently confuses, then keep only those with high variance across candidates and few "don't know" answers.

### An LLM can fill the rest for a few dollars, if you ground it

Filling 5,000 characters by 500 questions means 2.5 million judgments. Sending all 500 questions for one entity per call (5,000 calls, about 6,300 input and 2,500 output tokens each) costs about **$9.40 on Claude Haiku 5.5, or $4.70 with the 50% batch discount**. The same job costs about $188 or $94 on Sonnet 5.5 and $376 or $188 on Opus 5.5 ([Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing); [batch processing](https://platform.claude.com/docs/en/build-with-claude/batch-processing)). Put the fixed question list first in the prompt so prompt caching can reuse it ([prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)). Set effort low, because current models think by default and bill thinking as output ([models overview](https://platform.claude.com/docs/en/about-claude/models/overview)). One call per entity-question pair would use about 12 times more input and far more requests, so avoid it. There is a precedent: a published dataset pairs **800 objects with 1,200 questions, all answered by Claude 3.5 Sonnet** ([arXiv 2504.04204](https://arxiv.org/pdf/2504.04204)).

Accuracy is the real constraint. On the Head-to-Tail benchmark, GPT-4 and Llama 2-70B answered less accurately as entities moved from famous to obscure ([arXiv 2308.10168](https://arxiv.org/pdf/2308.10168)). An audit of a knowledge base elicited from a frontier LLM found reliability highest for persons and lowest for business and sports ([arXiv 2510.07024](https://arxiv.org/pdf/2510.07024)). The Geo20Q+ study found that LLMs deduce Global North and West entities better than others ([arXiv 2508.05525](https://arxiv.org/pdf/2508.05525v1)). No one has published how well LLM-filled matrices match human labels for subjective questions such as "Is your character funny?", so you need your own evaluation set.

Size your first release modestly. Research setups range from 158 objects in LMRL-Gym ([arXiv 2311.18232](https://arxiv.org/pdf/2311.18232)) to 10,000 entities ranked by LLM-rated commonness ([arXiv 2409.14762](https://arxiv.org/html/2409.14762v1)). About 3,000 to 5,000 candidates and 200 to 500 questions gives a matrix of 1 to 2.5 million cells, a few megabytes in memory. Players mostly pick famous characters, so a popularity-ranked head set covers most games. Your "not found" log then tells you where to grow.

## Every finished game becomes training data

The learning loop is the part of Akinator and 20Q that is documented best. 20Q added no data except visitors' answers, and when it guessed wrong the player typed the right object, which joined the network ([20Q.net Q&A](https://www.20q.net/flat/rbqanda.html)). About a million online games produced **10 million associations** ([Mental Floss](https://mentalfloss.com/article/22269/how-electronic-20-questions-games-work)). Akinator "learns the best questions to ask through experience from past players" and asks for the name after repeated misses ([Wikipedia: Akinator](https://en.wikipedia.org/wiki/Akinator)). AllenAI built a 20 Questions web app specifically to collect commonsense knowledge from game logs ([allenai/twentyquestions](https://github.com/allenai/twentyquestions)).

The mechanics are straightforward. When a game ends with a confirmed character, either because the guess was right or because the player named it, add one count to the matching answer cell for every question asked, roughly 25 increments per game. Recompute the smoothed likelihoods in a batch job. Games where the player named a character the engine missed are the most valuable, because they mark exactly where the table was wrong. If the name is new, fuzzy-match it against existing names and aliases, then create a pending row seeded from this game's answers. An offline LLM call can fill its other cells before a moderator promotes it.

None of the public sources describe how Akinator or 20Q handle moderation or trolls, so the defences below are design choices rather than observed practice. Score each finished game by the log-likelihood of its answers under the confirmed character, and discard or down-weight games far below the norm or with random-looking patterns. Cap any single game's contribution and slow the drift of well-established characters, so a coordinated group cannot rewrite them. Rate-limit by user and IP. Send new names and questions to a queue with automated filters, require independent submissions from several users before review, and reject private individuals and minors, following Akinator's public-figures-only rule ([Akinator FAQ](https://en.akinator.com/content/6/everything-you-ve-always-wanted-to-know-about-akinator)). Now and then, ask a low-gain question about a top candidate so that sparse cells fill in. No source says how many games a character needs before its probabilities settle, so track that yourself.

## Open-source code offers patterns, not a foundation

No dominant open-source Akinator clone exists. The useful projects are small, and you should read them for ideas rather than fork them. Star counts are from a GitHub search on 2026-11-25, and licenses were not checked.

| Project | Stack | What to take from it |
|---|---|---|
| [rouge8/20questions](https://github.com/rouge8/20questions) (64 stars) | Python web app | Entropy selection that penalizes questions with many "unsure" answers |
| [chrisspen/asklet](https://github.com/chrisspen/asklet) (19 stars) | Python, Django | 20Q-style learning with relational storage of games; author wrote own ranking because the 20Q patent "doesn't completely describe" it |
| [nesterovsky-bros/KB](https://github.com/nesterovsky-bros/KB) (42 stars) | T-SQL, PL/pgSQL | Whole engine inside the database |
| [hatimmangat/Movie-AkinatorAI](https://github.com/hatimmangat/Movie-AkinatorAI) (0 stars) | Python, FastAPI | Closest match to your stack: LLM-free entropy plus Bayesian updates behind FastAPI |
| [Mohammed-Darrige/ai-akinator](https://github.com/Mohammed-Darrige/ai-akinator) | Python | Deterministic Bayesian engine, no turn-time LLM calls, measured selection latency |
| [up-left/akinator](https://github.com/up-left/akinator) (3 stars) | Python | REST API plus single-page app split |
| [apple/ml-entity-deduction-arena](https://github.com/apple/ml-entity-deduction-arena), [zhiyuanhubj/UoT](https://github.com/zhiyuanhubj/UoT) | Python | LLM benchmarks and prompts if you later test an LLM fallback |

Avoid the unofficial Akinator API wrappers. Akinator added Cloudflare protection around mid-2026, akipy broke, and the current Python packages restore access with cloudscraper or Playwright ([akinator.py](https://github.com/Ombucha/akinator.py); [akipy issue](https://www.goodfirstissue.org/advnpzn/akipy/issues/10)). Building on anti-bot circumvention is fragile and likely breaches the site's terms. The name is also off limits. **"AKINATOR" is a live US trademark of Elokence** (Reg. No. 6430444, classes 9, 28 and 41) ([Markinton](https://markinton.com/trademark/akinator-79283171)), so give your game its own name and mascot and describe it as a 20-questions game. The 20Q patent application is abandoned ([Google Patents](https://patents.google.com/patent/US20060230008A1/en)), and information-gain question selection is decades-old public method.

## Recommendations for your FastAPI, Postgres and Bayesian build

### The three designs compared

Your choice gives up open-domain guessing in exchange for speed, cost and control. The table puts the alternatives side by side.

| Design | Best accuracy evidence | Cost per 1,000 games | Per-turn latency | Can guess entities outside your data |
|---|---|---|---|---|
| Prompted LLM asks every question | 31% Things, 50% Celebrities for GPT-4 (2023); frontier 2026 models unverified | About $1 to $5 on small models, $15 to $190 on larger ones | 0.2 s to several seconds | Yes |
| LLM with explicit Bayesian design (BED-LLM, UoT) | 88 to 95% on Animals, 64% on Things | Not published; many calls per turn | Seconds unless likelihoods are cached | Yes |
| Prebuilt matrix with Bayesian information gain (your choice) | 20Q: 80% at 20 questions, 98% at 25 | About $0; a one-off $5 to $100 to seed the matrix | Single-digit milliseconds | No; grows through player submissions |

The fair reading is that an LLM-first design wins on day one coverage and setup effort: you write a prompt instead of a data pipeline. Your design wins on every per-game measure and on predictability, and the research shows that the gap in guessing skill closes only when LLM systems adopt the same Bayesian machinery you are building. The remaining risk in your plan is data quality on the long tail, not the algorithm.

### Engine and data settings to start from

Build the knowledge base offline. Rank candidates by a blend of log sitelinks and log pageviews and take the top 3,000 to 5,000 people and fictional characters. Pull their facts with batched Wikidata queries of 200 to 500 IDs each. Map those facts to templated questions, add LLM-proposed questions for traits graphs miss, and keep 200 to 500 questions. Fill missing and subjective cells with a small model through the batch API. Ground each prompt with the entity's Wikidata facts, ask for one of the five answers or a probability rather than a yes/no, and use a JSON schema with a fixed-length array. Run a second pass with the question order shuffled and set cells where the passes disagree to about 0.5. Where Wikidata already has a fact, trust Wikidata over the model. Hand-label 200 to 500 cells across popularity bands and check the LLM against them before launch.

In the engine, load the likelihood array (candidates by questions by five answers, float32) into NumPy when FastAPI starts and reload it after each batch recompute. The settings below are starting points to tune against logged games, not published Akinator values.

| Setting | Starting value |
|---|---|
| Smoothing pseudo-count toward each question's global answer mix | 1 to 5 |
| Likelihood floor | 0.02 to 0.05 |
| Temperature on likelihoods (correlated questions) | Exponent below 1, for example 0.7 |
| Candidates used for gain computation | Top K covering 99.9% of posterior mass |
| Guess when | Top posterior at least 0.85 to 0.9, or top-to-second ratio at least 5 to 10, or best gain below 0.05 bits |
| Hard question cap | 20 to 25 before the first guess |
| After a wrong guess | Multiply that candidate by a small factor, ask up to 5 more questions, allow 3 guesses, then ask for the name |
| Opening questions | Precompute and cache the first 1 to 3 |

### Storage, state and frontend

Postgres holds characters, aliases, questions, the per-cell answer counts, games, game answers and a submissions queue. Add pgvector to the same database if you want to spot near-duplicate questions and names, which saves you a second datastore. You do not need Redis at first. Store each game's answer log in Postgres and rebuild the posterior from it on every request. Twenty-five vector additions cost microseconds, the API stays stateless, and undo becomes "drop the last answer and recompute". Write to the learned counts only when a game ends with a confirmed character, and run the likelihood recompute as a nightly or hourly batch job.

On the frontend, show the five Akinator answers plus undo. Because the server responds in milliseconds you will hit Nielsen's 0.1 s target without tricks, but you can still precompute the next question for all five possible answers while the player reads, so the next question appears instantly. Log every question, answer, guess and "not found" name from launch. That log becomes your training data, your evaluation set and your roadmap.

### Where an LLM still helps

Keep LLMs out of the game loop but use them in three offline jobs: seeding the matrix, proposing questions that separate candidates players keep confusing, and pre-filling rows for newly submitted characters before moderation. Revisit the no-live-LLM decision only if your "not found" rate stays high after the submission loop has run for a while. At that point, a BED-style fallback that triggers only when the posterior stays flat after 25 questions adds open-domain reach to a small share of games, at the per-game prices shown above.

## Conclusion

The research points to a split that runs against the current enthusiasm for LLMs: the hard part of an Akinator-style game is not asking clever questions, which a few lines of information-gain code already do near-optimally, but holding an accurate, well-calibrated table of who answers what. The best LLM results come from systems that rebuild that table and that Bayesian loop around the model. That makes your design the stronger base, and it reframes the AI work as a data problem. Your largest unknown is how accurate LLM-filled cells are for obscure and fictional characters on subjective questions, and no published study answers that.

Two practical consequences follow. First, your launch quality depends more on your evaluation set and popularity ranking than on any engine setting, so spend your effort there. Second, player data will correct the LLM's errors only if you defend the counts against noise and trolls from the first game. 20Q reached 98% accuracy at 25 questions by learning from tens of millions of games, and your engine can improve the same way if every confirmed game feeds back into the table.
