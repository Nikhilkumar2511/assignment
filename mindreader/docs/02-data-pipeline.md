# MindReader: deliverable 2, Postgres schema and Wikidata pipeline

Code: `pipeline/` (Python package `mrpipe`), schema: `pipeline/schema/001_init.sql`.
Status: all stages run end to end on a synthetic dump in the real Wikidata JSON format, loading into Postgres 16. 13 tests pass. **I have not run it on the real dump**: this environment cannot reach Wikidata or the Wikimedia dumps. Section 7 lists what to run first and what to check.

## 1. Assumptions

1. **Input files.** `latest-all.json.bz2` (or `.gz`) from `dumps.wikimedia.org/wikidatawiki/entities/`, and 12 monthly files from `dumps.wikimedia.org/other/pageview_complete/monthly/`. Wikimedia's own tracker shows the monthly pageview files published both as Parquet and as text, so the loader reads both. I could not inspect a real monthly file, so the column detection is an assumption to check on the first run.
2. **Batch machine.** 8 vCPU, 32 GB RAM, 500 GB disk, with `lbzip2` (for .bz2) or `pigz` (for .gz) installed. Without them, Python's single-thread decompression takes about 15 to 20 hours per pass instead of roughly 1.5 to 3 hours.
3. **Two passes over the dump.** Pass 1 cannot know which items are fictional characters until it has seen the whole class graph, so labels for characters and attribute values come from pass 2.
4. **Wikidata IDs.** The pipeline uses Q5 (human), Q95074 (fictional character), Q178885 (deity), Q2239243 (mythical creature, confirmed by search), P2563 (superhuman ability, confirmed), plus standard properties (P31, P279, P21, P27, P106, P569, P570, P18 and so on). I could not confirm the Q-numbers for "mythical character" and "legendary figure", so those classes are found by English label pattern instead. Every class found this way is listed in `work/pass2/select_report.json` for you to review.
5. **Sensitive data is never extracted.** No religion (P140), ethnicity (P172), sexual orientation (P91) or medical condition (P1050). Political party is included for politicians only (support of 200 or more).
6. **Gender mapping.** Trans women count as female, trans men as male, and non-binary and intersex people as "nonbinary". So "Is your character female?" answers the way a player expects.
7. **Minors.** A living person born less than 18 years ago is flagged `is_minor` and never gets a photo.
8. **Deities.** Characters under the deity class tree are flagged `is_religious`. Whether to show gods of living religions is a product decision. The data keeps the flag so the game service can filter.
9. **The trait list has 136 questions,** not about 300 as I wrote in deliverable 1. That halves the LLM cost estimate. Adding traits later only needs a new `enrich submit` for them.

## 2. How to run

```bash
cd mindreader/pipeline
pip install -r requirements.txt
export DATABASE_URL=postgresql://user:pass@host:5432/mindreader

python -m mrpipe schema                                     # needs a database owner, no superuser
python -m mrpipe sample --dump latest-all.json.bz2 --out sample.json.gz --every 100   # 1% sample, for timing
python -m mrpipe all --work work --dump latest-all.json.bz2 --pageviews pageviews/   # pass1..load
python -m mrpipe images --work work                         # Commons photos -> work/images/img/*
python -m mrpipe enrich estimate --work work                # prints the LLM cost, spends nothing
python -m mrpipe enrich submit --work work --yes            # Claude Haiku 5.5, Message Batches API
python -m mrpipe enrich collect --work work                 # resumable; writes facts
python -m mrpipe i18n submit --work work --yes              # Claude Opus 5.5 rewrite + 6 translations
python -m mrpipe i18n collect --work work
```

Settings are environment variables (see `mrpipe/config.py`): `MR_TARGET_REAL` (350000), `MR_TARGET_FICTIONAL` (150000), `MR_HUMAN_PREFILTER` (3), `MR_SUPPORT_SCALE` (1.0), `MR_ENRICH_TOP_N` (50000), `MR_ENRICH_MODEL`, `MR_I18N_MODEL`, `MR_USER_AGENT`. Set `MR_USER_AGENT` to include a contact address before you call Commons. Wikimedia asks automated clients to identify themselves.

