"""Parse data/questions.json and data/characters.txt into yes-probabilities.

Used by the database seeder, the tests and the offline simulator, so all three see
exactly the same starting knowledge.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

P_YES = 0.95
P_UNSURE = 0.5
P_NO_EXPLICIT = 0.03
P_DEFAULT = 0.08
P_OUT_OF_SCOPE = 0.5

# How many "virtual player answers" the seed is worth. Real answers then shift the
# probabilities: after about this many games, players count as much as the seed.
SEED_WEIGHT_TAGGED = 6.0
SEED_WEIGHT_DEFAULT = 3.0

# Tags that imply other tags. Applied repeatedly until nothing changes.
IMPLIES: dict[str, list[str]] = {
    "real": ["human"],
    "harry_potter": ["from_book", "from_film", "british", "magic"],
    "marvel": ["from_comic", "from_film", "american"],
    "dc": ["from_comic", "from_film", "american"],
    "star_wars": ["from_film", "space"],
    "pokemon": ["from_game", "from_anime", "nintendo"],
    "nintendo": ["from_game", "japanese"],
    "from_anime": ["cartoon", "japanese"],
    "lotr": ["from_book", "from_film"],
    "disney": ["from_film", "american"],
    "rapper": ["musician"],
    "composer": ["musician"],
    "head_of_state": ["politician"],
    "football": ["athlete"],
    "basketball": ["athlete"],
    "cricket": ["athlete"],
    "tennis": ["athlete"],
    "racing": ["athlete"],
    "dog": ["animal"],
    "cat": ["animal"],
    "mouse": ["animal"],
    "bird": ["animal"],
    "bear": ["animal"],
    "superhero": ["superpowers"],
}
# A few implications are too strong for some characters; listed tags block them.
IMPLY_EXCEPT = {("superhero", "superpowers"): {"~superpowers", "!superpowers"}}


@dataclass
class SeedQuestion:
    key: str
    text: str
    scope: str
    default: float


@dataclass
class SeedEntity:
    name: str
    popularity: float
    description: str
    kind: str                 # "real" or "fictional"
    yes: dict[str, float]     # question key -> yes-probability
    weight: dict[str, float]  # question key -> seed weight


def load_questions(path: Path | None = None) -> list[SeedQuestion]:
    raw = json.loads((path or DATA_DIR / "questions.json").read_text(encoding="utf-8"))
    out = []
    for q in raw["questions"]:
        out.append(SeedQuestion(q["key"], q["text"], q.get("scope", "all"), float(q.get("default", P_DEFAULT))))
    keys = [q.key for q in out]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate question keys in questions.json")
    return out


def _expand(tags: set[str]) -> set[str]:
    plain = {t for t in tags if t[0] not in "~!"}
    changed = True
    while changed:
        changed = False
        for tag in list(plain):
            for implied in IMPLIES.get(tag, []):
                blockers = IMPLY_EXCEPT.get((tag, implied), set())
                if implied in plain or f"~{implied}" in tags or f"!{implied}" in tags or blockers & tags:
                    continue
                plain.add(implied)
                changed = True
    return plain | {t for t in tags if t[0] in "~!"}


def parse_entity_line(line: str, questions: list[SeedQuestion]) -> SeedEntity:
    parts = [p.strip() for p in line.split("|")]
    if len(parts) != 4:
        raise ValueError(f"Expected 4 fields separated by '|': {line!r}")
    name, pop, desc, tag_text = parts
    tags = _expand(set(tag_text.split()))
    known = {q.key for q in questions} | {"dead"}
    unknown = {t.lstrip("~!") for t in tags} - known
    if unknown:
        raise ValueError(f"{name}: unknown tags {sorted(unknown)}")

    kind = "real" if "real" in tags else "fictional"
    if kind == "real" and not ({"dead", "historical"} & tags):
        tags.add("alive")

    yes, weight = {}, {}
    for q in questions:
        out_of_scope = (q.scope == "real" and kind != "real") or (q.scope == "fictional" and kind == "real")
        if out_of_scope:
            yes[q.key], weight[q.key] = P_OUT_OF_SCOPE, SEED_WEIGHT_DEFAULT
        elif q.key in tags:
            yes[q.key], weight[q.key] = P_YES, SEED_WEIGHT_TAGGED
        elif f"~{q.key}" in tags:
            yes[q.key], weight[q.key] = P_UNSURE, SEED_WEIGHT_DEFAULT
        elif f"!{q.key}" in tags:
            yes[q.key], weight[q.key] = P_NO_EXPLICIT, SEED_WEIGHT_TAGGED
        else:
            yes[q.key], weight[q.key] = q.default, SEED_WEIGHT_DEFAULT
    return SeedEntity(name, float(pop), desc, kind, yes, weight)


def load_entities(questions: list[SeedQuestion], path: Path | None = None) -> list[SeedEntity]:
    out, seen = [], set()
    for raw in (path or DATA_DIR / "characters.txt").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        ent = parse_entity_line(line, questions)
        key = name_key(ent.name)
        if key in seen:
            raise ValueError(f"Duplicate character: {ent.name}")
        seen.add(key)
        out.append(ent)
    return out


def name_key(name: str) -> str:
    """Normalised name used for duplicate checks: 'Spider-Man' and 'spider man' match."""
    import re
    return re.sub(r"[^0-9a-z]+", " ", name.lower()).strip()


def prior_weight(popularity: float, times_played: int = 0) -> float:
    """Unnormalised prior: popular and often-played characters are guessed more readily."""
    return 1.0 + popularity / 25.0 + math.log1p(max(times_played, 0))


def build_kb_from_files():
    """KnowledgeBase straight from the data files, no database. For tests and simulation."""
    from .engine import KnowledgeBase
    questions = load_questions()
    entities = load_entities(questions)
    P = np.array([[e.yes[q.key] for q in questions] for e in entities])
    prior = np.log([prior_weight(e.popularity) for e in entities])
    return KnowledgeBase(
        entity_ids=list(range(1, len(entities) + 1)),
        entity_names=[e.name for e in entities],
        entity_descriptions=[e.description for e in entities],
        question_ids=list(range(1, len(questions) + 1)),
        question_texts=[q.text for q in questions],
        P=P, log_prior=prior,
    )
