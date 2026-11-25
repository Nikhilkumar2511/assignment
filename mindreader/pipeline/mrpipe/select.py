"""Choose the characters, and list every item pass 2 must fetch labels for.

Real people: the sitelink threshold N is tuned so the count lands closest to TARGET_REAL.
Fictional: items whose P31 class is below one of the fictional roots in the class graph,
ranked by sitelinks, top TARGET_FICTIONAL.
"""
from __future__ import annotations

import json

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from . import config as C
from .classes import ClassGraph

# Claims on selected people whose values become attribute values (labels needed).
HUMAN_VALUE_PROPS = ["p27", "p106", "p641", "p54", "p166", "p39", "p102", "p136", "p1303", "p69",
                     "p463", "p1412", "p103", "p800", "p1884", "p1340"]
FICTION_VALUE_PROPS = ["p27", "p1441", "p1080", "p8345", "p179", "p170", "p2563", "p1884", "p1340",
                       "p463", "p106"]
WORK_VALUE_PROPS = ["p8345", "p1080", "p179", "p170", "p50", "p495"]
ROLLUP_GROUP_PROPS = {"p106": C.GROUPS_BY_KEY["occupation"].rollup_depth,
                      "p166": C.GROUPS_BY_KEY["award"].rollup_depth,
                      "p39": C.GROUPS_BY_KEY["position"].rollup_depth}


def tune_threshold(sitelinks: np.ndarray, target: int) -> int:
    """Smallest-error N such that count(sitelinks >= N) is closest to target."""
    if len(sitelinks) == 0:
        return C.HUMAN_PREFILTER_SITELINKS
    values = np.sort(np.unique(sitelinks))
    counts = np.array([(sitelinks >= v).sum() for v in values])
    best = int(np.argmin(np.abs(counts - target)))
    return int(values[best])


def fictional_roots(graph: ClassGraph) -> tuple[set[int], dict[int, str]]:
    by_label = graph.find_by_label(C.FICTIONAL_ROOT_LABEL_PATTERNS)
    roots = set(C.FICTIONAL_ROOT_QIDS) | set(by_label)
    return roots, by_label


