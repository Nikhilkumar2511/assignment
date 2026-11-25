"""Pass 1 over the dump: people, the class graph, and every item that might matter later.

Outputs (Parquet, under work/pass1/):
  humans/       one row per human with >= HUMAN_PREFILTER_SITELINKS Wikipedia sitelinks
  texts/        labels, descriptions, aliases, sitelinks and image of those humans
  typed/        every non-human item with >= TYPED_PREFILTER_SITELINKS sitelinks, with the
                item-valued claims needed later (works, countries, occupations, characters...)
  class_edges/  every P279 (subclass of) edge in Wikidata, child -> parent
  class_labels/ English label of every item that has a P279 statement
"""
from __future__ import annotations

import orjson
import pyarrow as pa

from . import config as C
from .dump import PartWriter, run_parallel
from .wikidata import (aliases, descriptions, english_label, has_claim, has_empty_sitelinks, item_ids,
                       labels, peek_id, string_value, wikipedia_sitelinks, year_of)

ID_LIST = pa.list_(pa.int64())

TEXT_SCHEMA = pa.schema([
    ("qid", pa.int64()), ("en_label", pa.string()), ("labels", pa.string()), ("descriptions", pa.string()),
    ("aliases", pa.string()), ("sitelinks", pa.string()), ("image", pa.string()),
])

SCHEMAS = {
    "humans": pa.schema([("qid", pa.int64()), ("sitelinks", pa.int32()), ("birth_year", pa.int32()),
                         ("death_year", pa.int32()), ("dead", pa.bool_())]
                        + [(p.lower(), ID_LIST) for p in C.HUMAN_ITEM_PROPS]),
    "texts": TEXT_SCHEMA,
    "typed": pa.schema([("qid", pa.int64()), ("sitelinks", pa.int32()), ("en_label", pa.string())]
                       + [(p.lower(), ID_LIST) for p in C.TYPED_ITEM_PROPS]),
    "class_edges": pa.schema([("child", pa.int64()), ("parent", pa.int64())]),
    "class_labels": pa.schema([("qid", pa.int64()), ("en", pa.string())]),
}


def text_row(qid: int, e: dict, full: bool) -> dict:
    return {
        "qid": qid,
        "en_label": english_label(e),
        "labels": orjson.dumps(labels(e)).decode(),
        "descriptions": orjson.dumps(descriptions(e)).decode(),
        "aliases": orjson.dumps(aliases(e)).decode() if full else "{}",
        "sitelinks": orjson.dumps(wikipedia_sitelinks(e)).decode() if full else "{}",
        "image": string_value(e, "P18") if full else None,
    }


def handle(line: bytes, w: PartWriter, args: tuple) -> int:
    human_min, typed_min = args
    if has_empty_sitelinks(line) and b'"P279"' not in line:
        return 0
    pid = peek_id(line)
    if pid is None or pid[0] != "Q":
        return 0
    qid = pid[1]
    e = orjson.loads(line)
    kept = 0

    parents = item_ids(e, "P279")
    if parents:
        for parent in parents:
            w.add("class_edges", {"child": qid, "parent": parent})
        w.add("class_labels", {"qid": qid, "en": english_label(e)})
        kept = 1

    n_sites = len(wikipedia_sitelinks(e))
    p31 = item_ids(e, "P31")
    if C.Q_HUMAN in p31:
        if n_sites >= human_min:
            row = {"qid": qid, "sitelinks": n_sites, "birth_year": year_of(e, "P569"),
                   "death_year": year_of(e, "P570"), "dead": has_claim(e, "P570")}
            for p in C.HUMAN_ITEM_PROPS:
                row[p.lower()] = item_ids(e, p) if p != "P31" else p31
            w.add("humans", row)
            w.add("texts", text_row(qid, e, full=True))
            return 1
        return kept

    if n_sites >= typed_min:
        row = {"qid": qid, "sitelinks": n_sites, "en_label": english_label(e)}
        for p in C.TYPED_ITEM_PROPS:
            row[p.lower()] = p31 if p == "P31" else (parents if p == "P279" else item_ids(e, p))
        w.add("typed", row)
        kept = 1
    return kept


def run(dump_path: str, paths: C.Paths, workers: int | None = None, limit: int | None = None) -> dict:
    return run_parallel(dump_path, paths.p("pass1"), SCHEMAS, handle,
                        (C.HUMAN_PREFILTER_SITELINKS, C.TYPED_PREFILTER_SITELINKS), workers, limit)
