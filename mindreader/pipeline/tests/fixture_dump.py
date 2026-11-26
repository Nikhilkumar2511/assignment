"""A tiny Wikidata dump in the real JSON dump format, for end-to-end pipeline tests.

The ids of real-world anchors (Q5 human, Q95074 fictional character, Q668 India...) are
real Wikidata ids because the pipeline config refers to them. Everything else uses ids
from 1,000,000 up so it cannot be mistaken for real data.
"""
from __future__ import annotations

import bz2
import gzip
import json

LANG_LABELS = ("en", "hi", "es", "ja")


def _snak_item(prop: str, qid: int, rank: str = "normal") -> dict:
    return {"mainsnak": {"snaktype": "value", "property": prop, "datatype": "wikibase-item",
                         "datavalue": {"value": {"entity-type": "item", "numeric-id": qid, "id": f"Q{qid}"},
                                       "type": "wikibase-entityid"}},
            "type": "statement", "rank": rank}


def _snak_time(prop: str, year: int, precision: int = 11) -> dict:
    sign = "-" if year < 0 else "+"
    return {"mainsnak": {"snaktype": "value", "property": prop, "datatype": "time",
                         "datavalue": {"value": {"time": f"{sign}{abs(year):04d}-01-01T00:00:00Z", "timezone": 0,
                                                 "before": 0, "after": 0, "precision": precision,
                                                 "calendarmodel": "http://www.wikidata.org/entity/Q1985727"},
                                       "type": "time"}},
            "type": "statement", "rank": "normal"}


def _snak_string(prop: str, value: str) -> dict:
    return {"mainsnak": {"snaktype": "value", "property": prop, "datatype": "commonsMedia",
                         "datavalue": {"value": value, "type": "string"}}, "type": "statement", "rank": "normal"}


def item(qid: int, label: str, desc: str = "", claims: dict | None = None, sitelinks: int = 0,
         aliases: list[str] | None = None, extra_labels: dict | None = None) -> dict:
    labels = {"en": {"language": "en", "value": label}}
    for lang, val in (extra_labels or {}).items():
        labels[lang] = {"language": lang, "value": val}
    sites = {}
    wikis = ["enwiki", "hiwiki", "eswiki", "jawiki", "frwiki", "ptwiki", "arwiki", "dewiki", "itwiki", "ruwiki",
             "zhwiki", "kowiki", "plwiki", "nlwiki", "trwiki", "idwiki", "viwiki", "ukwiki", "svwiki", "hewiki"]
    for i in range(sitelinks):
        site = wikis[i] if i < len(wikis) else f"x{i}wiki"
        sites[site] = {"site": site, "title": label, "badges": []}
    if sitelinks:
        sites["commonswiki"] = {"site": "commonswiki", "title": f"Category:{label}", "badges": []}
        sites["enwikiquote"] = {"site": "enwikiquote", "title": label, "badges": []}
    ent = {"type": "item", "id": f"Q{qid}", "labels": labels,
           "descriptions": {"en": {"language": "en", "value": desc}} if desc else {},
           "aliases": {"en": [{"language": "en", "value": a} for a in (aliases or [])]} if aliases else {},
           "claims": {}, "sitelinks": sites}
    for prop, values in (claims or {}).items():
        if prop in ("P569", "P570"):
            ent["claims"][prop] = [_snak_time(prop, v) for v in values]
        elif prop == "P18":
            ent["claims"][prop] = [_snak_string(prop, v) for v in values]
        else:
            ent["claims"][prop] = [_snak_item(prop, v) for v in values]
    return ent


