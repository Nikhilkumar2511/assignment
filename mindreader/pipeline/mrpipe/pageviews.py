"""Sum the last 12 months of Wikipedia pageviews for every selected character.

Input: monthly files from https://dumps.wikimedia.org/other/pageview_complete/monthly/
Two layouts are accepted, because both have been published:
  * text (optionally .bz2 / .gz): "wiki_code page_title page_id access_method count breakdown"
    e.g. "en.wikipedia Virat_Kohli 1234 mobile-web 51234 A12B9..."
  * Parquet: columns are detected by name (wiki/project/domain, title, views/count).
Only wikis in config.PAGEVIEW_WIKIS are counted.
"""
from __future__ import annotations

import bz2
import glob
import gzip
import os
import shutil
import subprocess
from collections import defaultdict

import duckdb
import orjson
import pyarrow as pa
import pyarrow.parquet as pq

from . import config as C


def _site_to_code(site: str) -> str | None:
    """'enwiki' -> 'en.wikipedia', 'zh_yuewiki' -> 'zh-yue.wikipedia'."""
    if not site.endswith("wiki"):
        return None
    return site[:-4].replace("_", "-") + ".wikipedia"


def _normalize_code(code: str) -> str:
    # Older layouts put the mobile site in the domain: en.m.wikipedia
    return code.replace(".m.", ".")


def title_index(paths: C.Paths) -> dict[str, int]:
    """'en.wikipedia|Virat Kohli' -> qid, for every selected character's sitelinks."""
    allowed = {f"{w}.wikipedia" for w in C.PAGEVIEW_WIKIS}
    index: dict[str, int] = {}
    con = duckdb.connect()
    sources = [paths.p("pass1", "texts", "*.parquet"), paths.p("pass2", "texts", "*.parquet")]
    selected = (f"SELECT qid FROM read_parquet('{paths.p('pass2', 'selected_humans.parquet')}') UNION ALL "
                f"SELECT qid FROM read_parquet('{paths.p('pass2', 'selected_fiction.parquet')}')")
    for src in sources:
        if not glob.glob(src):
            continue
        for qid, sitelinks in con.sql(f"SELECT t.qid, t.sitelinks FROM read_parquet('{src}') t "
                                      f"WHERE t.qid IN ({selected})").fetchall():
            for site, title in orjson.loads(sitelinks).items():
                code = _site_to_code(site)
                if code in allowed:
                    index[f"{code}|{title}"] = int(qid)
    return index


def _open_text(path: str):
    if path.endswith(".bz2"):
        exe = shutil.which("lbzip2") or shutil.which("pbzip2")
        if exe:
            proc = subprocess.Popen([exe, "-dc", path], stdout=subprocess.PIPE, bufsize=1 << 20)
            return proc.stdout, proc
        return bz2.open(path, "rb"), None
    if path.endswith(".gz"):
        return gzip.open(path, "rb"), None
    return open(path, "rb"), None


def _scan_text(path: str, index: dict[str, int], totals: dict[int, int]) -> int:
    stream, proc = _open_text(path)
    matched = 0
    try:
        for raw in stream:
            parts = raw.split(b" ")
            if len(parts) < 5:
                continue
            try:
                code = _normalize_code(parts[0].decode())
                title = parts[1].decode("utf-8", "replace").replace("_", " ")
                count = int(parts[4]) if parts[4].isdigit() else int(parts[-2])
            except ValueError:
                continue
            qid = index.get(f"{code}|{title}")
            if qid is not None:
                totals[qid] += count
                matched += 1
    finally:
        stream.close()
        if proc:
            proc.wait()
    return matched


def _pick(columns: list[str], options: tuple[str, ...]) -> str:
    for opt in options:
        for col in columns:
            if col.lower() == opt:
                return col
    for opt in options:
        for col in columns:
            if opt in col.lower():
                return col
    raise ValueError(f"cannot find a column like {options} in {columns}")


def _scan_parquet(path: str, index: dict[str, int], totals: dict[int, int]) -> int:
    con = duckdb.connect()
    cols = [r[0] for r in con.sql(f"DESCRIBE SELECT * FROM read_parquet('{path}')").fetchall()]
    wiki = _pick(cols, ("wiki_code", "project", "domain_code", "wiki", "domain"))
    title = _pick(cols, ("page_title", "article", "title"))
    views = _pick(cols, ("views", "view_count", "count", "monthly_total", "total"))
    keys = pa.table({"k": pa.array(list(index.keys())), "qid": pa.array(list(index.values()), pa.int64())})
    con.register("keys", keys)
    rows = con.sql(f"""
        SELECT k.qid, sum(CAST(p."{views}" AS BIGINT)) FROM read_parquet('{path}') p
        JOIN keys k ON k.k = replace(p."{wiki}", '.m.', '.') || '|' || replace(p."{title}", '_', ' ')
        GROUP BY k.qid""").fetchall()
    for qid, n in rows:
        totals[int(qid)] += int(n or 0)
    return len(rows)


def run(paths: C.Paths, pageview_dir: str | None) -> dict:
    out = paths.p("build", "pageviews.parquet")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if not pageview_dir:
        pq.write_table(pa.table({"qid": pa.array([], pa.int64()), "views": pa.array([], pa.int64())}), out)
        return {"files": 0, "note": "no pageview directory given; popularity uses sitelinks only"}
    files = sorted(f for f in glob.glob(os.path.join(pageview_dir, "*")) if os.path.isfile(f))
    files = files[-C.PAGEVIEW_MONTHS:]
    index = title_index(paths)
    totals: dict[int, int] = defaultdict(int)
    matched = 0
    for f in files:
        matched += _scan_parquet(f, index, totals) if f.endswith(".parquet") else _scan_text(f, index, totals)
    pq.write_table(pa.table({"qid": pa.array(list(totals.keys()), pa.int64()),
                             "views": pa.array(list(totals.values()), pa.int64())}), out)
    return {"files": len(files), "titles_indexed": len(index), "rows_matched": matched,
            "characters_with_views": len(totals)}
