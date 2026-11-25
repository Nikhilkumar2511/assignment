"""Test setup: a fresh Postgres database per test session.

Set MR_TEST_DSN to a database URL whose user may CREATE DATABASE, for example
    MR_TEST_DSN=postgresql://mr:mr@localhost:5432/postgres
Tests that need Postgres are skipped when it is not set.
"""
from __future__ import annotations

import os
import sys
import uuid
from urllib.parse import urlsplit, urlunsplit

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))


def _with_db(dsn: str, name: str) -> str:
    parts = urlsplit(dsn)
    return urlunsplit(parts._replace(path="/" + name))


@pytest.fixture(scope="session")
def admin_dsn():
    dsn = os.environ.get("MR_TEST_DSN")
    if not dsn:
        pytest.skip("MR_TEST_DSN not set")
    return dsn


@pytest.fixture()
def fresh_db(admin_dsn):
    import psycopg
    name = f"mrtest_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}"')
    dsn = _with_db(admin_dsn, name)
    from mrpipe.__main__ import main
    main(["schema", "--dsn", dsn])
    yield dsn
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
