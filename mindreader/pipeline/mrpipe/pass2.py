"""Pass 2 over the dump: texts (labels, descriptions, aliases, sitelinks, image) for the
selected fictional characters and labels for every attribute value."""
from __future__ import annotations

import duckdb
import orjson

from . import config as C
from .dump import PartWriter, run_parallel
from .pass1 import TEXT_SCHEMA, text_row
from .wikidata import peek_id

SCHEMAS = {"texts": TEXT_SCHEMA}


def handle(line: bytes, w: PartWriter, args: tuple) -> int:
    wanted = args[0]
    pid = peek_id(line)
    if pid is None or pid[0] != "Q":
        return 0
    mode = wanted.get(pid[1])
    if mode is None:
        return 0
    w.add("texts", text_row(pid[1], orjson.loads(line), full=mode))
    return 1


def load_wanted(paths: C.Paths) -> dict[int, bool]:
    rows = duckdb.connect().execute(
        f"SELECT qid, \"full\" FROM read_parquet('{paths.p('pass2', 'wanted.parquet')}')").fetchall()
    return {int(q): bool(f) for q, f in rows}


def run(dump_path: str, paths: C.Paths, workers: int | None = None, limit: int | None = None) -> dict:
    wanted = load_wanted(paths)
    stats = run_parallel(dump_path, paths.p("pass2"), SCHEMAS, handle, (wanted,), workers, limit)
    stats["wanted"] = len(wanted)
    return stats
