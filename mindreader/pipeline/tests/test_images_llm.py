"""Image licensing and the two LLM steps, with the network and the API replaced by fakes."""
from __future__ import annotations

import io
import json
import os
from types import SimpleNamespace

import httpx
import psycopg
import pyarrow as pa
import pyarrow.parquet as pq
from PIL import Image

from mrpipe import config as C, images, llm_enrich, llm_i18n


def png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (800, 1000), (200, 50, 50)).save(buf, "PNG")
    return buf.getvalue()


def seed_entities(dsn: str) -> None:
    with psycopg.connect(dsn) as c:
        c.execute("""INSERT INTO entities (id, kind, sitelinks, popularity, is_minor) VALUES
                     (1, 'real', 50, 9, false), (2, 'real', 40, 8, false), (3, 'real', 30, 7, true),
                     (4, 'fictional', 20, 6, false), (5, 'real', 10, 5, false)""")
        c.execute("""INSERT INTO entity_labels (entity_id, lang, label, description) VALUES
                     (1, 'en', 'Free Photo Person', 'actor'), (2, 'en', 'NC Photo Person', 'singer'),
                     (3, 'en', 'Young Person', 'child actor'), (4, 'en', 'Cartoon Hero', 'cartoon'),
                     (5, 'en', 'Missing File Person', 'writer')""")


