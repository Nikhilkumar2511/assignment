"""Stream a Wikidata JSON dump and process it with a pool of worker processes.

The dump is one JSON array with one entity per line. Decompression runs in an
external program when one is installed (lbzip2 and pigz decompress much faster than
Python's bz2 and gzip modules); the main process splits the stream into chunks of
lines; each worker parses its chunks and writes its own Parquet part files.
"""
from __future__ import annotations

import bz2
import gzip
import io
import multiprocessing as mp
import os
import shutil
import subprocess
import sys
import time
from typing import Callable, Iterator

import pyarrow as pa
import pyarrow.parquet as pq

CHUNK_LINES = 2000
FLUSH_ROWS = 20000


def open_dump(path: str) -> tuple[io.BufferedIOBase, subprocess.Popen | None]:
    """Binary stream of the decompressed dump, plus the helper process if one was started."""
    if path.endswith(".bz2"):
        for tool in ("lbzip2", "pbzip2"):
            exe = shutil.which(tool)
            if exe:
                proc = subprocess.Popen([exe, "-dc", path], stdout=subprocess.PIPE, bufsize=1 << 20)
                return proc.stdout, proc
        return bz2.open(path, "rb"), None
    if path.endswith(".gz"):
        exe = shutil.which("pigz")
        if exe:
            proc = subprocess.Popen([exe, "-dc", path], stdout=subprocess.PIPE, bufsize=1 << 20)
            return proc.stdout, proc
        return gzip.open(path, "rb"), None
    return open(path, "rb"), None


def iter_chunks(stream: io.BufferedIOBase, limit: int | None = None) -> Iterator[list[bytes]]:
    """Lists of entity lines with the array brackets and trailing commas removed."""
    chunk: list[bytes] = []
    n = 0
    for raw in stream:
        line = raw.strip()
        if line in (b"[", b"]", b""):
            continue
        if line.endswith(b","):
            line = line[:-1]
        chunk.append(line)
        n += 1
        if len(chunk) >= CHUNK_LINES:
            yield chunk
            chunk = []
        if limit is not None and n >= limit:
            break
    if chunk:
        yield chunk


class PartWriter:
    """Buffers rows for several tables and writes numbered Parquet part files."""

    def __init__(self, out_dir: str, worker_id: int, schemas: dict[str, pa.Schema]):
        self.out_dir, self.worker_id, self.schemas = out_dir, worker_id, schemas
        self.rows: dict[str, list[dict]] = {name: [] for name in schemas}
        self.part = 0

    def add(self, table: str, row: dict) -> None:
        buf = self.rows[table]
        buf.append(row)
        if len(buf) >= FLUSH_ROWS:
            self.flush(table)

    def flush(self, table: str) -> None:
        buf = self.rows[table]
        if not buf:
            return
        os.makedirs(os.path.join(self.out_dir, table), exist_ok=True)
        tbl = pa.Table.from_pylist(buf, schema=self.schemas[table])
        pq.write_table(tbl, os.path.join(self.out_dir, table, f"w{self.worker_id:02d}-{self.part:05d}.parquet"),
                       compression="zstd")
        self.part += 1
        buf.clear()

    def close(self) -> None:
        for name in self.rows:
            self.flush(name)


def _worker(worker_id: int, queue: mp.Queue, counts: mp.Queue, out_dir: str,
            schemas: dict[str, pa.Schema], handler: Callable, handler_args: tuple) -> None:
    writer = PartWriter(out_dir, worker_id, schemas)
    seen = kept = 0
    error = None
    while True:
        chunk = queue.get()
        if chunk is None:
            break
        if error is not None:
            continue                      # keep draining so the reader never blocks
        try:
            for line in chunk:
                seen += 1
                kept += handler(line, writer, handler_args)
        except Exception:
            import traceback
            error = traceback.format_exc()
    if error is None:
        writer.close()
    counts.put((seen, kept, error))


def run_parallel(dump_path: str, out_dir: str, schemas: dict[str, pa.Schema], handler: Callable,
                 handler_args: tuple = (), workers: int | None = None, limit: int | None = None,
                 progress_every: float = 60.0) -> dict:
    """Feed the dump to `handler(line, writer, handler_args) -> 1 if kept else 0` in parallel."""
    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    ctx = mp.get_context("fork" if sys.platform != "win32" else "spawn")
    queue: mp.Queue = ctx.Queue(maxsize=workers * 4)
    counts: mp.Queue = ctx.Queue()
    procs = [ctx.Process(target=_worker, args=(i, queue, counts, out_dir, schemas, handler, handler_args))
             for i in range(workers)]
    for p in procs:
        p.start()
    stream, helper = open_dump(dump_path)
    started = last = time.time()
    lines = 0
    try:
        for chunk in iter_chunks(stream, limit):
            queue.put(chunk)
            lines += len(chunk)
            if time.time() - last > progress_every:
                last = time.time()
                rate = lines / (last - started)
                print(f"  {lines:,} entities read, {rate:,.0f}/s", flush=True)
    finally:
        for _ in procs:
            queue.put(None)
        stream.close()
        if helper:
            helper.wait()
    seen = kept = 0
    errors = []
    for _ in procs:
        s, k, err = counts.get()
        seen += s
        kept += k
        if err:
            errors.append(err)
    for p in procs:
        p.join()
        if p.exitcode != 0:
            raise RuntimeError(f"worker exited with code {p.exitcode}")
    if errors:
        raise RuntimeError("a worker failed:\n" + errors[0])
    return {"entities_read": seen, "entities_kept": kept, "seconds": round(time.time() - started, 1)}
