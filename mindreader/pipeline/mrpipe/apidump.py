"""Build a compact Wikidata dump from SPARQL exports (QLever), for machines that cannot
download or store the full 145 GB JSON dump.

It fetches only what the pipeline reads:
  * real people (P31 = Q5) with >= MIN_SITELINKS Wikipedia sitelinks
  * every fictional character under the fictional roots (any sitelink count)
  * the item-valued and date claims in config.HUMAN_ITEM_PROPS / TYPED_ITEM_PROPS
  * labels, descriptions and aliases in the game's 7 languages (+ "mul")
  * Wikipedia titles in those 7 languages and the total sitelink count
  * the whole P279 class graph with English labels
  * the items those claims point to (countries, occupations, works, franchises...), two levels deep

and writes them as dump lines in the official JSON format, so pass1/select/pass2 run
unchanged. Claims use the "truthy" (wdt:) values: preferred rank if any, else normal.

Every query result is saved as TSV under work/api/ and reused on rerun, so an
interrupted fetch resumes where it stopped.

    python -m mrpipe apidump --work work --out work/api-dump.json.gz
"""
from __future__ import annotations

import gzip
import json
import os
import re
import time
import urllib.parse
from collections import Counter, defaultdict

import httpx

from . import config as C

ENDPOINT = os.environ.get("MR_QLEVER", "https://qlever.dev/api/wikidata")
MIN_SITELINKS = int(os.environ.get("MR_API_MIN_SITELINKS", "8"))
MIN_SPACING = 8.0          # seconds between queries; the endpoint answers bursts with 429
CHUNK = 15000              # ids per VALUES query
LANG_FILTER = ", ".join(f'"{x}"' for x in C.LANGS + ["mul"])
WIKIS = {lang: f"https://{lang}.wikipedia.org/" for lang in C.LANGS}

PREFIXES = """PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX wikibase: <http://wikiba.se/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX schema: <http://schema.org/>
"""

ROOTS = " ".join(f"wd:Q{q}" for q in C.FICTIONAL_ROOT_QIDS)
EXCLUDE = " ".join(f"MINUS {{ ?x wdt:P31 wd:Q{q} }}" for q in C.FICTIONAL_EXCLUDE_CLASSES)
SUBSETS = {
    "human": f"?x wdt:P31 wd:Q5 ; wikibase:sitelinks ?sl . FILTER(?sl >= {MIN_SITELINKS})",
    "fiction": f"VALUES ?root {{ {ROOTS} }} ?x wdt:P31/wdt:P279* ?root . MINUS {{ ?x wdt:P31 wd:Q5 }} {EXCLUDE}",
}
SUBSET_PROPS = {
    "human": [p for p in C.HUMAN_ITEM_PROPS if p != "P31"] + ["P31"],
    "fiction": ["P31", "P21", "P27", "P1441", "P1080", "P8345", "P179", "P170", "P175", "P2563", "P1884",
                "P1340", "P463", "P106"],
}
# Value claims fetched for referenced items (works, countries, occupations...).
VALUE_PROPS = ["P31", "P30", "P1366", "P495", "P8345", "P1080", "P179", "P170", "P50", "P641", "P17", "P463"]
# Values referenced only once are only fetched for these props; others need >= 2 references.
ALWAYS_FETCH = {"P27", "P106", "P641", "P21", "P1441", "P495", "P170", "P50", "P8345", "P1080", "P179", "P31"}

_IRI = re.compile(r"^<http://www\.wikidata\.org/entity/Q(\d+)>$")
_LIT = re.compile(r'^"(.*)"(?:@([A-Za-z-]+)|\^\^<[^>]+>)?$', re.S)


def qid_of(cell: str) -> int | None:
    m = _IRI.match(cell)
    return int(m.group(1)) if m else None


def literal(cell: str) -> tuple[str, str | None]:
    m = _LIT.match(cell)
    if not m:
        return cell, None
    text = m.group(1).replace('\\"', '"').replace("\\n", " ").replace("\\t", " ").replace("\\\\", "\\")
    return text, m.group(2)


