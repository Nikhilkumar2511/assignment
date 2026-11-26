# Data Sources and Methods for an Akinator-style Knowledge Base

Research notes, compiled 2026-11-25. Network note: in this research session, direct page fetches of wikidata.org, mediawiki.org, meta.wikimedia.org and arxiv.org were blocked by the sandbox network policy, so most findings below come from search-result summaries of those pages (URLs given) rather than full-page reads. The SPARQL queries were written from documented Wikidata property and item IDs but **could not be executed against the live endpoint from this session**; test them before relying on them.

---

## 1. Wikidata: pulling people and fictional characters (SPARQL, limits, dumps, popularity priors)

### Takeaway
Wikidata is the best backbone for the candidate set: its structured data is CC0, and it has typed properties (occupation, gender, citizenship, birth date, "present in work") that map directly to yes/no questions. Use the live Query Service only for targeted pulls of fewer than about 10k rows. Since the May 2025 graph split, queries go to the "main" graph endpoint. Large pulls (all humans ranked by sitelinks) should come from the monthly JSON dump (about 145 GB gzipped) or an alternative engine. Use the sitelink count (`wikibase:sitelinks`) as the standard popularity prior, and add Wikimedia Pageviews API data where recency matters.

### Cited Findings
**Licensing**
- All structured data in Wikidata's main, property and lexeme namespaces is released under CC0 (public domain). Non-structured text in other namespaces is CC BY-SA. — [Wikidata:Licensing](https://www.wikidata.org/wiki/Wikidata:Licensing)
- Almost all content of other Wikimedia projects, including Wikipedia text, is dual-licensed CC BY-SA 3.0 and GFDL. This matters if you scrape Wikipedia article text for descriptions or LLM context. — [Wikimedia legal/license info](https://download.wikipedia.com/legal.html)

**Query Service (WDQS) limits and etiquette**
- Hard query deadline: 60 seconds. Each client gets 60 seconds of processing time per 60 seconds and 30 error queries per minute. These figures are from the WikidataQueryServiceR package docs, which restate the WDQS manual. — [WikidataQueryServiceR PDF (CRAN mirror)](https://mirror.linux.duke.edu/pub/cran/web/packages/WikidataQueryServiceR/WikidataQueryServiceR.pdf); 60-s timeout also in [Wikidata SPARQL analysis slides (LDOW2018)](https://ddll.inf.tu-dresden.de/w/images/8/83/Wikidata-SPARQL-analysis-LDOW2018-slides.pdf)
- A forum post quoting the WDQS manual gives a limit of 5 parallel queries per IP, and flags that the limit may change. — [Wikidata mailing list archive](https://www.mail-archive.com/wikidata@lists.wikimedia.org/msg09121.html) (secondary; verify on the WDQS User Manual)
- Clients must send a descriptive User-Agent, in the form `<name>/<version> (<homepage>; <contact>)`. Non-compliant clients may be blocked completely, and stricter enforcement of the User-Agent policy was reported in 2025. — [Wikidata:Data access](https://www.wikidata.org/wiki/Wikidata:Data_access); [Phabricator T402959](https://phabricator.wikimedia.org/T402959)
- Queries that read sitelinks are notoriously slow. Wikimedia's own task notes it is "often impossible to write a query involving sitelinks without the WDQS service timing out." — [Phabricator T288611](https://phabricator.wikimedia.org/T288611)

**Graph split (important since 2025)**
- WDQS was split into two graphs, live on 9 May 2025. Scholarly articles moved to a separate "scholarly" endpoint, and everything else stayed on the "main" graph. Queries that need both graphs must use SPARQL `SERVICE` federation. The main graph holds about 77M items and the scholarly graph about 45M. — [WikiCite/WDQS graph split FAQ](https://meta.wikimedia.org/wiki/WikiCite/WDQS_graph_split); [Lubiana, Rasberry, Mietchen, CEUR-WS 2025](https://ceur-ws.org/Vol-4064/PD-paper3.pdf)
- A June 2025 FAQ said the "legacy full" endpoint would be deprecated around November 2025. Check current endpoint status on the official docs. — [WikiCite/WDQS graph split FAQ](https://meta.wikimedia.org/wiki/WikiCite/WDQS_graph_split)
- Implication for this project: people, fictional characters, animals and objects are all on the main graph, so the split mostly helps (a smaller graph means fewer timeouts).

**Dumps**
- `wikidata-20250318-all.json.gz` was about 144.66 GB (144,658,836,759 bytes). A July 2025 Phabricator report puts `latest-all.json.gz` at about 147 GB. The same report flagged a truncated bz2 (about 4.9 GB) as a broken dump, so verify checksums before use. — [Phabricator T399544](https://phabricator.wikimedia.org/T399544); [Meta: Dumps sizes and growth](https://meta.wikimedia.org/wiki/Data_dumps/Dumps_sizes_and_growth)
- Wikidata was about 1.6 TB uncompressed as of January 2026, and dumps are produced monthly as of 2026. — [Meta: Dumps sizes and growth](https://meta.wikimedia.org/wiki/Data_dumps/Dumps_sizes_and_growth)
- The current files are listed at https://dumps.wikimedia.org/wikidatawiki/entities/ — [Meta: Data dumps](https://meta.wikimedia.org/wiki/Data_dumps)
- Hugging Face mirrors and parsed versions exist, which avoids parsing the 145 GB JSON yourself. — [Wikimedians/wikidata-all](https://huggingface.co/datasets/Wikimedians/wikidata-all/blob/main/README.md); [philippesaade/wikidata](https://huggingface.co/datasets/philippesaade/wikidata)
- The University of Freiburg's Wikidata cheat sheet (from the QLever group) documents query patterns for a faster alternative SPARQL engine over Wikidata, useful for heavy aggregate queries such as ranking all humans by sitelinks. — [Uni Freiburg Wikidata cheat sheet](https://ad-wiki.informatik.uni-freiburg.de/research/HowTos/WikidataCheatSheet?action=raw)

**Popularity priors**
- "The number of sitelinks is a good proxy for the popularity of an entity" (cheat sheet). The Wikidata forums describe counting sitelinks as the common way to get a "pseudo value for popularity." The value is read via the `wikibase:sitelinks` predicate. — [Uni Freiburg cheat sheet](https://ad-wiki.informatik.uni-freiburg.de/research/HowTos/WikidataCheatSheet?action=raw); [Wikidata mailing list](https://www.mail-archive.com/wikidata@lists.wikimedia.org/msg08773.html); [Help:Sitelinks](https://www.wikidata.org/wiki/Help:Sitelinks)
- Pageviews are not stored in Wikidata (a Phabricator proposal exists to add them). Per-article pageviews come from the Wikimedia Analytics (AQS) Pageviews API. — [Phabricator T120198](https://phabricator.wikimedia.org/T120198); [Meta Research:Data](https://meta.wikimedia.org/wiki/Research:Data); [AQS Analytics API getting started](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/documentation/getting-started.html); [AQS access policy](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/documentation/access-policy.html)

**Example SPARQL queries (untested in this session; IDs are standard Wikidata identifiers)**

Key IDs: `P31` instance of, `P279` subclass of, `Q5` human, `Q95074` fictional character, `Q15632617` fictional human, `P106` occupation, `P21` sex or gender, `P27` country of citizenship, `P569` date of birth, `P570` date of death, `P1441` present in work, `P1080` from narrative universe, `P170` creator, `Q33999` actor, `Q177220` singer, `Q82955` politician, `Q6581097` male, `Q6581072` female.

(a) Top real people by popularity. To avoid the 60-s timeout, restrict by occupation (or loop over occupations) instead of scanning all humans:
```sparql
SELECT ?person ?personLabel ?sitelinks WHERE {
  ?person wdt:P31 wd:Q5 ;
          wdt:P106 wd:Q33999 ;            # actor; loop over occupations
          wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= 50)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
ORDER BY DESC(?sitelinks)
LIMIT 2000
```

(b) Attribute pull for a fixed candidate list. This is the step that fills the matrix; batch about 200 to 500 QIDs per request via `VALUES`:
```sparql
SELECT ?p ?gender ?occupation ?country ?dob ?dod WHERE {
  VALUES ?p { wd:Q2831 wd:Q76 wd:Q937 }      # Michael Jackson, Obama, Einstein
  OPTIONAL { ?p wdt:P21 ?gender }
  OPTIONAL { ?p wdt:P106 ?occupation }
  OPTIONAL { ?p wdt:P27 ?country }
  OPTIONAL { ?p wdt:P569 ?dob }
  OPTIONAL { ?p wdt:P570 ?dod }
}
```

(c) Fictional characters with the work and franchise they appear in, ranked by sitelinks:
```sparql
SELECT ?c ?cLabel ?work ?workLabel ?universe ?universeLabel ?sl WHERE {
  ?c wdt:P31/wdt:P279* wd:Q95074 ;         # any subclass of fictional character
     wikibase:sitelinks ?sl .
  FILTER(?sl >= 20)
  OPTIONAL { ?c wdt:P1441 ?work }
  OPTIONAL { ?c wdt:P1080 ?universe }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
ORDER BY DESC(?sl) LIMIT 3000
```
The `P279*` path over all fictional-character subclasses is expensive. If it times out, enumerate the main subclasses first (for example fictional human `Q15632617`, anime/manga character, video game character), then query each.

(d) Counting how many candidates fall into an attribute value, useful for choosing questions that split the set roughly 50/50:
```sparql
SELECT ?occ ?occLabel (COUNT(?p) AS ?n) WHERE {
  VALUES ?p { ... candidate QIDs ... }
  ?p wdt:P106 ?occ .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
} GROUP BY ?occ ?occLabel ORDER BY DESC(?n)
```

### Inferences
- Recommended pipeline: (1) choose candidates by sitelinks from a dump or QLever, or from per-occupation WDQS queries; (2) pull attributes with batched `VALUES` queries; (3) add pageviews for a recency-aware prior (for example, last 12 months of en.wikipedia views) so that currently popular people are guessed first.
- Sitelinks favour historically and globally notable people (Einstein, Napoleon), while pageviews favour current pop culture. A blend, such as the log of each, is probably a better prior for an entertainment game whose players skew toward pop culture.
- Wikidata coverage of fictional characters is thinner and less consistent than for humans. Typical gaps are missing gender, species and work links, so plan on LLM or Fandom backfill for characters.

### Gaps
- Could not read the WDQS User Manual directly (network blocked), so the per-IP parallelism limit (5) and the exact current endpoint hostnames after the legacy-endpoint deprecation are unverified.
- No sourced current (late-2026) count of Q5 humans or Q95074 fictional characters in Wikidata was found.
- No sourced current size for `latest-all.json.gz` in 2026; the latest concrete figure is about 147 GB (July 2025).

---

## 2. Other sources: DBpedia, ConceptNet, Fandom, IMDb/TMDB, MyAnimeList/AniList, animal and object datasets (and licensing)

### Takeaway
For a commercial game, Wikidata (CC0) is the only source here with no legal friction. Wikipedia-derived sources (DBpedia, ConceptNet, Fandom) are share-alike (CC BY-SA), which requires attribution and may impose share-alike on redistributed derived datasets. IMDb and TMDB forbid commercial use without a paid or negotiated license. AniList is free below $150/month of revenue. MyAnimeList separates commercial from non-commercial apps and can revoke access.

### Cited Findings
| Source | What it gives | License / terms | Source |
|---|---|---|---|
| Wikidata | Entities and typed attributes | CC0 (structured data) | [Wikidata:Licensing](https://www.wikidata.org/wiki/Wikidata:Licensing) |
| Wikipedia text (and thus DBpedia abstracts) | Descriptions, infobox-derived facts | CC BY-SA 3.0 + GFDL dual license | [Wikimedia legal](https://download.wikipedia.com/legal.html) |
| ConceptNet 5 | Commonsense relations for objects and animals (IsA, HasA, CapableOf, UsedFor, AtLocation...) | CC BY-SA 4.0 (some HF cards say 3.0 or cc-by-4.0, which is inconsistent; the official site says 4.0). Required attribution: "This work includes data from ConceptNet 5, which was compiled by the Commonsense Computing Initiative." | [conceptnet.io](https://conceptnet.io:443); [HF conceptnet5 card](https://huggingface.co/datasets/conceptnet5/blob/main/README.md); [Zenodo 5.8](https://zenodo.org/records/3739540) |
| Fandom wikis | Deep fictional-character detail (species, affiliation, powers, appearance) | Text is CC BY-SA 3.0 Unported; some wikis use other licenses; images and video are **not** CC BY-SA by default | [Fandom Licensing](https://www.fandom.com/Licensing); [Community Help:Licensing](https://community.fandom.com/wiki/Help:Licensing) |
| Fandom dumps | Bulk text | Wikia/Fandom stopped regular dumps after about 2010. Per-wiki dumps, where available, are linked from Special:Statistics. Third-party HF compilations exist (for example, all dumps available as of February 2025), labelled CC BY-SA 3.0. | [ArchiveTeam Fandom](https://wiki.archiveteam.org/index.php/Fandom); [HF nyuuzyou/fandom](https://huggingface.co/datasets/nyuuzyou/fandom); [HF RyokoAI/Fandom23K](https://huggingface.co/datasets/RyokoAI/Fandom23K/blob/main/README.md) |
| IMDb Non-Commercial Datasets | Titles, people, principal cast and characters, ratings (TSV) | Personal and non-commercial use only. You may not republish or repurpose the data to build a database. Commercial use goes through IMDb content licensing. | [IMDb Help: Can I use IMDb data](https://help.imdb.com/article/imdb/general-information/can-i-use-imdb-data-in-my-software/G5JTRESSHJBBHTGX); [IMDb non-commercial datasets](https://developer.imdb.com/non-commercial-datasets) |
| TMDB API | Movies/TV, cast, character names, popularity score | Free for non-commercial use with attribution. "License does not permit any commercial use" without a separate written agreement. Using cached data to train or validate models for others needs a commercial agreement. | [TMDB API Terms of Use](https://themoviedb.org:443/api-terms-of-use); [TMDB developer FAQ](https://developer.themoviedb.org/docs/faq) |
| AniList GraphQL API | Anime/manga characters (gender, age, role), popularity/favourites | Free without permission below $150/month revenue; above that, a commercial license by email. Rate limit 90 req/min nominally, but the docs also show a "degraded" 30 req/min warning (conflicting). | [AniList Terms of Use](https://anilist.gitbook.io/anilist-apiv2-docs/docs/guide/terms-of-use); [AniList Rate Limiting](https://docs.anilist.co/guide/rate-limiting) |
| MyAnimeList API | Anime/manga, characters | Governed by the MAL API License and Developer Agreement, which separates commercial uses (subscription, ads, paid apps) from non-commercial (free apps). MAL can revoke access at any time. | [MAL API Agreement](https://myanimelist.net/static/apiagreement.html) |
| McRae semantic feature norms | 541 concrete concepts (animals, objects) with participant-listed features; "gold standard" of feature norms | License not found in this research | [PMC article on property norms](https://pmc.ncbi.nlm.nih.gov/articles/PMC4237904) |
| THINGS-based 20Q dataset | 800 objects × 1,200 questions, answers generated by Claude 3.5 Sonnet, released publicly | See section 6 | [arXiv 2504.04204](https://arxiv.org/pdf/2504.04204) |

### Inferences
- A practical licensing-safe stack is: Wikidata (CC0) for entities and facts; ConceptNet or Wikipedia (CC BY-SA, with attribution on an about/credits page) for object and animal commonsense; and LLM-generated answers for everything else. Use IMDb and TMDB for internal validation or popularity checks, not as a shipped database, unless licensed.
- Share-alike risk: if you ship a derived candidate × question matrix built substantially from CC BY-SA text (Fandom, Wikipedia, ConceptNet), the matrix may need to be CC BY-SA too. Keeping the shipped matrix sourced from Wikidata plus your own LLM judgments and player feedback limits this. This is not legal advice; it needs a lawyer's review.
- For anime characters, AniList's "favourites" count is a good popularity prior within that domain. It is free for small apps.

### Gaps
- DBpedia's own dataset license page was not retrieved. DBpedia derives from Wikipedia, so CC BY-SA (and possibly GFDL) is expected, but this is unverified.
- Licenses for the McRae norms, the CSLB property norms, THINGS, and Animals with Attributes (AwA2: 50 animal classes × 85 binary attributes) were not found in this research. Searches for "CSLB" returned the California Contractors State License Board. The AwA2 class/attribute counts are from background knowledge, not a fetched source.
- MyAnimeList rate limits and commercial fees were not found.

---

## 3. Converting structured attributes into yes/no questions, and LLM question generation

### Takeaway
Map each (property, value) pair, or a derived bucket, to a templated question. Keep only questions that split the current candidate pool usefully (high information gain), and hand-curate the top 100 to 200. Use an LLM to propose additional "fuzzy" questions that knowledge graphs cannot express ("Does your character wear glasses?", "Is your character known for being evil?"), then filter them with the same information-gain test.

### Cited Findings
- Real Akinator also learns from players. Characters it does not know can be added by players, but only public figures are allowed. When a new entry is close to existing ones, it shows lists of candidate characters or questions. — [Akinator official FAQ](https://en.akinator.com/content/6/everything-you-ve-always-wanted-to-know-about-akinator)
- In LLM 20-Questions research, the Q20LLM dataset was built by prompting LLMs (Llama 3 70B and Mixtral via Groq, plus Mistral Large) for "a list of 500 diverse and simple keywords suitable for the 20 Questions game," together with generated game transcripts. It is CC0. — [HF cvmistralparis/Q20LLM](https://huggingface.co/datasets/cvmistralparis/Q20LLM)
- The THINGS-based dataset in "Adaptive Elicitation of Latent Information Using Natural Language" pairs 800 objects with 1,200 questions, all answered by Claude 3.5 Sonnet. This is a working precedent for an LLM-generated entity × question matrix. — [arXiv 2504.04204](https://arxiv.org/pdf/2504.04204)

**Template mapping (design proposal built on the Wikidata properties in section 1)**

| Attribute (Wikidata) | Question template | Notes |
|---|---|---|
| P31 = Q5 vs Q95074 | "Is your character a real person?" | First question in nearly all games; about 1 bit |
| P21 = Q6581072 | "Is your character female?" | |
| P106 ∈ {actor, singer, footballer, politician...} | "Is your character an actor/actress?", "...known for music?" | Group occupations into about 20 to 30 coarse buckets (music, film/TV, sport, politics, science, internet creator) |
| P27 | "Is your character American?", "...from Asia?" | Bucket by continent and by top 10 countries |
| P569 | "Was your character born before 1950?", "...after 1990?" | Threshold questions at quantiles of the candidate pool |
| P570 present | "Is your character dead?" | For fictional characters, ask the LLM instead |
| P1441/P1080 | "Is your character from an anime?", "...from the Marvel universe?", "...from a video game?" | Map work type (P31 of the work) to medium |
| Species (fictional) | "Is your character an animal?", "...a robot?" | Usually needs Fandom or LLM backfill |

### Inferences
- Pick and order questions by expected information gain (entropy reduction) over the popularity-weighted candidate distribution. The best first questions split the mass near 50/50, as "real vs fictional" and "male vs female" do.
- Phrase questions so that "probably / probably not / don't know" are natural answers, as Akinator does. Store per-pair yes-probabilities in [0,1], not booleans, so the engine tolerates player mistakes and ambiguous questions.
- An LLM question-generation loop works as follows. (1) Give the LLM samples of candidates that the current question bank cannot tell apart, and ask for questions that separate them. (2) Deduplicate by embedding similarity. (3) Have the LLM answer each new question for the confusable set. (4) Keep a question only if it has high variance across candidates and low "don't know" rates.

### Gaps
- No public documentation was found on how Akinator's Limule engine actually selects questions; the information-gain approach is an inference.
- No published benchmark compares templated KG questions with LLM-generated questions for guessing accuracy.

---

## 4. Using an LLM to fill in the matrix: cost, batching, accuracy

### Takeaway
A 5,000 × 500 matrix (2.5M judgments) is cheap if you ask for all 500 answers for one entity in a single call (5,000 calls), cache the shared question list, and use the Batch API (50% off). That works out to roughly single-digit dollars on a Haiku-class model and about $100 to $200 on Sonnet/Opus-class models, excluding thinking tokens. The real constraint is accuracy on long-tail entities, so ground the prompt with Wikidata facts or a Wikipedia summary and spot-check against Wikidata.

### Cited Findings
**Pricing (Anthropic first-party, per 1M tokens, from the claude-api skill's model table cached 2026-11-03; verify on the live page)** — [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing.md)
- Claude Haiku 5.5: $0.10 input / $0.50 output (for prompts up to 100K tokens; $0.50 / $2.50 beyond).
- Claude Sonnet 5.5: $2 / $10. Claude Opus 5.5: $4 / $20.
- Message Batches API: asynchronous, "50% cost reduction on all token usage." — [Anthropic batch processing docs](https://platform.claude.com/docs/en/build-with-claude/batch-processing.md)
- Prompt caching: cache reads cost about 0.1× the input price and cache writes about 1.25×. Caching is a prefix match, so put the fixed question list first and the varying entity last. — [Anthropic prompt caching docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching.md)
- Current models think by default; on some, thinking cannot be disabled (Opus 5.5 controls it only via `effort`; the default is `medium`). Thinking tokens are billed as output, so use `effort: "low"` for bulk labeling. — [Anthropic models overview](https://platform.claude.com/docs/en/about-claude/models/overview.md)

**Accuracy concerns**
- Head-to-Tail benchmark: GPT-4 and Llama 2-70B accuracy declines from head to torso to tail entities, and most sharply in domains like academics. — [Head-to-Tail, arXiv 2308.10168](https://arxiv.org/pdf/2308.10168)
- Hallucination-rate trends across popularity differ by model: for GPT-4 the rate decreased toward the tail (more abstention), while for Llama 2-70B it increased. — [arXiv 2308.10168](https://arxiv.org/pdf/2308.10168)
- Entity frequency in pre-training causes asymmetric recognition of logically equivalent facts (tested on Wikidata5M triples). — [arXiv 2503.22362](https://arxiv.org/html/2503.22362v2)
- An audit of GPTKB v1.5 (a KB elicited from a frontier LLM) found accuracy held up as exploration reached obscure entities even as Wikidata coverage fell. Reliability was highest for persons and locations and lowest for business and sports. — [arXiv 2510.07024](https://arxiv.org/pdf/2510.07024)
- The incomplete-information 20Q paper used GPT-3.5 to score commonness of 78,890 candidate entities and kept the top 10,000. This is a precedent for using an LLM to estimate a popularity prior. — [arXiv 2409.14762](https://arxiv.org/html/2409.14762v1)

**Cost worked example (arithmetic on the prices above; token counts are assumptions)**

Assumptions: one request per entity. The prompt holds about 500 questions × ~12 tokens = 6,000 tokens, plus about 300 tokens of entity context (name, Wikidata facts, a short description). Output is a compact JSON array of 500 probabilities (one decimal each) at about 2,500 tokens. Thinking tokens are excluded.
- Totals: 5,000 calls → about 31.5M input tokens and 12.5M output tokens.

| Model | Standard | Batch (−50%) | Batch + cached question list (approx.) |
|---|---|---|---|
| Haiku 5.5 ($0.10/$0.50) | $3.15 + $6.25 ≈ **$9.40** | ≈ **$4.70** | ≈ $3.3 (output dominates) |
| Sonnet 5.5 ($2/$10) | $63 + $125 ≈ **$188** | ≈ **$94** | ≈ $65 |
| Opus 5.5 ($4/$20) | $126 + $250 ≈ **$376** | ≈ **$188** | ≈ $130 |

The cached column assumes about 6,000 of the 6,300 input tokens are read from cache at 0.1×, and that batch and cache discounts stack. Verify stacking on the pricing page; cache hits inside batches are best-effort.

- Naive alternative, one call per (entity, question) pair: 2.5M requests × ~150 input tokens ≈ 375M input tokens, which is about 12× more input. It is also far more requests against rate limits. Avoid it.
- Middle ground: one call per entity per question block of about 100 questions (25k calls). This keeps outputs short and reduces position effects in long answer lists.

### Inferences
- Recommended strategy: (1) use Wikidata as ground truth where the attribute exists and do not ask the LLM; (2) have the LLM fill only missing or "fuzzy" cells; (3) run two models, or the same model twice with shuffled question order, and treat disagreement as uncertainty (p ≈ 0.5) or a trigger for review; (4) calibrate by checking LLM answers against Wikidata on attributes both cover (gender, occupation, nationality, alive/dead), stratified by sitelink bucket; (5) over time, update the probabilities from real player answers with a Bayesian/Beta update, as Akinator's learning-from-players approach does.
- Ask for a probability or a 5-level answer (yes / probably / unknown / probably not / no), not a binary. This matches the game's answer set and lets the engine absorb ambiguity ("Is X tall?").
- Ground every prompt with retrieved facts (the Wikidata claims plus the first paragraph of the Wikipedia article). This is the main mitigation for long-tail hallucination.
- Use structured outputs (JSON schema with a fixed-length array) so 500 answers parse reliably, and validate the array length.

### Gaps
- No published measurement of LLM accuracy on Akinator-style subjective questions (for example "Is your character funny?") was found. You will need your own eval set of about 200 to 500 hand-labeled cells.
- Thinking-token overhead per request at `low` effort was not measured; it could materially raise output cost on models that always think.
- Whether batch and prompt-caching discounts fully stack was not verified from the live docs in this session.

---

## 5. Choosing the size of the candidate set and question bank for v1

### Takeaway
Akinator itself has at least 100k characters and has grown through player contributions. Research 20Q setups range from 158 to about 10k entities, and LLM-labeled matrices of 800 × 1,200 are published. A sensible v1 is about 2,000 to 5,000 popularity-ranked candidates and about 200 to 500 questions, with an "add your character" loop to grow from there.

### Cited Findings
- Akinator database size: "more than 100,000 characters" per Gizmodo. Other numbers (1.5M, 2M, 3M+) appear only on unofficial AI-avatar pages that conflict with one another. — [Gizmodo](https://gizmodo.com/download/akinator); unofficial: [shapes.inc](https://www.shapes.inc/akinator01) (low reliability)
- Akinator is built on Elokence's "Limule" engine. — [Wikipedia: Akinator](https://en.wikipedia.org/wiki/Akinator)
- Research pools: LMRL Gym 20Q uses 158 objects across 17 categories (100K generated conversations). The incomplete-information study filtered 78,890 entities down to the top 10,000 by LLM-rated commonness. THINGS-20Q uses 800 objects × 1,200 questions. Geo20Q+ uses geographically diverse Wikipedia entities and reports that LLMs deduce Global North/West entities better. A Multi-Turn Puzzles benchmark samples from the WordNet noun lexicon. — [LMRL Gym, arXiv 2311.18232](https://arxiv.org/pdf/2311.18232); [arXiv 2409.14762](https://arxiv.org/html/2409.14762v1); [arXiv 2504.04204](https://arxiv.org/pdf/2504.04204); [Geo20Q+, arXiv 2508.05525](https://arxiv.org/pdf/2508.05525v1); [arXiv 2508.10142](https://arxiv.org/html/2508.10142v2)
- One unofficial page says Akinator asks up to about 25 questions per round. — [shapes.inc FAQ](https://shapes.inc/akinator-wjyx/faq) (unverified)

### Inferences
- Information-theory sanity check: 20 well-chosen binary questions can in principle separate 2^20 ≈ 1M candidates, and 5,000 candidates need only about 12.3 bits. Real questions are correlated and noisy, though, so having 25 or more questions available per game, and 200 to 500 in the bank, gives the headroom needed for noisy answers.
- With a popularity prior, a small head set covers most games, because players mostly pick famous characters. Start with the top 3,000 to 5,000 by a blended sitelinks and pageviews score across humans and fictional characters. Add a few hundred animals and objects only if those modes are in scope.
- At this size the matrix is 1M to 2.5M cells (a few MB as uint8 probabilities), so the whole thing fits in memory on the client or server and inference per question is trivial.
- Track a "not found" rate and the names users submit; these show where to expand the candidate set next.

### Gaps
- No official Elokence figure for the current number of Akinator characters or questions was found.
- No empirical study on the minimum question-bank size needed for a target guess accuracy was found.

---

## 6. Existing public datasets for 20 Questions / guessing games

### Takeaway
There is no public Akinator-style people × attributes matrix. The most reusable assets are the AllenAI Twenty Questions data (commonsense object Q&A), the THINGS-based 800 × 1,200 LLM-answered matrix, and small LLM-generated 20Q corpora on Hugging Face. For people and characters you have to build the matrix yourself from Wikidata plus an LLM.

### Cited Findings
- **AllenAI twentyquestions**: crowdsourced 20Q questions and answers about everyday objects, mirrored on Hugging Face as `maximedb/twentyquestions` and `metaeval/twentyquestions`. — [HF maximedb/twentyquestions](https://huggingface.co/datasets/maximedb/twentyquestions/discussions) ("taken from https://github.com/allenai/twentyquestions"); [HF metaeval/twentyquestions](https://huggingface.co/datasets/metaeval/twentyquestions/tree/main)
- **THINGS 20Q (Adaptive Elicitation paper)**: 800 THINGS objects, each with answers to 1,200 questions generated by Claude 3.5 Sonnet, stated as publicly available. — [arXiv 2504.04204](https://arxiv.org/pdf/2504.04204)
- **Q20LLM**: CC0; game and keyword splits; keywords span literature, food, travel, religion and more; generated with Llama 3 70B, Mixtral and Mistral Large. — [HF cvmistralparis/Q20LLM](https://huggingface.co/datasets/cvmistralparis/Q20LLM)
- **clips/20Q**: small HF dataset (1K to 10K examples) with a mostly unfilled dataset card. — [HF clips/20Q](https://huggingface.co/datasets/clips/20Q/tree/00d84f741dda99d94db780c90ebb5f980050381d)
- **roborovski/twenty_questions**: another HF repo; contents not inspected. — [HF roborovski/twenty_questions](https://huggingface.co/datasets/roborovski/twenty_questions/tree/main/data)
- **Open-source 20Q entity set used in arXiv 2409.14762**: 78,890 entities (top 10k kept by commonness); also includes a "BrainKing" variant with misleading answers. — [arXiv 2409.14762](https://arxiv.org/pdf/2409.14762)
- **LMRL Gym 20Q**: 100K conversations, a GPT-3.5 oracle, 158 objects in 17 categories. — [arXiv 2311.18232](https://arxiv.org/pdf/2311.18232)
- **BIG-bench twenty_questions task**: model-vs-model 20Q game. — [BIG-bench twenty_questions](https://www.github.com/google/BIG-bench/blob/main/bigbench/benchmark_tasks/twenty_questions)
- **Geo20Q+**: geographically diverse entity set from Wikipedia, built to measure regional bias (COLM 2025). — [arXiv 2508.05525](https://arxiv.org/pdf/2508.05525v1)
- **Mintaka** (Amazon): complex QA over Wikidata entities. Not 20Q, but a source of Wikidata-linked popular entities. — [HF AmazonScience/mintaka](https://huggingface.co/datasets/AmazonScience/mintaka)

### Inferences
- These datasets are most useful for (a) evaluating an LLM-driven questioner or answerer, (b) object and animal modes (AllenAI, THINGS), and (c) prompt and format examples for LLM matrix generation. None covers celebrities or fictional characters at Akinator scale.
- The Geo20Q+ finding of regional bias suggests auditing the candidate set and LLM answers for Global North/West skew, especially if the game targets international audiences.

### Gaps
- No Kaggle dataset specifically for Akinator or 20Q was found in this research. Kaggle was not directly searchable from this session.
- Licenses for the AllenAI twentyquestions data and the THINGS-20Q release were not confirmed.