def commons_transport() -> httpx.MockTransport:
    meta = {
        "Free.jpg": {"LicenseShortName": "CC BY-SA 4.0", "License": "cc-by-sa-4.0",
                     "Artist": '<a href="//commons.wikimedia.org/wiki/User:X">Jane <b>Photographer</b></a>',
                     "LicenseUrl": "https://creativecommons.org/licenses/by-sa/4.0"},
        "Nc.jpg": {"LicenseShortName": "CC BY-NC 2.0", "License": "cc-by-nc-2.0", "Artist": "Someone"},
        "Kid.jpg": {"LicenseShortName": "CC0", "License": "cc0", "Artist": "Parent"},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "upload.example.org":
            return httpx.Response(200, content=png_bytes(), headers={"content-type": "image/png"})
        titles = request.url.params["titles"].split("|")
        pages = []
        for t in titles:
            name = t.removeprefix("File:")
            if name not in meta:
                pages.append({"title": t, "missing": True})
                continue
            pages.append({"title": t, "imageinfo": [{
                "url": f"https://upload.example.org/{name}", "thumburl": f"https://upload.example.org/512px-{name}",
                "descriptionurl": f"https://commons.wikimedia.org/wiki/File:{name}", "mime": "image/jpeg",
                "width": 800, "height": 1000, "sha1": "abc",
                "extmetadata": {k: {"value": v} for k, v in meta[name].items()}}]})
        assert request.headers["user-agent"].startswith("MindReaderPipeline")
        return httpx.Response(200, json={"query": {"pages": pages}})

    return httpx.MockTransport(handler)


def test_images(tmp_path, fresh_db):
    seed_entities(fresh_db)
    paths = C.Paths(str(tmp_path / "work")).ensure()
    pq.write_table(pa.table({"qid": pa.array([1, 2, 3, 5], pa.int64()),
                             "file": ["Free.jpg", "Nc.jpg", "Kid.jpg", "Gone.jpg"]}),
                   paths.p("build", "images_wanted.parquet"))
    client = httpx.Client(transport=commons_transport(), headers={"User-Agent": C.USER_AGENT})
    out = images.run(paths, fresh_db, commons=images.Commons(client, requests_per_second=1000))
    assert out == {"requested": 4, "ok": 1, "rejected_license": 1, "rejected_minor": 1, "failed": 1}
    for size in (256, 512):
        for ext in ("webp", "avif"):
            f = paths.p("images", f"img/1-{size}.{ext}")
            assert os.path.exists(f)
            assert max(Image.open(f).size) == size
    with psycopg.connect(fresh_db) as c:
        row = c.execute("SELECT status, license_short, author, storage_prefix FROM images WHERE entity_id = 1").fetchone()
        assert row == ("ok", "CC BY-SA 4.0", "Jane Photographer", "img/1")
    # A second run only fetches what changed.
    again = images.run(paths, fresh_db, commons=images.Commons(client, requests_per_second=1000))
    assert again == {"requested": 1, "failed": 1}      # only the failed download is retried


class FakeBatches:
    """Stands in for client.messages.batches: answers each request with `responder(params)`."""

    def __init__(self, responder):
        self.responder, self.batches = responder, {}

    def create(self, requests):
        bid = f"msgbatch_{len(self.batches)}"
        self.batches[bid] = list(requests)
        return SimpleNamespace(id=bid, processing_status="in_progress")

    def retrieve(self, bid):
        return SimpleNamespace(id=bid, processing_status="ended")

    def results(self, bid):
        for req in self.batches[bid]:
            text, stop = self.responder(req["params"])
            msg = SimpleNamespace(stop_reason=stop, content=[SimpleNamespace(type="text", text=text)])
            yield SimpleNamespace(custom_id=req["custom_id"], result=SimpleNamespace(type="succeeded", message=msg))


def fake_client(responder):
    return SimpleNamespace(messages=SimpleNamespace(batches=FakeBatches(responder)))


def test_enrich(tmp_path, fresh_db):
    seed_entities(fresh_db)
    traits = llm_enrich.load_traits()
    with psycopg.connect(fresh_db) as c:
        for t in traits:
            c.execute("INSERT INTO questions (key, kind, scope, status, source) VALUES (%s, 'trait', %s, 'active', 'trait')",
                      (f"trait:{t['key']}", t["scope"]))
    seen_params = []

    def responder(params):
        seen_params.append(params)
        user = params["messages"][0]["content"]
        props = params["output_config"]["format"]["schema"]["properties"]["answers"]["properties"]
        if "Missing File Person" in user:
            return json.dumps({"known": False, "answers": {k: "unsure" for k in props}}), "end_turn"
        if "Young Person" in user:
            return "", "refusal"
        answers = {k: "unsure" for k in props}
        answers["wears_glasses"] = "yes"
        answers["has_beard"] = "no"
        return json.dumps({"known": True, "answers": answers}), "end_turn"

    client = fake_client(responder)
    state = str(tmp_path / "llm" / "enrich.json")
    chars = llm_enrich.select_characters(fresh_db, 10)
    assert [ch["id"] for ch in chars] == [1, 2, 3, 4, 5]
    est = llm_enrich.estimate(chars, traits)
    assert est["characters"] == 5 and est["usd_without_cache"] < 0.05
    llm_enrich.submit(fresh_db, state, top_n=10, client=client)
    p = seen_params[0] if seen_params else client.messages.batches.batches["msgbatch_0"][0]["params"]
    assert p["model"] == "claude-haiku-5-5" and p["output_config"]["effort"] == "low"
    assert p["system"][0]["cache_control"] == {"type": "ephemeral"}
    out = llm_enrich.collect(fresh_db, state, client=client)
    assert out["refused"] == 1 and out["characters_unknown_to_model"] == 1
    assert out["facts_written"] == 6               # 3 known characters x 2 non-unsure answers
    fict_req = next(r for r in client.messages.batches.batches["msgbatch_0"] if r["custom_id"] == "e4")
    fict_traits = fict_req["params"]["output_config"]["format"]["schema"]["properties"]["answers"]["properties"]
    assert "can_fly" in fict_traits and "billionaire" not in fict_traits
    with psycopg.connect(fresh_db) as c:
        yes_w, no_w = c.execute("""SELECT f.yes_w, f.no_w FROM facts f JOIN questions q ON q.id = f.question_id
                                   WHERE f.entity_id = 1 AND q.key = 'trait:wears_glasses'""").fetchone()
        assert abs(yes_w / (yes_w + no_w) - 0.92) < 1e-3
    # Characters with LLM facts are not selected again.
    assert {ch["id"] for ch in llm_enrich.select_characters(fresh_db, 10)} == {3, 5}


def test_i18n(tmp_path, fresh_db):
    with psycopg.connect(fresh_db) as c:
        for i, text in enumerate(["Is your character from United States?", "Is your character a member of X?",
                                  "Is your character a fan of something offensive?"]):
            qid = c.execute("INSERT INTO questions (key, kind, scope, status, source) VALUES (%s, 'trait', 'all', "
                            "'active', 'trait') RETURNING id", (f"trait:t{i}",)).fetchone()[0]
            c.execute("INSERT INTO question_texts (question_id, lang, text, origin) VALUES (%s, 'en', %s, 'template')",
                      (qid, text))
        human_q = qid - 1
        c.execute("INSERT INTO question_texts (question_id, lang, text, origin) VALUES (%s, 'hi', 'मानव अनुवाद', 'human')",
                  (human_q,))

    def responder(params):
        lines = params["messages"][0]["content"].split("\n")[1:]
        items = []
        for line in lines:
            qid = int(line.split(":")[0])
            keep = "offensive" not in line
            items.append({"id": qid, "keep": keep, "reason": "" if keep else "offensive", "en": f"Q{qid} plain?",
                          **{lang: f"{lang}-{qid}" for lang in llm_i18n.TARGET_LANGS}})
        return json.dumps({"items": items}), "end_turn"

    client = fake_client(responder)
    state = str(tmp_path / "llm" / "i18n.json")
    assert len(llm_i18n.pending_questions(fresh_db)) == 3
    llm_i18n.submit(fresh_db, state, client=client)
    req = client.messages.batches.batches["msgbatch_0"][0]
    assert req["params"]["model"] == "claude-opus-5-5"
    out = llm_i18n.collect(fresh_db, state, client=client)
    assert out["questions_rejected"] == 1 and out["texts_written"] == 14
    with psycopg.connect(fresh_db) as c:
        assert c.execute("SELECT count(*) FROM questions WHERE status = 'rejected'").fetchone()[0] == 1
        assert c.execute("SELECT text FROM question_texts WHERE question_id = %s AND lang = 'hi'",
                         (human_q,)).fetchone()[0] == "मानव अनुवाद"          # human text survives
        assert c.execute("SELECT text FROM question_texts WHERE question_id = %s AND lang = 'ja'",
                         (human_q,)).fetchone()[0] == f"ja-{human_q}"
        assert c.execute("SELECT count(*) FROM moderation_log WHERE action = 'reject_question'").fetchone()[0] == 1
    assert llm_i18n.pending_questions(fresh_db) == []
