-- MindReader database schema, version 1.
-- Postgres 16. Apply with:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f schema/001_init.sql
--
-- Design notes
-- * Characters are keyed by their Wikidata numeric id (Q42 -> 42). Player-submitted
--   characters that have no Wikidata item get negative ids from a sequence.
-- * The P(yes | character, question) matrix is "virtual": most questions are
--   (attribute group, value) pairs, and the probability comes from the character's
--   values in that group plus the group's p_match / p_other. Only cells that come from
--   somewhere else (LLM trait fill, admins, learned evidence) are stored in `facts`.
-- * Learned evidence is append-only (`evidence`); a nightly job folds it, with time
--   decay, into `evidence_agg`, which the snapshot builder reads.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;

-- unaccent() is not IMMUTABLE, so it cannot be used in an index directly.
CREATE OR REPLACE FUNCTION mr_normalize(txt text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT btrim(regexp_replace(lower(public.unaccent('public.unaccent'::regdictionary, coalesce(txt, ''))),
                              -- ASCII punctuation, Latin-1 punctuation, general and CJK punctuation, fullwidth
                              -- forms. Not [[:punct:]]: in some locales it also matches combining
                              -- marks such as the Devanagari nukta and breaks Hindi names.
                              E'[\\s!-/:-@\\[-`{-~\\u00a1-\\u00bf\\u00d7\\u00f7\\u2000-\\u206f\\u3000-\\u303f\\u30fb\\uff01-\\uff0f\\uff1a-\\uff20]+',
                              ' ', 'g'))
$$;

-- ---------------------------------------------------------------- reference data

CREATE TABLE languages (
  code        text PRIMARY KEY,               -- 'en', 'hi', 'es', 'pt', 'ja', 'fr', 'ar'
  name        text NOT NULL,
  rtl         boolean NOT NULL DEFAULT false
);
INSERT INTO languages (code, name, rtl) VALUES
  ('en', 'English', false), ('hi', 'Hindi', false), ('es', 'Spanish', false),
  ('pt', 'Portuguese', false), ('ja', 'Japanese', false), ('fr', 'French', false),
  ('ar', 'Arabic', true);

-- ---------------------------------------------------------------- characters

CREATE SEQUENCE player_entity_id_seq START WITH 1;   -- used negated for player submissions

CREATE TABLE entities (
  id              bigint PRIMARY KEY,                 -- Wikidata numeric id, or negative for player-made
  kind            text NOT NULL CHECK (kind IN ('real', 'fictional')),
  status          text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'pending', 'hidden')),
  source          text NOT NULL DEFAULT 'wikidata' CHECK (source IN ('wikidata', 'player', 'admin')),
  sitelinks       integer NOT NULL DEFAULT 0,         -- Wikipedia sitelinks only
  pageviews_12m   bigint NOT NULL DEFAULT 0,
  popularity      real NOT NULL DEFAULT 0,            -- log-scale score, the snapshot prior is built from it
  birth_year      integer,                            -- negative for BCE
  is_minor        boolean NOT NULL DEFAULT false,     -- living person under 18: never shown with a photo
  is_religious    boolean NOT NULL DEFAULT false,     -- deity or figure of worship: product decides how to treat
  hidden_reason   text,
  times_played    integer NOT NULL DEFAULT 0,
  times_guessed   integer NOT NULL DEFAULT 0,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX entities_status_pop_idx ON entities (status, popularity DESC);

CREATE TABLE entity_labels (
  entity_id   bigint NOT NULL REFERENCES entities (id) ON DELETE CASCADE,
  lang        text NOT NULL REFERENCES languages (code),
  label       text NOT NULL,
  description text,                                   -- Wikidata description (CC0), one line
  PRIMARY KEY (entity_id, lang)
);

-- Every searchable name: labels and aliases in all supported languages.
CREATE TABLE entity_names (
  entity_id   bigint NOT NULL REFERENCES entities (id) ON DELETE CASCADE,
  lang        text NOT NULL,
  name        text NOT NULL,
  is_alias    boolean NOT NULL DEFAULT false,
  name_norm   text GENERATED ALWAYS AS (mr_normalize(name)) STORED,
  PRIMARY KEY (entity_id, lang, name)
);
CREATE INDEX entity_names_trgm_idx ON entity_names USING gin (name_norm gin_trgm_ops);
CREATE INDEX entity_names_prefix_idx ON entity_names (name_norm text_pattern_ops);

CREATE TABLE entity_sitelinks (
  entity_id   bigint NOT NULL REFERENCES entities (id) ON DELETE CASCADE,
  wiki        text NOT NULL,                          -- 'enwiki', 'hiwiki', ...
  title       text NOT NULL,
  PRIMARY KEY (entity_id, wiki)
);

-- ---------------------------------------------------------------- attributes