### Expected runtime and cost (estimates, not measured on the real dump)

| Step | Estimate | Basis |
|---|---|---|
| Pass 1 | 1.5 to 3 h | Decompression bound. Parsing measured at 1,500 lines/s per core for 95 KB entities and 15,000 lines/s for 14 KB entities (`scripts/bench_pass1.py`), about 0.3 h on 4 cores. |
| Select, build, load | under 1 h | In-memory Python over about 500k characters. |
| Pass 2 | 1.5 to 3 h | Same decompression cost; only wanted ids are parsed. |
| Pageviews | under 1 h | 12 files, dictionary lookups. |
| Images | 10 to 20 h for about 250k photos | Throttled to 5 requests per second to respect Commons. Resumable. |
| LLM trait fill | about USD 20 for 50,000 characters | `enrich estimate` on the fixture: about 1,600 input and 1,200 output tokens per character at Haiku 5.5 batch prices, before thinking tokens. |
| LLM rewrite and translation | about USD 5 to 15 for 50,000 questions | 40 questions per request on Opus 5.5 at batch prices. |

## 3. Dump filters

| Set | Rule | Target |
|---|---|---|
| Real people | `P31` contains Q5, and Wikipedia sitelinks >= N. Pass 1 keeps everyone with >= 3; `select` picks the N whose count is closest to 350,000 and reports it. | ~350k |
| Fictional | `P31` is a class below Q95074, Q178885, Q2239243, or a label-matched mythology class (P279 closure over the whole dump), and not human. Ranked by sitelinks, top 150,000. | ~150k |
| Sitelinks | Only Wikipedias: keys ending in `wiki`, minus commons, species, meta, wikidata, mediawiki, sources, incubator, foundation, outreach, wikimania, wikifunctions. | |
| Byte-level prefilter | A line with `"sitelinks":{}` and no `"P279"` is skipped without JSON parsing. That covers most of the dump: scholarly articles, taxa without articles, and so on. | |
| Rank | Deprecated statements are ignored; preferred statements come first. | |
| Popularity | `ln(1 + sitelinks) + 0.6 × ln(1 + pageviews over 12 months)`, pageviews summed over 30 large Wikipedias. | |

## 4. Attribute-to-question mapping

Every question is either an attribute-group question, computed from the character's values, or a trait question, filled by the LLM and players. For group questions:
- P(yes) is `p_match` when the character has the value.
- It is `p_other` when the character has only other values in that group.
- It is 0.5 when the group is empty for that character.

Wikidata is open world, so `p_other` is high for groups where a missing value proves little (occupation 0.12, language 0.2) and low for exclusive ones (gender 0.04).

