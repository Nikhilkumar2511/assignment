"""Database models. Postgres in production, SQLite for local runs and tests.

Set DATABASE_URL, for example:
    postgresql://user:pass@host:5432/mindreader
    sqlite:///./mindreader.db   (the default)
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, event)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def _now() -> datetime:
    return datetime.now(timezone.utc)


def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "sqlite:///./mindreader.db")
    # Hosts such as Render and Heroku hand out postgres:// URLs; SQLAlchemy needs the driver name.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


class Base(DeclarativeBase):
    pass


class Entity(Base):
    __tablename__ = "entities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    name_key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    description: Mapped[str] = mapped_column(String(200), default="")
    kind: Mapped[str] = mapped_column(String(16), default="fictional")   # real | fictional | unknown
    popularity: Mapped[float] = mapped_column(Float, default=30.0)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)  # active | pending | hidden
    times_played: Mapped[int] = mapped_column(Integer, default=0)
    times_guessed: Mapped[int] = mapped_column(Integer, default=0)
    taught_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Question(Base):
    __tablename__ = "questions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(60), unique=True)
    text: Mapped[str] = mapped_column(String(200))
    scope: Mapped[str] = mapped_column(String(16), default="all")
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | hidden
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Fact(Base):
    """Evidence for one (character, question) pair, as weighted yes and no counts."""
    __tablename__ = "facts"
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True)
    yes_w: Mapped[float] = mapped_column(Float, default=0.0)
    no_w: Mapped[float] = mapped_column(Float, default=0.0)


class Game(Base):
    __tablename__ = "games"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    state: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="asking", index=True)
    entity_id: Mapped[int | None] = mapped_column(ForeignKey("entities.id", ondelete="SET NULL"), nullable=True)
    taught: Mapped[bool] = mapped_column(Boolean, default=False)
    learned: Mapped[bool] = mapped_column(Boolean, default=False)
    flagged: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Meta(Base):
    """Key/value store. 'kb_version' changes whenever the knowledge base changes,
    so every app process knows when to reload it."""
    __tablename__ = "meta"
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[int] = mapped_column(Integer, default=0)


def make_engine(url: str | None = None):
    url = url or database_url()
    kwargs = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    eng = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        @event.listens_for(eng, "connect")
        def _sqlite_pragmas(conn, _record):  # pragma: no cover - trivial
            cur = conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()
    return eng


def make_sessionmaker(eng):
    return sessionmaker(bind=eng, expire_on_commit=False)
