"""End to end: fixture dump -> pass 1 -> select -> pass 2 -> pageviews -> build -> Postgres."""
from __future__ import annotations

import dataclasses

import duckdb
import psycopg
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from fixture_dump import write_dump, write_pageviews
from mrpipe import build, classes, config as C, load, pageviews, pass1, pass2, select
from mrpipe.wikidata import has_empty_sitelinks, peek_id


@pytest.fixture()
def small_targets(monkeypatch):
    monkeypatch.setattr(C, "TARGET_REAL", 10)
    monkeypatch.setattr(C, "TARGET_FICTIONAL", 7)
    monkeypatch.setattr(C, "SUPPORT_SCALE", 0.0)


def run_all(tmp_path, dump_name="dump.json.bz2", pv_name="pageviews-202501-user.bz2"):
    dump = str(tmp_path / dump_name)
    write_dump(dump)
    pv_dir = tmp_path / "pv"
    pv_dir.mkdir(exist_ok=True)
    write_pageviews(str(pv_dir / pv_name))
    paths = C.Paths(str(tmp_path / "work")).ensure()
    reports = {
        "pass1": pass1.run(dump, paths, workers=2),
        "select": select.run(paths),
        "pass2": pass2.run(dump, paths, workers=2),
        "pageviews": pageviews.run(paths, str(pv_dir)),
        "build": build.run(paths),
    }
    return paths, reports


def attrs_of(dsn: str, qid: int) -> set[str]:
    with psycopg.connect(dsn) as c:
        rows = c.execute("""
            SELECT g.key || '=' || coalesce(vl.label, av.value_key) FROM entity_attrs a
            JOIN attr_values av ON av.id = a.value_id JOIN attr_groups g ON g.id = av.group_id
            LEFT JOIN attr_value_labels vl ON vl.value_id = av.id AND vl.lang = 'en'
            WHERE a.entity_id = %s""", (qid,)).fetchall()
    return {r[0] for r in rows}


# ------------------------------------------------------------------ unit level

def test_peek_id_and_prefilter():
    assert peek_id(b'{"type":"item","id":"Q42","labels":{}}') == ("Q", 42)
    assert peek_id(b'{"type":"property","id":"P31"}') == ("P", 31)
    assert has_empty_sitelinks(b'{"id":"Q1","sitelinks":{}}')


def test_threshold_tuning():
    sitelinks = pa.array([100, 50, 20, 20, 10, 9, 5, 5, 5, 3]).to_numpy()
    assert select.tune_threshold(sitelinks, 4) == 20     # 4 people have >= 20
    assert select.tune_threshold(sitelinks, 6) == 9


def test_render_articles():
    assert build.render("Is your character a {label}?", "occupation", "actor") == "Is your character an actor?"
    assert build.render("Is your character a {label}?", "occupation", "university teacher") == \
        "Is your character a university teacher?"
    assert build.render("Is your character from {label}?", "country", "United States") == \
        "Is your character from the United States?"
    assert build.render("Is your character from {label}?", "country", "India") == "Is your character from India?"


def test_class_graph_stops_at_generic_classes():
    import numpy as np
    g = classes.ClassGraph(np.array([3, 2, 1]), np.array([2, 1, 0]), {0: "top", 1: "occupation", 2: "athlete", 3: "cricketer"})
    assert [a for a, _ in g.ancestors(3, 5)] == [2, 1, 0]
    assert [a for a, _ in g.ancestors(3, 5, stop={1})] == [2]
    assert g.descendants([1]) == {1, 2, 3}


# ------------------------------------------------------------------ extraction and build

def test_selection_and_attributes(tmp_path, small_targets):
    paths, rep = run_all(tmp_path)
    sel = rep["select"]
    assert sel["humans_selected"] == 10 and sel["human_sitelink_threshold_N"] == 9
    assert sel["fictional_selected"] == 7
    assert "Q1000016" in sel["fictional_root_classes_by_label"]            # "mythological hero"
    assert rep["pass1"]["entities_read"] == 87
    b = rep["build"]
    assert b["entities"] == 17 and b["minors"] == 1 and b["religious"] == 1
    ents = {r["qid"]: r for r in pq.read_table(paths.p("build", "entities.parquet")).to_pylist()}
    assert 1000120 not in ents and 1000121 not in ents and 1000107 not in ents
    # pageviews push Virat Kohli above an equally linked person without views
    assert ents[1000094]["pageviews_12m"] == 1_050_000
    assert ents[1000094]["popularity"] > ents[1000098]["popularity"]
    qs = {r["key"]: r for r in pq.read_table(paths.p("build", "questions.parquet")).to_pylist()}
    assert qs["eq:country:Q145"]["text_en"] == "Is your character from the United Kingdom?"
    assert qs["eq:occupation:Q33999"]["text_en"] == "Is your character an actor?"
    assert qs["in:region:asia"]["support"] == 6
    assert "trait:wears_glasses" in qs
    assert not any(k.startswith("eq:occupation:Q1000002") for k in qs)   # no climbing past "occupation"


