"""Turn the extracted claims into characters, attribute values and questions.

This is the attribute-to-question mapping. Every rule is listed in config.GROUPS,
config.FIXED_QUESTIONS and config.BIRTH_YEAR_QUESTIONS; this module applies them.

Outputs (Parquet, under work/build/):
  entities, entity_labels, entity_names, entity_sitelinks, images_wanted,
  attr_values, attr_value_labels, entity_attrs, questions, plus build_report.json
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
from collections import Counter, defaultdict

import duckdb
import orjson
import pyarrow as pa
import pyarrow.parquet as pq

from . import config as C
from .classes import ClassGraph
from .select import fictional_roots

NOW_YEAR = dt.date.today().year


class Lookups:
    """Everything the mapping rules need to look up, loaded once."""

    def __init__(self, paths: C.Paths, graph: ClassGraph):
        self.graph = graph
        con = duckdb.connect()
        p1, p2 = paths.p("pass1"), paths.p("pass2")
        self.humans = con.sql(f"SELECT * FROM read_parquet('{p2}/selected_humans.parquet')").to_arrow_table().to_pylist()
        self.fiction = con.sql(f"SELECT * FROM read_parquet('{p2}/selected_fiction.parquet')").to_arrow_table().to_pylist()
        wanted = f"read_parquet('{p2}/wanted.parquet')"
        self.typed = {r["qid"]: r for r in con.sql(
            f"SELECT t.* FROM read_parquet('{p1}/typed/*.parquet') t WHERE t.qid IN (SELECT qid FROM {wanted})"
        ).to_arrow_table().to_pylist()}
        self.texts: dict[int, dict] = {}
        need = ({r["qid"] for r in self.humans} | {r["qid"] for r in self.fiction}
                | {r[0] for r in con.sql(f"SELECT qid FROM {wanted}").fetchall()})
        con.register("need", pa.table({"qid": pa.array(sorted(need), pa.int64())}))
        for src in (f"{p1}/texts/*.parquet", f"{p2}/texts/*.parquet"):
            try:
                rel = con.sql(f"SELECT t.* FROM read_parquet('{src}') t JOIN need USING (qid)")
            except duckdb.IOException:
                continue
            for r in rel.to_arrow_table().to_pylist():
                self.texts.setdefault(r["qid"], r)
        # Labels of value items that are humans (creators) come from pass 2 as well.
        self.views = dict(con.sql(f"SELECT qid, views FROM read_parquet('{paths.p('build', 'pageviews.parquet')}')").fetchall())
        deity = {r[0] for r in con.sql(f"SELECT qid FROM read_parquet('{p2}/deity_classes.parquet')").fetchall()}
        roots, _ = fictional_roots(graph)
        myth_roots = (roots - {95074}) | {2239243}
        self.deity_classes = deity
        self.myth_classes = graph.descendants(sorted(myth_roots))
        self.stop_ids = {q for q, lab in graph.labels.items() if lab.lower() in C.ROLLUP_STOP_LABELS}

    def label_en(self, qid: int) -> str | None:
        t = self.texts.get(qid)
        if t and t.get("en_label"):
            return t["en_label"]
        return self.graph.label(qid)

    def labels_all(self, qid: int) -> dict[str, str]:
        t = self.texts.get(qid)
        labs = orjson.loads(t["labels"]) if t and t.get("labels") else {}
        if "en" not in labs:
            en = self.label_en(qid)
            if en:
                labs["en"] = en
        return labs

    def typed_list(self, qid: int, prop: str) -> list[int]:
        row = self.typed.get(qid)
        return list(row.get(prop) or []) if row else []


# ------------------------------------------------------------------ mapping rules

def map_country(lk: Lookups, country: int) -> int:
    """Follow 'replaced by' (P1366) while there is exactly one successor, at most 3 hops."""
    cur = country
    for _ in range(3):
        succ = lk.typed_list(cur, "p1366")
        if len(succ) != 1:
            break
        cur = succ[0]
    return cur


def regions_of(lk: Lookups, country: int) -> set[str]:
    if country in C.REGION_BY_COUNTRY:
        return {C.REGION_BY_COUNTRY[country]}
    out = set()
    for cont in lk.typed_list(country, "p30"):
        region = C.CONTINENT_REGION.get(cont)
        if region == "north_america" and country not in (30, 16):
            region = "latin_america"
        if region and region != "antarctica":
            out.add(region)
    return out


def rollup(lk: Lookups, values: list[int], depth: int, include_p31: bool = False) -> set[int]:
    out = set(values)
    for v in values:
        out.update(a for a, _ in lk.graph.ancestors(v, depth, lk.stop_ids))
        if include_p31:
            for cls in lk.typed_list(v, "p31"):
                out.add(cls)
                out.update(a for a, _ in lk.graph.ancestors(cls, max(depth - 1, 0), lk.stop_ids))
    return {v for v in out if v not in lk.stop_ids}


def human_values(lk: Lookups, h: dict) -> list[tuple[str, str]]:
    vals: list[tuple[str, str]] = [("kind", "real")]
    q = lambda n: f"Q{n}"  # noqa: E731
    for g in h["p21"] or []:
        if g in C.GENDER_MAP:
            vals.append(("gender", C.GENDER_MAP[g]))
            break
    by, dy = h["birth_year"], h["death_year"]
    if h["dead"] or dy is not None or (by is not None and by < NOW_YEAR - 110):
        vals.append(("vital", "dead"))
    elif by is not None:
        vals.append(("vital", "alive"))
    if by is not None:
        vals.append(("birth_year", f"year:{by}"))
    countries = {map_country(lk, c) for c in h["p27"] or []}
    for c in countries:
        vals.append(("country", q(c)))
        vals.extend(("region", r) for r in regions_of(lk, c))
    occs = rollup(lk, list(h["p106"] or []), C.GROUPS_BY_KEY["occupation"].rollup_depth)
    vals.extend(("occupation", q(o)) for o in occs)
    sports = set(h["p641"] or [])
    for o in occs:
        sports.update(lk.typed_list(o, "p641"))
    vals.extend(("sport", q(s)) for s in sports)
    vals.extend(("team", q(t)) for t in h["p54"] or [])
    vals.extend(("award", q(a)) for a in rollup(lk, list(h["p166"] or []), C.GROUPS_BY_KEY["award"].rollup_depth, True))
    vals.extend(("position", q(p)) for p in rollup(lk, list(h["p39"] or []), C.GROUPS_BY_KEY["position"].rollup_depth))
    simple = {"party": "p102", "genre": "p136", "instrument": "p1303", "educated_at": "p69", "member_of": "p463",
              "notable_work": "p800", "hair_color": "p1884", "eye_color": "p1340"}
    for group, prop in simple.items():
        vals.extend((group, q(v)) for v in h[prop] or [])
    for lang in set((h["p1412"] or []) + (h["p103"] or [])):
        vals.append(("language", q(lang)))
    return vals


def fiction_values(lk: Lookups, f: dict) -> tuple[list[tuple[str, str]], bool]:
    vals: list[tuple[str, str]] = [("kind", "fictional")]
    q = lambda n: f"Q{n}"  # noqa: E731
    p31 = list(f["p31"] or [])
    for g in f["p21"] or []:
        if g in C.GENDER_MAP:
            vals.append(("gender", C.GENDER_MAP[g]))
            break
    works = list(f["p1441"] or [])
    vals.extend(("work", q(w)) for w in works)
    franchises = set((f["p8345"] or []) + (f["p1080"] or []) + (f["p179"] or []))
    creators = set(f["p170"] or [])
    countries = set(f["p27"] or [])
    work_classes: list[int] = []
    for w in works:
        franchises.update(lk.typed_list(w, "p8345") + lk.typed_list(w, "p1080") + lk.typed_list(w, "p179"))
        creators.update(lk.typed_list(w, "p170") + lk.typed_list(w, "p50"))
        if not f["p27"]:
            countries.update(lk.typed_list(w, "p495"))
        work_classes.extend(lk.typed_list(w, "p31"))
    vals.extend(("franchise", q(x)) for x in franchises)
    vals.extend(("creator", q(x)) for x in creators)
    for c in {map_country(lk, c) for c in countries}:
        vals.append(("country", q(c)))
        vals.extend(("region", r) for r in regions_of(lk, c))
    media = lk.graph.match_patterns(work_classes, C.MEDIUM_PATTERNS, depth=3)
    media |= lk.graph.match_patterns(p31, C.MEDIUM_PATTERNS, depth=1)
    is_myth = any(c in lk.myth_classes for c in p31)
    if is_myth:
        media.add("mythology")
    vals.extend(("medium", m) for m in media)
    types = lk.graph.match_patterns(p31, C.CHAR_TYPE_PATTERNS, depth=4)
    is_deity = any(c in lk.deity_classes for c in p31)
    if is_deity:
        types.add("deity")
    vals.extend(("char_type", t) for t in types)
    vals.extend(("power", q(x)) for x in f["p2563"] or [])
    vals.extend(("hair_color", q(x)) for x in f["p1884"] or [])
    vals.extend(("eye_color", q(x)) for x in f["p1340"] or [])
    vals.extend(("member_of", q(x)) for x in f["p463"] or [])
    vals.extend(("occupation", q(o)) for o in rollup(lk, list(f["p106"] or []), 1))
    return vals, is_deity


# ------------------------------------------------------------------ question text helpers

def with_article(label: str) -> str:
    return ("an " if re.match(r"[aeiou]", label, re.I) and not re.match(r"(uni|eu|one)", label, re.I) else "a ") + label


# Country names that read naturally with "the": "from the United Kingdom".
_THE_PREFIXES = ("united ", "republic ", "kingdom ", "democratic ", "people's ", "state of ", "federated ",
                 "islamic republic", "netherlands", "philippines", "bahamas", "gambia", "maldives",
                 "czech republic", "central african", "dominican republic", "solomon islands", "marshall islands")


def render(template: str, group: str, label: str) -> str:
    if group == "occupation":
        return template.replace("a {label}", with_article(label))
    if group == "country" and label.lower().startswith(_THE_PREFIXES):
        label = "the " + label
    return template.format(label=label)


def norm_text(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


# ------------------------------------------------------------------ main

def run(paths: C.Paths, graph: ClassGraph | None = None) -> dict:
    graph = graph or ClassGraph.load(paths.p("pass1"))
    lk = Lookups(paths, graph)
    report: dict = {}

    entity_rows = []
    per_entity: dict[int, set[tuple[str, str]]] = defaultdict(set)

    def add_attr(qid: int, group: str, value: str) -> None:
        per_entity[qid].add((group, value))

    for h in lk.humans:
        qid = h["qid"]
        for g, v in human_values(lk, h):
            add_attr(qid, g, v)
        alive = h["birth_year"] is not None and not h["dead"] and h["death_year"] is None
        entity_rows.append({
            "qid": qid, "kind": "real", "sitelinks": h["sitelinks"], "birth_year": h["birth_year"],
            "is_minor": bool(alive and h["birth_year"] > NOW_YEAR - 18), "is_religious": False})
    selected_humans = {h["qid"] for h in lk.humans}
    for f in lk.fiction:
        qid = f["qid"]
        vals, is_deity = fiction_values(lk, f)
        for g, v in vals:
            add_attr(qid, g, v)
        entity_rows.append({"qid": qid, "kind": "fictional", "sitelinks": f["sitelinks"], "birth_year": None,
                            "is_minor": False, "is_religious": is_deity})
        # Famous roles: the actors who played this character.
        franchises = sorted({v for (g, v) in vals if g == "franchise"})
        for actor in f["p175"] or []:
            if actor in selected_humans:
                add_attr(actor, "played_character", f"Q{qid}")
                for fr in franchises:
                    add_attr(actor, "played_in_franchise", fr)

    for r in entity_rows:
        views = int(lk.views.get(r["qid"], 0))
        r["pageviews_12m"] = views
        r["popularity"] = round(C.SITELINK_WEIGHT * math.log1p(r["sitelinks"]) + C.PAGEVIEW_WEIGHT * math.log1p(views), 4)

    attrs = [(e, g, v) for e, pairs in per_entity.items() for (g, v) in sorted(pairs)]
    del per_entity
    # Entity sets for groups with fixed multi-value questions, to count support exactly.
    fixed_members: dict[tuple[str, str], set[int]] = defaultdict(set)
    for e, g, v in attrs:
        if g in C.FIXED_QUESTIONS:
            fixed_members[(g, v)].add(e)

    # ---- support and value labels
    support = Counter((g, v) for (_, g, v) in attrs)
    value_rows, value_label_rows = [], []
    for (g, v), n in sorted(support.items()):
        wid = int(v[1:]) if v.startswith("Q") and v[1:].isdigit() else None
        value_rows.append({"group_key": g, "value_key": v, "wikidata_id": wid, "support": n})
        if wid is not None:
            for lang, lab in lk.labels_all(wid).items():
                value_label_rows.append({"group_key": g, "value_key": v, "lang": lang, "label": lab})

    # ---- questions
    questions = []
    by_group: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for (g, v), n in support.items():
        by_group[g].append((v, n))
    for group in C.GROUPS:
        values = by_group.get(group.key, [])
        if group.key in C.FIXED_QUESTIONS:
            present = dict(values)
            for suffix, text, yes_values in C.FIXED_QUESTIONS[group.key]:
                keys = [v for v in yes_values if v in present]
                n = len(set().union(*(fixed_members[(group.key, v)] for v in keys))) if keys else 0
                if keys and n >= C.min_support(group):
                    questions.append({"key": f"in:{group.key}:{suffix}", "kind": "in", "group_key": group.key,
                                      "value_keys": keys, "scope": group.scope, "support": n, "text_en": text})
        elif group.key == "birth_year":
            years = {int(v.split(":")[1]): n for v, n in values}
            for suffix, text, lo, hi in C.BIRTH_YEAR_QUESTIONS:
                keys = [f"year:{y}" for y in sorted(years)
                        if (lo is None or y >= lo) and (hi is None or y < hi)]
                n = sum(years[int(k.split(':')[1])] for k in keys)
                if keys:
                    questions.append({"key": f"in:birth_year:{suffix}", "kind": "in", "group_key": "birth_year",
                                      "value_keys": keys, "scope": group.scope, "support": n, "text_en": text})
        elif group.template:
            eligible = sorted((x for x in values if x[1] >= C.min_support(group)), key=lambda x: (-x[1], x[0]))
            for v, n in eligible[:group.max_questions]:
                label = lk.label_en(int(v[1:])) if v.startswith("Q") else None
                if not label:
                    continue
                questions.append({"key": f"eq:{group.key}:{v}", "kind": "eq", "group_key": group.key,
                                  "value_keys": [v], "scope": group.scope, "support": n,
                                  "text_en": render(group.template, group.key, label)})

    # Drop exact duplicate wordings, keeping the question with more support.
    best: dict[str, dict] = {}
    for qn in questions:
        k = norm_text(qn["text_en"])
        if k not in best or qn["support"] > best[k]["support"]:
            best[k] = qn
    dropped = len(questions) - len(best)
    questions = sorted(best.values(), key=lambda x: x["key"])

    with open(os.path.join(os.path.dirname(__file__), "..", "data", "trait_questions.json")) as fh:
        traits = json.load(fh)["traits"]
    for t in traits:
        questions.append({"key": f"trait:{t['key']}", "kind": "trait", "group_key": None, "value_keys": None,
                          "scope": t["scope"], "support": 0, "text_en": t["text"]})

    # ---- texts for characters
    label_rows, name_rows, site_rows, image_rows = [], [], [], []
    for r in entity_rows:
        t = lk.texts.get(r["qid"])
        if not t:
            continue
        labs = orjson.loads(t["labels"])
        descs = orjson.loads(t["descriptions"])
        alis = orjson.loads(t["aliases"])
        if "en" not in labs and t.get("en_label"):
            labs["en"] = t["en_label"]
        for lang, lab in labs.items():
            label_rows.append({"qid": r["qid"], "lang": lang, "label": lab, "description": descs.get(lang)})
            name_rows.append({"qid": r["qid"], "lang": lang, "name": lab, "is_alias": False})
        for lang, names in alis.items():
            for nm in names:
                if nm != labs.get(lang):
                    name_rows.append({"qid": r["qid"], "lang": lang, "name": nm, "is_alias": True})
        for wiki, title in orjson.loads(t["sitelinks"]).items():
            site_rows.append({"qid": r["qid"], "wiki": wiki, "title": title})
        if t.get("image") and not r["is_minor"]:
            image_rows.append({"qid": r["qid"], "file": t["image"]})
    # Characters without an English or any label cannot be shown; drop them.
    labelled = {x["qid"] for x in label_rows}
    missing = [r["qid"] for r in entity_rows if r["qid"] not in labelled]
    entity_rows = [r for r in entity_rows if r["qid"] in labelled]
    attrs = [a for a in attrs if a[0] in labelled]

    out = paths.p("build")
    pq.write_table(pa.Table.from_pylist(entity_rows), f"{out}/entities.parquet")
    pq.write_table(pa.Table.from_pylist(label_rows, schema=pa.schema([
        ("qid", pa.int64()), ("lang", pa.string()), ("label", pa.string()), ("description", pa.string())])),
        f"{out}/entity_labels.parquet")
    pq.write_table(pa.Table.from_pylist(name_rows, schema=pa.schema([
        ("qid", pa.int64()), ("lang", pa.string()), ("name", pa.string()), ("is_alias", pa.bool_())])),
        f"{out}/entity_names.parquet")
    pq.write_table(pa.Table.from_pylist(site_rows, schema=pa.schema([
        ("qid", pa.int64()), ("wiki", pa.string()), ("title", pa.string())])), f"{out}/entity_sitelinks.parquet")
    pq.write_table(pa.Table.from_pylist(image_rows, schema=pa.schema([("qid", pa.int64()), ("file", pa.string())])),
                   f"{out}/images_wanted.parquet")
    pq.write_table(pa.Table.from_pylist(value_rows, schema=pa.schema([
        ("group_key", pa.string()), ("value_key", pa.string()), ("wikidata_id", pa.int64()), ("support", pa.int32())])),
        f"{out}/attr_values.parquet")
    pq.write_table(pa.Table.from_pylist(value_label_rows, schema=pa.schema([
        ("group_key", pa.string()), ("value_key", pa.string()), ("lang", pa.string()), ("label", pa.string())])),
        f"{out}/attr_value_labels.parquet")
    pq.write_table(pa.table({"qid": pa.array([a[0] for a in attrs], pa.int64()),
                             "group_key": pa.array([a[1] for a in attrs]),
                             "value_key": pa.array([a[2] for a in attrs])}), f"{out}/entity_attrs.parquet")
    pq.write_table(pa.Table.from_pylist(questions, schema=pa.schema([
        ("key", pa.string()), ("kind", pa.string()), ("group_key", pa.string()), ("value_keys", pa.list_(pa.string())),
        ("scope", pa.string()), ("support", pa.int32()), ("text_en", pa.string())])), f"{out}/questions.parquet")

    per_group = Counter(q["group_key"] or "trait" for q in questions)
    report.update({
        "entities": len(entity_rows), "real": sum(r["kind"] == "real" for r in entity_rows),
        "fictional": sum(r["kind"] == "fictional" for r in entity_rows), "minors": sum(r["is_minor"] for r in entity_rows),
        "religious": sum(r["is_religious"] for r in entity_rows), "dropped_without_label": len(missing),
        "attribute_rows": len(attrs), "attribute_values": len(value_rows), "questions": len(questions),
        "questions_per_group": dict(sorted(per_group.items())), "duplicate_wordings_dropped": dropped,
        "images_wanted": len(image_rows),
        "avg_attributes_per_entity": round(len(attrs) / max(1, len(entity_rows)), 1),
    })
    with open(f"{out}/build_report.json", "w") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    return report
