"""MindReader: think of a character, answer questions, and the game guesses who it is.

Run locally:   uvicorn app.main:app --reload
API docs:      http://localhost:8000/docs
"""
from __future__ import annotations

import hmac
import logging
import os
import secrets
import threading
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from . import engine as eng
from .db import Entity, Fact, Game, Question, make_engine, make_sessionmaker
from .kb import KBStore, bump_version
from .learning import TeachError, learn_from_win, teach
from .seed import init_db
from .seed_data import name_key

log = logging.getLogger("mindreader")
STATIC = Path(__file__).resolve().parent / "static"
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")
TRUST_PROXY = os.environ.get("TRUST_PROXY", "1") == "1"   # most hosts sit behind a proxy
STALE_GAME_HOURS = 48

db_engine = make_engine()
SessionLocal = make_sessionmaker(db_engine)
kb_store = KBStore(SessionLocal)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db(db_engine, SessionLocal)
    kb_store.get()
    yield


app = FastAPI(title="MindReader", version="1.0.0", lifespan=lifespan,
              description="A character guessing game driven by Bayesian information gain.")


# --------------------------------------------------------------------------- helpers

def get_db():
    with SessionLocal() as s:
        yield s


class RateLimiter:
    """Sliding-window limit per client IP. In-memory, so the limit is per app process."""

    def __init__(self, limit: int, window: float):
        self.limit, self.window = limit, window
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                raise HTTPException(429, "Too many requests. Slow down a little.")
            q.append(now)
            if len(self.hits) > 50_000:      # keep memory bounded
                self.hits.clear()


new_game_limit = RateLimiter(int(os.environ.get("RATE_NEW_GAMES_PER_MIN", "30")), 60)
action_limit = RateLimiter(int(os.environ.get("RATE_ACTIONS_PER_MIN", "300")), 60)
teach_limit = RateLimiter(int(os.environ.get("RATE_TEACH_PER_HOUR", "20")), 3600)


def client_ip(request: Request) -> str:
    if TRUST_PROXY:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def require_admin(authorization: str = Header(default="")) -> None:
    token = authorization.removeprefix("Bearer ").strip()
    if not ADMIN_TOKEN or not hmac.compare_digest(token, ADMIN_TOKEN):
        raise HTTPException(401, "Admin token required.")


def load_game(s: Session, game_id: str) -> Game:
    game = s.get(Game, game_id)
    if game is None:
        raise HTTPException(404, "Game not found. Start a new one.")
    return game


def save_state(game: Game, state: dict) -> None:
    game.state = dict(state)          # new object so SQLAlchemy sees the JSON change
    game.status = state["status"]


def entity_card(kb: eng.KnowledgeBase, s: Session, eid: int | None) -> dict | None:
    if eid is None:
        return None
    row = kb.eidx.get(eid)
    if row is not None:
        return {"id": eid, "name": kb.entity_names[row], "description": kb.entity_descriptions[row]}
    ent = s.get(Entity, eid)
    return {"id": eid, "name": ent.name, "description": ent.description} if ent else None


def view(kb: eng.KnowledgeBase, s: Session, game: Game) -> dict:
    st = game.state
    q = None
    if st["status"] == "asking" and st["current_q"] is not None:
        col = kb.qidx.get(st["current_q"])
        text = kb.question_texts[col] if col is not None else (s.get(Question, st["current_q"]).text)
        q = {"id": st["current_q"], "text": text}
    return {
        "game_id": game.id,
        "status": st["status"],
        "step": len(st["answers"]) + (1 if st["status"] == "asking" else 0),
        "question": q,
        "guess": entity_card(kb, s, st["pending_guess"]) if st["status"] == "guessing" else None,
        "answer_entity": entity_card(kb, s, game.entity_id) if st["status"] in ("won", "lost") else None,
        "confidence": round(eng.confidence(kb, st), 3) if st["status"] in ("asking", "guessing") else None,
        "wrong_guesses": len(st["wrong_guesses"]),
        "max_guesses": eng.MAX_GUESSES,
        "can_undo": st["status"] in ("asking", "guessing") and bool(st["answers"]),
        "can_teach": st["status"] == "lost" and not game.taught,
    }


_cleanup_counter = 0


