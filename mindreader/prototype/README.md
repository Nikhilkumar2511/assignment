# MindReader prototype (Python reference implementation)

A small, working version of the game: FastAPI + Postgres or SQLite, a NumPy Bayesian engine,
247 hand-tagged characters and 108 questions. It is the reference the production TypeScript
engine is checked against (see `../docs/01-architecture.md`).

## Run

    pip install -r requirements.txt
    uvicorn app.main:app            # SQLite file mindreader.db by default
    # or: DATABASE_URL=postgresql://user:pass@host/db uvicorn app.main:app

Open http://localhost:8000. API docs at /docs. Set ADMIN_TOKEN to use /api/admin/*.

## Test and simulate

    python -m pytest -q                              # 21 tests (SQLite)
    TEST_DATABASE_URL=postgresql://... python -m pytest -q
    python -m scripts.simulate --noise 0.1 --rounds 2

Simulation results on the seed data (simulated players answer from the same data, so these
are upper bounds): 100% wins with perfect answers (12.6 questions on average);
93% wins with 10% of answers wrong (about 20 questions).

## Layout

- `app/engine.py`: posterior update, expected information gain, guess and undo rules
- `app/seed_data.py`, `data/`: question bank and character tags
- `app/learning.py`: learning from finished games, troll check, new characters
- `app/main.py`: HTTP API and static page
