"""Loads the knowledge base from the database into NumPy and keeps it fresh.

Every app process holds its own copy. When any process changes the knowledge base
(a finished game, a new character), it bumps meta.kb_version; the others notice
within CHECK_EVERY seconds and reload.
"""
from __future__ import annotations

import threading
import time

import numpy as np
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .db import Entity, Fact, Meta, Question
from .engine import KnowledgeBase
from .seed_data import prior_weight

CHECK_EVERY = 5.0  # seconds


def read_version(s: Session) -> int:
    row = s.get(Meta, "kb_version")
    return row.value if row else 0


def bump_version(s: Session) -> None:
    if s.get(Meta, "kb_version") is None:
        s.add(Meta(key="kb_version", value=1))
    else:
        s.execute(update(Meta).where(Meta.key == "kb_version").values(value=Meta.value + 1))


def load_kb(s: Session) -> KnowledgeBase:
    version = read_version(s)
    ents = s.execute(select(Entity.id, Entity.name, Entity.description, Entity.popularity, Entity.times_played)
                     .where(Entity.status == "active").order_by(Entity.id)).all()
    qs = s.execute(select(Question.id, Question.text).where(Question.status == "active").order_by(Question.id)).all()
    eidx = {e.id: i for i, e in enumerate(ents)}
    qidx = {q.id: j for j, q in enumerate(qs)}
    P = np.full((len(ents), len(qs)), 0.5)
    for eid, qid, yes_w, no_w in s.execute(select(Fact.entity_id, Fact.question_id, Fact.yes_w, Fact.no_w)):
        i, j = eidx.get(eid), qidx.get(qid)
        if i is None or j is None:
            continue
        total = yes_w + no_w
        # One extra virtual answer each way keeps sparse evidence from hitting 0 or 1.
        P[i, j] = (yes_w + 0.5) / (total + 1.0)
    prior = np.log([prior_weight(e.popularity, e.times_played) for e in ents]) if ents else np.array([])
    return KnowledgeBase(
        entity_ids=[e.id for e in ents], entity_names=[e.name for e in ents],
        entity_descriptions=[e.description for e in ents],
        question_ids=[q.id for q in qs], question_texts=[q.text for q in qs],
        P=P, log_prior=prior, version=version,
    )


class KBStore:
    def __init__(self, session_factory):
        self._sf = session_factory
        self._kb: KnowledgeBase | None = None
        self._checked = 0.0
        self._lock = threading.Lock()

    def get(self) -> KnowledgeBase:
        now = time.monotonic()
        if self._kb is not None and now - self._checked < CHECK_EVERY:
            return self._kb
        with self._lock:
            if self._kb is not None and time.monotonic() - self._checked < CHECK_EVERY:
                return self._kb
            with self._sf() as s:
                if self._kb is None or read_version(s) != self._kb.version:
                    self._kb = load_kb(s)
            self._checked = time.monotonic()
            return self._kb

    def invalidate(self) -> None:
        """Force a version check on the next get(), e.g. right after this process changed the KB."""
        self._checked = 0.0
