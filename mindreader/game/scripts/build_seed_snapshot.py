"""Build the small seed snapshot (247 hand-tagged characters, 108 questions) from the
prototype's data files. The web app ships it for offline play; the game service can use it
when no full Wikidata snapshot is configured.

    python game/scripts/build_seed_snapshot.py game/data/seed
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "prototype"))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

from app.seed_data import DATA_DIR, load_entities, load_questions, prior_weight  # noqa: E402
from mrpipe import snapshot  # noqa: E402

# First matching tag gives the card theme (colours are chosen by the web app).
THEMES = ["marvel", "dc", "star_wars", "harry_potter", "pokemon", "nintendo", "disney", "lotr", "from_anime",
          "bollywood", "cricket", "football", "basketball", "tennis", "fighter", "racing", "athlete",
          "musician", "actor", "politician", "royalty", "scientist", "business", "writer", "artist",
          "youtuber", "from_game", "from_tv", "from_film", "from_book", "from_comic", "cartoon"]


# Topics: the engine avoids asking many questions on one topic in a row.
TOPICS = {
    "country": "american british indian japanese european latin_american african asian_other punjabi",
    "medium": "from_book from_film from_tv from_game from_anime from_comic cartoon kids_show",
    "franchise": "disney marvel dc star_wars harry_potter lotr nintendo pokemon",
    "sport": "athlete football basketball cricket tennis fighter racing olympic captain bowler",
    "film": "south_cinema film_family action_star romance_star khan beauty_queen hollywood_too",
    "job": "actor bollywood musician rapper band dancer comedian politician head_of_state royalty military activist "
           "scientist inventor business tech billionaire youtuber tv_host writer artist composer director",
    "looks": "mask cape hat glasses beard bald blonde red_hair wears_red green yellow blue small giant",
    "animal": "animal dog cat mouse bird bear sea",
    "powers": "superhero villain superpowers magic flies strong speed",
    "era": "alive born_after_1990 historical elderly child freedom_struggle",
}
TOPIC_OF = {k: t for t, keys in TOPICS.items() for k in keys.split()}
# Near-duplicates: at most one question of each cluster is asked in a game.
DUPLICATES = [("male", "female"), ("superhero", "superpowers")]
DUP_OF = {k: i + 1 for i, pair in enumerate(DUPLICATES) for k in pair}


def main(out_dir: str) -> None:
    questions = load_questions()
    entities = load_entities(questions)
    tags_by_name = {}
    for raw in (DATA_DIR / "characters.txt").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            name, _, _, tags = [p.strip() for p in line.split("|")]
            tags_by_name[name] = set(tags.split())

    prior = np.array([math.log(prior_weight(e.popularity)) for e in entities], dtype=np.float32)
    kind = np.array([1 if e.kind == "real" else 2 for e in entities], dtype=np.uint8)
    qs = [{"id": i + 1, "key": f"seed:{q.key}", "kind": "cells", "group": None, "values": None,
           "scope": q.scope, "dup": DUP_OF.get(q.key), "topic": TOPIC_OF.get(q.key), "text": {"en": q.text}} for i, q in enumerate(questions)]
    all_idx = np.arange(len(entities), dtype=np.int64)
    cells = [(all_idx, np.array([e.yes[q.key] for e in entities])) for q in questions]
    display = []
    for i, e in enumerate(entities):
        tags = tags_by_name.get(e.name, set())
        theme = next((t for t in THEMES if t in tags), e.kind)
        display.append({"id": i + 1, "k": e.kind, "n": {"en": e.name}, "d": {"en": e.description}, "t": theme})
    stats = snapshot.write(out_dir, version=1, source="seed", groups=[], questions=qs, prior=prior, kind=kind,
                           group_csr={}, cells=cells, display=display)
    print(stats)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "data", "seed"))
