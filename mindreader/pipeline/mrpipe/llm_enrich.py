"""Fill trait questions (data/trait_questions.json) for the most popular characters with an LLM.

Wikidata says where a character is from and what they do; it rarely says whether they
wear glasses or can fly. For the top ENRICH_TOP_N characters by popularity, one batch
request per character asks the model to answer every trait in its scope. Answers become
explicit cells in `facts` (source 'llm') with a modest weight, so player answers
outweigh them after a few games.

Commands (see cli.py): `enrich estimate`, `enrich submit`, `enrich collect`.
"""
from __future__ import annotations

import json
import os

import anthropic
import psycopg
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming

from . import config as C
from .llm_batch import collect as batch_collect
from .llm_batch import message_json, submit as batch_submit

ANSWER_P = {"yes": 0.92, "probably": 0.72, "probably_not": 0.28, "no": 0.08}
LLM_WEIGHT = 3.0          # pseudo-answers; a seeded Wikidata fact is worth more, a player game is worth 1
FACT_GROUPS = ("occupation", "country", "franchise", "work", "medium", "char_type", "creator", "position", "team")

SYSTEM_PROMPT = """You fill in a knowledge base for a character guessing game. Players think of a famous real \
person or fictional character and answer yes/no questions about them. For the character given, answer each trait \
the way a typical player who knows the character would answer it.

Rules:
- "yes" or "no" when the answer is clear and well known.
- "probably" or "probably_not" when it is mostly true or mostly false, or true only in some versions.
- "unsure" when you do not know, or when players would genuinely disagree.
- For appearance, answer for the character's best-known look.
- For real people, answer from public, widely reported facts only. Never guess private details.
- If you do not recognise the character at all, set "known" to false and answer "unsure" everywhere.

Traits (key: question):
{traits}"""


def load_traits() -> list[dict]:
    with open(os.path.join(os.path.dirname(__file__), "..", "data", "trait_questions.json")) as f:
        return json.load(f)["traits"]


def traits_for(kind: str, traits: list[dict]) -> list[dict]:
    return [t for t in traits if t["scope"] in ("all", kind)]


def schema_for(trait_list: list[dict]) -> dict:
    enum = ["yes", "probably", "unsure", "probably_not", "no"]
    return {
        "type": "object",
        "properties": {
            "known": {"type": "boolean"},
            "answers": {
                "type": "object",
                "properties": {t["key"]: {"type": "string", "enum": enum} for t in trait_list},
                "required": [t["key"] for t in trait_list],
                "additionalProperties": False,
            },
        },
        "required": ["known", "answers"],
        "additionalProperties": False,
    }


def system_for(trait_list: list[dict]) -> list[dict]:
    lines = "\n".join(f"{t['key']}: {t['text']}" for t in trait_list)
    return [{"type": "text", "text": SYSTEM_PROMPT.format(traits=lines), "cache_control": {"type": "ephemeral"}}]


def select_characters(dsn: str, top_n: int) -> list[dict]:
    """Top characters by popularity that have no LLM facts yet, with a short fact summary."""
    sql = """
        WITH top AS (
          SELECT e.id, e.kind FROM entities e
          WHERE e.status = 'active' AND NOT EXISTS (SELECT 1 FROM facts f WHERE f.entity_id = e.id AND f.source = 'llm')
          ORDER BY e.popularity DESC, e.id LIMIT %s)
        SELECT t.id, t.kind, l.label, l.description,
               (SELECT string_agg(g.key || ': ' || vl.label, '; ' ORDER BY g.id, vl.label)
                FROM entity_attrs a JOIN attr_values av ON av.id = a.value_id
                JOIN attr_groups g ON g.id = av.group_id
                JOIN attr_value_labels vl ON vl.value_id = av.id AND vl.lang = 'en'
                WHERE a.entity_id = t.id AND g.key = ANY(%s)) AS facts
        FROM top t JOIN entity_labels l ON l.entity_id = t.id AND l.lang = 'en'
        ORDER BY t.id"""
    with psycopg.connect(dsn) as conn:
        rows = conn.execute(sql, (top_n, list(FACT_GROUPS))).fetchall()
    return [{"id": r[0], "kind": r[1], "name": r[2], "description": r[3] or "", "facts": (r[4] or "")[:600]}
            for r in rows]


