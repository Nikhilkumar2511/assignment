"""Fetch character photos from Wikimedia Commons, keep only reusable licences, and make
256 px and 512 px WebP and AVIF thumbnails.

* Metadata comes from the Commons API (imageinfo + extmetadata), 50 files per request.
* Allowed licences: CC0, public domain, CC BY, CC BY-SA (any version). Anything with
  NC (non-commercial), ND (no derivatives), "fair use" or "non-free" is rejected.
* Minors never get a photo (they are excluded upstream and checked again here).
* Files are written to a local folder (sync it to R2 or any S3 bucket with rclone or
  `aws s3 sync`), and the result is upserted into the `images` table.
"""
from __future__ import annotations

import html
import io
import os
import re
import time
from dataclasses import dataclass

import duckdb
import httpx
import psycopg
from PIL import Image

from . import config as C

API = "https://commons.wikimedia.org/w/api.php"
SIZES = (256, 512)
ALLOWED = re.compile(r"^(cc0|cc[- ]?zero|public domain|pd\b|pd-|cc[- ]by([- ]sa)?[- ]?\d|cc[- ]by([- ]sa)?$)", re.I)
FORBIDDEN = re.compile(r"\b(nc|nd|non[- ]?commercial|no[- ]?deriv|fair use|non[- ]?free|all rights reserved)\b", re.I)


@dataclass
class ImageResult:
    qid: int
    file: str
    status: str
    license_short: str | None = None
    license_url: str | None = None
    author: str | None = None
    credit_url: str | None = None
    restrictions: str | None = None
    width: int | None = None
    height: int | None = None
    sha1: str | None = None
    storage_prefix: str | None = None


def license_ok(short: str | None, code: str | None) -> bool:
    for value in (short or "", code or ""):
        if FORBIDDEN.search(value):
            return False
    return bool(ALLOWED.search((short or "").strip()) or ALLOWED.search((code or "").strip()))


def plain_text(markup: str | None, limit: int = 200) -> str | None:
    if not markup:
        return None
    text = html.unescape(re.sub(r"<[^>]+>", " ", markup))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit] or None


class Commons:
    def __init__(self, client: httpx.Client | None = None, requests_per_second: float = 5.0):
        self.client = client or httpx.Client(headers={"User-Agent": C.USER_AGENT}, timeout=30.0,
                                             follow_redirects=True)
        self.min_interval = 1.0 / requests_per_second
        self._last = 0.0

    def _get(self, url: str, params: dict | None = None) -> httpx.Response:
        for attempt in range(5):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            resp = self.client.get(url, params=params)
            if resp.status_code in (429, 500, 502, 503, 504):
                time.sleep(float(resp.headers.get("retry-after", 2 ** attempt)))
                continue
            resp.raise_for_status()
            return resp
        resp.raise_for_status()
        return resp

    def metadata(self, files: list[str]) -> dict[str, dict]:
        """File name (without 'File:') -> imageinfo dict, for up to 50 files."""
        titles = "|".join(f"File:{f}" for f in files)
        data = self._get(API, {"action": "query", "format": "json", "formatversion": "2", "prop": "imageinfo",
                               "iiprop": "url|size|sha1|mime|extmetadata", "iiurlwidth": "512",
                               "titles": titles, "maxlag": "5"}).json()
        query = data.get("query", {})
        rename = {n["to"]: n["from"] for n in query.get("normalized", [])}
        out = {}
        for page in query.get("pages", []):
            info = (page.get("imageinfo") or [None])[0]
            original = rename.get(page["title"], page["title"])
            out[original.removeprefix("File:")] = info
        return out

    def download(self, url: str) -> bytes:
        return self._get(url).content


def make_thumbnails(data: bytes, out_dir: str, qid: int) -> tuple[str, int, int]:
    img = Image.open(io.BytesIO(data))
    img.load()
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
    width, height = img.size
    prefix = f"img/{qid}"
    os.makedirs(os.path.join(out_dir, "img"), exist_ok=True)
    for size in SIZES:
        thumb = img.copy()
        thumb.thumbnail((size, size), Image.LANCZOS)
        thumb.save(os.path.join(out_dir, f"{prefix}-{size}.webp"), "WEBP", quality=80, method=5)
        thumb.save(os.path.join(out_dir, f"{prefix}-{size}.avif"), "AVIF", quality=55)
    return prefix, width, height