def maybe_cleanup(s: Session) -> None:
    """Every 200 new games, delete unfinished games older than STALE_GAME_HOURS."""
    global _cleanup_counter
    _cleanup_counter += 1
    if _cleanup_counter % 200:
        return
    cutoff = datetime.now(timezone.utc) - timedelta(hours=STALE_GAME_HOURS)
    s.execute(delete(Game).where(Game.status.in_(["asking", "guessing"]), Game.updated_at < cutoff))


# --------------------------------------------------------------------------- request bodies

Answer = Literal["yes", "probably", "dont_know", "probably_not", "no"]


class AnswerIn(BaseModel):
    question_id: int
    answer: Answer


class GuessIn(BaseModel):
    correct: bool


class TeachIn(BaseModel):
    entity_id: Optional[int] = None
    name: Optional[str] = Field(None, max_length=80)
    description: Optional[str] = Field(None, max_length=200)


class QuestionIn(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9_]{2,60}$")
    text: str = Field(min_length=5, max_length=200)
    scope: Literal["all", "real", "fictional"] = "all"


# --------------------------------------------------------------------------- game API

@app.post("/api/games", status_code=201)
def create_game(request: Request, s: Session = Depends(get_db)):
    new_game_limit.check(client_ip(request))
    kb = kb_store.get()
    if kb.n_entities == 0 or kb.n_questions == 0:
        raise HTTPException(503, "The knowledge base is empty.")
    state = eng.advance(kb, eng.new_state(secrets.randbelow(2**31)))
    game = Game(id=str(uuid.uuid4()), state=state, status=state["status"])
    s.add(game)
    maybe_cleanup(s)
    s.commit()
    return view(kb, s, game)


@app.get("/api/games/{game_id}")
def get_game(game_id: str, s: Session = Depends(get_db)):
    return view(kb_store.get(), s, load_game(s, game_id))


@app.post("/api/games/{game_id}/answer")
def answer(game_id: str, body: AnswerIn, request: Request, s: Session = Depends(get_db)):
    action_limit.check(client_ip(request))
    kb = kb_store.get()
    game = load_game(s, game_id)
    st = game.state
    # A double click sends the same answer twice. If this question was the one just
    # answered, return the current view instead of an error.
    if st["status"] != "asking" or body.question_id != st["current_q"]:
        if st["answers"] and st["answers"][-1][0] == body.question_id:
            return view(kb, s, game)
        raise HTTPException(409, "That question is no longer current.")
    try:
        save_state(game, eng.apply_answer(kb, dict(st, answers=list(st["answers"])), body.question_id, body.answer))
    except ValueError as e:
        raise HTTPException(409, str(e))
    s.commit()
    return view(kb, s, game)


@app.post("/api/games/{game_id}/guess")
def guess_response(game_id: str, body: GuessIn, request: Request, s: Session = Depends(get_db)):
    action_limit.check(client_ip(request))
    kb = kb_store.get()
    game = load_game(s, game_id)
    st = dict(game.state, answers=list(game.state["answers"]), wrong_guesses=list(game.state["wrong_guesses"]))
    try:
        new = eng.apply_guess_response(kb, st, body.correct)
    except ValueError as e:
        raise HTTPException(409, str(e))
    save_state(game, new)
    if new["status"] == "won":
        learn_from_win(s, kb, game)
    s.commit()
    if new["status"] == "won":
        kb_store.invalidate()
    return view(kb, s, game)


@app.post("/api/games/{game_id}/undo")
def undo(game_id: str, request: Request, s: Session = Depends(get_db)):
    action_limit.check(client_ip(request))
    kb = kb_store.get()
    game = load_game(s, game_id)
    try:
        save_state(game, eng.undo(kb, dict(game.state, answers=list(game.state["answers"]))))
    except ValueError as e:
        raise HTTPException(409, str(e))
    s.commit()
    return view(kb, s, game)


@app.post("/api/games/{game_id}/teach")
def teach_game(game_id: str, body: TeachIn, request: Request, s: Session = Depends(get_db)):
    teach_limit.check(client_ip(request))
    if body.entity_id is None and not body.name:
        raise HTTPException(422, "Send entity_id or name.")
    kb = kb_store.get()
    game = load_game(s, game_id)
    try:
        ent, created = teach(s, kb, game, body.entity_id, body.name, body.description)
    except TeachError as e:
        raise HTTPException(400, str(e))
    s.commit()
    kb_store.invalidate()
    if ent.status == "pending":
        msg = f"Thanks! {ent.name} is new to me. I will start guessing it once a few more players teach it."
    else:
        msg = f"Thanks! I will remember that about {ent.name}."
    return {"ok": True, "created": created, "entity": {"id": ent.id, "name": ent.name, "status": ent.status},
            "message": msg}


