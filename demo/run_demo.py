"""Runs the demo: builds the clean baseline, then every scenario in demo/scenarios.

Each scenario runs in its own copy of the baseline repo and is checked like a pull
request against main. The clean scenarios must pass every check; each attack must
be caught by the check named in its `# expect:` line.

    python demo/run_demo.py [--jobs 4] [--only T3,A6]
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
WORK = DEMO / ".work"
sys.path.insert(0, str(ROOT))
from aqv.engine import CHECKS  # noqa: E402


def header(path):
    meta = {}
    for line in path.read_text().splitlines():
        if line.startswith("# ") and ":" in line:
            k, _, v = line[2:].partition(":")
            meta[k.strip()] = v.strip()
    meta["expect"] = [] if meta.get("expect", "none") == "none" else [x.strip() for x in meta["expect"].split(",")]
    return meta


def verify(repo, out, base=None):
    cmd = [sys.executable, "-m", "aqv", "check", "--repo", str(repo), "--out", str(out)]
    if base:
        cmd += ["--base", base]
    t = time.time()
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
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
    rep, secs = verify(repo, d / "out", base="main")
    failing = sorted(k for k, v in rep["checks"].items() if v in ("fail", "error"))
    ok = set(meta["expect"]) <= set(failing) if meta["expect"] else not failing
    return {"name": name, "title": meta.get("title", ""), "expect": meta["expect"], "failing": failing,
            "statuses": {r["id"]: r["status"] for r in rep["requirements"]}, "checks": rep["checks"],
            "ok": ok, "seconds": round(secs)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--only", default="")
    a = ap.parse_args()

    WORK.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, GNUPGHOME=str(WORK / "gnupg"), DEMO=str(DEMO))
    os.environ["GNUPGHOME"] = env["GNUPGHOME"]
    print("Building the baseline repo ...", flush=True)
    subprocess.run([sys.executable, str(DEMO / "build_baseline.py"), str(WORK / "baseline"),
                    "--gnupg", env["GNUPGHOME"]], check=True, capture_output=True)

    results = []
    only = [x for x in a.only.split(",") if x]
    if not only:
        print("Checking the baseline (all history) ...", flush=True)
        rep, secs = verify(WORK / "baseline", WORK / "runs" / "baseline", base=None)
        failing = sorted(k for k, v in rep["checks"].items() if v in ("fail", "error"))
        results.append({"name": "baseline", "title": "Baseline: six requirements built the right way, all history",
                        "expect": [], "failing": failing, "statuses": {r["id"]: r["status"] for r in rep["requirements"]},
                        "checks": rep["checks"], "ok": not failing, "seconds": round(secs)})
        print(f"  baseline: {'ok' if not failing else 'FAILED ' + ', '.join(failing)} ({round(secs)}s)", flush=True)

    scenarios = sorted((DEMO / "scenarios").glob("*.sh"))
    if only:
        scenarios = [p for p in scenarios if any(p.stem.startswith(o) for o in only)]
    with cf.ThreadPoolExecutor(max_workers=a.jobs) as pool:
        futs = {pool.submit(run_scenario, p, env): p for p in scenarios}
        for f in cf.as_completed(futs):
            r = f.result()
            results.append(r)
            if "error" in r:
                print(f"  {r['name']}: SCRIPT ERROR\n{r['error']}", flush=True)
            else:
                mark = "ok" if r["ok"] else "MISSED"
                print(f"  {r['name']}: {mark}; failing checks: {', '.join(r['failing']) or 'none'} ({r['seconds']}s)",
                      flush=True)

    results.sort(key=lambda r: (r["name"] != "baseline", r["name"]))
    (WORK / "demo-results.json").write_text(json.dumps(results, indent=2))
    if not only:
        write_markdown(results)
    bad = [r for r in results if not r.get("ok")]
    print(f"\n{len(results) - len(bad)} of {len(results)} scenarios behaved as expected.")
    return 1 if bad else 0


def write_markdown(results):
    clean = [r for r in results if not r["expect"] and "error" not in r]
    lines = ["# Demo results", "",
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
    (DEMO / "RESULTS.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())