| Group | Source | Scope | p_match / p_other | Min support | Example question |
|---|---|---|---|---|---|
| kind | P31 = Q5 or fictional | all | 0.97 / 0.03 | 1 | Is your character a real person? |
| gender | P21 | all | 0.95 / 0.04 | 50 | Is your character female? |
| vital | P570 present, or born over 110 years ago | real | 0.95 / 0.05 | 1 | Is your character still alive? |
| birth_year | P569 year; 14 threshold questions | real | 0.95 / 0.05 | 1 | Was your character born in 1990 or later? |
| region | Country -> 10 regions (South Asia, Middle East, Latin America...) | all | 0.93 / 0.08 | 1 | Is your character from the Middle East? |
| country | P27, or P495 of the work for fictional characters; historical states follow P1366 when there is one successor | all | 0.93 / 0.08 | 200 | Is your character from India? |
| occupation | P106 + 3 levels of parent occupations, stopping at generic classes | all | 0.92 / 0.12 | 150 | Is your character a cricketer? |
| sport | P641, also inferred from the occupation | all | 0.92 / 0.08 | 100 | Is your character known for cricket? |
| team | P54 | real | 0.92 / 0.12 | 120 | Has your character played for FC Barcelona? |
| award | P166 + 2 levels of parents | real | 0.90 / 0.15 | 150 | Has your character won the Nobel Prize? |
| position | P39 + 2 levels of parents | real | 0.92 / 0.10 | 30 | Has your character been Prime Minister of India? |
| party | P102 | real | 0.90 / 0.10 | 200 | Is your character a member of the ... Party? |
| genre, instrument, educated_at, language | P136, P1303, P69, P1412 + P103 | real | see config | 150 to 300 | Does your character play the guitar? |
| member_of | P463 (bands, hero teams) | all | 0.93 / 0.08 | 3 | Is your character a member of BTS? |
| notable_work | P800 | real | 0.88 / 0.10 | 3 | Is your character known for Titanic? |
| franchise | P8345, P1080, P179 on the character or its works | fictional | 0.95 / 0.06 | 3 | Is your character from Naruto? |
| work | P1441 | fictional | 0.93 / 0.08 | 3 | Does your character appear in One Piece? |
| medium | Label patterns on the works' classes (anime, manga, film, TV, comics, game, book, animated, mythology) | fictional | 0.90 / 0.15 | 1 | Is your character from an anime? |
| creator | P170, or P170 / P50 of the work | fictional | 0.90 / 0.08 | 5 | Was your character created by Akira Toriyama? |
| char_type | Label patterns on the character's classes (human, animal, dog, robot, alien, deity, superhero, villain, Pokemon...) | fictional | 0.92 / 0.08 | 1 | Is your character a robot, android or AI? |
| power | P2563 | fictional | 0.90 / 0.25 | 20 | Does your character have this power: flight? |
| hair_color, eye_color | P1884, P1340 | all | 0.88 / 0.10 | 50 | Does your character have black hair? |
| played_character | Reverse of P175 (performer) on characters | real | 0.93 / 0.10 | 1 | Has your character played Spider-Man? |
| played_in_franchise | Franchises of those characters | real | 0.90 / 0.10 | 3 | Has your character acted in Harry Potter? |
| trait (136) | `data/trait_questions.json`, filled by the LLM for the top 50k | per trait | yes 0.92 ... no 0.08, weight 3 | | Does your character wear glasses? |

Question keys are stable (`eq:country:Q668`, `in:birth_year:after_1990`, `trait:wears_glasses`), so question ids survive monthly reloads. Questions with identical English wording are merged, keeping the one with more support. The English template text is replaced by the LLM rewrite in `i18n`. That step also rejects offensive, vague or non-yes/no questions and logs why in `moderation_log`.

## 5. Schema overview

```mermaid
erDiagram
  entities ||--o{ entity_labels : "7 languages"
  entities ||--o{ entity_names : "labels + aliases, trigram index"
  entities ||--o{ entity_attrs : has
  attr_groups ||--o{ attr_values : contains
  attr_values ||--o{ entity_attrs : "is value of"
  attr_values ||--o{ attr_value_labels : "7 languages"
  attr_groups ||--o{ questions : "eq / in questions"
  questions ||--o{ question_texts : "7 languages"
  entities ||--o{ facts : "LLM and admin cells"
  questions ||--o{ facts : ""
  entities ||--o| images : "Commons photo + licence"
  games ||--o{ evidence : "answers of confirmed games"
  evidence }o--|| entities : ""
  evidence_agg }o--|| questions : "nightly, time-decayed"
  devices ||--o{ games : "reliability"
  games ||--o| submissions : "new character"
```

Other tables: `takedown_requests`, `denylist` (instant hides between snapshots), `moderators`, `moderation_log`, `snapshots`, `pipeline_runs`, `languages`.

