"""Compares the two published demo page sets: demo/results (Python run) and demo/results-go (Go run).

    .venv/bin/python scripts/demo_parity.py

The two sets come from independent demo runs, so some text differs whichever verifier made it. After
removing what is known to differ (the Go pages' label and footer commands, text that changes on every run, and
the order tests are listed in), every page should be identical. Prints each page that still differs and the
first differing line, then a summary by kind of difference.
"""
import difflib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY, GO = ROOT / "demo" / "results", ROOT / "demo" / "results-go"

# (pattern, replacement) pairs applied to both sides
KNOWN = [
    (r" · Go verifier(?=</span>)", ""),                                  # eyebrow label on the Go pages
    (r"python demo/run_demo\.py --impl go", "python demo/run_demo.py"),  # footer command
    (r' aria-current="page"', ""),                                       # which nav link is highlighted
    (r"0x[0-9a-f]{6,}", "0x…"), (r"Test Case ID: \w+", "Test Case ID: …"), (r"127\.0\.0\.1:\d+", "127.0.0.1:…"),
    (r"\b[0-9a-f]{32}\b", "<token>"), (r"' \(\d+\) panicked", "' (…) panicked"),
    (r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?", "<timestamp>"),
    (r"\b\d+(?:\.\d+)?\s?(?:ms|s)\b", "<duration>"),
    # Each demo run rebuilds the repo with new signed commits, so every commit hash differs.
    (r"(?<![0-9A-Za-z_])(?=[0-9a-f]{7}(?![0-9A-Za-z_]))(?=[0-9a-f]*[a-f])(?=[0-9a-f]*[0-9])[0-9a-f]{7}", "<sha>"),
    # ... including hashes that happen to be all digits, found by where the page prints them
    (r"<code>[0-9a-f]{7}</code>", "<code><sha></code>"), (r"(?<=\.\.)[0-9a-f]{7}", "<sha>"),
    (r"[0-9a-f]{7}(?=\.\.)", "<sha>"), (r"(?<=changed in )[0-9a-f]{7}", "<sha>"),
    (r"(?<=wording change \()[0-9a-f]{7}", "<sha>"), (r"(?<=all history to )[0-9a-f]{7}", "<sha>"),
    (r"(?<=[:;] )[0-9a-f]{7}(?= (?:has|by|changes|cites|signature|refers|'))", "<sha>"),  # git-rule messages
]


def norm(text):
    for pat, rep in KNOWN:
        text = re.sub(pat, rep, text)
    return text


def main():
    files = sorted(p.relative_to(PY) for p in PY.rglob("*") if p.is_file())
    kinds, bad = {}, []
    for rel in files:
        other = GO / rel
        if not other.exists():
            bad.append((rel, "missing in Go pages", "")); continue
        a, b = norm((PY / rel).read_text()), norm(other.read_text())
        if a != b:
            i = next((k for k, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
            d = f"at char {i}: python …{a[max(0, i - 40):i + 90]!r} / go …{b[max(0, i - 40):i + 90]!r}"
            bad.append((rel, "differs", d[:420]))
    for rel, why, d in bad[:12]:
        print(f"  {rel}: {why} {d}")
    if len(bad) > 12:
        print(f"  ... and {len(bad) - 12} more")
        kinds.setdefault(str(rel).split("/")[0] if "/" in str(rel) else "index", []).append(rel)
    print(f"{len(files) - len(bad)} of {len(files)} pages match after removing text that differs between any two runs")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
