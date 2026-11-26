import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Use a throwaway SQLite file unless TEST_DATABASE_URL points at a real Postgres.
_tmp = tempfile.mkdtemp(prefix="mindreader-test-")
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_tmp}/test.db")
os.environ["ADMIN_TOKEN"] = "test-admin-token"
os.environ["AUTO_APPROVE_AFTER"] = "2"
os.environ["RATE_TEACH_PER_HOUR"] = "1000"
os.environ["RATE_NEW_GAMES_PER_MIN"] = "1000"
os.environ["RATE_ACTIONS_PER_MIN"] = "100000"


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    from app.db import Base
    from app.main import app, db_engine
    Base.metadata.drop_all(db_engine)
    with TestClient(app) as c:
        yield c