Search: `mr_normalize()` lower-cases, strips accents and splits on punctuation, keeping combining marks. Under some locales `[[:punct:]]` matches the Devanagari nukta, which broke Hindi names; the function uses explicit ranges instead and is tested on Hindi, Japanese, Arabic and full-width text. A GIN trigram index serves fuzzy typeahead: "Virat Koli" finds Virat Kohli.

## 6. What the tests cover

`MR_TEST_DSN=postgresql://user:pass@localhost/postgres python -m pytest -q` (the user needs CREATEDB). 13 tests, all passing:
- **Extraction.** Pass 1, select and pass 2 on a fixture dump in the Wikidata JSON format: bz2 and gzip, a property entity, an item without sitelinks, non-Wikipedia sitelinks.
- **Selection.** The threshold is tuned to the target, low-sitelink people are dropped, and the label-matched mythology root is found.
- **Mapping.** Gandhi's British Raj citizenship maps to India and South Asia. Einstein gets both Nobel Prize levels but not the generic "award". Kohli gets cricket inferred from "cricketer". Tom Holland gets "played Spider-Man". Naruto gets anime + TV + human + creator. Hanuman gets deity + mythology. The child is flagged as a minor.
- **Pageviews.** Both formats are read, mobile domains are merged, and unknown wikis are ignored.
- **Postgres.** Loading twice keeps question ids. Characters dropped from a later selection are hidden, then restored. Search works by prefix, by fuzzy match and in Japanese.
- **Images.** Against a fake Commons: CC BY-SA accepted, NC rejected, minor rejected, missing file marked failed. Thumbnails are written at 256 and 512 px in WebP and AVIF, the author's HTML is stripped, and a rerun retries only the failure.
- **LLM steps.** Against a fake batch API: the right models, effort, cached system prompt and per-scope JSON schema. Refusals and "unknown character" answers are skipped, and probabilities are stored correctly. Rejected questions are logged, and human translations are never overwritten.
- **Robustness.** A worker crash stops the run with the worker's traceback instead of hanging.

## 7. What you should test

1. **Schema on your Postgres:** `python -m mrpipe schema`. Expect "schema applied". If `CREATE EXTENSION` fails, ask your host to allow `pg_trgm` and `unaccent`; both are on Neon, Supabase, RDS and Cloud SQL.
2. **1% sample for timing:** `python -m mrpipe sample ... --every 100`, then `python -m mrpipe pass1 --dump sample.json.gz`. Multiply the time by 100 to estimate a full pass. The sample's class tree is incomplete, so don't judge selection quality from it.
3. **Full run, then read `work/pass2/select_report.json`:**
   - `human_sitelink_threshold_N` and `humans_selected` (about 350k).
   - `fictional_selected` (about 150k).
   - `fictional_root_classes_by_label`: remove any class that is not a character class by tightening `FICTIONAL_ROOT_LABEL_PATTERNS`.
   - `top_fictional_classes`: these should look like "fictional human", "anime character" and so on.
4. **Read `work/build/build_report.json`:** `questions_per_group` and `avg_attributes_per_entity`. A fictional average under 5 means the LLM fill is essential.
5. **Spot-check 20 famous characters you know** (mix countries and media):
   `SELECT g.key, vl.label FROM entity_attrs a JOIN attr_values av ON av.id=a.value_id JOIN attr_groups g ON g.id=av.group_id LEFT JOIN attr_value_labels vl ON vl.value_id=av.id AND vl.lang='en' WHERE a.entity_id = 42;` (replace 42 with the number from the character's Wikidata URL, for example `Q42`).
6. **Pageview columns:** run `pageviews` on one month first. If it raises "cannot find a column", send me the column names and I'll adjust `_pick`.
7. **Images:** run `images --limit 200`, then open 10 thumbnails and check the author and licence against the Commons page.
8. **LLM:** run `enrich estimate`, then `enrich submit --top 500 --yes` before the full 50k. Spot-check 20 characters' facts and the `characters_unknown_to_model` count.