@app.get("/api/characters")
def search_characters(search: str = Query("", max_length=60), limit: int = Query(8, ge=1, le=20),
                      s: Session = Depends(get_db)):
    key = name_key(search)
    if len(key) < 2:
        return []
    rows = s.execute(select(Entity.id, Entity.name, Entity.description)
                     .where(Entity.status == "active", Entity.name_key.contains(key))
                     .order_by(Entity.popularity.desc()).limit(limit)).all()
    return [{"id": r.id, "name": r.name, "description": r.description} for r in rows]


@app.get("/api/stats")
def stats(s: Session = Depends(get_db)):
    kb = kb_store.get()
    finished = s.scalar(select(func.count()).select_from(Game).where(Game.status.in_(["won", "lost"]))) or 0
    won = s.scalar(select(func.count()).select_from(Game).where(Game.status == "won")) or 0
    return {"characters": kb.n_entities, "questions": kb.n_questions, "games_finished": finished,
            "games_won": won, "win_rate": round(won / finished, 3) if finished else None}


@app.get("/healthz")
def healthz():
    return {"ok": True, "kb_version": kb_store.get().version}


# --------------------------------------------------------------------------- admin API

@app.get("/api/admin/pending", dependencies=[Depends(require_admin)])
def admin_pending(s: Session = Depends(get_db)):
    rows = s.scalars(select(Entity).where(Entity.status == "pending").order_by(Entity.taught_count.desc())).all()
    return [{"id": e.id, "name": e.name, "description": e.description, "taught_count": e.taught_count,
             "created_at": e.created_at.isoformat()} for e in rows]


@app.get("/api/admin/flagged", dependencies=[Depends(require_admin)])
def admin_flagged(limit: int = Query(50, le=500), s: Session = Depends(get_db)):
    rows = s.scalars(select(Game).where(Game.flagged.is_not(None)).order_by(Game.updated_at.desc()).limit(limit)).all()
    return [{"game_id": g.id, "entity_id": g.entity_id, "reason": g.flagged, "answers": g.state["answers"]} for g in rows]


@app.post("/api/admin/entities/{entity_id}/{action}", dependencies=[Depends(require_admin)])
def admin_entity(entity_id: int, action: Literal["approve", "hide", "unhide"], s: Session = Depends(get_db)):
    ent = s.get(Entity, entity_id)
    if ent is None:
        raise HTTPException(404, "Unknown character.")
    ent.status = {"approve": "active", "hide": "hidden", "unhide": "active"}[action]
    bump_version(s)
    s.commit()
    kb_store.invalidate()
    return {"id": ent.id, "name": ent.name, "status": ent.status}


@app.post("/api/admin/questions", status_code=201, dependencies=[Depends(require_admin)])
def admin_add_question(body: QuestionIn, s: Session = Depends(get_db)):
    if s.scalar(select(Question).where(Question.key == body.key)):
        raise HTTPException(409, "A question with that key exists.")
    s.add(Question(key=body.key, text=body.text, scope=body.scope))
    # No facts yet: every character starts at 50/50 and players fill it in over time.
    bump_version(s)
    s.commit()
    kb_store.invalidate()
    return {"ok": True}


@app.post("/api/admin/questions/{question_id}/{action}", dependencies=[Depends(require_admin)])
def admin_question(question_id: int, action: Literal["hide", "unhide"], s: Session = Depends(get_db)):
    n = s.execute(update(Question).where(Question.id == question_id)
                  .values(status="hidden" if action == "hide" else "active")).rowcount
    if not n:
        raise HTTPException(404, "Unknown question.")
    bump_version(s)
    s.commit()
    kb_store.invalidate()
    return {"ok": True}


# --------------------------------------------------------------------------- web page

app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")


@app.exception_handler(Exception)
async def unhandled(_request: Request, exc: Exception):
    log.exception("Unhandled error", exc_info=exc)
    return JSONResponse({"detail": "Something went wrong on our side. Please try again."}, status_code=500)
