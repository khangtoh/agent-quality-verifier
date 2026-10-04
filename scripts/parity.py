"""Checks that the Go verifier gives the same answers as the Python one.

    .venv/bin/python scripts/parity.py --lang python      # or several, or "all"

For every repo the last demo run left in demo/.work/<lang>/ (the baseline and each
scenario), runs bin/aqv on it with the same base and environment as the demo, writes
its outputs next to the Python ones (out-go/), and compares results.json, report.txt
and report.html. Paths that differ only because the output folder differs are
normalised first. Writes demo/.work/parity-<lang>.json and prints a summary.
"""
import argparse
import concurrent.futures as cf
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "demo"
WORK_ROOT = DEMO / ".work"
sys.path.insert(0, str(DEMO))
sys.path.insert(0, str(ROOT))
from aqv import cli, html  # noqa: E402
from build_baseline import LANGS, load_lang  # noqa: E402

BIN = ROOT / "bin" / "aqv"
COMPARE_ONLY = False


# Text that changes from one run to the next whichever implementation runs: object
# addresses in pytest failure messages, Schemathesis's random test-case IDs, and the
# random free port the service is started on, and how long the tests took.
RUN_SPECIFIC = [(re.compile(r"0x[0-9a-f]{6,}"), "0x…"), (re.compile(r"Test Case ID: \w+"), "Test Case ID: …"),
                (re.compile(r"127\.0\.0\.1:\d+"), "127.0.0.1:…"),
                (re.compile(r"\b\d+(?:\.\d+)?\s?(?:ms|s)\b"), "<duration>"),  # test runners' elapsed times
                (re.compile(r"\b[0-9a-f]{32}\b"), "<token>"),  # random session tokens the demo apps print
                (re.compile(r"' \(\d+\) panicked"), "' (…) panicked"),  # Rust test thread IDs
                (re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?"),
                 "<timestamp>")]  # timestamps in framework error responses


def normalize(text, out):
    text = text.replace(str(out / "work"), "<work>").replace(str(out), "<out>")
    for rx, repl in RUN_SPECIFIC:
        text = rx.sub(repl, text)
    return text


def diff_results(py, go):
    """Human-readable differences between two results.json trees."""
    problems = []
    if py["checks"] != go["checks"]:
        for k in py["checks"]:
            if py["checks"][k] != go["checks"].get(k):
                problems.append(f"check {k}: python {py['checks'][k]}, go {go['checks'].get(k)}")
    ps = {r["id"]: (r["status"], r["failing_checks"]) for r in py["requirements"]}
    gs = {r["id"]: (r["status"], r["failing_checks"]) for r in go["requirements"]}
    for rid in sorted(set(ps) | set(gs)):
        if ps.get(rid) != gs.get(rid):
            problems.append(f"{rid}: python {ps.get(rid)}, go {gs.get(rid)}")
    pr = [(r["check"], r["scope"], r["subject"], r["verdict"], r["summary"]) for r in py["results"]]
    gr = [(r["check"], r["scope"], r["subject"], r["verdict"], r["summary"]) for r in go["results"]]
    if pr != gr:
        for i, (a, b) in enumerate(zip(pr, gr)):
            if a != b:
                problems.append(f"result {i}: python {a}, go {b}")
        if len(pr) != len(gr):
            problems.append(f"{len(pr)} python results, {len(gr)} go results")
    return problems


TEST_LABEL = re.compile(r": (pass|fail|error|skipped)$")


def canonical(rep):
    """Test cases in a fixed order. Runners that run tests in parallel (cargo-nextest, Gradle)
    report them in the order they finished, so older outputs list them in run order."""
    for r in rep["results"]:
        d = r["details"]
        if isinstance(d.get("tests"), list):
            d["tests"] = sorted(d["tests"])
        if isinstance(d.get("failing"), list):
            d["failing"] = sorted(d["failing"], key=lambda f: f["test"])
            # Messages are stored cut at 300 characters; run-specific parts of different
            # lengths (thread IDs) move the cut, so compare a shorter prefix.
            for f in d["failing"]:
                f["message"] = f["message"][:250]
    for req in rep["requirements"]:
        now, out, run = req.get("now", []), [], []
        for e in now + [None]:
            if e is not None and TEST_LABEL.search(e["label"]):
                run.append(e)
                continue
            out += sorted(run, key=lambda x: x["label"].split(": ")[0])
            run = []
            if e is not None:
                out.append(e)
        if "now" in req:
            req["now"] = out
    return rep


