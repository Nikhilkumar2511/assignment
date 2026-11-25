"""Turn finished games into knowledge.

- Won game: the guessed character's facts move toward this player's answers.
- Lost game: the player names their character. An existing one learns from the answers;
  a new name becomes a 'pending' character that goes live after enough different
  players teach it (or an admin approves it).
- Answers that contradict the knowledge base on most of its confident facts are
  treated as trolling or a mix-up and are not learned from.
"""
from __future__ import annotations

import os
import re

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from .db import Entity, Fact, Game
from .engine import ANSWER_VALUES, KnowledgeBase
from .kb import bump_version
from .seed_data import name_key

AUTO_APPROVE_AFTER = int(os.environ.get("AUTO_APPROVE_AFTER", "3"))
LEARN_WEIGHT = 1.0
TROLL_MIN_CONFIDENT = 6
TROLL_MAX_DISAGREE = 0.5

# Kept short on purpose. Extend it, or swap in a proper moderation service.
_BLOCKED = re.compile(r"(https?://|www\.|\.com\b|fuck|shit|bitch|cunt|nigg|fagg|porn|rape|nazi)", re.I)
_ALLOWED = re.compile(r"^[\w .,'&()\-!?:]+$", re.UNICODE)


class TeachError(ValueError):
    pass


def validate_name(name: str) -> str:
    name = re.sub(r"\s+", " ", name or "").strip()
    if not 2 <= len(name) <= 60:
        raise TeachError("Name must be 2 to 60 characters.")
    if not re.search(r"[^\W\d_]", name, re.UNICODE):
        raise TeachError("Name must contain letters.")
    if not _ALLOWED.match(name) or _BLOCKED.search(name):
        raise TeachError("That name is not allowed.")
    return name


def validate_description(desc: str | None) -> str:
    desc = re.sub(r"\s+", " ", desc or "").strip()[:140]
    if desc and _BLOCKED.search(desc):
        raise TeachError("That description is not allowed.")
    return desc


def looks_like_trolling(kb: KnowledgeBase, entity_id: int, answers: list) -> str | None:
    row = kb.eidx.get(entity_id)
    if row is None:
        return None
    confident = disagree = 0
    for qid, ans in answers:
        v, col = ANSWER_VALUES.get(ans), kb.qidx.get(qid)
        if v is None or col is None:
            continue
        p = kb.P[row, col]
        if p >= 0.85 or p <= 0.15:
            confident += 1
            disagree += abs(v - p) > 0.6
    if confident >= TROLL_MIN_CONFIDENT and disagree / confident > TROLL_MAX_DISAGREE:
        return f"answers contradicted {disagree} of {confident} confident facts"
    return None


def _add_evidence(s: Session, entity_id: int, answers: list) -> None:
    existing = set(s.scalars(select(Fact.question_id).where(Fact.entity_id == entity_id)))
    new_rows = []
    for qid, ans in answers:
        v = ANSWER_VALUES.get(ans)
        if v is None:
            continue
        dy, dn = v * LEARN_WEIGHT, (1 - v) * LEARN_WEIGHT
        if qid in existing:
            s.execute(update(Fact).where(Fact.entity_id == entity_id, Fact.question_id == qid)
                      .values(yes_w=Fact.yes_w + dy, no_w=Fact.no_w + dn))
        else:
            # Start unknown facts at 50/50 with the weight of one answer.
            new_rows.append({"entity_id": entity_id, "question_id": qid, "yes_w": 0.5 + dy, "no_w": 0.5 + dn})
            existing.add(qid)
    if new_rows:
        s.execute(insert(Fact), new_rows)


def learn_from_win(s: Session, kb: KnowledgeBase, game: Game) -> None:
    eid = game.state["pending_guess"]
    game.entity_id = eid
    s.execute(update(Entity).where(Entity.id == eid)
              .values(times_played=Entity.times_played + 1, times_guessed=Entity.times_guessed + 1))
    flag = looks_like_trolling(kb, eid, game.state["answers"])
    if flag:
        game.flagged = flag
    else:
        _add_evidence(s, eid, game.state["answers"])
        game.learned = True
    bump_version(s)


def teach(s: Session, kb: KnowledgeBase, game: Game, entity_id: int | None,
          name: str | None, description: str | None) -> tuple[Entity, bool]:
    """Player tells us who they were thinking of after a loss. Returns (entity, created)."""
    if game.status != "lost":
        raise TeachError("You can only teach the game after it loses.")
    if game.taught:
        raise TeachError("This game has already been taught.")

    created = False
    if entity_id is not None:
        ent = s.get(Entity, entity_id)
        if ent is None or ent.status == "hidden":
            raise TeachError("Unknown character.")
    else:
        clean = validate_name(name or "")
        ent = s.scalar(select(Entity).where(Entity.name_key == name_key(clean)))
        if ent is None:
            ent = Entity(name=clean, name_key=name_key(clean), description=validate_description(description),
                         kind="unknown", popularity=20.0, status="pending", taught_count=0)
            s.add(ent)
            s.flush()
            created = True
        elif ent.status == "hidden":
            raise TeachError("That name is not allowed.")

    flag = looks_like_trolling(kb, ent.id, game.state["answers"]) if ent.status == "active" else None
    if flag:
        game.flagged = flag
    else:
        _add_evidence(s, ent.id, game.state["answers"])
        game.learned = True
    ent.times_played += 1
    if ent.status == "pending":
        ent.taught_count += 1
        if ent.taught_count >= AUTO_APPROVE_AFTER:
            ent.status = "active"
    game.entity_id = ent.id
    game.taught = True
    bump_version(s)
    return ent, created