class QLever:
    def __init__(self, cache_dir: str, client: httpx.Client | None = None):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.client = client or httpx.Client(timeout=httpx.Timeout(float(os.environ.get("MR_QLEVER_TIMEOUT", "240")), connect=30.0),
                                             headers={"User-Agent": C.USER_AGENT})
        self._last = 0.0

    def tsv(self, name: str, query: str) -> str:
        """Run a query (or reuse its cached result) and return the path of the TSV file."""
        path = os.path.join(self.cache_dir, f"{name}.tsv")
        if os.path.exists(path):
            return path
        body = urllib.parse.urlencode({"query": PREFIXES + query})
        for attempt in range(8):
            wait = MIN_SPACING - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                with self.client.stream("POST", ENDPOINT, content=body,
                                        headers={"Accept": "text/tab-separated-values",
                                                 "Content-Type": "application/x-www-form-urlencoded"}) as resp:
                    if resp.status_code in (429, 502, 503, 504):
                        time.sleep(min(300, 15 * (attempt + 1)))
                        continue
                    if resp.status_code != 200:
                        detail = resp.read()[:500]
                        if name.endswith("_claims") and (b"allocate" in detail or b"memory" in detail.lower()):
                            raise QueryTooBig(f"{name}: {detail[:120]!r}")
                        raise RuntimeError(f"{name}: HTTP {resp.status_code}: {detail!r}")
                    tmp = path + ".part"
                    with open(tmp, "wb") as f:
                        for chunk in resp.iter_bytes(1 << 20):
                            f.write(chunk)
                    os.replace(tmp, path)
                    return path
            except httpx.TimeoutException:
                # A query that runs this long is too big for the shared endpoint: let the caller split it.
                if name.endswith("_claims"):
                    raise QueryTooBig(f"{name}: timed out")
                time.sleep(min(300, 15 * (attempt + 1)))
            except httpx.TransportError:
                time.sleep(min(300, 15 * (attempt + 1)))
        raise RuntimeError(f"{name}: gave up after repeated errors")

    @staticmethod
    def rows(path: str):
        with open(path, encoding="utf-8") as f:
            next(f, None)
            for line in f:
                yield line.rstrip("\n").split("\t")


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


