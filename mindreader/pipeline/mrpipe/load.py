"""Load a build into Postgres. Safe to rerun every month on a fresh dump.

Rules
* Characters are upserted by Wikidata id. Wikidata characters missing from the new
  build are hidden (not deleted), so their learned evidence survives if they return.
* Attribute rows from Wikidata are replaced; rows added by admins stay.
* Questions are upserted by key, so question ids never change. Generated questions
  missing from the new build are hidden. Statuses set by admins are left alone.
* English template text is written only if there is none yet, or if the existing text
  also came from the template (LLM rewrites and human edits are never overwritten).
"""
from __future__ import annotations

import json

import duckdb
import psycopg

from . import config as C


def _copy(cur, table: str, columns: list[str], rows) -> int:
    n = 0
    with cur.copy(f"COPY {table} ({', '.join(columns)}) FROM STDIN") as cp:
        for row in rows:
            cp.write_row(row)
            n += 1
    return n


def _rows(path: str, columns: list[str]):
    cursor = duckdb.connect().execute(f"SELECT {', '.join(columns)} FROM read_parquet('{path}')")
    while True:
        batch = cursor.fetchmany(50000)
        if not batch:
            break
        yield from batch


def run(paths: C.Paths, dsn: str, dump_date: str | None = None) -> dict:
    b = paths.p("build")
    stats: dict = {}
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO pipeline_runs (stage, dump_date) VALUES ('load', %s) RETURNING id", (dump_date,))
        run_id = cur.fetchone()[0]
        cur.execute("SET LOCAL work_mem = '256MB'")

        # ---- attribute groups
        for g in C.GROUPS:
            cur.execute("""
                INSERT INTO attr_groups (id, key, scope, p_match, p_other, min_support, max_questions, description)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET key = EXCLUDED.key, scope = EXCLUDED.scope, p_match = EXCLUDED.p_match,
                  p_other = EXCLUDED.p_other, min_support = EXCLUDED.min_support,
                  max_questions = EXCLUDED.max_questions, description = EXCLUDED.description
            """, (g.id, g.key, g.scope, g.p_match, g.p_other, C.min_support(g), g.max_questions, g.description))

        # ---- entities
        cur.execute("""CREATE TEMP TABLE t_entities (id bigint, kind text, sitelinks int, pageviews_12m bigint,
                       popularity real, birth_year int, is_minor bool, is_religious bool) ON COMMIT DROP""")
        stats["entities"] = _copy(cur, "t_entities", ["id", "kind", "sitelinks", "pageviews_12m", "popularity",
                                                       "birth_year", "is_minor", "is_religious"],
                                  _rows(f"{b}/entities.parquet", ["qid", "kind", "sitelinks", "pageviews_12m",
                                                                   "popularity", "birth_year", "is_minor", "is_religious"]))
        cur.execute("CREATE UNIQUE INDEX ON t_entities (id)")
        cur.execute("ANALYZE t_entities")
        cur.execute("""
            INSERT INTO entities (id, kind, sitelinks, pageviews_12m, popularity, birth_year, is_minor, is_religious)
            SELECT id, kind, sitelinks, pageviews_12m, popularity, birth_year, is_minor, is_religious FROM t_entities
            ON CONFLICT (id) DO UPDATE SET kind = EXCLUDED.kind, sitelinks = EXCLUDED.sitelinks,
              pageviews_12m = EXCLUDED.pageviews_12m, popularity = EXCLUDED.popularity,
              birth_year = EXCLUDED.birth_year, is_minor = EXCLUDED.is_minor, is_religious = EXCLUDED.is_religious,
              status = CASE WHEN entities.hidden_reason = 'not in latest selection' THEN 'active' ELSE entities.status END,
              hidden_reason = CASE WHEN entities.hidden_reason = 'not in latest selection' THEN NULL ELSE entities.hidden_reason END,
              updated_at = now()
        """)
        cur.execute("""
            UPDATE entities SET status = 'hidden', hidden_reason = 'not in latest selection', updated_at = now()
            WHERE source = 'wikidata' AND status = 'active'
              AND NOT EXISTS (SELECT 1 FROM t_entities t WHERE t.id = entities.id)
        """)
        stats["entities_hidden_not_selected"] = cur.rowcount

        # ---- labels, names, sitelinks (replaced for every character in the build)
        cur.execute("DELETE FROM entity_labels WHERE entity_id IN (SELECT id FROM t_entities)")
        cur.execute("CREATE TEMP TABLE t_labels (entity_id bigint, lang text, label text, description text) ON COMMIT DROP")
        _copy(cur, "t_labels", ["entity_id", "lang", "label", "description"],
              _rows(f"{b}/entity_labels.parquet", ["qid", "lang", "label", "description"]))
        cur.execute("""INSERT INTO entity_labels SELECT l.* FROM t_labels l JOIN languages g ON g.code = l.lang
                       JOIN t_entities e ON e.id = l.entity_id ON CONFLICT DO NOTHING""")
        stats["labels"] = cur.rowcount
        cur.execute("DELETE FROM entity_names WHERE entity_id IN (SELECT id FROM t_entities)")
        cur.execute("CREATE TEMP TABLE t_names (entity_id bigint, lang text, name text, is_alias bool) ON COMMIT DROP")
        _copy(cur, "t_names", ["entity_id", "lang", "name", "is_alias"],
              _rows(f"{b}/entity_names.parquet", ["qid", "lang", "name", "is_alias"]))
        cur.execute("""INSERT INTO entity_names (entity_id, lang, name, is_alias)
                       SELECT n.entity_id, n.lang, n.name, bool_and(n.is_alias) FROM t_names n
                       JOIN t_entities e ON e.id = n.entity_id GROUP BY 1, 2, 3
                       ON CONFLICT DO NOTHING""")
        stats["names"] = cur.rowcount
        cur.execute("DELETE FROM entity_sitelinks WHERE entity_id IN (SELECT id FROM t_entities)")
        cur.execute("CREATE TEMP TABLE t_sites (entity_id bigint, wiki text, title text) ON COMMIT DROP")
        _copy(cur, "t_sites", ["entity_id", "wiki", "title"],
              _rows(f"{b}/entity_sitelinks.parquet", ["qid", "wiki", "title"]))
        cur.execute("""INSERT INTO entity_sitelinks SELECT s.* FROM t_sites s JOIN t_entities e ON e.id = s.entity_id
                       ON CONFLICT DO NOTHING""")

        # ---- attribute values and labels
        cur.execute("""CREATE TEMP TABLE t_values (group_key text, value_key text, wikidata_id bigint, support int)
                       ON COMMIT DROP""")
        _copy(cur, "t_values", ["group_key", "value_key", "wikidata_id", "support"],
              _rows(f"{b}/attr_values.parquet", ["group_key", "value_key", "wikidata_id", "support"]))
        cur.execute("UPDATE attr_values SET support = 0")
        cur.execute("""
            INSERT INTO attr_values (group_id, value_key, wikidata_id, support)
            SELECT g.id, v.value_key, v.wikidata_id, v.support FROM t_values v JOIN attr_groups g ON g.key = v.group_key
            ON CONFLICT (group_id, value_key) DO UPDATE SET support = EXCLUDED.support, wikidata_id = EXCLUDED.wikidata_id
        """)
        stats["attr_values"] = cur.rowcount
        cur.execute("""CREATE TEMP TABLE t_vlabels (group_key text, value_key text, lang text, label text) ON COMMIT DROP""")
        _copy(cur, "t_vlabels", ["group_key", "value_key", "lang", "label"],
              _rows(f"{b}/attr_value_labels.parquet", ["group_key", "value_key", "lang", "label"]))
        cur.execute("""
            INSERT INTO attr_value_labels (value_id, lang, label)
            SELECT av.id, l.lang, l.label FROM t_vlabels l
            JOIN attr_groups g ON g.key = l.group_key
            JOIN attr_values av ON av.group_id = g.id AND av.value_key = l.value_key
            JOIN languages lg ON lg.code = l.lang
            ON CONFLICT (value_id, lang) DO UPDATE SET label = EXCLUDED.label
        """)

        # ---- character attributes
        cur.execute("DELETE FROM entity_attrs WHERE source = 'wikidata' AND entity_id IN (SELECT id FROM t_entities)")
        cur.execute("CREATE TEMP TABLE t_attrs (entity_id bigint, group_key text, value_key text) ON COMMIT DROP")
        _copy(cur, "t_attrs", ["entity_id", "group_key", "value_key"],
              _rows(f"{b}/entity_attrs.parquet", ["qid", "group_key", "value_key"]))
        cur.execute("ANALYZE t_attrs")
        cur.execute("""
            INSERT INTO entity_attrs (entity_id, value_id, source)
            SELECT a.entity_id, av.id, 'wikidata' FROM t_attrs a
            JOIN attr_groups g ON g.key = a.group_key
            JOIN attr_values av ON av.group_id = g.id AND av.value_key = a.value_key
            ON CONFLICT DO NOTHING
        """)
        stats["entity_attrs"] = cur.rowcount

        # ---- questions
        cur.execute("""CREATE TEMP TABLE t_questions (key text, kind text, group_key text, value_keys text[],
                       scope text, support int, text_en text) ON COMMIT DROP""")
        _copy(cur, "t_questions", ["key", "kind", "group_key", "value_keys", "scope", "support", "text_en"],
              _rows(f"{b}/questions.parquet", ["key", "kind", "group_key", "value_keys", "scope", "support", "text_en"]))
        cur.execute("""
            WITH resolved AS (
              SELECT q.key, q.kind, g.id AS group_id, q.scope, q.support,
                     (SELECT array_agg(av.id ORDER BY av.id) FROM unnest(q.value_keys) vk
                      JOIN attr_values av ON av.group_id = g.id AND av.value_key = vk) AS value_ids
              FROM t_questions q LEFT JOIN attr_groups g ON g.key = q.group_key
            )
            INSERT INTO questions (key, kind, group_id, value_ids, scope, status, support, source)
            SELECT key, kind, group_id, value_ids, scope, 'active', support,
                   CASE WHEN kind = 'trait' THEN 'trait' ELSE 'generated' END FROM resolved
            ON CONFLICT (key) DO UPDATE SET value_ids = EXCLUDED.value_ids, support = EXCLUDED.support,
              scope = EXCLUDED.scope,
              status = CASE WHEN questions.status = 'hidden' AND questions.source = 'generated'
                            THEN 'active' ELSE questions.status END,
              updated_at = now()
        """)
        stats["questions_upserted"] = cur.rowcount
        cur.execute("""
            UPDATE questions SET status = 'hidden', updated_at = now()
            WHERE source = 'generated' AND status = 'active'
              AND NOT EXISTS (SELECT 1 FROM t_questions t WHERE t.key = questions.key)
        """)
        stats["questions_hidden"] = cur.rowcount
        cur.execute("""
            INSERT INTO question_texts (question_id, lang, text, origin)
            SELECT q.id, 'en', t.text_en, 'template' FROM t_questions t JOIN questions q ON q.key = t.key
            ON CONFLICT (question_id, lang) DO UPDATE SET text = EXCLUDED.text
              WHERE question_texts.origin = 'template'
        """)

        cur.execute("UPDATE pipeline_runs SET finished_at = now(), stats = %s WHERE id = %s",
                    (json.dumps(stats), run_id))
    return stats
