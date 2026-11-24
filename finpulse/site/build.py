#!/usr/bin/env python3
"""Build the static website from site/page.html and site/finpulse-engine.js.

Writes ../docs/index.html, one self-contained file that GitHub Pages can serve as is.
With --fragment PATH it also writes the page without the outer <html> skeleton.
Run from the finpulse folder:  python3 site/build.py
"""
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parent
REPO = SITE.parent.parent
page = (SITE / "page.html").read_text()
engine = (SITE / "finpulse-engine.js").read_text()
assert page.count("/*__ENGINE__*/") == 1 and page.count("<!--BODY-->") == 1 and "</script>" not in engine
page = page.replace("/*__ENGINE__*/", engine)
head, body = page.split("<!--BODY-->")

full = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        f"{head}</head>\n<body>{body}</body>\n</html>\n")
out = REPO / "docs" / "index.html"
out.parent.mkdir(exist_ok=True)
out.write_text(full)
print(f"wrote {out} ({len(full):,} bytes)")

if "--fragment" in sys.argv:
    target = Path(sys.argv[sys.argv.index("--fragment") + 1])
    target.write_text(head + body)
    print(f"wrote {target}")
