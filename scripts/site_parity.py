"""Checks that the Go site writer (aqv site) writes the same home page and comparison pages as Python.

    .venv/bin/python scripts/site_parity.py

The Python generators (aqv/html.py site_index, experiments/report.py) write the committed index.html and
docs/compare/*.html. This runs `aqv site` into a scratch copy of the inputs and compares every file byte for
byte. Run it after regenerating the pages with Python.
"""
import difflib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = ["index.html", "docs/compare/openfasttrace.html", "docs/compare/intentbond.html"]


def main():
    tmp = Path(tempfile.mkdtemp(prefix="aqv-site-"))
    try:
        # Only what the writer reads: the experiment results, the scenario scripts, and which pages exist.
        shutil.copytree(ROOT / "experiments", tmp / "experiments", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(ROOT / "demo" / "scenarios", tmp / "demo" / "scenarios")
        (tmp / "demo" / "results-go").mkdir(parents=True)
        (tmp / "demo" / "results-go" / "index.html").write_text("")
        for rel in ("docs/compare/openfasttrace.html", "docs/compare/intentbond.html"):
            (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
            (tmp / rel).write_text("")
        subprocess.run([str(ROOT / "bin" / "aqv"), "site", "--root", str(tmp), "--meta", str(ROOT / "demo" / "langs.json"),
                        "--py-work", str(ROOT / "demo" / ".work"), "--go-work", str(ROOT / "demo" / ".work-go")],
                       check=True, capture_output=True, cwd=ROOT)
        bad = 0
        for rel in FILES:
            a, b = (ROOT / rel).read_text(), (tmp / rel).read_text()
            if a == b:
                continue
            bad += 1
            i = next((k for k, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
            print(f"  {rel}: differs at char {i}: python …{a[max(0, i - 50):i + 120]!r} / go …{b[max(0, i - 50):i + 120]!r}")
        print(f"{len(FILES) - bad} of {len(FILES)} site pages are byte-identical in Go and Python")
        return 1 if bad else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
