"""Helpers for reading one Wikidata entity (the JSON dump format)."""
from __future__ import annotations

import re

from .config import LANGS, MAX_ALIASES_PER_LANG, NON_WIKIPEDIA_SITES

_ID_RE = re.compile(rb'"id"\s*:\s*"([QPL])(\d+)"')


def peek_id(line: bytes) -> tuple[str, int] | None:
    """Read the entity id from the start of a dump line without parsing the JSON."""
    m = _ID_RE.search(line, 0, 200)
    if not m:
        return None
    return m.group(1).decode(), int(m.group(2))


def has_empty_sitelinks(line: bytes) -> bool:
    return b'"sitelinks":{}' in line or b'"sitelinks": {}' in line


def _statements(entity: dict, prop: str):
    for st in entity.get("claims", {}).get(prop, ()):
        if st.get("rank") == "deprecated":
            continue
        snak = st.get("mainsnak", {})
        if snak.get("snaktype") != "value":
            continue
        yield st, snak.get("datavalue", {}).get("value")


def item_ids(entity: dict, prop: str) -> list[int]:
    """Numeric ids of item-valued statements, preferred rank first, no duplicates."""
    preferred, normal = [], []
    for st, value in _statements(entity, prop):
        if not isinstance(value, dict):
            continue
        nid = value.get("numeric-id")
        if nid is None:
            vid = value.get("id", "")
            if not vid.startswith("Q"):
                continue
            nid = int(vid[1:])
        (preferred if st.get("rank") == "preferred" else normal).append(int(nid))
    out: list[int] = []
    for n in preferred + normal:
        if n not in out:
            out.append(n)
    return out


def year_of(entity: dict, prop: str) -> int | None:
    """Year from a time-valued statement such as P569 (date of birth). BCE years are negative.
    Values coarser than a century (precision < 7) are ignored."""
    best = None
    for st, value in _statements(entity, prop):
        if not isinstance(value, dict) or "time" not in value:
            continue
        if int(value.get("precision", 0)) < 7:
            continue
        t = value["time"]
        try:
            sign = -1 if t[0] == "-" else 1
            year = sign * int(t[1:].split("-", 1)[0])
        except (ValueError, IndexError):
            continue
        if st.get("rank") == "preferred":
            return year
        if best is None:
            best = year
    return best


def has_claim(entity: dict, prop: str) -> bool:
    """True if the property has a known or "unknown value" statement (e.g. an unknown death date)."""
    return any(st.get("rank") != "deprecated" and st.get("mainsnak", {}).get("snaktype") in ("value", "somevalue")
               for st in entity.get("claims", {}).get(prop, ()))


def string_value(entity: dict, prop: str) -> str | None:
    preferred = None
    for st, value in _statements(entity, prop):
        if isinstance(value, str):
            if st.get("rank") == "preferred":
                return value
            preferred = preferred or value
    return preferred


def wikipedia_sitelinks(entity: dict) -> dict[str, str]:
    out = {}
    for site, link in entity.get("sitelinks", {}).items():
        if site.endswith("wiki") and site not in NON_WIKIPEDIA_SITES:
            out[site] = link.get("title", "")
    return out


def labels(entity: dict) -> dict[str, str]:
    """Labels in the game's languages. Since 2024 many names live only under "mul"
    (one label for all languages); it fills in for English when English is missing."""
    lab = entity.get("labels", {})
    out = {lang: lab[lang]["value"] for lang in LANGS if lang in lab}
    if "en" not in out and "mul" in lab:
        out["en"] = lab["mul"]["value"]
    return out


def descriptions(entity: dict) -> dict[str, str]:
    des = entity.get("descriptions", {})
    return {lang: des[lang]["value"] for lang in LANGS if lang in des}


def aliases(entity: dict) -> dict[str, list[str]]:
    ali = entity.get("aliases", {})
    out = {lang: [a["value"] for a in ali[lang][:MAX_ALIASES_PER_LANG]] for lang in LANGS if lang in ali}
    if "mul" in ali:
        out.setdefault("en", [])
        out["en"].extend(a["value"] for a in ali["mul"][:MAX_ALIASES_PER_LANG] if a["value"] not in out["en"])
    return out


def english_label(entity: dict) -> str | None:
    lab = entity.get("labels", {})
    if "en" in lab:
        return lab["en"]["value"]
    for alt in ("en-gb", "en-us", "en-ca", "mul"):
        if alt in lab:
            return lab[alt]["value"]
    return None
