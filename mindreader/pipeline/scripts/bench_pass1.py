"""Throughput of the pass 1 handler on synthetic entities sized like real Wikidata items.

Real dump lines vary from ~1 KB (a scholarly article with no sitelinks) to several hundred
KB (Albert Einstein). This builds three kinds and times the handler on one core:
  famous person   ~60 KB: 120 labels, 80 sitelinks, 70 statements with references
  ordinary item   ~6 KB : a work or place with a few sitelinks
  no-sitelink item ~2 KB: skipped by the byte-level prefilter without JSON parsing

    python scripts/bench_pass1.py
"""
from __future__ import annotations

import os
import sys
import time

import orjson

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from mrpipe import pass1  # noqa: E402


class NullWriter:
    def add(self, table, row):
        pass


def statement(prop: str, qid: int, refs: int) -> dict:
    snak = {"snaktype": "value", "property": prop, "datatype": "wikibase-item",
            "datavalue": {"value": {"entity-type": "item", "numeric-id": qid, "id": f"Q{qid}"},
                          "type": "wikibase-entityid"}}
    ref = {"hash": "a" * 40, "snaks": {"P248": [dict(snak, property="P248")], "P813": [{
        "snaktype": "value", "property": "P813", "datatype": "time",
        "datavalue": {"value": {"time": "+2024-01-01T00:00:00Z", "precision": 11}, "type": "time"}}]},
           "snaks-order": ["P248", "P813"]}
    return {"mainsnak": snak, "type": "statement", "id": f"Q1${'b' * 36}", "rank": "normal",
            "references": [ref] * refs}


def entity(qid: int, n_langs: int, n_sites: int, n_claims: int, refs: int, human: bool) -> bytes:
    langs = [f"l{i}" for i in range(n_langs)] + ["en", "hi", "ja"]
    e = {"type": "item", "id": f"Q{qid}",
         "labels": {lg: {"language": lg, "value": f"Name {qid} {lg}"} for lg in langs},
         "descriptions": {lg: {"language": lg, "value": f"a description in {lg} " * 3} for lg in langs[: n_langs // 2]},
         "aliases": {lg: [{"language": lg, "value": f"alias {k}"} for k in range(3)] for lg in langs[:10]},
         "claims": {}, "sitelinks": {f"s{i}wiki": {"site": f"s{i}wiki", "title": f"Title {qid}", "badges": []}
                                     for i in range(n_sites)}}
    props = ["P31", "P21", "P27", "P106", "P166", "P54", "P69", "P463", "P1412", "P800"] + [f"P{9000 + i}" for i in range(60)]
    for i in range(n_claims):
        p = props[i % len(props)]
        e["claims"].setdefault(p, []).append(statement(p, 5 if (p == "P31" and human) else 100 + i, refs))
    return orjson.dumps(e)


def bench(label: str, lines: list[bytes]) -> float:
    w = NullWriter()
    args = (3, 1)
    start = time.perf_counter()
    for line in lines:
        pass1.handle(line, w, args)
    dt = time.perf_counter() - start
    size = sum(map(len, lines)) / len(lines) / 1024
    rate = len(lines) / dt
    print(f"{label:18s} {size:6.1f} KB/line  {rate:9,.0f} lines/s per core")
    return rate


if __name__ == "__main__":
    famous = [entity(1000 + i, 120, 80, 70, 2, True) for i in range(300)]
    ordinary = [entity(5000 + i, 25, 4, 15, 1, False) for i in range(2000)]
    bare = [entity(9000 + i, 3, 0, 8, 1, False) for i in range(5000)]
    r_f = bench("famous person", famous)
    r_o = bench("ordinary item", ordinary)
    r_b = bench("no-sitelink item", bare)
    # Rough mix for the 2025-2026 dump: ~117M entities, ~30% with sitelinks.
    mix = {"famous": (2e6, r_f), "ordinary": (33e6, r_o), "bare": (82e6, r_b)}
    core_seconds = sum(n / r for n, r in mix.values())
    for cores in (4, 8, 16):
        print(f"pass 1 parse time on {cores:2d} worker cores: {core_seconds / cores / 3600:5.1f} h (decompression not included)")
