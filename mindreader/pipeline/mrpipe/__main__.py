"""Command line for the MindReader data pipeline.

    python -m mrpipe schema   --dsn $DATABASE_URL
    python -m mrpipe sample   --dump latest-all.json.bz2 --out sample.json.gz --every 100
    python -m mrpipe all      --work work --dump latest-all.json.bz2 --pageviews pv/ --dsn $DATABASE_URL
    python -m mrpipe images   --work work --dsn $DATABASE_URL
    python -m mrpipe enrich   estimate|submit|collect --work work --dsn $DATABASE_URL
    python -m mrpipe i18n     submit|collect --work work --dsn $DATABASE_URL

Single stages: pass1, select, pass2, pageviews, build, load (same flags as `all`).
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import time

from . import config as C


def _print(title: str, obj) -> None:
    print(f"== {title}")
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def cmd_schema(a) -> None:
    import psycopg
    path = os.path.join(os.path.dirname(__file__), "..", "schema", "001_init.sql")
    with psycopg.connect(a.dsn, autocommit=True) as conn:
        conn.execute(open(path).read())
    print("schema applied")


def cmd_sample(a) -> None:
    """Every Nth entity of the dump, for timing runs. Class trees in a sample are incomplete,
    so use it to measure speed and extrapolate counts, not to judge selection quality."""
    from .dump import iter_chunks, open_dump
    stream, proc = open_dump(a.dump)
    n = kept = 0
    with gzip.open(a.out, "wt", encoding="utf-8") as out:
        out.write("[\n")
        first = True
        for chunk in iter_chunks(stream):
            for line in chunk:
                if n % a.every == 0:
                    out.write(("" if first else ",\n") + line.decode())
                    first = False
                    kept += 1
                n += 1
        out.write("\n]\n")
    if proc:
        proc.wait()
    print(f"read {n:,} entities, wrote {kept:,} to {a.out}")


def run_stage(name: str, a, paths: C.Paths) -> dict:
    from . import build, load, pageviews, pass1, pass2, select
    started = time.time()
    if name == "pass1":
        out = pass1.run(a.dump, paths, a.workers, a.limit)
    elif name == "select":
        out = select.run(paths)
    elif name == "pass2":
        out = pass2.run(a.dump, paths, a.workers, a.limit)
    elif name == "pageviews":
        out = pageviews.run(paths, a.pageviews)
    elif name == "build":
        out = build.run(paths)
    elif name == "load":
        out = load.run(paths, a.dsn, a.dump_date)
    else:
        raise ValueError(name)
    out = dict(out)
    out["stage_seconds"] = round(time.time() - started, 1)
    _print(name, out)
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="mrpipe", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, dump=False, dsn=False):
        p.add_argument("--work", default="work", help="working directory for intermediate files")
        if dump:
            p.add_argument("--dump", required=True, help="latest-all.json.bz2 or .gz")
            p.add_argument("--workers", type=int, default=None)
            p.add_argument("--limit", type=int, default=None, help="stop after this many entities (testing)")
        if dsn:
            p.add_argument("--dsn", default=os.environ.get("DATABASE_URL"), required=not os.environ.get("DATABASE_URL"))

    p = sub.add_parser("schema"); p.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    p = sub.add_parser("apidump"); common(p); p.add_argument("--out", required=True)
    p = sub.add_parser("sample"); p.add_argument("--dump", required=True); p.add_argument("--out", required=True)
    p.add_argument("--every", type=int, default=100)
    for stage in ("pass1", "pass2"):
        common(sub.add_parser(stage), dump=True)
    common(sub.add_parser("select"))
    p = sub.add_parser("pageviews"); common(p); p.add_argument("--pageviews", default=None)
    common(sub.add_parser("build"))
    p = sub.add_parser("load"); common(p, dsn=True); p.add_argument("--dump-date", default=None)
    p = sub.add_parser("all"); common(p, dump=True, dsn=True)
    p.add_argument("--pageviews", default=None, help="folder with 12 monthly pageview_complete files")
    p.add_argument("--dump-date", default=None)
    p = sub.add_parser("images"); common(p, dsn=True)
    p.add_argument("--out", default=None); p.add_argument("--limit", type=int, default=None)
    p.add_argument("--rps", type=float, default=5.0, help="Commons requests per second")
    p.add_argument("--refresh", action="store_true")
    p = sub.add_parser("enrich"); p.add_argument("action", choices=["estimate", "submit", "collect"]); common(p, dsn=True)
    p.add_argument("--top", type=int, default=C.ENRICH_TOP_N); p.add_argument("--model", default=C.ENRICH_MODEL)
    p.add_argument("--yes", action="store_true", help="confirm spending money on submit")
    p.add_argument("--no-wait", action="store_true")
    p = sub.add_parser("i18n"); p.add_argument("action", choices=["submit", "collect"]); common(p, dsn=True)
    p.add_argument("--model", default=C.I18N_MODEL)
    p.add_argument("--yes", action="store_true"); p.add_argument("--no-wait", action="store_true")

    a = ap.parse_args(argv)
    if a.cmd == "schema":
        return cmd_schema(a)
    if a.cmd == "sample":
        return cmd_sample(a)
    if a.cmd == "apidump":
        from . import apidump
        return _print("apidump", apidump.run(C.Paths(a.work).ensure(), a.out))
    paths = C.Paths(a.work).ensure()
    if a.cmd in ("pass1", "select", "pass2", "pageviews", "build", "load"):
        run_stage(a.cmd, a, paths)
    elif a.cmd == "all":
        report = {s: run_stage(s, a, paths) for s in ("pass1", "select", "pass2", "pageviews", "build", "load")}
        with open(paths.p("run_report.json"), "w") as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    elif a.cmd == "images":
        from . import images
        _print("images", images.run(paths, a.dsn, a.out, images.Commons(requests_per_second=a.rps), a.refresh, a.limit))
    elif a.cmd == "enrich":
        from . import llm_enrich as E
        state = paths.p("llm", "enrich_batches.json")
        if a.action == "estimate":
            _print("estimate", E.estimate(E.select_characters(a.dsn, a.top), E.load_traits()))
        elif a.action == "submit":
            if not a.yes:
                sys.exit("This spends money. Run `enrich estimate` first, then add --yes.")
            _print("submitted", E.submit(a.dsn, state, a.top, a.model))
        else:
            _print("collected", E.collect(a.dsn, state, a.model, wait=not a.no_wait))
    elif a.cmd == "i18n":
        from . import llm_i18n as T
        state = paths.p("llm", "i18n_batches.json")
        if a.action == "submit":
            if not a.yes:
                sys.exit(f"This spends money: {len(T.pending_questions(a.dsn))} questions pending. Add --yes.")
            _print("submitted", T.submit(a.dsn, state, a.model))
        else:
            _print("collected", T.collect(a.dsn, state, wait=not a.no_wait))


if __name__ == "__main__":
    main()
