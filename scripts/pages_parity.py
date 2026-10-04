"""Checks that the Go page writer (aqv pages) and the Python one produce the same pages.

    .venv/bin/python scripts/pages_parity.py [--work demo/.work-go] [--keep DIR]

Both render from the same demo run (demo/<work>/<lang>/demo-results.json and the runs it
points to), into temporary folders, with the same variant label and command text. Every file
is then compared byte for byte: the per-language demo.html and RESULTS.md, every scenario
run page, the example pages and text reports, and the all-languages index. Prints each
difference with its first differing line, and exits non-zero if any file differs.
"""
import argparse
import difflib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "demo"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEMO))
import run_demo  # noqa: E402
from aqv import html  # noqa: E402

VARIANT = "Go verifier"
COMMAND = "python demo/run_demo.py --impl go"


def python_pages(work, out):
    run_demo.WORK_ROOT = work
    langs = []
    for meta in json.loads((DEMO / "langs.json").read_text()):
        lang = meta["lang"]
        f = work / lang / "demo-results.json"
        if not f.exists():
            continue
        run_demo.WORK = work / lang
        results = json.loads(f.read_text())
        run_demo.write_markdown(lang, results, results_dir=out, command=COMMAND)
        run_demo.write_html(lang, results, results_dir=out, variant=VARIANT, command=COMMAND)
        langs.append({**meta, "results": results})
    (out / "index.html").write_text(html.languages_report(
        langs, nav="../../", variant=VARIANT, command=COMMAND, current="demo/results-go/index.html"))


def compare(a, b):
    fa = {p.relative_to(a): p for p in a.rglob("*") if p.is_file()}
    fb = {p.relative_to(b): p for p in b.rglob("*") if p.is_file()}
    problems = []
    for rel in sorted(set(fa) | set(fb)):
        if rel not in fa:
            problems.append(f"{rel}: only in Go output")
        elif rel not in fb:
            problems.append(f"{rel}: only in Python output")
        elif fa[rel].read_bytes() != fb[rel].read_bytes():
            x, y = fa[rel].read_text().splitlines(), fb[rel].read_text().splitlines()
            d = next((l for l in difflib.unified_diff(x, y, "python", "go", lineterm="", n=0)
                      if l[:1] in "+-" and l[:3] not in ("+++", "---")), "")
            problems.append(f"{rel}: differs, first difference: {d[:300]}")
    return len(fa), problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default="demo/.work-go")
    ap.add_argument("--keep", help="keep both renderings under this folder")
    a = ap.parse_args()
    work = (ROOT / a.work).resolve()
    tmp = Path(tempfile.mkdtemp(prefix="aqv-pages-"))
    try:
        py_out, go_out = tmp / "python", tmp / "go"
        py_out.mkdir()
        python_pages(work, py_out)
        subprocess.run([str(ROOT / "bin" / "aqv"), "pages", "--work", str(work), "--meta", str(DEMO / "langs.json"),
                        "--out", str(go_out), "--variant", VARIANT, "--command", COMMAND], check=True,
                       capture_output=True, cwd=ROOT)
        n, problems = compare(py_out, go_out)
        for p in problems[:30]:
            print("  " + p)
        print(f"{n - len([p for p in problems if 'only in' in p or 'differs' in p])} of {n} pages are byte-identical "
              f"in Go and Python" + ("" if not problems else f"; {len(problems)} differ"))
        if a.keep:
            dest = Path(a.keep)
            shutil.rmtree(dest, ignore_errors=True)
            shutil.copytree(tmp, dest)
        return 1 if problems else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