CREATE TABLE attr_groups (
  id            smallint PRIMARY KEY,
  key           text NOT NULL UNIQUE,                 -- 'country', 'occupation', 'franchise', ...
  scope         text NOT NULL CHECK (scope IN ('all', 'real', 'fictional')),
  p_match       real NOT NULL CHECK (p_match > 0 AND p_match < 1),   -- P(yes) when the character has the value
  p_other       real NOT NULL CHECK (p_other > 0 AND p_other < 1),   -- P(yes) when it has only other values in the group
  min_support   integer NOT NULL,                     -- characters needed before a value becomes a question
  max_questions integer NOT NULL,
  description   text NOT NULL
);

CREATE TABLE attr_values (
  id           integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  group_id     smallint NOT NULL REFERENCES attr_groups (id),
  value_key    text NOT NULL,                         -- 'Q668', 'year:1990', 'medium:anime'
  wikidata_id  bigint,
  support      integer NOT NULL DEFAULT 0,
  UNIQUE (group_id, value_key)
);

CREATE TABLE attr_value_labels (
  value_id  integer NOT NULL REFERENCES attr_values (id) ON DELETE CASCADE,
  lang      text NOT NULL REFERENCES languages (code),
  label     text NOT NULL,
  PRIMARY KEY (value_id, lang)
);

CREATE TABLE entity_attrs (
  entity_id  bigint NOT NULL REFERENCES entities (id) ON DELETE CASCADE,
  value_id   integer NOT NULL REFERENCES attr_values (id) ON DELETE CASCADE,
  source     text NOT NULL DEFAULT 'wikidata' CHECK (source IN ('wikidata', 'derived', 'admin')),
  PRIMARY KEY (entity_id, value_id)
);
CREATE INDEX entity_attrs_value_idx ON entity_attrs (value_id);

-- ---------------------------------------------------------------- questions

CREATE TABLE questions (
  id            integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,   -- ids are never reused
  key           text NOT NULL UNIQUE,                 -- 'eq:country:Q668', 'in:birth_year:after_1990', 'trait:wears_glasses'
  kind          text NOT NULL CHECK (kind IN ('eq', 'in', 'trait')),
  group_id      smallint REFERENCES attr_groups (id),
  value_ids     integer[],                            -- eq: one value, in: a set of values, trait: NULL
  scope         text NOT NULL CHECK (scope IN ('all', 'real', 'fictional')),
  status        text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'hidden', 'rejected')),
  support       integer NOT NULL DEFAULT 0,
  usefulness    real NOT NULL DEFAULT 0,              -- nightly: average information gain when asked
  dup_cluster   integer,                              -- nightly: questions in one cluster are near duplicates
  times_asked   integer NOT NULL DEFAULT 0,
  source        text NOT NULL DEFAULT 'generated' CHECK (source IN ('generated', 'trait', 'admin')),
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  CHECK ((kind = 'trait') = (group_id IS NULL))
);
CREATE INDEX questions_status_idx ON questions (status);

CREATE TABLE question_texts (
  question_id  integer NOT NULL REFERENCES questions (id) ON DELETE CASCADE,
  lang         text NOT NULL REFERENCES languages (code),
  text         text NOT NULL,
  origin       text NOT NULL CHECK (origin IN ('template', 'llm', 'human')),
  reviewed     boolean NOT NULL DEFAULT false,
  PRIMARY KEY (question_id, lang)
);

-- Explicit cells: LLM trait fill, admin edits. yes_w / no_w are pseudo-counts.
CREATE TABLE facts (
  entity_id    bigint NOT NULL REFERENCES entities (id) ON DELETE CASCADE,
  question_id  integer NOT NULL REFERENCES questions (id) ON DELETE CASCADE,
  yes_w        real NOT NULL CHECK (yes_w >= 0),
  no_w         real NOT NULL CHECK (no_w >= 0),
  source       text NOT NULL CHECK (source IN ('llm', 'admin')),
  model        text,
  updated_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (entity_id, question_id, source)
);
CREATE INDEX facts_question_idx ON facts (question_id);

-- ---------------------------------------------------------------- images