def entities() -> list[dict]:
    E = []
    a = E.append
    # ---- classes (have P279)
    a(item(1000001, "fictional entity", claims={"P279": [35120]}))
    a(item(95074, "fictional character", claims={"P279": [1000001]}, sitelinks=30))
    a(item(15632617, "fictional human", claims={"P279": [95074]}, sitelinks=5))
    a(item(1000010, "anime character", claims={"P279": [95074]}, sitelinks=4))
    a(item(1000012, "fictional animal", claims={"P279": [95074]}, sitelinks=3))
    a(item(1000011, "fictional dog", claims={"P279": [1000012]}, sitelinks=2))
    a(item(1000013, "superhero", claims={"P279": [95074]}, sitelinks=40))
    a(item(1000014, "supernatural being", claims={"P279": [1000001]}))
    a(item(178885, "deity", claims={"P279": [1000014]}, sitelinks=60))
    a(item(1000015, "Hindu deity", claims={"P279": [178885]}, sitelinks=10))
    a(item(1000017, "hero", claims={"P279": [215627]}))
    a(item(1000016, "mythological hero", claims={"P279": [1000017]}, sitelinks=6))
    a(item(12737077, "occupation", claims={"P279": [1000002]}))
    a(item(483501, "artist", claims={"P279": [12737077]}))
    a(item(1000022, "athlete", claims={"P279": [12737077]}, sitelinks=50))
    a(item(1000020, "cricketer", claims={"P279": [1000022], "P641": [5375]}, sitelinks=30))
    a(item(937857, "association football player", claims={"P279": [1000022], "P641": [2736]}, sitelinks=40))
    a(item(33999, "actor", claims={"P279": [483501]}, sitelinks=80))
    a(item(1000023, "film actor", claims={"P279": [33999]}, sitelinks=40))
    a(item(639669, "musician", claims={"P279": [483501]}, sitelinks=70))
    a(item(177220, "singer", claims={"P279": [639669]}, sitelinks=70))
    a(item(36180, "writer", claims={"P279": [483501]}, sitelinks=90))
    a(item(1000026, "comics artist", claims={"P279": [483501]}, sitelinks=20))
    a(item(1000025, "mangaka", claims={"P279": [1000026]}, sitelinks=20))
    a(item(82955, "politician", claims={"P279": [12737077]}, sitelinks=90))
    a(item(169470, "physicist", claims={"P279": [12737077]}, sitelinks=60))
    a(item(5398426, "television series", claims={"P279": [1000003]}, sitelinks=60))
    a(item(63952888, "anime television series", claims={"P279": [5398426]}, sitelinks=5))
    a(item(1000089, "animated television series", claims={"P279": [5398426]}, sitelinks=8))
    a(item(11424, "film", claims={"P279": [1000003]}, sitelinks=100))
    a(item(7889, "video game", claims={"P279": [1000003]}, sitelinks=100))
    a(item(7725634, "literary work", claims={"P279": [1000003]}, sitelinks=40))
    a(item(8261, "novel", claims={"P279": [7725634]}, sitelinks=100))
    a(item(618779, "award", claims={"P279": [1000004]}, sitelinks=50))
    a(item(7191, "Nobel Prize", claims={"P279": [618779]}, sitelinks=100))
    a(item(38104, "Nobel Prize in Physics", claims={"P279": [7191]}, sitelinks=90))
    a(item(4164871, "position", claims={"P279": [1000004]}, sitelinks=10))
    a(item(14212, "prime minister", claims={"P279": [4164871]}, sitelinks=60))
    a(item(1000050, "Prime Minister of India", claims={"P279": [14212]}, sitelinks=60))
    # ---- countries, continents, sports, teams, languages (typed items)
    a(item(668, "India", claims={"P31": [6256], "P30": [48]}, sitelinks=200, extra_labels={"hi": "भारत"}))
    a(item(17, "Japan", claims={"P31": [6256], "P30": [48]}, sitelinks=200, extra_labels={"ja": "日本"}))
    a(item(30, "United States", claims={"P31": [6256], "P30": [49]}, sitelinks=200))
    a(item(145, "United Kingdom", claims={"P31": [6256], "P30": [46]}, sitelinks=200))
    a(item(183, "Germany", claims={"P31": [6256], "P30": [46]}, sitelinks=200))
    a(item(155, "Brazil", claims={"P31": [6256], "P30": [18]}, sitelinks=200))
    a(item(96, "Mexico", claims={"P31": [6256], "P30": [49]}, sitelinks=200))
    a(item(129286, "British Raj", claims={"P31": [3024240], "P1366": [668, 843]}, sitelinks=80))
    a(item(1000061, "Dominion of India", claims={"P31": [3024240], "P1366": [668]}, sitelinks=40))
    a(item(843, "Pakistan", claims={"P31": [6256], "P30": [48]}, sitelinks=200))
    a(item(5375, "cricket", claims={"P31": [31629]}, sitelinks=150, extra_labels={"hi": "क्रिकेट"}))
    a(item(2736, "association football", claims={"P31": [31629]}, sitelinks=200))
    a(item(1000070, "India national cricket team", claims={"P31": [12973014]}, sitelinks=40))
    a(item(1568, "Hindi", claims={"P31": [34770]}, sitelinks=150))
    # ---- works and franchises
    a(item(1000081, "Naruto", desc="Japanese media franchise", claims={"P31": [196600]}, sitelinks=30))
    a(item(1000080, "Naruto", desc="anime television series", sitelinks=60,
           claims={"P31": [63952888], "P495": [17], "P170": [1000090], "P8345": [1000081]}))
    a(item(1000083, "Harry Potter", desc="book series", claims={"P31": [277759]}, sitelinks=90))
    a(item(1000087, "Wizarding World", desc="fictional universe", claims={"P31": [559618]}, sitelinks=30))
    a(item(1000082, "Harry Potter and the Philosopher's Stone", sitelinks=80,
           claims={"P31": [8261], "P495": [145], "P50": [1000091], "P179": [1000083]}))
    a(item(1000085, "Spider-Man", desc="media franchise", claims={"P31": [196600]}, sitelinks=40))
    a(item(1000084, "Spider-Man: Homecoming", sitelinks=60,
           claims={"P31": [11424], "P495": [30], "P8345": [1000085]}))
    a(item(1000086, "Super Mario Bros.", sitelinks=70, claims={"P31": [7889], "P495": [17]}))
    a(item(1000088, "Scooby-Doo, Where Are You!", sitelinks=30, claims={"P31": [1000089], "P495": [30]}))
    a(item(1000110, "wall-crawling", desc="superpower", claims={"P31": [1047698]}, sitelinks=2))
    a(item(1000111, "black hair", claims={"P31": [1000112]}, sitelinks=5))
    # ---- fictional characters
    a(item(1000100, "Naruto Uzumaki", "protagonist of Naruto", sitelinks=18,
           claims={"P31": [1000010, 15632617], "P21": [6581097], "P1441": [1000080], "P1884": [1000111]},
           extra_labels={"ja": "うずまきナルト", "hi": "नारुतो उज़ुमाकी"}, aliases=["Naruto"]))
    a(item(1000101, "Harry Potter", "fictional wizard", sitelinks=20,
           claims={"P31": [15632617], "P21": [6581097], "P1441": [1000082], "P1080": [1000087],
                   "P175": [1000092], "P1884": [1000111]}))
    a(item(1000102, "Spider-Man", "Marvel Comics superhero", sitelinks=19,
           claims={"P31": [1000013, 15632617], "P21": [6581097], "P1441": [1000084], "P2563": [1000110],
                   "P175": [1000093], "P27": [30]}))
    a(item(1000103, "Mario", "Nintendo character", sitelinks=17,
           claims={"P31": [15632617], "P21": [6581097], "P1441": [1000086]}))
    a(item(1000104, "Scooby-Doo", "cartoon Great Dane", sitelinks=12,
           claims={"P31": [1000011], "P21": [44148], "P1441": [1000088]}))
    a(item(1000105, "Hanuman", "Hindu deity", sitelinks=16, claims={"P31": [1000015], "P21": [6581097]}))
    a(item(1000106, "Heracles", "hero of Greek mythology", sitelinks=17,
           claims={"P31": [1000016], "P21": [6581097]}))
    a(item(1000107, "Obscure Sidekick", "minor character", sitelinks=1, claims={"P31": [15632617]}))
    # ---- people
    def person(qid, name, sl, born, country, occ, gender=6581097, died=None, **more):
        claims = {"P31": [5], "P21": [gender], "P27": country, "P106": occ, "P569": [born]}
        if died:
            claims["P570"] = [died]
        claims.update(more)
        return item(qid, name, f"test person {name}", claims=claims, sitelinks=sl)
    a(person(1000090, "Masashi Kishimoto", 12, 1974, [17], [1000025]))
    a(person(1000091, "J. K. Rowling", 15, 1965, [145], [36180], gender=6581072))
    a(person(1000092, "Daniel Radcliffe", 14, 1989, [145], [1000023]))
    a(person(1000093, "Tom Holland", 13, 1996, [145], [1000023]))
    a(person(1000094, "Virat Kohli", 20, 1988, [668], [1000020], P54=[1000070], P1412=[1568],
             P18=["Virat Kohli 2019.jpg"]))
    a(person(1000095, "Mahatma Gandhi", 20, 1869, [129286, 1000061], [82955], died=1948))
    a(person(1000096, "Albert Einstein", 20, 1879, [183, 30], [169470], died=1955, P166=[38104]))
    a(person(1000097, "Pele", 19, 1940, [155], [937857], died=2022))
    a(person(1000098, "Narendra Modi", 20, 1950, [668], [82955], P39=[1000050]))
    a(person(1000099, "Child Actor", 9, 2015, [30], [1000023]))
    a(person(1000122, "Mexican Singer", 8, 1970, [96], [177220], gender=6581072))
    a(person(1000120, "Minor Footballer", 3, 1995, [155], [937857]))
    a(person(1000121, "Unknown Person", 1, 1990, [30], [33999]))
    # ---- noise
    a({"type": "item", "id": "Q1000200", "labels": {"en": {"language": "en", "value": "A scholarly article"}},
       "descriptions": {}, "aliases": {}, "claims": {"P31": [_snak_item("P31", 13442814)]}, "sitelinks": {}})
    a({"type": "property", "id": "P31", "labels": {"en": {"language": "en", "value": "instance of"}},
       "datatype": "wikibase-item", "claims": {}})
    return E


