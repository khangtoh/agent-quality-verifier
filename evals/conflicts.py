#!/usr/bin/env python3
"""Asks whether the verifier notices documents that disagree, and documents that moved.

    .venv/bin/python evals/conflicts.py [--run evals/runs/<a finished, clean run>]

Two parts, neither needs an agent:

  conflicts   Each conflict is planted alone, by a person, in a fresh workspace where no code
              exists yet. The question is whether the verifier says so before an agent builds on it.
  drift       (with --run) On a copy of a finished build, a person changes a contract or the plan
              and nothing else. The question is whether the affected requirements stop being Sync.

Each case is checked twice: with the consistency checks off (the verifier as it was) and on.
A case is **caught** when every check it expects newly fails; a probe (no expected check) when any
check newly fails; a control when nothing newly fails. Writes conflicts.json and conflicts.md.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run as R  # noqa: E402

SLOW = "T7,A7"
NEW = "C1,C2,C3,C4,C5,C6,C7,A8"


def failing(results):
    return {(x["check"], x["subject"]) for x in results["results"] if x["verdict"] in ("fail", "error")}


ENV = None  # set in main: the stack's environment for checks, with one build folder for every copy


def check(work, repo, label, skip):
    tree, results = R.final_check(work, repo, work / label, skip, ENV)
    R.git(repo, "worktree", "remove", "--force", str(tree), check=False)
    return results


def both(work, repo):
    return check(work, repo, "before", f"{SLOW},{NEW}"), check(work, repo, "after", SLOW)


def judge(case, base, results):
    """What newly fails against the clean baseline, and whether that is what the case expects."""
    new = sorted(failing(results) - failing(base))
    checks = sorted({c for c, _ in new})
    base_status = {r["id"]: r["status"] for r in base["requirements"]}
    moved = {r["id"]: f"{base_status[r['id']]} → {r['status']}" for r in results["requirements"]
             if r["status"] != base_status[r["id"]]}
    said = [x["summary"] for x in results["results"] if (x["check"], x["subject"]) in new]
    if case["expect"] is None:
        ok = not checks
    elif case["expect"]:
        ok = all(c in checks for c in case["expect"])
    else:
        ok = bool(checks)
    return {"new_checks": checks, "statuses_moved": moved, "said": said, "ok": ok}


def human_commit(repo, message, trailer=None):
    R.git(repo, "add", "-A")
    R.git(repo, "commit", "-q", "-m", message, *(["--trailer", trailer] if trailer else []), who=R.HUMAN)


def row_of(case, base_before, base_after, work, repo):
    before, after = both(work, repo)
    b, a = judge(case, base_before, before), judge(case, base_after, after)
    kind = "control" if case["expect"] is None else ("probe" if not case["expect"] else "targeted")
    result = ("clean" if a["ok"] else "false alarm") if kind == "control" else ("caught" if a["ok"] else "missed")
    was = ("clean" if b["ok"] else "false alarm") if kind == "control" else ("caught" if b["ok"] else "missed")
    print(f"{case['name']}: {was} → {result} ({', '.join(a['new_checks']) or 'nothing new'})")
    return {"name": case["name"], "what": case["what"], "between": case.get("between", ""), "kind": kind,
            "expect": case["expect"], "before": b, "after": a, "before_result": was, "result": result}


def table(rows, first):
    lines = [f"| Case | {first} | Expected | Verifier before | Verifier now | What it says now |", "|---|---|---|---|---|---|"]
    for r in rows:
        expect = "nothing (control)" if r["expect"] is None else (", ".join(r["expect"]) or "probe")
        moved = "; ".join(f"{i} {m}" for i, m in r["after"]["statuses_moved"].items())
        said = (r["after"]["said"] or ["-"])[0]
        now = f"**{r['result']}**" + (f": {', '.join(r['after']['new_checks'])}" if r["after"]["new_checks"] else "")
        was = r["before_result"] + (f": {', '.join(r['before']['new_checks'])}" if r["before"]["new_checks"] else "")
        lines.append(f"| {r['name']} | {r['what']} | {expect} | {was} | {now}{' (' + moved + ')' if moved else ''} | {said} |")
    return lines


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--problem", default="ledger")
    ap.add_argument("--stack", default="go")
    ap.add_argument("--run", help="a finished, clean run to plant drift on")
    ap.add_argument("--out", default=str(R.ROOT / "evals" / "runs" / "_conflicts"))
    args = ap.parse_args()
    folder, problem = R.load_problem(args.problem)
    module = R.load_variant(folder, "conflicts")
    out = Path(args.out).resolve()
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    global ENV
    ENV = R.check_env(problem["stacks"][args.stack], out)

    # ---- conflicts on the seed
    work = out / "seed"
    work.mkdir()
    repo = R.setup(args.problem, args.stack, work)
    seed_before, seed_after = both(work, repo)
    seed_noise = sorted(f"{c} {s}" for c, s in failing(seed_after) if c[0] == "C" or c == "A8")
    conflict_rows = []
    for case in module.CONFLICTS:
        work = out / case["name"]
        work.mkdir()
        repo = R.setup(args.problem, args.stack, work)
        case["apply"](repo)
        human_commit(repo, "docs: revise the requirements, the contracts and the plan")
        conflict_rows.append(row_of(case, seed_before, seed_after, work, repo))
        shutil.rmtree(repo, ignore_errors=True)

    # ---- drift on a finished build
    drift_rows, build_noise, build = [], [], None
    if args.run:
        run_dir = Path(args.run).resolve()
        build = run_dir.name

        def copy(name):
            work = out / name
            work.mkdir()
            repo = work / "repo"
            shutil.copytree(run_dir / "repo", repo, symlinks=True)
            R.git(repo, "worktree", "prune")
            R.git(repo, "reset", "-q", "--hard")
            R.git(repo, "checkout", "-q", "main")
            # A run made before the consistency checks existed: a person turns them on.
            wanted = (folder / "stacks" / args.stack / ".aqv.yml").read_text()
            if (repo / ".aqv.yml").read_text() != wanted:
                (repo / ".aqv.yml").write_text(wanted)
                human_commit(repo, "chore: turn on the consistency checks")
            return work, repo

        work, repo = copy("build")
        base_before, base_after = both(work, repo)
        build_noise = sorted(f"{c} {s}: {x['summary']}" for x in base_after["results"]
                             for c, s in [(x["check"], x["subject"])]
                             if x["verdict"] in ("fail", "error") and (c[0] == "C" or c == "A8"))
        shutil.rmtree(repo, ignore_errors=True)
        for case in module.DRIFTS:
            work, repo = copy(case["name"])
            case["apply"](repo)
            human_commit(repo, case["message"], case.get("trailer"))
            drift_rows.append(row_of(case, base_before, base_after, work, repo))
            shutil.rmtree(repo, ignore_errors=True)

    def count(rows, kind, key, good):
        return sum(1 for r in rows if r["kind"] == kind and r[key] == good), sum(1 for r in rows if r["kind"] == kind)

    summary = {"build": build, "seed_false_alarms": seed_noise, "build_false_alarms": build_noise,
               "conflicts": conflict_rows, "drift": drift_rows}
    (out / "conflicts.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    lines = [f"# Conflicts and drift: {args.problem} · {args.stack}", "",
             "## Conflicts planted before any code exists", ""]
    cb, n = count(conflict_rows, "targeted", "before_result", "caught")
    ca, _ = count(conflict_rows, "targeted", "result", "caught")
    pa, pn = count(conflict_rows, "probe", "result", "caught")
    lines += [f"- Conflicts a check is written for: **{ca} of {n} caught** (before: {cb} of {n})",
              f"- Probes (the conflict is in the meaning of two sentences): **{pa} of {pn} caught**",
              f"- False alarms on the unedited problem: {len(seed_noise)}" + (f" ({'; '.join(seed_noise)})" if seed_noise else ""), ""]
    lines += table(conflict_rows, "What the people wrote")
    if drift_rows:
        db, n = count(drift_rows, "targeted", "before_result", "caught")
        da, _ = count(drift_rows, "targeted", "result", "caught")
        ctl, cn = count(drift_rows, "control", "result", "clean")
        lines += ["", f"## Drift planted on a finished build ({build})", "",
                  f"- Changes a check is written for: **{da} of {n} caught** (before: {db} of {n})",
                  f"- Controls that stayed clean: {ctl} of {cn}",
                  f"- False alarms from the new checks on the finished build itself: {len(build_noise)}"
                  + ("".join(f"\n  - {x}" for x in build_noise)), ""]
        lines += table(drift_rows, "What a person changed after the build")
    (out / "conflicts.md").write_text("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines))


if __name__ == "__main__":
    main()
