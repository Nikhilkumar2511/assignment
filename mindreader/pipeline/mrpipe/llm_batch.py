"""Shared Message Batches plumbing: submit in chunks, remember batch ids, collect results.

Batch state is kept in a JSON file so a run can be stopped and resumed:
    {"batches": [{"id": "msgbatch_...", "collected": false}, ...]}
"""
from __future__ import annotations

import json
import os
import time
from typing import Callable, Iterable

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

MAX_REQUESTS_PER_BATCH = 10_000


def load_state(path: str) -> dict:
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"batches": []}


def save_state(path: str, state: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, path)


def submit(client: anthropic.Anthropic, requests: Iterable[tuple[str, MessageCreateParamsNonStreaming]],
           state_path: str) -> list[str]:
    """Create batches of at most MAX_REQUESTS_PER_BATCH requests. Returns new batch ids."""
    state = load_state(state_path)
    ids, chunk = [], []

    def flush() -> None:
        if not chunk:
            return
        batch = client.messages.batches.create(requests=[Request(custom_id=cid, params=p) for cid, p in chunk])
        state["batches"].append({"id": batch.id, "collected": False, "size": len(chunk)})
        save_state(state_path, state)
        ids.append(batch.id)
        chunk.clear()

    for cid, params in requests:
        chunk.append((cid, params))
        if len(chunk) >= MAX_REQUESTS_PER_BATCH:
            flush()
    flush()
    return ids


def collect(client: anthropic.Anthropic, state_path: str, handle: Callable[[str, object], None],
            wait: bool = True, poll_seconds: int = 60) -> dict:
    """Call handle(custom_id, message) for each succeeded request of every uncollected batch.
    Returns counts per result type. Errored and expired requests are counted, not retried."""
    state = load_state(state_path)
    counts: dict[str, int] = {}
    for entry in state["batches"]:
        if entry["collected"]:
            continue
        while True:
            batch = client.messages.batches.retrieve(entry["id"])
            if batch.processing_status == "ended":
                break
            if not wait:
                counts["pending_batches"] = counts.get("pending_batches", 0) + 1
                break
            time.sleep(poll_seconds)
        if batch.processing_status != "ended":
            continue
        for result in client.messages.batches.results(entry["id"]):
            kind = result.result.type
            if kind == "succeeded":
                msg = result.result.message
                if msg.stop_reason == "refusal":
                    kind = "refused"
                elif msg.stop_reason == "max_tokens":
                    kind = "truncated"
                else:
                    handle(result.custom_id, msg)
            counts[kind] = counts.get(kind, 0) + 1
        entry["collected"] = True
        save_state(state_path, state)
    return counts


def message_json(msg) -> dict:
    """The JSON object from a structured-output response."""
    text = next(b.text for b in msg.content if b.type == "text")
    return json.loads(text)