def process(rows: list[tuple[int, str]], out_dir: str, commons: Commons, minors: set[int]) -> list[ImageResult]:
    results = []
    for start in range(0, len(rows), 50):
        batch = rows[start:start + 50]
        meta = commons.metadata([f for _, f in batch])
        for qid, file in batch:
            if qid in minors:
                results.append(ImageResult(qid, file, "rejected_minor"))
                continue
            info = meta.get(file) or meta.get(file.replace("_", " "))
            if not info:
                results.append(ImageResult(qid, file, "failed"))
                continue
            em = info.get("extmetadata", {})
            val = lambda k: (em.get(k) or {}).get("value")  # noqa: E731
            short, code = val("LicenseShortName"), val("License")
            res = ImageResult(qid, file, "rejected_license", license_short=plain_text(short, 60),
                              license_url=val("LicenseUrl"), author=plain_text(val("Artist")),
                              credit_url=info.get("descriptionurl"), restrictions=plain_text(val("Restrictions"), 100),
                              sha1=info.get("sha1"))
            if not license_ok(short, code) or not str(info.get("mime", "")).startswith("image/"):
                results.append(res)
                continue
            try:
                data = commons.download(info.get("thumburl") or info["url"])
                res.storage_prefix, res.width, res.height = make_thumbnails(data, out_dir, qid)
                res.status = "ok"
            except (httpx.HTTPError, OSError, ValueError):
                res.status = "failed"
            results.append(res)
    return results


def save(results: list[ImageResult], dsn: str) -> None:
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        for r in results:
            cur.execute("""
                INSERT INTO images (entity_id, commons_file, status, license_short, license_url, author, credit_url,
                                    restrictions, width, height, sha1, storage_prefix, fetched_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (entity_id) DO UPDATE SET commons_file = EXCLUDED.commons_file, status = EXCLUDED.status,
                  license_short = EXCLUDED.license_short, license_url = EXCLUDED.license_url, author = EXCLUDED.author,
                  credit_url = EXCLUDED.credit_url, restrictions = EXCLUDED.restrictions, width = EXCLUDED.width,
                  height = EXCLUDED.height, sha1 = EXCLUDED.sha1, storage_prefix = EXCLUDED.storage_prefix,
                  fetched_at = now()
                WHERE images.status <> 'takedown'
            """, (r.qid, f"File:{r.file}", r.status, r.license_short, r.license_url, r.author, r.credit_url,
                  r.restrictions, r.width, r.height, r.sha1, r.storage_prefix))


def run(paths: C.Paths, dsn: str, out_dir: str | None = None, commons: Commons | None = None,
        refresh: bool = False, limit: int | None = None) -> dict:
    """Fetch every wanted image that is not stored yet (or all with refresh=True)."""
    out_dir = out_dir or paths.p("images")
    wanted = duckdb.sql(f"SELECT qid, file FROM read_parquet('{paths.p('build', 'images_wanted.parquet')}') "
                        f"ORDER BY qid").fetchall()
    with psycopg.connect(dsn) as conn:
        have = {r[0]: (r[1], r[2]) for r in conn.execute("SELECT entity_id, commons_file, status FROM images").fetchall()}
        minors = {r[0] for r in conn.execute("SELECT id FROM entities WHERE is_minor").fetchall()}
    # New or changed files, and earlier failures. Licence and minor rejections stay rejected
    # until the file changes; takedowns are never refetched.
    todo = [(q, f) for q, f in wanted
            if q not in have or have[q][1] == "failed" or (have[q][0] != f"File:{f}" and have[q][1] != "takedown")
            or (refresh and have[q][1] != "takedown")]
    if limit:
        todo = todo[:limit]
    results = process(todo, out_dir, commons or Commons(), minors)
    save(results, dsn)
    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    return {"requested": len(todo), **counts}
