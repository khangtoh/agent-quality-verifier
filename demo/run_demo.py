"""Runs the demo: builds the clean baseline, then every scenario in demo/scenarios.

Each scenario runs in its own copy of the baseline repo and is checked like a pull
request against main. The clean scenarios must pass every check; each attack must
be caught by the check named in its `# expect:` line.

    python demo/run_demo.py [--lang python,go] [--jobs 4] [--only T3,A6]
    python demo/run_demo.py --html-only     # rebuild the HTML pages from the last runs
"""
import argparse
import concurrent.futures as cf
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "demo"
WORK_ROOT = DEMO / ".work"
RESULTS = DEMO / "results"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEMO))
from aqv import html  # noqa: E402
from aqv.engine import CHECKS  # noqa: E402
from build_baseline import LANGS, load_lang  # noqa: E402

WORK = WORK_ROOT  # set per language in run_language()


def header(path):
    meta = {}
    for line in path.read_text().splitlines():
        if line.startswith("# ") and ":" in line:
            k, _, v = line[2:].partition(":")
            meta[k.strip()] = v.strip()
    meta["expect"] = [] if meta.get("expect", "none") == "none" else [x.strip() for x in meta["expect"].split(",")]
    return meta


def verify(repo, out, base=None, env=None):
    cmd = [sys.executable, "-m", "aqv", "check", "--repo", str(repo), "--out", str(out)]
    if base:
        cmd += ["--base", base]
    t = time.time()
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env=env)
    rep = json.loads((out / "results.json").read_text()) if (out / "results.json").exists() else None
    if rep is None:
        raise RuntimeError(f"verifier crashed on {repo}:\n{r.stdout}\n{r.stderr}")
    return rep, time.time() - t


def run_scenario(path, env):
    meta = header(path)
    name = path.stem
    d = WORK / "runs" / name
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    repo = d / "repo"
    shutil.copytree(WORK / "baseline", repo, symlinks=True)
    s = subprocess.run(["bash", str(path)], cwd=repo, env=env, capture_output=True, text=True)
    if s.returncode:
        return {"name": name, "title": meta.get("title", ""), "expect": meta["expect"], "error":
                f"scenario script failed:\n{s.stdout}\n{s.stderr}"}
    rep, secs = verify(repo, d / "out", base="main", env=env)
    failing = sorted(k for k, v in rep["checks"].items() if v in ("fail", "error"))
    ok = set(meta["expect"]) <= set(failing) if meta["expect"] else not failing
    return {"name": name, "title": meta.get("title", ""), "expect": meta["expect"], "failing": failing,
            "statuses": {r["id"]: r["status"] for r in rep["requirements"]}, "checks": rep["checks"],
            "ok": ok, "seconds": round(secs), "out": str(d / "out")}


EXAMPLES = ["baseline", "T7-weak-tests", "A6-leaked-field"]


def write_html(lang, results):
    """demo/results/<lang>/demo.html for the whole run, plus single-run reports for a few samples."""
    L = load_lang(lang)
    out_dir = RESULTS / lang
    out_dir.mkdir(parents=True, exist_ok=True)
    scenarios = []
    for r in results:
        if "error" in r:
            continue
        rep = scrub(json.loads((Path(r["out"]) / "results.json").read_text()))
        scenarios.append({**r, "report": rep})
        (out_dir / "runs").mkdir(exist_ok=True)
        (out_dir / "runs" / f"{r['name']}.html").write_text(html.run_report(rep, nav="../../../../"))
        if r["name"] in EXAMPLES:
            (out_dir / f"{r['name']}.html").write_text(html.run_report(rep, nav="../../../"))
            (out_dir / f"{r['name']}.txt").write_text(scrub_text((Path(r["out"]) / "report.txt").read_text()))
    (out_dir / "demo.html").write_text(html.demo_report(scenarios, language=f"{L.NAME} ({L.STACK})", nav="../../../"))


# Comparison pages built by experiments/report.py: (html, markdown, title, description).
COMPARE = [
    ("docs/compare/openfasttrace.html", "experiments/openfasttrace/README.md", "OpenFastTrace",
     "Requirement tracing through a document hierarchy, on the same 26 attacks."),
    ("docs/compare/intentbond.html", "experiments/intentbond/README.md", "IntentBond",
     "Links, tests and a review gate against a git baseline, with retained evidence, on the same 26 attacks."),
]


def write_index():
    langs = []
    for lang in LANGS:
        f = WORK_ROOT / lang / "demo-results.json"
        if f.exists():
            L = load_lang(lang)
            langs.append({"lang": lang, "name": L.NAME, "stack": L.STACK, "mechanisms": getattr(L, "MECHANISMS", {}),
                          "results": json.loads(f.read_text())})
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "index.html").write_text(html.languages_report(langs, nav="../../"))
    compare = [c for c in COMPARE if (ROOT / c[0]).exists()]
    (ROOT / "index.html").write_text(html.site_index(langs, compare))


def scrub_text(text):
    return text.replace(str(WORK_ROOT) + "/", "")


def scrub(rep):
    """Drop local paths so the committed pages don't show this machine's directories."""
    return json.loads(json.dumps(rep).replace(str(WORK_ROOT) + "/", ""))


