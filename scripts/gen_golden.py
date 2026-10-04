"""Writes internal/aqv/testdata/golden.json: the Python verifier's answers for the
low-level helpers, which the Go unit tests must reproduce exactly.

    .venv/bin/python scripts/gen_golden.py

Mutants come from every code line of the six demo baselines in demo/.work/<lang>/baseline.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import shutil  # noqa: E402

from aqv import engine, gitx, mutate, runner, spec  # noqa: E402

JUNIT_SCENARIOS = ["baseline", "T5-failing-test", "T5-suite-broken"]

FAMILY = {"python": "python"}
CODE_EXT = {".py", ".js", ".cjs", ".mjs", ".ts", ".go", ".rs", ".kt"}


def main():
    out = {"mutants": [], "mentions": [], "word_diff": [], "routes": [], "fnmatch": [], "under": [], "id_token": []}
    lines = []
    for lang_dir in sorted((ROOT / "demo" / ".work").glob("*/baseline")):
        lang = lang_dir.parent.name
        for path in sorted(lang_dir.rglob("*")):
            if path.suffix not in CODE_EXT or "node_modules" in path.parts or "target" in path.parts \
                    or "build" in path.parts or ".git" in path.parts:
                continue
            for line in path.read_text(errors="ignore").splitlines(True):
                lines.append((FAMILY.get(lang, "c"), line))
    lines += [("c", 'x := "a > b" + `c < d`\n'), ("python", "if a not in b and c >= 1:\n"),
              ("c", "let s = '→' + x - 1;\n"), ("python", "    return value  # 3 > 2\n")]
    seen = set()
    for fam, line in lines:
        if (fam, line) in seen:
            continue
        seen.add((fam, line))
        out["mutants"].append({"family": fam, "line": line, "mutants": mutate.mutants(line, fam)})
    names = ["test_AC_auth_002_locks", "TestAC_auth_002LocksAfterThree", "ac_auth_002_x", "AC-auth-002 locks",
             "AC-auth-0021 x", "xAC_auth_002", "TestAC_auth_002", "AC auth 002", "test_ac_auth_002x",
             "AC-auth-012 locks", "LockoutTest > AC-auth-002 locks after three()"]
    for n in names:
        for rid in ["AC-auth-002", "AC-auth-012"]:
            out["mentions"].append({"name": n, "id": rid, "result": spec.mentions(n, rid)})
    for rid in ["AC-auth-002", "AC-billing-v2-010"]:
        out["id_token"].append({"id": rid, "result": spec.id_token(rid)})
    pairs = [("Accounts lock after 3 consecutive failed sign-in attempts.",
              "Accounts lock after 5 consecutive failed sign-in attempts."),
             ("(api: POST /x) a b c d", "(api: POST /x) a c d e f"), ("one two", "one two three"),
             ("a b c", "c"), ("same", "same")]
    for a, b in pairs:
        out["word_diff"].append({"old": a, "new": b, "diff": spec.word_diff(a, b), "segments": spec.word_segments(a, b)})
    for r in ["GET /users/:id", "get /users/{user_id}/", "POST /", "DELETE /a/<int:x>/b", "GET /"]:
        out["routes"].append({"route": r, "result": engine.normalize_route(r)})
    for name, pat in [("specs/auth.md", "specs/*.md"), ("specs/a/b.md", "specs/*.md"), ("x_test.go", "*_test.go"),
                      ("a/b/x_test.go", "*_test.go"), ("Cargo.lock", "*.lock"), ("a.md", "?.md"),
                      ("ab.md", "?.md"), ("b.txt", "[ab].txt"), ("c.txt", "[!ab].txt"), ("x.lock", "*.LOCK")]:
        out["fnmatch"].append({"name": name, "pat": pat, "result": __import__("fnmatch").fnmatch(name, pat)})
    for path, prefixes in [("src/app/x.py", ["src/"]), ("internal/a_test.go", ["*_test.go"]),
                           ("internal/a.go", ["*_test.go"]), ("tests/x.py", ["src/", "lib/"])]:
        out["under"].append({"path": path, "prefixes": prefixes, "result": gitx.under(path, prefixes)})
    out["junit"] = junit_cases()
    dest = ROOT / "internal" / "aqv" / "testdata" / "golden.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(f"{len(out['mutants'])} lines, {sum(len(m['mutants']) for m in out['mutants'])} mutants -> {dest}")


def junit_cases():
    """Copies real JUnit reports from the last demo run into testdata/junit/ and records how
    the Python verifier reads them."""
    base = ROOT / "internal" / "aqv" / "testdata" / "junit"
    if base.exists():
        shutil.rmtree(base)
    cases = []
    for lang_dir in sorted((ROOT / "demo" / ".work").glob("*/runs")):
        lang = lang_dir.parent.name
        for scen in JUNIT_SCENARIOS:
            run = lang_dir / scen
            work = (run if scen == "baseline" else run / "out") / "work"
            files = [work / "junit-full.xml"] if (work / "junit-full.xml").exists() else []
            repo = lang_dir.parent / "baseline" if scen == "baseline" else run / "repo"
            if not files:
                files = sorted((repo / "build" / "test-results" / "test").glob("*.xml"))
            if not files:
                continue
            dest = base / f"{lang}-{scen}"
            dest.mkdir(parents=True)
            copied = []
            for f in files:
                shutil.copy(f, dest / f.name)
                copied.append(f"testdata/junit/{lang}-{scen}/{f.name}")
            got, errors = runner.parse_junit([str(ROOT / "internal" / "aqv" / c) for c in copied])
            cases.append({"files": copied, "errors": errors,
                          "cases": [[c.name, c.classname, c.outcome, c.message] for c in (got or [])]})
    return cases


if __name__ == "__main__":
    main()
