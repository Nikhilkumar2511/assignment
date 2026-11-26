"""Load the data files into the database. Safe to run on every start.

Adds questions and characters that are in the files but not yet in the database.
Never overwrites what players have already taught the game.

    python -m app.seed
"""
from __future__ import annotations

import logging

from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError

from .db import Base, Entity, Fact, Question, make_engine, make_sessionmaker
from .kb import bump_version
from .seed_data import load_entities, load_questions, name_key

log = logging.getLogger("mindreader.seed")


def sync_from_files(session_factory) -> tuple[int, int]:
    """Returns (new_questions, new_characters)."""
    questions = load_questions()
    entities = load_entities(questions)
    try:
        with session_factory() as s:
            existing_q = {k: i for i, k in s.execute(select(Question.id, Question.key))}
            existing_e = {k: i for i, k in s.execute(select(Entity.id, Entity.name_key))}
            seed_by_key = {name_key(e.name): e for e in entities}

            new_q = [q for q in questions if q.key not in existing_q]
            for q in new_q:
                row = Question(key=q.key, text=q.text, scope=q.scope)
                s.add(row)
                s.flush()
                existing_q[q.key] = row.id
                # Give every existing character evidence for the new question.
                facts = []
                for ekey, eid in existing_e.items():
                    seed = seed_by_key.get(ekey)
                    p, w = (seed.yes[q.key], seed.weight[q.key]) if seed else (0.5, 1.0)
                    facts.append({"entity_id": eid, "question_id": row.id, "yes_w": p * w, "no_w": (1 - p) * w})
                if facts:
                    s.execute(insert(Fact), facts)

            new_e = [e for e in entities if name_key(e.name) not in existing_e]
            for e in new_e:
                row = Entity(name=e.name, name_key=name_key(e.name), description=e.description,
                             kind=e.kind, popularity=e.popularity, status="active")
                s.add(row)
                s.flush()
                existing_e[row.name_key] = row.id
                s.execute(insert(Fact), [
                    {"entity_id": row.id, "question_id": existing_q[q.key],
                     "yes_w": e.yes[q.key] * e.weight[q.key], "no_w": (1 - e.yes[q.key]) * e.weight[q.key]}
                    for q in questions
                ])

            if new_q or new_e:
                bump_version(s)
            s.commit()
            return len(new_q), len(new_e)
    except IntegrityError:
        # Another worker seeded at the same moment. Its data is identical, so this is fine.
        log.info("Seed raced with another process; skipping.")
        return 0, 0


def init_db(eng, session_factory) -> None:
    Base.metadata.create_all(eng)
    nq, ne = sync_from_files(session_factory)
    if nq or ne:
        log.info("Seeded %d questions and %d characters.", nq, ne)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    eng = make_engine()
    sf = make_sessionmaker(eng)
    Base.metadata.create_all(eng)
    print("added questions=%d characters=%d" % sync_from_files(sf))