class Store:
    """Claims, texts and counts per numeric id, filled from TSV results."""

    def __init__(self):
        self.claims: dict[int, dict[str, list]] = defaultdict(lambda: defaultdict(list))
        self.labels: dict[int, dict[str, str]] = defaultdict(dict)
        self.descs: dict[int, dict[str, str]] = defaultdict(dict)
        self.aliases: dict[int, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        self.titles: dict[int, dict[str, str]] = defaultdict(dict)
        self.sitelinks: dict[int, int] = {}
        self.image: dict[int, str] = {}

    def add_item_claims(self, path: str, prop: str) -> set[int]:
        seen = set()
        for row in QLever.rows(path):
            if len(row) < 2:
                continue
            s, v = qid_of(row[0]), qid_of(row[1])
            if s is None or v is None:
                continue
            lst = self.claims[s][prop]
            if v not in lst:
                lst.append(v)
            seen.add(v)
        return seen

    def add_dates(self, path: str, prop: str) -> None:
        for row in QLever.rows(path):
            s = qid_of(row[0]) if row else None
            if s is None or len(row) < 2:
                continue
            text, _ = literal(row[1])
            m = re.match(r"^(-?)0*(\d{1,6})-", text)
            if m and prop not in self.claims[s]:
                year = int(m.group(2)) * (-1 if m.group(1) else 1)
                self.claims[s][prop] = [year]

    def add_texts(self, path: str, target: dict, multi: bool = False) -> None:
        for row in QLever.rows(path):
            s = qid_of(row[0]) if row else None
            if s is None or len(row) < 2:
                continue
            text, lang = literal(row[1])
            if not lang:
                continue
            if multi:
                if len(target[s][lang]) < C.MAX_ALIASES_PER_LANG:
                    target[s][lang].append(text)
            else:
                target[s].setdefault(lang, text)


def subset_queries(q: QLever, store: Store, subset: str) -> list[int]:
    pat = SUBSETS[subset]
    path = q.tsv(f"{subset}_ids", f"SELECT DISTINCT ?x ?s WHERE {{ {pat} OPTIONAL {{ ?x wikibase:sitelinks ?s0 }} "
                                  f"BIND(COALESCE(?s0, 0) AS ?s) }}")
    ids = []
    for row in QLever.rows(path):
        x = qid_of(row[0])
        if x is None:
            continue
        ids.append(x)
        store.sitelinks[x] = int(literal(row[1])[0]) if len(row) > 1 and row[1] else 0
    log(f"{subset}: {len(ids):,} ids")
    refs: Counter = Counter()
    for prop in SUBSET_PROPS[subset]:
        path = q.tsv(f"{subset}_{prop}", f"SELECT ?x ?v WHERE {{ {pat} ?x wdt:{prop} ?v . FILTER(isIRI(?v)) }}")
        for v in store.add_item_claims(path, prop):
            refs[(prop, v)] += 0
        for row in QLever.rows(path):
            v = qid_of(row[1]) if len(row) > 1 else None
            if v is not None:
                refs[(prop, v)] += 1
        log(f"{subset} {prop}: done")
    if subset == "human":
        for prop in C.TIME_PROPS:
            store.add_dates(q.tsv(f"{subset}_{prop}", f"SELECT ?x ?v WHERE {{ {pat} ?x wdt:{prop} ?v }}"), prop)
    path = q.tsv(f"{subset}_P18", f"SELECT ?x ?v WHERE {{ {pat} ?x wdt:P18 ?v }}")
    for row in QLever.rows(path):
        x = qid_of(row[0])
        if x is not None and len(row) > 1 and x not in store.image:
            store.image[x] = urllib.parse.unquote(row[1].strip("<>").rsplit("/", 1)[-1]).replace("_", " ")
    texts(q, store, subset, pat)
    path = q.tsv(f"{subset}_titles", f"""SELECT ?x ?w ?t WHERE {{ {pat}
        VALUES ?w {{ {' '.join(f'<{u}>' for u in WIKIS.values())} }}
        ?a schema:about ?x ; schema:isPartOf ?w ; schema:name ?t }}""")
    site_by_url = {u: f"{lang}wiki" for lang, u in WIKIS.items()}
    for row in QLever.rows(path):
        x = qid_of(row[0])
        if x is not None and len(row) > 2:
            store.titles[x][site_by_url.get(row[1].strip("<>"), "xxwiki")] = literal(row[2])[0]
    store._refs = getattr(store, "_refs", Counter()) + refs
    return ids


def texts(q: QLever, store: Store, name: str, pat: str) -> None:
    store.add_texts(q.tsv(f"{name}_labels", f"SELECT ?x ?l WHERE {{ {pat} ?x rdfs:label ?l . "
                                            f"FILTER(LANG(?l) IN ({LANG_FILTER})) }}"), store.labels)
    store.add_texts(q.tsv(f"{name}_descs", f"SELECT ?x ?l WHERE {{ {pat} ?x schema:description ?l . "
                                           f"FILTER(LANG(?l) IN ({LANG_FILTER})) }}"), store.descs)
    store.add_texts(q.tsv(f"{name}_aliases", f"SELECT ?x ?l WHERE {{ {pat} ?x skos:altLabel ?l . "
                                             f"FILTER(LANG(?l) IN ({LANG_FILTER})) }}"), store.aliases, multi=True)


class QueryTooBig(RuntimeError):
    pass


def claims_for(q: QLever, store: Store, ids: list[int], tag: str) -> set[int]:
    """VALUE_PROPS claims for ids in one query; halves the batch while the endpoint runs out of memory."""
    values = "VALUES ?x { " + " ".join(f"wd:Q{i}" for i in ids) + " }"
    props = " ".join(f"wdt:{p}" for p in VALUE_PROPS)
    try:
        path = q.tsv(f"{tag}_claims", f"SELECT ?x ?p ?v WHERE {{ {values} VALUES ?p {{ {props} }} ?x ?p ?v . "
                                      f"FILTER(isIRI(?v)) }}")
    except QueryTooBig:
        if len(ids) <= 50:
            raise
        half = len(ids) // 2
        log(f"{tag}: too big for the endpoint, splitting {len(ids):,} ids")
        return claims_for(q, store, ids[:half], tag + "a") | claims_for(q, store, ids[half:], tag + "b")
    refs: set[int] = set()
    for row in QLever.rows(path):
        if len(row) < 3:
            continue
        x, v = qid_of(row[0]), qid_of(row[2])
        prop = row[1].strip("<>").rsplit("/", 1)[-1]
        if x is None or v is None:
            continue
        lst = store.claims[x][prop]
        if v not in lst:
            lst.append(v)
        if prop != "P31":
            refs.add(v)
    return refs


def value_queries(q: QLever, store: Store, ids: list[int], level: int) -> set[int]:
    """Claims, labels and sitelink counts for referenced items, in VALUES chunks."""
    new_refs: set[int] = set()
    for start in range(0, len(ids), CHUNK):
        chunk = ids[start:start + CHUNK]
        values = "VALUES ?x { " + " ".join(f"wd:Q{i}" for i in chunk) + " }"
        tag = f"val{level}_{start // CHUNK:04d}"
        new_refs |= claims_for(q, store, chunk, tag)
        path = q.tsv(f"{tag}_sl", f"SELECT ?x ?s WHERE {{ {values} ?x wikibase:sitelinks ?s }}")
        for row in QLever.rows(path):
            x = qid_of(row[0])
            if x is not None and len(row) > 1:
                store.sitelinks[x] = int(literal(row[1])[0])
        texts(q, store, tag, values)
        log(f"values level {level}: {min(start + CHUNK, len(ids)):,}/{len(ids):,}")
    return new_refs


def class_graph(q: QLever) -> tuple[str, str]:
    edges = q.tsv("classes_edges", "SELECT ?c ?p WHERE { ?c wdt:P279 ?p . FILTER(isIRI(?p)) }")
    labels = q.tsv("classes_labels", """SELECT ?c ?l WHERE { { SELECT DISTINCT ?c WHERE { ?c wdt:P279 ?any } }
        ?c rdfs:label ?l . FILTER(LANG(?l) = "en" || LANG(?l) = "mul") }""")
    return edges, labels


def statement(prop: str, value) -> dict:
    if prop in C.TIME_PROPS:
        sign = "-" if value < 0 else "+"
        dv = {"value": {"time": f"{sign}{abs(value):04d}-00-00T00:00:00Z", "precision": 9}, "type": "time"}
        dtype = "time"
    elif prop == "P18":
        dv, dtype = {"value": value, "type": "string"}, "commonsMedia"
    else:
        dv = {"value": {"entity-type": "item", "numeric-id": value, "id": f"Q{value}"}, "type": "wikibase-entityid"}
        dtype = "wikibase-item"
    return {"mainsnak": {"snaktype": "value", "property": prop, "datatype": dtype, "datavalue": dv},
            "type": "statement", "rank": "normal"}


def entity_line(qid: int, store: Store) -> bytes:
    labs = dict(store.labels.get(qid, {}))
    if "en" not in labs and "mul" in labs:
        labs["en"] = labs["mul"]
    descs = store.descs.get(qid, {})
    alis = store.aliases.get(qid, {})
    claims = {p: [statement(p, v) for v in vals] for p, vals in store.claims.get(qid, {}).items()}
    if qid in store.image:
        claims["P18"] = [statement("P18", store.image[qid])]
    ent = {
        "type": "item", "id": f"Q{qid}", "_keep": 1, "_sitelink_count": store.sitelinks.get(qid, 0),
        "labels": {k: {"language": k, "value": v} for k, v in labs.items()},
        "descriptions": {k: {"language": k, "value": v} for k, v in descs.items()},
        "aliases": {k: [{"language": k, "value": a} for a in v] for k, v in alis.items()},
        "claims": claims,
        "sitelinks": {site: {"site": site, "title": t, "badges": []} for site, t in store.titles.get(qid, {}).items()},
    }
    return json.dumps(ent, ensure_ascii=False, separators=(",", ":")).encode()


def run(paths: C.Paths, out_path: str, qlever: QLever | None = None) -> dict:
    q = qlever or QLever(paths.p("api"))
    store = Store()
    humans = subset_queries(q, store, "human")
    fiction = subset_queries(q, store, "fiction")
    refs: Counter = store._refs
    level1 = sorted({v for (prop, v), n in refs.items() if prop in ALWAYS_FETCH or n >= 2}
                    - set(humans) - set(fiction))
    log(f"level-1 values: {len(level1):,}")
    second = value_queries(q, store, level1, 1)
    level2 = sorted(second - set(level1) - set(humans) - set(fiction))
    log(f"level-2 values: {len(level2):,}")
    value_queries(q, store, level2, 2)
    edges_path, labels_path = class_graph(q)

    # Class items: P279 edges and English labels only.
    parents: dict[int, list[int]] = defaultdict(list)
    for row in QLever.rows(edges_path):
        c, p = (qid_of(row[0]), qid_of(row[1])) if len(row) > 1 else (None, None)
        if c is not None and p is not None:
            parents[c].append(p)
    class_label: dict[int, str] = {}
    for row in QLever.rows(labels_path):
        c = qid_of(row[0]) if row else None
        if c is not None and len(row) > 1:
            text, lang = literal(row[1])
            if lang == "en" or c not in class_label:
                class_label[c] = text

    written = set()
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with gzip.open(out_path, "wb", compresslevel=5) as out:
        out.write(b"[\n")
        first = True

        def emit(line: bytes) -> None:
            nonlocal first
            out.write(line if first else b",\n" + line)
            first = False

        for qid in humans + fiction + level1 + level2:
            if qid in written:
                continue
            written.add(qid)
            if qid in parents and "P279" not in store.claims.get(qid, {}):
                store.claims[qid]["P279"] = parents[qid]
            if qid not in store.labels and qid in class_label:
                store.labels[qid]["en"] = class_label[qid]
            emit(entity_line(qid, store))
        for c, ps in parents.items():
            if c in written:
                continue
            lab = {"en": {"language": "en", "value": class_label[c]}} if c in class_label else {}
            emit(json.dumps({"type": "item", "id": f"Q{c}", "labels": lab, "descriptions": {}, "aliases": {},
                             "claims": {"P279": [statement("P279", p) for p in ps]}, "sitelinks": {}},
                            ensure_ascii=False, separators=(",", ":")).encode())
        out.write(b"\n]\n")
    stats = {"humans": len(humans), "fiction": len(fiction), "values_level1": len(level1),
             "values_level2": len(level2), "classes": len(parents), "lines": len(written) + len(parents)}
    with open(paths.p("api", "apidump_report.json"), "w") as f:
        json.dump(stats, f, indent=2)
    return stats
