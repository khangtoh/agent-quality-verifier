"""Runs OpenFastTrace on the verifier's Python demo scenarios.

    python experiments/openfasttrace/run.py --work <dir> --gnupg <short dir> --oft-jar <openfasttrace-4.10.0.jar>

Builds the Python baseline, adds OFT notation (oft_layer.adopt), then for every
scenario: copies the repo, runs the same scenario script the verifier's demo uses,
tags what it added (oft_layer.update), and runs `oft trace specs src tests` on the
result. Two probes follow: which file types OFT reads tags from, and what OFT reports
for a requirement hierarchy (feature -> requirement -> design) that this verifier
doesn't model.
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
sys.path.insert(0, str(HERE.parent))
import oft_layer  # noqa: E402

EXTENSIONS = ["py", "js", "ts", "tsx", "go", "rs", "kt", "kts", "java", "yaml", "json", "toml", "sh", "feature"]


def sh(cmd, cwd, env=None, check=True):
    r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    if check and r.returncode:
        raise SystemExit(f"{cmd} failed in {cwd}:\n{r.stdout}\n{r.stderr}")
    return r


def commit(repo, env, msg):
    e = dict(env, GIT_AUTHOR_NAME="dev-agent", GIT_AUTHOR_EMAIL="agent@example.com",
             GIT_COMMITTER_NAME="dev-agent", GIT_COMMITTER_EMAIL="agent@example.com")
    sh(["git", "add", "-A"], repo, e)
    if sh(["git", "diff", "--cached", "--quiet"], repo, e, check=False).returncode:
        sh(["git", "commit", "-q", "-m", msg], repo, e)


def trace(jar, cwd, *paths):
    # Java prints a notice to stderr when JAVA_TOOL_OPTIONS is set; OFT needs no network.
    env = {k: v for k, v in os.environ.items() if k != "JAVA_TOOL_OPTIONS"}
    r = sh(["java", "-jar", jar, "trace", "-c", "BLACK_AND_WHITE", "-v", "failure_summaries", *paths], cwd, env, check=False)
    defects = []
    for line in r.stdout.splitlines():
        m = re.match(r"not ok \[.*\] (\S+) \(([^)]*)\)", line)
        if m:
            item, needs = m.groups()
            if item.startswith(("impl~", "utest~")):
                defects.append(f"{item.split('~')[0]} tag points to a requirement that doesn't exist at that revision")
            else:
                defects.append(f"{item} ({needs})" if needs else item)
    total = re.search(r"(ok|not ok) - (\d+) total", r.stdout)
    return {"exit": r.returncode, "defects": list(dict.fromkeys(defects)), "items": int(total.group(2)) if total else None}


def fresh(d):
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    return d


def extension_probe(jar, work):
    out = {}
    for ext in EXTENSIONS:
        d = fresh(work / "ext" / ext)
        (d / "spec.md").write_text("### R\n`req~r~1`\n\nx\n\nNeeds: impl\n")
        (d / f"f.{ext}").write_text("// [impl->req~r~1]\n# [impl->req~r~1]\n")
        out[ext] = trace(jar, d, ".")["exit"] == 0
    return out


HIERARCHY = """# Hierarchy probe

### Sign in
`feat~sign-in~1`

Users can sign in.

Needs: req

### Sign in with email and password
`req~auth-001~1`

Users sign in with email and password.

Covers:
- feat~sign-in~1

Needs: dsn

### Password check design
`dsn~password-check~1`

Passwords are compared as salted SHA-256 digests.

Covers:
- req~auth-001~1

Needs: impl, utest
"""


def hierarchy_probe(jar, work):
    d = fresh(work / "hierarchy")
    (d / "spec.md").write_text(HIERARCHY)
    (d / "auth.py").write_text("# [impl->dsn~password-check~1]\ndef password_matches(): ...\n")
    full = trace(jar, d, ".")
    (d / "test_auth.py").write_text("# [utest->dsn~password-check~1]\ndef test_password_matches(): ...\n")
    complete = trace(jar, d, ".")
    return {"design_without_test": full, "complete_chain": complete}


def duplicate_probe(jar, work):
    """Two items with the same ID and revision, as when an agent pastes a new requirement under an old ID."""
    d = fresh(work / "duplicate")
    (d / "spec.md").write_text("### A\n`req~r~1`\n\nfirst\n\nNeeds: impl\n\n### B\n`req~r~1`\n\nsecond\n\nNeeds: impl\n")
    (d / "a.py").write_text("# [impl->req~r~1]\n")
    env = {k: v for k, v in os.environ.items() if k != "JAVA_TOOL_OPTIONS"}
    r = sh(["java", "-jar", jar, "trace", "-c", "BLACK_AND_WHITE", "-v", "failure_details", "."], d, env, check=False)
    return {"exit": r.returncode, "duplicate_reported": "duplicate" in r.stdout}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--gnupg", required=True)
    ap.add_argument("--oft-jar", required=True)
    a = ap.parse_args()
    work = Path(a.work).resolve()
    jar = str(Path(a.oft_jar).resolve())
    env = dict(os.environ, GNUPGHOME=a.gnupg, DEMO=str(DEMO), AQV_LANG="python")

    base = work / "baseline"
    if not base.exists():
        sh([sys.executable, str(DEMO / "build_baseline.py"), str(base), "--gnupg", a.gnupg, "--lang", "python"], ROOT, env)
    twin = work / "twin-oft"
    if twin.exists():
        shutil.rmtree(twin)
    shutil.copytree(base, twin, symlinks=True)
    oft_layer.adopt(twin)
    commit(twin, env, "chore: adopt OpenFastTrace tags")

    results = {"baseline": trace(jar, twin, "specs", "src", "tests")}
    print("baseline ->", results["baseline"], flush=True)
    for script in sorted((DEMO / "scenarios").glob("*.sh")) + sorted((HERE.parent / "variants").glob("*.sh")):
        sid = script.stem
        repo = work / f"oft-{sid}"
        if repo.exists():
            shutil.rmtree(repo)
        shutil.copytree(twin, repo, symlinks=True)
        start = sh(["git", "rev-parse", "HEAD"], repo).stdout.strip()
        sh(["bash", str(script)], repo, env)
        oft_layer.update(repo, start, bump="no-bump" not in sid)
        commit(repo, env, "chore: update trace links\n\nRefs: none")
        head = script.read_text()
        results[sid] = {**trace(jar, repo, "specs", "src", "tests"),
                        "title": re.search(r"^# title: (.+)$", head, re.M).group(1),
                        "ours": re.search(r"^# expect: (.+)$", head, re.M).group(1)}
        print(sid, "->", results[sid]["exit"], results[sid]["defects"], flush=True)

    probes = {"extensions": extension_probe(jar, work), "hierarchy": hierarchy_probe(jar, work),
              "duplicate": duplicate_probe(jar, work)}
    print("probes ->", probes, flush=True)
    (HERE / "results" / "openfasttrace.json").write_text(json.dumps(results, indent=2) + "\n")
    (HERE / "results" / "probes.json").write_text(json.dumps(probes, indent=2) + "\n")


if __name__ == "__main__":
    main()