def build_requests(chars: list[dict], traits: list[dict], model: str):
    per_kind = {k: (system_for(traits_for(k, traits)), schema_for(traits_for(k, traits))) for k in ("real", "fictional")}
    for ch in chars:
        system, schema = per_kind[ch["kind"]]
        kind_text = "real person" if ch["kind"] == "real" else "fictional character"
        user = (f"Character: {ch['name']}\nType: {kind_text}\nDescription: {ch['description']}\n"
                f"Known facts: {ch['facts'] or 'none'}")
        yield f"e{ch['id']}", MessageCreateParamsNonStreaming(
            model=model,
            max_tokens=8000,
            system=system,
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": user}],
        )


def estimate(chars: list[dict], traits: list[dict]) -> dict:
    """Rough cost at Claude Haiku 5.5 batch prices (50% off $0.10 / $0.50 per million tokens)."""
    sys_tokens = {k: len(system_for(traits_for(k, traits))[0]["text"]) // 4 for k in ("real", "fictional")}
    n_traits = {k: len(traits_for(k, traits)) for k in ("real", "fictional")}
    inp = sum(sys_tokens[c["kind"]] + 80 + len(c["facts"]) // 4 for c in chars)
    out = sum(n_traits[c["kind"]] * 9 + 300 for c in chars)
    cost = inp / 1e6 * 0.05 + out / 1e6 * 0.25
    return {"characters": len(chars), "input_tokens": inp, "output_tokens_est": out,
            "usd_without_cache": round(cost, 2),
            "note": "Estimate only: thinking tokens vary. Cached system prompts make input cheaper."}


def submit(dsn: str, state_path: str, top_n: int = C.ENRICH_TOP_N, model: str = C.ENRICH_MODEL,
           client: anthropic.Anthropic | None = None) -> list[str]:
    chars = select_characters(dsn, top_n)
    return batch_submit(client or anthropic.Anthropic(), build_requests(chars, load_traits(), model), state_path)


def collect(dsn: str, state_path: str, model: str = C.ENRICH_MODEL, client: anthropic.Anthropic | None = None,
            wait: bool = True) -> dict:
    with psycopg.connect(dsn) as conn:
        qids = dict(conn.execute("SELECT key, id FROM questions WHERE kind = 'trait'").fetchall())
    rows: list[tuple] = []
    unknown = 0

    def handle(custom_id: str, msg) -> None:
        nonlocal unknown
        data = message_json(msg)
        entity = int(custom_id[1:])
        if not data.get("known", False):
            unknown += 1
            return
        for key, answer in data["answers"].items():
            p = ANSWER_P.get(answer)
            qid = qids.get(f"trait:{key}")
            if p is None or qid is None:
                continue
            rows.append((entity, qid, round(p * LLM_WEIGHT, 3), round((1 - p) * LLM_WEIGHT, 3), model))

    counts = batch_collect(client or anthropic.Anthropic(), state_path, handle, wait=wait)
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.executemany("""
            INSERT INTO facts (entity_id, question_id, yes_w, no_w, source, model)
            VALUES (%s, %s, %s, %s, 'llm', %s)
            ON CONFLICT (entity_id, question_id, source) DO UPDATE
              SET yes_w = EXCLUDED.yes_w, no_w = EXCLUDED.no_w, model = EXCLUDED.model, updated_at = now()
        """, rows)
    counts["facts_written"] = len(rows)
    counts["characters_unknown_to_model"] = unknown
    return counts