def run_language(lang, jobs, only):
    global WORK
    L = load_lang(lang)
    WORK = WORK_ROOT / lang
    WORK.mkdir(parents=True, exist_ok=True)
    gnupg = WORK_ROOT / "gnupg"
    env = dict(os.environ, GNUPGHOME=str(gnupg), DEMO=str(DEMO), AQV_LANG=lang)
    shared = WORK / "shared"
    shared.mkdir(exist_ok=True)
    env.update(getattr(L, "env", lambda shared: {})(shared))
    os.environ.update({k: v for k, v in env.items() if k not in os.environ or k in ("GNUPGHOME", "AQV_LANG")})
    print(f"[{lang}] building the baseline repo ...", flush=True)
    b = subprocess.run([sys.executable, str(DEMO / "build_baseline.py"), str(WORK / "baseline"),
                        "--gnupg", str(gnupg), "--lang", lang, "--shared", str(shared)],
                       capture_output=True, text=True, env=env)
    if b.returncode:
        print(b.stdout + b.stderr)
        raise SystemExit(f"[{lang}] baseline build failed")

    results = []
    if not only:
        print(f"[{lang}] checking the baseline (all history) ...", flush=True)
        rep, secs = verify(WORK / "baseline", WORK / "runs" / "baseline", base=None, env=env)
        failing = sorted(k for k, v in rep["checks"].items() if v in ("fail", "error"))
        results.append({"name": "baseline", "title": "Baseline: six requirements built the right way, all history",
                        "expect": [], "failing": failing, "statuses": {r["id"]: r["status"] for r in rep["requirements"]},
                        "checks": rep["checks"], "ok": not failing, "seconds": round(secs),
                        "out": str(WORK / "runs" / "baseline")})
        print(f"  [{lang}] baseline: {'ok' if not failing else 'FAILED ' + ', '.join(failing)} ({round(secs)}s)",
              flush=True)

    scenarios = sorted((DEMO / "scenarios").glob("*.sh"))
    if only:
        scenarios = [p for p in scenarios if any(p.stem.startswith(o) for o in only)]
    with cf.ThreadPoolExecutor(max_workers=min(jobs, getattr(L, "JOBS", jobs))) as pool:
        futs = {pool.submit(run_scenario, p, env): p for p in scenarios}
        for f in cf.as_completed(futs):
            r = f.result()
            results.append(r)
            if "error" in r:
                print(f"  [{lang}] {r['name']}: SCRIPT ERROR\n{r['error']}", flush=True)
            else:
                mark = "ok" if r["ok"] else "MISSED"
                print(f"  [{lang}] {r['name']}: {mark}; failing checks: {', '.join(r['failing']) or 'none'} "
                      f"({r['seconds']}s)", flush=True)

    results.sort(key=lambda r: (r["name"] != "baseline", r["name"]))
    if not only:
        (WORK / "demo-results.json").write_text(json.dumps(results, indent=2))
        write_markdown(lang, results)
        write_html(lang, results)
    bad = [r for r in results if not r.get("ok")]
    print(f"[{lang}] {len(results) - len(bad)} of {len(results)} scenarios behaved as expected.", flush=True)
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="python", help="comma-separated, or 'all'")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--only", default="")
    ap.add_argument("--html-only", action="store_true")
    a = ap.parse_args()
    langs = LANGS if a.lang == "all" else [x for x in a.lang.split(",") if x]

    if a.html_only:
        global WORK
        for lang in langs:
            WORK = WORK_ROOT / lang
            if (WORK / "demo-results.json").exists():
                results = json.loads((WORK / "demo-results.json").read_text())
                write_markdown(lang, results)
                write_html(lang, results)
        write_index()
        print(f"Wrote {RESULTS}")
        return 0

    only = [x for x in a.only.split(",") if x]
    ok = True
    for lang in langs:
        results = run_language(lang, a.jobs, only)
        ok = ok and all(r.get("ok") for r in results)
    if not only:
        write_index()
    return 0 if ok else 1


def write_markdown(lang, results):
    clean = [r for r in results if not r["expect"] and "error" not in r]
    L = load_lang(lang)
    lines = [f"# Demo results: {L.NAME}", "", f"Stack: {L.STACK}.", "",
             "Generated by `python demo/run_demo.py`. Each attack runs in its own copy of the baseline repo and "
             "is checked like a pull request against `main`.", "",
             "## Every check, clean and attacked", "",
             "| Check | What it checks | Clean runs | Caught by |", "|---|---|---|---|"]
    for chk, name in CHECKS.items():
        verdicts = sorted({r["checks"][chk] for r in clean})
        catchers = [r["name"] for r in results if chk in r.get("expect", []) and r.get("ok")]
        missed = [r["name"] for r in results if chk in r.get("expect", []) and not r.get("ok")]
        cell = ", ".join(f"`{c}`" for c in catchers) or "—"
        if missed:
            cell += " · missed: " + ", ".join(f"`{m}`" for m in missed)
        lines.append(f"| {chk} | {name} | {' / '.join(verdicts)} | {cell} |")
    lines += ["", "## Scenarios", "", "| Scenario | What happens | Expected | Failing checks | Statuses that changed | Result |",
              "|---|---|---|---|---|---|"]
    for r in results:
        if "error" in r:
            lines.append(f"| `{r['name']}` | {r['title']} | {', '.join(r['expect'])} | script error | | ❌ |")
            continue
        changed = ", ".join(f"{k}: {v}" for k, v in r["statuses"].items() if v != "Sync") or "all Sync"
        lines.append(f"| `{r['name']}` | {r['title']} | {', '.join(r['expect']) or 'all pass'} | "
                     f"{', '.join(r['failing']) or 'none'} | {changed} | {'✅' if r['ok'] else '❌'} |")
    (RESULTS / lang).mkdir(parents=True, exist_ok=True)
    (RESULTS / lang / "RESULTS.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())
