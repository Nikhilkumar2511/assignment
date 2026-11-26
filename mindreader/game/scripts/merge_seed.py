"""Add the hand-curated seed characters that Wikidata lacks (Chhota Bheem, Shaktimaan, Pushpa Raj...)
to a pipeline database, mapping their tags onto the Wikidata attribute groups.

Characters already in the database (same English name and kind) are left alone: their
Wikidata facts are richer. New ones get negative ids and source 'admin'.

    python game/scripts/merge_seed.py postgresql://user:pass@host/db
"""
from __future__ import annotations

import os
import sys

import psycopg

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "prototype"))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

from app.seed_data import DATA_DIR, load_entities, load_questions, name_key  # noqa: E402

# seed tag -> (group key, value key). Q-ids are the Wikidata items the pipeline uses.
TAG_VALUES: dict[str, list[tuple[str, str]]] = {
    "male": [("gender", "male")], "female": [("gender", "female")],
    "indian": [("region", "south_asia"), ("country", "Q668")],
    "american": [("region", "north_america"), ("country", "Q30")],
    "british": [("region", "europe"), ("country", "Q145")],
    "japanese": [("region", "east_asia"), ("country", "Q17")],
    "european": [("region", "europe")], "latin_american": [("region", "latin_america")],
    "african": [("region", "africa")], "asian_other": [("region", "asia")],
    "from_anime": [("medium", "anime")], "cartoon": [("medium", "animated")], "from_tv": [("medium", "tv")],
    "from_film": [("medium", "film")], "from_book": [("medium", "book")], "from_comic": [("medium", "comics")],
    "from_game": [("medium", "video_game")],
    "human": [("char_type", "human")], "animal": [("char_type", "animal")], "robot": [("char_type", "robot")],
    "superhero": [("char_type", "superhero")], "villain": [("char_type", "villain")], "alien": [("char_type", "alien")],
    "dog": [("char_type", "dog")], "cat": [("char_type", "cat")], "monster": [("char_type", "monster")],
    "magic": [("char_type", "magic_user")],
}
# seed tag -> English occupation label as it appears in the database
OCCUPATIONS = {
    "actor": "actor", "musician": "singer", "rapper": "rapper", "cricket": "cricketer", "football": "association football player",
    "politician": "politician", "scientist": "scientist", "writer": "writer", "youtuber": "YouTuber", "comedian": "comedian",
    "business": "businessperson", "director": "film director", "dancer": "dancer", "athlete": "athlete",
}


def main(dsn: str) -> None:
    questions = load_questions()
    entities = load_entities(questions)
    tags_by_name = {}
    for raw in (DATA_DIR / "characters.txt").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            name, _, _, tags = [p.strip() for p in line.split("|")]
            tags_by_name[name] = set(tags.split())

    added, skipped = [], 0
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        groups = dict(cur.execute("SELECT key, id FROM attr_groups").fetchall())
        occ_ids = {}
        for tag, label in OCCUPATIONS.items():
            row = cur.execute("""
                SELECT av.value_key FROM attr_values av JOIN attr_value_labels l ON l.value_id = av.id AND l.lang = 'en'
                WHERE av.group_id = %s AND lower(l.label) = lower(%s) ORDER BY av.support DESC LIMIT 1""",
                (groups["occupation"], label)).fetchone()
            if row:
                occ_ids[tag] = row[0]

        for e in entities:
            tags = tags_by_name.get(e.name, set())
            hit = cur.execute("""
                SELECT 1 FROM entity_names n JOIN entities x ON x.id = n.entity_id
                WHERE n.lang = 'en' AND n.name_norm = mr_normalize(%s) AND x.kind = %s LIMIT 1""",
                (e.name, e.kind)).fetchone()
            if hit:
                skipped += 1
                continue
            existing = cur.execute("SELECT id FROM entities WHERE source = 'admin' AND id IN "
                                   "(SELECT entity_id FROM entity_labels WHERE lang = 'en' AND label = %s)",
                                   (e.name,)).fetchone()
            if existing:
                eid = existing[0]
            else:
                eid = -cur.execute("SELECT nextval('player_entity_id_seq')").fetchone()[0]
            popularity = 3.0 + (e.popularity - 45) / 53 * 2.0       # seed 45..98 -> about 3.0..5.0
            cur.execute("""
                INSERT INTO entities (id, kind, status, source, sitelinks, popularity)
                VALUES (%s, %s, 'active', 'admin', 0, %s)
                ON CONFLICT (id) DO UPDATE SET popularity = EXCLUDED.popularity, status = 'active'""",
                (eid, e.kind, popularity))
            cur.execute("""INSERT INTO entity_labels (entity_id, lang, label, description) VALUES (%s, 'en', %s, %s)
                           ON CONFLICT (entity_id, lang) DO UPDATE SET label = EXCLUDED.label, description = EXCLUDED.description""",
                        (eid, e.name, e.description))
            cur.execute("INSERT INTO entity_names (entity_id, lang, name) VALUES (%s, 'en', %s) ON CONFLICT DO NOTHING",
                        (eid, e.name))
            pairs = [("kind", e.kind)]
            for tag in tags:
                pairs += TAG_VALUES.get(tag, [])
                if tag in occ_ids:
                    pairs.append(("occupation", occ_ids[tag]))
            cur.execute("DELETE FROM entity_attrs WHERE entity_id = %s AND source = 'admin'", (eid,))
            for group_key, value_key in set(pairs):
                cur.execute("""
                    INSERT INTO attr_values (group_id, value_key) VALUES (%s, %s)
                    ON CONFLICT (group_id, value_key) DO NOTHING""", (groups[group_key], value_key))
                cur.execute("""
                    INSERT INTO entity_attrs (entity_id, value_id, source)
                    SELECT %s, id, 'admin' FROM attr_values WHERE group_id = %s AND value_key = %s
                    ON CONFLICT DO NOTHING""", (eid, groups[group_key], value_key))
            added.append(e.name)
    print(f"already in Wikidata: {skipped}; added: {len(added)}")
    print(", ".join(added))


if __name__ == "__main__":
    main(sys.argv[1])
