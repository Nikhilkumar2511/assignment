"""The game engine's knowledge snapshot: what the game service loads into memory.

A snapshot is a folder with three files:
  manifest.json  questions, attribute groups, and an index of the typed arrays
  arrays.bin     little-endian typed arrays, each 8-byte aligned
  display.json   per character, in engine order: names, descriptions, kind, theme, image

Arrays
  ids         i32[N]    stable character id (Wikidata number, or seed id); tokens store these
  prior       f32[N]    log prior per character (popularity)
  kind        u8[N]     1 real, 2 fictional
  g{id}.ptr   i32[N+1]  per attribute group: CSR offsets into g{id}.val
  g{id}.val   i32[nnz]  attribute value ids
  cells.ptr   i32[M+1]  per question (manifest order): offsets into cells.ent / cells.p
  cells.ent   i32[nnz]  character indices, ascending within a question
  cells.p     u8[nnz]   P(yes) * 255, rounded

P(yes | character, question) = the explicit cell if there is one; otherwise, for a group
question, p_match / p_other / 0.5 from the character's values in the group; otherwise 0.5.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
from collections import defaultdict

import numpy as np

from . import config as C

FORMAT = 1


def quantize(p: float) -> int:
    return int(min(255, max(0, round(p * 255))))


def write(out_dir: str, *, version: int, source: str, groups: list[dict], questions: list[dict],
          prior: np.ndarray, kind: np.ndarray, group_csr: dict[int, tuple[np.ndarray, np.ndarray]],
          cells: list[tuple[np.ndarray, np.ndarray]], display: list[dict]) -> dict:
    """cells[i] = (entity indices, p in 0..1) for questions[i]."""
    os.makedirs(out_dir, exist_ok=True)
    n = len(prior)
    assert len(kind) == n == len(display)
    assert len(cells) == len(questions)
    arrays: dict[str, dict] = {}
    blobs: list[bytes] = []
    offset = 0

    def add(name: str, arr: np.ndarray, typ: str) -> None:
        nonlocal offset
        dtype = {"f32": "<f4", "i32": "<i4", "u8": "u1"}[typ]
        data = np.ascontiguousarray(arr, dtype=dtype).tobytes()
        arrays[name] = {"type": typ, "offset": offset, "length": int(len(arr))}
        pad = (-len(data)) % 8
        blobs.append(data + b"\0" * pad)
        offset += len(data) + pad

    add("ids", np.array([d["id"] for d in display], dtype=np.int64), "i32")
    add("prior", prior, "f32")
    add("kind", kind, "u8")
    for gid, (ptr, val) in sorted(group_csr.items()):
        assert len(ptr) == n + 1
        add(f"g{gid}.ptr", ptr, "i32")
        add(f"g{gid}.val", val, "i32")
    qptr = np.zeros(len(questions) + 1, dtype=np.int64)
    ents, ps = [], []
    for i, (e, p) in enumerate(cells):
        order = np.argsort(e, kind="stable")
        ents.append(np.asarray(e, dtype=np.int64)[order])
        ps.append(np.array([quantize(x) for x in np.asarray(p)[order]], dtype=np.uint8))
        qptr[i + 1] = qptr[i] + len(e)
    add("cells.ptr", qptr, "i32")
    add("cells.ent", np.concatenate(ents) if ents else np.zeros(0), "i32")
    add("cells.p", np.concatenate(ps) if ps else np.zeros(0), "u8")

    manifest = {
        "format": FORMAT, "version": int(version), "source": source,
        "createdAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "langs": C.LANGS, "entityCount": n, "groups": groups, "questions": questions, "arrays": arrays,
    }
    with open(os.path.join(out_dir, "arrays.bin"), "wb") as f:
        for b in blobs:
            f.write(b)
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(out_dir, "display.json"), "w", encoding="utf-8") as f:
        json.dump(display, f, ensure_ascii=False, separators=(",", ":"))
    return {"entities": n, "questions": len(questions), "cells": int(qptr[-1]),
            "bytes": offset, "groups": len(group_csr)}


# ------------------------------------------------------------------ export from Postgres

PRIOR_POPULARITY = 0.7      # log prior = 0.7 * popularity + 0.3 * ln(1 + times played)
PRIOR_PLAYED = 0.3
GROUP_BASE_WEIGHT = 4.0     # how many player answers a Wikidata-derived value is worth
TRAIT_BASE_WEIGHT = 1.0


def export_from_postgres(dsn: str, out_dir: str, version: int | None = None, max_entities: int | None = None,
                         quotas: list[tuple[str, str, int]] | None = None, langs: list[str] | None = None,
                         min_question_support: int = 1) -> dict:
    """max_entities keeps only the most popular characters; quotas = [(group key, value key, n)]
    guarantees at least n of them with that attribute (e.g. ("region", "south_asia", 6000)).
    langs limits display and question text to those languages (all when None)."""
    import psycopg

    with psycopg.connect(dsn) as conn:
        ents = conn.execute("""
            SELECT e.id, e.kind, e.popularity, e.times_played FROM entities e
            WHERE e.status = 'active' AND NOT EXISTS (SELECT 1 FROM denylist d WHERE d.entity_id = e.id)
            ORDER BY e.popularity DESC, e.id""").fetchall()
        if max_entities is not None and len(ents) > max_entities:
            chosen: dict[int, tuple] = {}
            for group_key, value_key, n in quotas or []:
                for row in conn.execute("""
                    SELECT e.id, e.kind, e.popularity, e.times_played FROM entities e
                    JOIN entity_attrs a ON a.entity_id = e.id JOIN attr_values av ON av.id = a.value_id
                    JOIN attr_groups g ON g.id = av.group_id
                    WHERE e.status = 'active' AND g.key = %s AND av.value_key = %s
                    ORDER BY e.popularity DESC, e.id LIMIT %s""", (group_key, value_key, n)).fetchall():
                    chosen[row[0]] = row
            for row in ents:
                if len(chosen) >= max_entities:
                    break
                chosen.setdefault(row[0], row)
            ents = sorted(chosen.values(), key=lambda r: (-(r[2] or 0), r[0]))
        index = {row[0]: i for i, row in enumerate(ents)}
        n = len(ents)
        prior = np.array([PRIOR_POPULARITY * (p or 0) + PRIOR_PLAYED * math.log1p(t or 0)
                          for _, _, p, t in ents], dtype=np.float32)
        kind = np.array([1 if k == "real" else 2 for _, k, _, _ in ents], dtype=np.uint8)

        groups = [{"id": g, "key": k, "pMatch": float(pm), "pOther": float(po)} for g, k, pm, po in conn.execute(
            "SELECT id, key, p_match, p_other FROM attr_groups ORDER BY id").fetchall()]
        gparams = {g["id"]: g for g in groups}
        per_group: dict[int, list[list[int]]] = {g["id"]: [[] for _ in range(n)] for g in groups}
        with conn.cursor(name="attrs") as cur:
            cur.itersize = 200_000
            cur.execute("""SELECT a.entity_id, av.group_id, av.id FROM entity_attrs a
                           JOIN attr_values av ON av.id = a.value_id""")
            for eid, gid, vid in cur:
                i = index.get(eid)
                if i is not None:
                    per_group[gid][i].append(vid)
        group_csr = {}
        for gid, lists in per_group.items():
            lengths = np.array([len(x) for x in lists], dtype=np.int64)
            if lengths.sum() == 0:
                continue
            ptr = np.concatenate([[0], np.cumsum(lengths)])
            val = np.array([v for lst in lists for v in lst], dtype=np.int64)
            group_csr[gid] = (ptr, val)

        qrows = conn.execute("""
            SELECT q.id, q.key, q.kind, q.group_id, q.value_ids, q.scope, q.dup_cluster,
                   jsonb_object_agg(t.lang, t.text) FILTER (WHERE t.lang IS NOT NULL)
            FROM questions q LEFT JOIN question_texts t ON t.question_id = q.id
            WHERE q.status = 'active' GROUP BY q.id ORDER BY q.id""").fetchall()
        qrows = [r for r in qrows if r[7] and "en" in r[7] and (r[2] == "trait" or r[3] in group_csr)]
        # Drop value questions that no (or too few) selected character can answer "yes" to.
        if max_entities is not None:
            members: dict[tuple[int, int], int] = defaultdict(int)
            for gid, (ptr, val) in group_csr.items():
                for v in val.tolist():
                    members[(gid, v)] += 1
            qrows = [r for r in qrows if r[2] == "trait"
                     or sum(members.get((r[3], v), 0) for v in (r[4] or [])) >= min_question_support]
        if langs:
            qrows = [r[:7] + ({k: v for k, v in r[7].items() if k in langs},) for r in qrows]
        qindex = {r[0]: i for i, r in enumerate(qrows)}
        questions = [{"id": r[0], "key": r[1], "kind": "cells" if r[2] == "trait" else "group",
                      "group": r[3], "values": r[4], "scope": r[5], "dup": r[6], "text": r[7]} for r in qrows]

        # Explicit cells: LLM/admin facts plus learned evidence, on top of the base probability.
        acc: dict[tuple[int, int], list[float]] = defaultdict(lambda: [0.0, 0.0])
        for table in ("facts", "evidence_agg"):
            for eid, qid, yes_w, no_w in conn.execute(f"SELECT entity_id, question_id, yes_w, no_w FROM {table}"):
                if eid in index and qid in qindex:
                    a = acc[(index[eid], qindex[qid])]
                    a[0] += yes_w
                    a[1] += no_w
        cell_lists: list[tuple[list[int], list[float]]] = [([], []) for _ in questions]
        for (i, qi), (yes_w, no_w) in acc.items():
            q = questions[qi]
            if q["kind"] == "cells":
                base, w = 0.5, TRAIT_BASE_WEIGHT
            else:
                ptr, val = group_csr[q["group"]]
                vals = set(val[ptr[i]:ptr[i + 1]].tolist())
                g = gparams[q["group"]]
                base = g["pMatch"] if vals & set(q["values"]) else (g["pOther"] if vals else 0.5)
                w = GROUP_BASE_WEIGHT
            p = (base * w + yes_w) / (w + yes_w + no_w)
            cell_lists[qi][0].append(i)
            cell_lists[qi][1].append(min(0.99, max(0.01, p)))
        cells = [(np.array(e, dtype=np.int64), np.array(p, dtype=np.float64)) for e, p in cell_lists]

        labels: dict[int, dict] = defaultdict(lambda: {"n": {}, "d": {}})
        for eid, lang, label, desc in conn.execute("SELECT entity_id, lang, label, description FROM entity_labels"):
            if eid in index and (not langs or lang in langs):
                labels[eid]["n"][lang] = label
                if desc:
                    labels[eid]["d"][lang] = desc
        themes = dict(conn.execute("""
            SELECT DISTINCT ON (a.entity_id) a.entity_id, vl.label FROM entity_attrs a
            JOIN attr_values av ON av.id = a.value_id JOIN attr_groups g ON g.id = av.group_id
            JOIN attr_value_labels vl ON vl.value_id = av.id AND vl.lang = 'en'
            WHERE g.key IN ('franchise', 'occupation')
            ORDER BY a.entity_id, (g.key = 'franchise') DESC, av.support DESC""").fetchall())
        images = {r[0]: r[1:] for r in conn.execute("""
            SELECT entity_id, storage_prefix, author, license_short, license_url, credit_url FROM images
            WHERE status = 'ok'""").fetchall()}
        if version is None:
            version = (conn.execute("SELECT coalesce(max(version), 0) + 1 FROM snapshots").fetchone()[0])

    display = []
    for eid, k, _, _ in ents:
        item = {"id": eid, "k": k, **labels.get(eid, {"n": {}, "d": {}})}
        if eid in themes:
            item["t"] = themes[eid]
        if eid in images:
            prefix, author, lic, lic_url, credit = images[eid]
            item["img"] = {"p": prefix, "a": author, "l": lic, "lu": lic_url, "c": credit}
        display.append(item)
    stats = write(out_dir, version=version, source="wikidata", groups=groups, questions=questions, prior=prior,
                  kind=kind, group_csr=group_csr, cells=cells, display=display)
    return stats
