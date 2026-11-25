"""Rewrite generated questions into plain, friendly English and translate them into
Hindi, Spanish, Portuguese, Japanese, French and Arabic. The same call screens out
questions that are offensive, ambiguous or not answerable with yes or no.

40 questions per request. Results go to question_texts (origin 'llm', reviewed false);
rejected questions get status 'rejected' and a moderation_log entry with the reason.
Text written by people (origin 'human') is never replaced.
"""
from __future__ import annotations

import anthropic
import psycopg
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from psycopg.types.json import Jsonb

from . import config as C
from .llm_batch import collect as batch_collect
from .llm_batch import message_json, submit as batch_submit

PER_REQUEST = 40
TARGET_LANGS = [lang for lang in C.LANGS if lang != "en"]

SYSTEM = """You edit questions for a free family-friendly guessing game played worldwide. The player thinks of a \
famous real person or fictional character, and the game asks yes/no questions about "your character".

For each question you receive:
1. Rewrite it in plain, friendly English that a 12-year-old understands. Keep the meaning exactly. Keep it short \
(under 15 words when possible). Always refer to the person as "your character". Use the common English name of \
things (for example "American" instead of "from United States of America" is fine if the meaning stays the same).
2. Translate the rewritten question into Hindi (Devanagari), Spanish, Portuguese (Brazil), Japanese, French and \
Modern Standard Arabic. Translate naturally, as a native speaker would ask it. Keep proper names in their usual \
form in each language.
3. Set "keep" to false, with a short "reason", if the question is offensive, sexual, about religion, ethnicity, \
health or sexual orientation, cannot be answered with yes or no, or is too vague to answer. Otherwise "keep" is \
true and "reason" is an empty string.

Return one item per input question, with the same id."""

SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "keep": {"type": "boolean"},
                    "reason": {"type": "string"},
                    "en": {"type": "string"},
                    **{lang: {"type": "string"} for lang in TARGET_LANGS},
                },
                "required": ["id", "keep", "reason", "en", *TARGET_LANGS],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


def pending_questions(dsn: str) -> list[tuple[int, str]]:
    """Active questions whose translations are not all present yet."""
    sql = """
        SELECT q.id, t.text FROM questions q JOIN question_texts t ON t.question_id = q.id AND t.lang = 'en'
        WHERE q.status = 'active'
          AND (SELECT count(*) FROM question_texts x WHERE x.question_id = q.id AND x.lang <> 'en') < %s
        ORDER BY q.id"""
    with psycopg.connect(dsn) as conn:
        return conn.execute(sql, (len(TARGET_LANGS),)).fetchall()


def build_requests(questions: list[tuple[int, str]], model: str):
    system = [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}]
    for start in range(0, len(questions), PER_REQUEST):
        chunk = questions[start:start + PER_REQUEST]
        body = "\n".join(f"{qid}: {text}" for qid, text in chunk)
        yield f"q{chunk[0][0]}_{len(chunk)}", MessageCreateParamsNonStreaming(
            model=model,
            max_tokens=32000,
            system=system,
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": f"Questions (id: text):\n{body}"}],
        )


def submit(dsn: str, state_path: str, model: str = C.I18N_MODEL, client: anthropic.Anthropic | None = None) -> list[str]:
    return batch_submit(client or anthropic.Anthropic(), build_requests(pending_questions(dsn), model), state_path)


def collect(dsn: str, state_path: str, client: anthropic.Anthropic | None = None, wait: bool = True) -> dict:
    texts: list[tuple] = []
    rejected: list[tuple[int, str]] = []

    def handle(custom_id: str, msg) -> None:
        for item in message_json(msg)["items"]:
            if not item["keep"]:
                rejected.append((item["id"], item["reason"]))
                continue
            for lang in ["en", *TARGET_LANGS]:
                if item.get(lang):
                    texts.append((item["id"], lang, item[lang].strip()))

    counts = batch_collect(client or anthropic.Anthropic(), state_path, handle, wait=wait)
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.executemany("""
            INSERT INTO question_texts (question_id, lang, text, origin, reviewed)
            SELECT %s, %s, %s, 'llm', false WHERE EXISTS (SELECT 1 FROM questions WHERE id = %s)
            ON CONFLICT (question_id, lang) DO UPDATE SET text = EXCLUDED.text, origin = 'llm', reviewed = false
              WHERE question_texts.origin <> 'human'
        """, [(q, lang, text, q) for q, lang, text in texts])
        for qid, reason in rejected:
            cur.execute("UPDATE questions SET status = 'rejected', updated_at = now() WHERE id = %s AND source <> 'admin'",
                        (qid,))
            cur.execute("INSERT INTO moderation_log (moderator, action, target, details) VALUES (%s, %s, %s, %s)",
                        ("llm-screen", "reject_question", f"question:{qid}", Jsonb({"reason": reason})))
    counts["texts_written"] = len(texts)
    counts["questions_rejected"] = len(rejected)
    return counts