def touch_tracked(repo):
    """Give the repo's files a fresh modification time, as when the demo had just written them.
    Rust's copies share one Cargo target folder, and Cargo trusts timestamps: without this, a
    repo written two days ago looks older than the last build and gets another copy's binary."""
    now = time.time()
    for f in subprocess.run(["git", "-C", str(repo), "ls-files", "-z"], capture_output=True, text=True).stdout.split("\0"):
        p = Path(repo) / f
        if f and p.is_file() and not p.is_symlink():
            os.utime(p, (now, now))


def check_one(lang, name, repo, out_py, base, env):
    out_go = out_py.parent / (out_py.name + "-go") if name == "baseline" else out_py.parent / "out-go"
    cmd = [str(BIN), "check", "--repo", str(repo), "--out", str(out_go)]
    if base:
        cmd += ["--base", base]
    t = time.time()
    if COMPARE_ONLY and (out_go / "results.json").exists():
        r = subprocess.CompletedProcess(cmd, 0, "", "")
    else:
        touch_tracked(repo)
        r = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True)
    secs = round(time.time() - t)
    if not (out_go / "results.json").exists():
        return {"name": name, "ok": False, "seconds": secs, "problems": [f"go verifier crashed: {(r.stdout + r.stderr)[-800:]}"]}
    # Engine: the two results.json files, with run-specific text removed and tests in a fixed order.
    py_text = normalize((out_py / "results.json").read_text(), out_py)
    go_text = normalize((out_go / "results.json").read_text(), out_go)
    py, go = canonical(json.loads(py_text)), canonical(json.loads(go_text))
    problems = diff_results(py, go)
    engine_same = json.dumps(py, sort_keys=False) == json.dumps(go, sort_keys=False)
    if not problems and not engine_same:
        problems.append("same verdicts and summaries, different details in results.json")
    # Renderer: Go's report.txt and report.html against Python's rendering of Go's results.json.
    go_rep = json.loads((out_go / "results.json").read_text())
    render = {"report.txt": cli.text_report(go_rep) + "\n", "report.html": html.run_report(go_rep)}
    for f, expected in render.items():
        if (out_go / f).read_text() != expected:
            problems.append(f"{f} differs from Python's rendering of the same results")
    return {"name": name, "ok": not problems, "seconds": secs, "problems": problems,
            "failing_checks": sorted(k for k, v in go_rep["checks"].items() if v in ("fail", "error"))}


def run_lang(lang, jobs):
    L = load_lang(lang)
    work = WORK_ROOT / lang
    shared = work / "shared"
    env = dict(os.environ, GNUPGHOME=str(WORK_ROOT / "gnupg"), DEMO=str(DEMO), AQV_LANG=lang,
               AQV_PYTHON=str(ROOT / ".venv" / "bin" / "python"), AQV_HOME=str(ROOT))
    env.update(getattr(L, "env", lambda shared: {})(shared))
    tasks = [("baseline", work / "baseline", work / "runs" / "baseline", None)]
    for d in sorted((work / "runs").iterdir()):
        if d.name != "baseline" and (d / "repo").is_dir() and (d / "out" / "results.json").exists():
            tasks.append((d.name, d / "repo", d / "out", "main"))
    results = []
    with cf.ThreadPoolExecutor(max_workers=min(jobs, getattr(L, "JOBS", jobs))) as pool:
        futs = [pool.submit(check_one, lang, *t, env) for t in tasks]
        for f in cf.as_completed(futs):
            r = f.result()
            results.append(r)
            print(f"  [{lang}] {r['name']}: {'same' if r['ok'] else 'DIFFERENT'} ({r['seconds']}s)"
                  + "".join(f"\n      {p}" for p in r["problems"][:6]), flush=True)
    results.sort(key=lambda r: r["name"])
    (WORK_ROOT / f"parity-{lang}.json").write_text(json.dumps(results, indent=2))
    same = sum(r["ok"] for r in results)
    print(f"[{lang}] {same} of {len(results)} runs give the same answer in Go and Python", flush=True)
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="python")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--compare-only", action="store_true", help="reuse existing out-go/ results instead of rerunning Go")
    a = ap.parse_args()
    global COMPARE_ONLY
    COMPARE_ONLY = a.compare_only
    langs = LANGS if a.lang == "all" else a.lang.split(",")
    total = same = 0
    for lang in langs:
        rs = run_lang(lang, a.jobs)
        total += len(rs)
        same += sum(r["ok"] for r in rs)
    print(f"{same} of {total} runs give the same answer in Go and Python")
    return 0 if same == total else 1


if __name__ == "__main__":
    sys.exit(main())
