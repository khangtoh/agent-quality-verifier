"""aqv: check an agent's work against the spec.

    python -m aqv check [--repo .] [--base main] [--out out/] [--skip T7,A7] [--only H1,H2]
"""
import argparse
import json
import os
import sys

from . import gitx
from .engine import CHECKS, Engine

MARK = {"pass": "pass", "fail": "FAIL", "error": "ERROR", "skip": "skip", "not_covered": "not covered",
        "not_run": "not run"}
GROUPS = [("Tests prove the spec", "T"), ("The API matches its OpenAPI contract", "A"),
          ("Git follows the conventions", "H")]


def text_report(rep):
    out = []
    rng = f"{rep['base'][:7]}..{rep['head'][:7]}" if rep["base"] else f"all history to {rep['head'][:7]}"
    out.append(f"Agent Quality Verifier: {os.path.basename(rep['repo'])} ({rep['head_branch']}, {rng})")
    out.append("")
    out.append(f"{'REQUIREMENT':<13}{'STATUS':<13}FAILING CHECKS")
    for r in rep["requirements"]:
        out.append(f"{r['id']:<13}{r['status']:<13}{', '.join(r['failing_checks']) or '-'}")
    out.append("")
    for title, prefix in GROUPS:
        out.append(title)
        for chk, name in CHECKS.items():
            if not chk.startswith(prefix):
                continue
            v = rep["checks"][chk]
            out.append(f"  {chk:<4}{MARK[v]:<13}{name}")
            for r in rep["results"]:
                if r["check"] == chk and r["verdict"] in ("fail", "error", "not_covered"):
                    subj = "" if r["subject"] in ("history", "project", "spec", "contract") else f"{r['subject']}: "
                    out.append(f"        {subj}{r['summary']}")
        out.append("")
    if rep["scorecard"]:
        out.append("Agent scorecard (this range)")
        for who, a in rep["scorecard"].items():
            out.append(f"  {who}: {a['commits']} commit(s), git rule pass rate {a['git_rule_pass_rate']:.0%}, "
                       f"requirements {', '.join(a['requirements_referenced']) or '-'}")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="aqv")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="run the checks")
    c.add_argument("--repo", default=".")
    c.add_argument("--base", help="base ref; checks the range base..HEAD like a pull request")
    c.add_argument("--out", help="directory for results.json and report.txt")
    c.add_argument("--skip", default="", help="comma-separated checks to skip")
    c.add_argument("--only", default="", help="comma-separated checks to run")
    c.add_argument("--record", action="store_true",
                   help="when every check passes, record HEAD as the last verified commit (refs/aqv/verified)")
    a = ap.parse_args(argv)

    out = a.out or os.path.join(a.repo, ".aqv-out")
    os.makedirs(out, exist_ok=True)
    eng = Engine(a.repo, base=a.base, skip=[x for x in a.skip.split(",") if x],
                 only=[x for x in a.only.split(",") if x] or None, workdir=os.path.join(out, "work"))
    rep = eng.run()
    with open(os.path.join(out, "results.json"), "w") as f:
        json.dump(rep, f, indent=2, default=list)
    txt = text_report(rep)
    with open(os.path.join(out, "report.txt"), "w") as f:
        f.write(txt + "\n")
    print(txt)
    failed = [k for k, v in rep["checks"].items() if v in ("fail", "error")]
    if a.record and not failed:
        gitx.git(eng.repo, "update-ref", eng.cfg["git"]["verified_ref"], eng.head)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