def test_gzip_dump_and_parquet_pageviews(tmp_path, small_targets):
    dump = str(tmp_path / "d.json.gz")
    write_dump(dump)
    paths = C.Paths(str(tmp_path / "work")).ensure()
    pass1.run(dump, paths, workers=1)
    select.run(paths)
    pass2.run(dump, paths, workers=1)
    pv = tmp_path / "pvp"
    pv.mkdir()
    pq.write_table(pa.table({"wiki_code": ["en.wikipedia", "en.m.wikipedia", "en.wikipedia"],
                             "page_title": ["Virat_Kohli", "Virat_Kohli", "Nobody"],
                             "views": [10, 5, 99]}), str(pv / "2025-01.parquet"))
    out = pageviews.run(paths, str(pv))
    assert out["characters_with_views"] == 1
    views = dict(duckdb.sql(f"SELECT qid, views FROM read_parquet('{paths.p('build', 'pageviews.parquet')}')").fetchall())
    assert views == {1000094: 15}


def test_worker_error_is_raised(tmp_path):
    from mrpipe.dump import run_parallel

    def boom(line, writer, args):
        raise ValueError("bad line")
    dump = str(tmp_path / "d.json")
    write_dump(dump)
    with pytest.raises(RuntimeError, match="bad line"):
        run_parallel(dump, str(tmp_path / "out"), {}, boom, (), workers=2)


# ------------------------------------------------------------------ Postgres load

def test_load_into_postgres(tmp_path, small_targets, fresh_db):
    paths, _ = run_all(tmp_path)
    first = load.run(paths, fresh_db, "2026-11-01")
    assert first["entities"] == 17
    with psycopg.connect(fresh_db) as c:
        ids_before = dict(c.execute("SELECT key, id FROM questions").fetchall())
    again = load.run(paths, fresh_db, "2026-11-01")
    with psycopg.connect(fresh_db) as c:
        ids_after = dict(c.execute("SELECT key, id FROM questions").fetchall())
        assert ids_before == ids_after                                  # question ids are stable
        assert again["entity_attrs"] == first["entity_attrs"]
        # search: accents, aliases and other scripts
        hits = c.execute("SELECT DISTINCT entity_id FROM entity_names WHERE name_norm LIKE mr_normalize(%s) || '%%'",
                         ("NARUTO",)).fetchall()
        assert hits == [(1000100,)]
        hits = c.execute("SELECT entity_id FROM entity_names WHERE name_norm %% mr_normalize(%s) ORDER BY "
                         "similarity(name_norm, mr_normalize(%s)) DESC LIMIT 1", ("Virat Koli", "Virat Koli")).fetchall()
        assert hits == [(1000094,)]
        assert c.execute("SELECT label FROM entity_labels WHERE entity_id = 1000100 AND lang = 'ja'").fetchone()[0] == \
            "うずまきナルト"
        groups = dict(c.execute("SELECT key, p_other FROM attr_groups").fetchall())
        assert groups["gender"] < groups["occupation"]
    gandhi = attrs_of(fresh_db, 1000095)
    assert {"country=India", "region=south_asia", "vital=dead", "occupation=politician"} <= gandhi
    kohli = attrs_of(fresh_db, 1000094)
    assert {"sport=cricket", "occupation=cricketer", "occupation=athlete", "team=India national cricket team",
            "language=Hindi"} <= kohli
    holland = attrs_of(fresh_db, 1000093)
    assert {"played_character=Spider-Man", "played_in_franchise=Spider-Man"} <= holland
    naruto = attrs_of(fresh_db, 1000100)
    assert {"medium=anime", "medium=tv", "char_type=human", "creator=Masashi Kishimoto", "region=east_asia",
            "franchise=Naruto"} <= naruto
    hanuman = attrs_of(fresh_db, 1000105)
    assert {"char_type=deity", "medium=mythology"} <= hanuman
    einstein = attrs_of(fresh_db, 1000096)
    assert {"award=Nobel Prize in Physics", "award=Nobel Prize", "region=europe", "region=north_america"} <= einstein
    assert "award=award" not in einstein


def test_reload_hides_dropped_characters(tmp_path, small_targets, fresh_db, monkeypatch):
    paths, _ = run_all(tmp_path)
    load.run(paths, fresh_db)
    monkeypatch.setattr(C, "TARGET_REAL", 5)
    select.run(paths)
    build.run(paths)
    out = load.run(paths, fresh_db)
    assert out["entities_hidden_not_selected"] >= 4
    with psycopg.connect(fresh_db) as c:
        hidden = c.execute("SELECT count(*) FROM entities WHERE status = 'hidden' AND hidden_reason = "
                           "'not in latest selection'").fetchone()[0]
        assert hidden == out["entities_hidden_not_selected"]
    monkeypatch.setattr(C, "TARGET_REAL", 10)
    select.run(paths)
    build.run(paths)
    load.run(paths, fresh_db)
    with psycopg.connect(fresh_db) as c:
        assert c.execute("SELECT count(*) FROM entities WHERE status = 'hidden'").fetchone()[0] == 0


def test_groups_are_consistent():
    keys = [g.key for g in C.GROUPS]
    assert len(keys) == len(set(keys)) and len({g.id for g in C.GROUPS}) == len(keys)
    for g in C.GROUPS:
        assert 0 < g.p_other < 0.5 < g.p_match < 1, g.key
        assert g.template or g.key in C.FIXED_QUESTIONS or g.key == "birth_year", g.key
    assert dataclasses.is_dataclass(C.GROUPS[0])