def write_dump(path: str) -> None:
    lines = [json.dumps(e, separators=(",", ":"), ensure_ascii=False) for e in entities()]
    body = "[\n" + ",\n".join(lines) + "\n]\n"
    opener = bz2.open if path.endswith(".bz2") else gzip.open if path.endswith(".gz") else open
    with opener(path, "wt", encoding="utf-8") as f:
        f.write(body)


def write_pageviews(path: str) -> None:
    """pageview_complete style text: wiki_code title page_id access count breakdown."""
    rows = [
        ("en.wikipedia", "Virat_Kohli", 1, "mobile-web", 900000),
        ("en.wikipedia", "Virat_Kohli", 1, "desktop", 100000),
        ("hi.wikipedia", "Virat_Kohli", 2, "mobile-web", 50000),
        ("en.wikipedia", "Harry_Potter", 3, "desktop", 400000),
        ("en.wikipedia", "Mahatma_Gandhi", 4, "desktop", 300000),
        ("en.wikipedia", "Child_Actor", 5, "desktop", 10),
        ("en.wikipedia", "Unrelated_Page", 6, "desktop", 999999),
        ("xx.wikipedia", "Virat_Kohli", 7, "desktop", 5),
    ]
    opener = bz2.open if path.endswith(".bz2") else open
    with opener(path, "wt", encoding="utf-8") as f:
        for w, t, pid, acc, n in rows:
            f.write(f"{w} {t} {pid} {acc} {n} A{n}\n")
