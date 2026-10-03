"""Runs IntentBond on the verifier's Python demo scenarios.

    python experiments/intentbond/run.py --work <dir> --gnupg <short dir> --ib <path to ib>

Builds the Python baseline, adds IntentBond notation (oft_layer.adopt) under two
scopes, then for every scenario: copies the repo, runs the same scenario script the
verifier's demo uses, tags what it added (oft_layer.update), and runs
`ib check --base <main before the scenario> --candidate HEAD`.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DEMO = ROOT / "demo"
sys.path.insert(0, str(HERE))
import oft_layer  # noqa: E402

TEST_CMD = ["python3", "-m", "pytest", "-p", "no:cacheprovider", "-q", "--junitxml=test-results.xml"]
BASE_SCOPE = {
    "schema_version": 1,
    "name": "auth-service",
    "inputs": ["specs", "src", "tests", "pyproject.toml"],
    "specification_paths": ["specs"],
    "test_paths": ["tests", "pyproject.toml"],
    "required_coverage": {"req": ["impl", "utest"]},
    "tests": {
        "format": "junit",
        "command": TEST_CMD,
        "report": "test-results.xml",
        "timeout_seconds": 120,
        "execution_links": {"format": "junit-properties-v1", "artifact_types": ["utest"]},
    },
}


def scopes(baseline_tests):
    default = json.loads(json.dumps(BASE_SCOPE))
    strict = json.loads(json.dumps(BASE_SCOPE))
    strict["policy"] = {"require_revision_increase": True, "allow_skipped_tests": False}
    strict["tests"]["execution_links"]["required_artifacts"] = baseline_tests
    return {"default": default, "strict": strict}


def sh(cmd, cwd, env=None, check=True):
    r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    if check and r.returncode:
        raise SystemExit(f"{cmd} failed in {cwd}:\n{r.stdout}\n{r.stderr}")
    return r


def commit(repo, env, msg, agent=True):
    who = ("dev-agent", "agent@example.com") if agent else ("Pat Product", "pat@example.com")
    e = dict(env, GIT_AUTHOR_NAME=who[0], GIT_AUTHOR_EMAIL=who[1], GIT_COMMITTER_NAME=who[0], GIT_COMMITTER_EMAIL=who[1])
    sh(["git", "add", "-A"], repo, e)
    if sh(["git", "diff", "--cached", "--quiet"], repo, e, check=False).returncode:
        sh(["git", "commit", "-q", "-m", msg], repo, e)


def ib_check(ib, repo, base, out, env):
    # Java prints a notice when JAVA_TOOL_OPTIONS is set (as in some CI containers);
    # IntentBond counts any OFT output as an import diagnostic. OFT needs no network.
    env = {k: v for k, v in env.items() if k != "JAVA_TOOL_OPTIONS"}
    if out.exists():  # ib check refuses an existing output directory
        shutil.rmtree(out)
    r = sh([ib, "check", "--base", base, "--candidate", "HEAD", "--out", str(out)], repo, env, check=False)
    summary = (out / "summary.md").read_text() if (out / "summary.md").exists() else ""
    return r.returncode, summary, (r.stdout + r.stderr)


def reasons(out, summary, log):
    """What IntentBond reported: non-passing summary rows, OFT defects and test counts."""
    found = []
    for row in re.findall(r"^\| ([^|]+) \| <code>([^<]+)</code>", summary, re.M):
        if row[1] not in ("passed", "matched", "not_required", "recorded"):
            found.append(f"{row[0].strip()}: {row[1]}")
    for log_name in ("candidate-trace.log", "base-trace.log"):
        f = out / log_name
        if f.exists():
            for line in f.read_text().splitlines():
                m = re.match(r"not ok \[.*\] (\S+) \(([^)]*)\)", line)
                if m and not m.group(1).startswith(("impl~", "utest~")):
                    found.append(f"OFT: {m.group(1)} ({m.group(2)})" if m.group(2) else f"OFT: {m.group(1)}")
                elif m:
                    found.append(f"OFT: orphan {m.group(1).split('~')[0]} tag")
    m = re.search(r"Reported cases: ([^.]+)\.", summary)
    if m:
        found.append("tests: " + m.group(1))
    for d in re.findall(r"^- <code>(.+?)</code>$", summary, re.M):
        found.append("diagnostic: " + d)
    if not summary:
        found += [l.strip() for l in log.splitlines() if l.strip() and "JAVA_TOOL" not in l][-4:]
    return list(dict.fromkeys(found))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--gnupg", required=True)
    ap.add_argument("--ib", required=True)
    ap.add_argument("--python-bin", required=True, help="bin directory whose python3 has the demo's test dependencies")
    ap.add_argument("--only")
    a = ap.parse_args()
    work = Path(a.work).resolve()
    env = dict(os.environ, GNUPGHOME=a.gnupg, DEMO=str(DEMO), AQV_LANG="python",
               PATH=f"{a.python_bin}:{os.environ['PATH']}")

    base = work / "baseline"
    if not base.exists():
        sh([sys.executable, str(DEMO / "build_baseline.py"), str(base), "--gnupg", a.gnupg, "--lang", "python"], ROOT, env)

    results = {}
    for name in ("default", "strict"):
        twin = work / f"twin-{name}"
        if twin.exists():
            shutil.rmtree(twin)
        shutil.copytree(base, twin, symlinks=True)
        oft_layer.adopt(twin, BASE_SCOPE)
        tests = sorted(set(re.findall(r'oft_id\("(utest~[^~"]+)~1"\)', "".join(p.read_text() for p in (twin / "tests").glob("test_*.py")))))
        (twin / "scope.json").write_text(json.dumps(scopes(tests)[name], indent=2) + "\n")
        commit(twin, env, "chore: adopt IntentBond traceability", agent=False)
        out_dir = work / f"ev-{name}-baseline"
        code, summary, log = ib_check(a.ib, twin, "HEAD", out_dir, env)
        results.setdefault("baseline", {})[name] = {"exit": code, "reasons": reasons(out_dir, summary, log)}
        print(f"[{name}] baseline -> exit {code}", flush=True)

        for script in sorted((DEMO / "scenarios").glob("*.sh")) + sorted((HERE / "variants").glob("*.sh")):
            sid = script.stem
            if a.only and a.only not in sid:
                continue
            repo = work / f"{name}-{sid}"
            if repo.exists():
                shutil.rmtree(repo)
            shutil.copytree(twin, repo, symlinks=True)
            start = sh(["git", "rev-parse", "HEAD"], repo).stdout.strip()
            s = sh(["bash", str(script)], repo, env, check=False)
            if s.returncode:
                raise SystemExit(f"{sid}: scenario failed\n{s.stdout}\n{s.stderr}")
            oft_layer.update(repo, start, bump="no-bump" not in sid)
            commit(repo, env, "chore: update trace links\n\nRefs: none")
            out_dir = work / f"ev-{name}-{sid}"
            code, summary, log = ib_check(a.ib, repo, start, out_dir, env)
            head = script.read_text()
            results.setdefault(sid, {})[name] = {"exit": code, "reasons": reasons(out_dir, summary, log)}
            results[sid]["title"] = re.search(r"^# title: (.+)$", head, re.M).group(1)
            results[sid]["ours"] = re.search(r"^# expect: (.+)$", head, re.M).group(1)
            print(f"[{name}] {sid} -> exit {code}", flush=True)

    (work / "results.json").write_text(json.dumps(results, indent=2))
    print(work / "results.json")


if __name__ == "__main__":
    main()
