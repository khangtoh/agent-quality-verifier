"""Checks that every relative link in the site's HTML pages points at a file that exists.

    python scripts/check_links.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    files = [ROOT / "index.html", ROOT / "docs" / "framework.html", *ROOT.glob("docs/compare/*.html"),
             *ROOT.glob("demo/results*/**/*.html")]
    bad = 0
    for f in files:
        for href in re.findall(r'href="([^"#]+)', f.read_text()):
            if href.startswith(("http", "mailto")):
                continue
            if not (f.parent / href).resolve().exists():
                bad += 1
                print(f"BROKEN {f.relative_to(ROOT)} -> {href}")
    print(f"{len(files)} pages checked, {bad} broken links")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
