# MindReader data pipeline

Builds the character knowledge base from the Wikidata JSON dump into Postgres:
about 350k real people and 150k fictional characters, attributes, generated questions in
7 languages, licensed photos, and LLM-filled traits.

Full documentation (assumptions, filters, attribute-to-question mapping, runtimes, costs,
test plan): [`../docs/02-data-pipeline.md`](../docs/02-data-pipeline.md).

```bash
pip install -r requirements.txt
export DATABASE_URL=postgresql://user:pass@host:5432/mindreader
python -m mrpipe schema
python -m mrpipe all --work work --dump latest-all.json.bz2 --pageviews pageviews/
python -m mrpipe images --work work
python -m mrpipe enrich estimate --work work      # then: enrich submit --yes, enrich collect
python -m mrpipe i18n submit --work work --yes    # then: i18n collect
```

Tests (need a Postgres user with CREATEDB):

```bash
MR_TEST_DSN=postgresql://user:pass@localhost:5432/postgres python -m pytest -q
```

| Module | Job |
|---|---|
| `mrpipe/dump.py` | Streams the dump through lbzip2 / pigz and a pool of worker processes |
| `mrpipe/pass1.py` | People, the P279 class graph, typed items |
| `mrpipe/select.py` | Tunes the sitelink threshold, finds fictional characters, lists items for pass 2 |
| `mrpipe/pass2.py` | Labels, descriptions, aliases, sitelinks and images for the selection |
| `mrpipe/pageviews.py` | 12 months of pageviews (text or Parquet monthly files) |
| `mrpipe/build.py` | Attribute rules and question generation |
| `mrpipe/load.py` | Idempotent load into Postgres with stable question ids |
| `mrpipe/images.py` | Commons licence filter and WebP / AVIF thumbnails |
| `mrpipe/llm_enrich.py` | Trait answers for the top characters (Message Batches API) |
| `mrpipe/llm_i18n.py` | Question rewrite, translation and screening (Message Batches API) |