CREATE TABLE images (
  entity_id      bigint PRIMARY KEY REFERENCES entities (id) ON DELETE CASCADE,
  commons_file   text NOT NULL,                       -- 'File:Example.jpg'
  status         text NOT NULL CHECK (status IN ('ok', 'rejected_license', 'rejected_minor', 'failed', 'takedown')),
  license_short  text,                                -- 'CC BY-SA 4.0'
  license_url    text,
  author         text,                                -- plain text, tags stripped
  credit_url     text,                                -- the file's Commons page
  restrictions   text,                                -- Commons 'Restrictions' field, e.g. 'personality'
  width          integer,
  height         integer,
  sha1           text,
  storage_prefix text,                                -- 'img/42' -> img/42-256.webp, -512.avif, ...
  fetched_at     timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- games and learning

CREATE TABLE devices (
  device_hash  bytea PRIMARY KEY,                     -- HMAC of a random id kept in localStorage
  games        integer NOT NULL DEFAULT 0,
  agreements   real NOT NULL DEFAULT 0,               -- answers that matched confident facts
  disagreements real NOT NULL DEFAULT 0,
  reliability  real NOT NULL DEFAULT 1.0 CHECK (reliability >= 0 AND reliability <= 1),
  updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE games (
  id                uuid PRIMARY KEY,                 -- from the signed game token
  started_at        timestamptz NOT NULL,
  finished_at       timestamptz,
  snapshot_version  integer NOT NULL,
  lang              text NOT NULL,
  outcome           text NOT NULL CHECK (outcome IN ('won', 'lost', 'abandoned')),
  n_questions       smallint NOT NULL,
  n_guesses         smallint NOT NULL,
  guessed_entity_id bigint,
  true_entity_id    bigint,                           -- confirmed by the player, if any
  answers           jsonb NOT NULL,                   -- [[question_id, answer_code], ...]
  device_hash       bytea REFERENCES devices (device_hash) ON DELETE SET NULL,
  reliability       real,
  device_class      smallint,                         -- 0 low, 1 mid, 2 high end
  country           char(2),                          -- from the CDN header, country level only
  flagged           text
);
CREATE INDEX games_finished_idx ON games (finished_at);
CREATE INDEX games_true_entity_idx ON games (true_entity_id);

CREATE TABLE evidence (
  game_id      uuid NOT NULL REFERENCES games (id) ON DELETE CASCADE,
  entity_id    bigint NOT NULL REFERENCES entities (id) ON DELETE CASCADE,
  question_id  integer NOT NULL REFERENCES questions (id) ON DELETE CASCADE,
  answer       smallint NOT NULL CHECK (answer IN (0, 1, 2, 3, 4)),   -- yes, probably, dont_know, probably_not, no
  weight       real NOT NULL CHECK (weight >= 0),
  created_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (game_id, question_id)
);
CREATE INDEX evidence_cell_idx ON evidence (entity_id, question_id);
CREATE INDEX evidence_created_idx ON evidence (created_at);

CREATE TABLE evidence_agg (
  entity_id    bigint NOT NULL REFERENCES entities (id) ON DELETE CASCADE,
  question_id  integer NOT NULL REFERENCES questions (id) ON DELETE CASCADE,
  yes_w        real NOT NULL,
  no_w         real NOT NULL,
  updated_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (entity_id, question_id)
);

-- ---------------------------------------------------------------- moderation and safety

CREATE TABLE submissions (
  id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  game_id            uuid REFERENCES games (id) ON DELETE SET NULL,
  name               text NOT NULL CHECK (char_length(name) BETWEEN 2 AND 80),
  description        text CHECK (char_length(description) <= 200),
  lang               text NOT NULL,
  status             text NOT NULL DEFAULT 'pending'
                       CHECK (status IN ('pending', 'approved', 'rejected', 'merged')),
  auto_checks        jsonb NOT NULL DEFAULT '{}'::jsonb,   -- blocklist, classifier, wikidata match, minor check
  matched_entity_id  bigint REFERENCES entities (id),
  created_entity_id  bigint REFERENCES entities (id),
  reject_reason      text,
  reviewed_by        text,
  reviewed_at        timestamptz,
  created_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX submissions_status_idx ON submissions (status, created_at);

CREATE TABLE takedown_requests (
  id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  kind            text NOT NULL CHECK (kind IN ('image', 'likeness', 'data', 'other')),
  entity_id       bigint REFERENCES entities (id),
  url             text,
  requester_name  text NOT NULL,
  requester_email text NOT NULL,
  details         text NOT NULL,
  status          text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'actioned', 'declined')),
  resolution      text,
  created_at      timestamptz NOT NULL DEFAULT now(),
  resolved_at     timestamptz
);

-- Immediate hides, checked by the game service between snapshots.
CREATE TABLE denylist (
  entity_id   bigint PRIMARY KEY,
  reason      text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE moderators (
  id          integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  email       text NOT NULL UNIQUE,
  token_hash  bytea NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  disabled    boolean NOT NULL DEFAULT false
);

CREATE TABLE moderation_log (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  moderator   text NOT NULL,
  action      text NOT NULL,
  target      text NOT NULL,
  details     jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- operations

CREATE TABLE snapshots (
  version      integer PRIMARY KEY,
  created_at   timestamptz NOT NULL DEFAULT now(),
  storage_key  text NOT NULL,
  sha256       text NOT NULL,
  n_entities   integer NOT NULL,
  n_questions  integer NOT NULL,
  notes        text
);

CREATE TABLE pipeline_runs (
  id           integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  stage        text NOT NULL,
  dump_date    date,
  started_at   timestamptz NOT NULL DEFAULT now(),
  finished_at  timestamptz,
  stats        jsonb NOT NULL DEFAULT '{}'::jsonb
);

COMMIT;