def run(paths: C.Paths, graph: ClassGraph | None = None) -> dict:
    graph = graph or ClassGraph.load(paths.p("pass1"))
    con = duckdb.connect()
    p1 = paths.p("pass1")
    report: dict = {}

    # ---- real people
    sl = con.sql(f"SELECT sitelinks FROM read_parquet('{p1}/humans/*.parquet')").fetchnumpy()["sitelinks"]
    n = tune_threshold(sl, C.TARGET_REAL)
    humans = con.sql(
        f"SELECT * FROM read_parquet('{p1}/humans/*.parquet') WHERE sitelinks >= {n}").to_arrow_table()
    report["human_sitelink_threshold_N"] = n
    report["humans_in_pass1"] = int(len(sl))
    report["humans_selected"] = humans.num_rows

    # ---- fictional characters
    roots, label_roots = fictional_roots(graph)
    fict_classes = graph.descendants(sorted(roots))
    deity_classes = graph.descendants(C.DEITY_ROOT_QIDS)
    report["fictional_root_classes_by_label"] = {f"Q{q}": lab for q, lab in sorted(label_roots.items())}
    report["fictional_classes"] = len(fict_classes)
    con.register("fict_classes", pa.table({"cls": pa.array(sorted(fict_classes), pa.int64())}))
    fiction = con.sql(f"""
        SELECT t.* FROM read_parquet('{p1}/typed/*.parquet') t
        WHERE EXISTS (SELECT 1 FROM unnest(t.p31) AS u(c) JOIN fict_classes f ON f.cls = u.c)
          AND NOT EXISTS (SELECT 1 FROM unnest(t.p31) AS u(c) WHERE u.c = {C.Q_HUMAN})
        ORDER BY t.sitelinks DESC, t.qid
        LIMIT {C.TARGET_FICTIONAL}""").to_arrow_table()
    report["fictional_selected"] = fiction.num_rows
    report["fictional_min_sitelinks"] = int(min(fiction.column("sitelinks").to_pylist(), default=0))

    # Most common classes among selected characters, for a human sanity check.
    con.register("fiction", fiction)
    top_classes = con.sql("""
        SELECT c, count(*) AS n FROM (SELECT unnest(p31) AS c FROM fiction) GROUP BY c ORDER BY n DESC LIMIT 40
    """).fetchall()
    report["top_fictional_classes"] = [{"qid": f"Q{c}", "label": graph.label(c), "count": n} for c, n in top_classes]

    # ---- items whose labels pass 2 must fetch
    wanted_values: set[int] = set()

    def add_lists(table: pa.Table, props: list[str]) -> None:
        for p in props:
            if p in table.column_names:
                for lst in table.column(p).to_pylist():
                    if lst:
                        wanted_values.update(lst)

    add_lists(humans, HUMAN_VALUE_PROPS)
    add_lists(fiction, FICTION_VALUE_PROPS)
    works = {w for lst in fiction.column("p1441").to_pylist() if lst for w in lst}
    con.register("works", pa.table({"qid": pa.array(sorted(works), pa.int64())}))
    work_rows = con.sql(f"""SELECT t.* FROM read_parquet('{p1}/typed/*.parquet') t
                                JOIN works USING (qid)""").to_arrow_table()
    add_lists(work_rows, WORK_VALUE_PROPS)

    # Parent occupations, awards and positions become values too (not through generic
    # classes such as "occupation" itself).
    stop = {q for q, lab in graph.labels.items() if lab.lower() in C.ROLLUP_STOP_LABELS}
    occupations: set[int] = set()
    for p, depth in ROLLUP_GROUP_PROPS.items():
        for lst in humans.column(p).to_pylist():
            for v in lst or ():
                anc = {a for a, _ in graph.ancestors(v, depth, stop)}
                wanted_values.update(anc)
                if p == "p106":
                    occupations.update(anc | {v})
    for lst in fiction.column("p106").to_pylist():
        occupations.update(lst or ())
    # Sports implied by occupations ("cricketer" -> cricket).
    con.register("occs", pa.table({"qid": pa.array(sorted(occupations), pa.int64())}))
    for (sport,) in con.sql(f"""SELECT unnest(t.p641) FROM read_parquet('{p1}/typed/*.parquet') t
                                JOIN occs USING (qid)""").fetchall():
        wanted_values.add(int(sport))
    # Successor countries, so historical states can map to today's country.
    countries = {c for lst in humans.column("p27").to_pylist() if lst for c in lst}
    countries |= {c for lst in fiction.column("p27").to_pylist() if lst for c in lst}
    countries |= {c for lst in work_rows.column("p495").to_pylist() if lst for c in lst}
    con.register("countries", pa.table({"qid": pa.array(sorted(countries), pa.int64())}))
    succ = con.sql(f"""SELECT unnest(t.p1366) FROM read_parquet('{p1}/typed/*.parquet') t
                           JOIN countries USING (qid)""").fetchall()
    wanted_values.update(int(s[0]) for s in succ)

    human_ids = set(humans.column("qid").to_pylist())
    fiction_ids = set(fiction.column("qid").to_pylist())
    # Humans already have texts from pass 1; everything else needs pass 2.
    full = sorted(fiction_ids)
    label_only = sorted(wanted_values - fiction_ids - human_ids)
    pq.write_table(humans, paths.p("pass2", "selected_humans.parquet"))
    pq.write_table(fiction, paths.p("pass2", "selected_fiction.parquet"))
    pq.write_table(pa.table({"qid": pa.array(full + label_only, pa.int64()),
                             "full": pa.array([True] * len(full) + [False] * len(label_only))}),
                   paths.p("pass2", "wanted.parquet"))
    pq.write_table(pa.table({"qid": pa.array(sorted(deity_classes), pa.int64())}),
                   paths.p("pass2", "deity_classes.parquet"))
    report["pass2_full"] = len(full)
    report["pass2_label_only"] = len(label_only)
    with open(paths.p("pass2", "select_report.json"), "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    return report
