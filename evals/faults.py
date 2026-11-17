#!/usr/bin/env python3
"""Plants known faults in a finished run and asks whether the verifier notices each one.

    .venv/bin/python evals/faults.py --run evals/runs/<name> [--only shadow-column,lineage-swap]

The run should be one where every requirement is Sync and the held-out tests pass. Each fault is
applied to its own copy of the run's repository, as a signed agent commit on a properly named
branch merged into main, so that the only thing wrong is the fault itself. The copy is then
checked the same way as the original, and the held-out tests are run against it.

A fault is **caught** when every check it expects newly fails. For a probe (no expected check), it
is caught when any check newly fails. Writes faults.json and faults.md into the run folder.
"""
import argparse
import importlib.util
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run as R  # noqa: E402

SKIP = "T7,A7"  # the slow checks; none of the seeded faults is aimed at them


def failing(results):
    return {(x["check"], x["subject"]) for x in results["results"] if x["verdict"] in ("fail", "error")}


def check_and_judge(work, repo, folder, conf, env):
    tree, results = R.final_check(work, repo, work / "check", SKIP, env)
    try:
        oracle, why = R.run_oracle(work, tree, folder, conf, work / "oracle.xml", env)
    finally:
        R.git(repo, "worktree", "remove", "--force", str(tree), check=False)
    broken = sorted(n for n, (ok, _) in (oracle or {}).items() if not ok)
    return results, (why or broken)


def plant(repo, fault):
    branch = f"fix/{fault['refs'] or 'AC-led-001'}-{fault['name']}"
    R.git(repo, "reset", "-q", "--hard")
    R.git(repo, "checkout", "-q", "main")
    R.git(repo, "checkout", "-q", "-b", branch)
    fault["apply"](repo)
    R.git(repo, "add", "-A")
    args = ["commit", "-q", "-m", fault["subject"]]
    if fault["refs"]:
        args += ["--trailer", f"Refs: {fault['refs']}"]
    R.git(repo, *args, "--trailer", "Co-Authored-By: Claude <noreply@anthropic.com>")
    R.git(repo, "checkout", "-q", "main")
    R.git(repo, "merge", "-q", "--no-ff", branch, "-m", f"Merge branch '{branch}'")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    run_dir = Path(args.run).resolve()
    meta = json.loads((run_dir / "meta.json").read_text())
    folder, problem = R.load_problem(meta["problem"])
    conf = problem["stacks"][meta["stack"]]
    env = R.check_env(conf, run_dir)  # one build folder for the run and every copy of it
    spec = importlib.util.spec_from_file_location("faults", folder / "faults.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    only = [x for x in args.only.split(",") if x]
    out_dir = run_dir / "faults"
    out_dir.mkdir(exist_ok=True)

    base_work = out_dir / "_baseline"
    shutil.rmtree(base_work, ignore_errors=True)
    base_work.mkdir()
    base_results, base_oracle = check_and_judge(base_work, run_dir / "repo", folder, conf, env)
    base_failing = failing(base_results)
    base_status = {r["id"]: r["status"] for r in base_results["requirements"]}
    rows = []
    for fault in module.FAULTS:
        if only and fault["name"] not in only:
            continue
        work = out_dir / fault["name"]
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir()
        repo = work / "repo"
        shutil.copytree(run_dir / "repo", repo, symlinks=True)
        R.git(repo, "worktree", "prune")
        row = {"name": fault["name"], "what": fault["what"], "expect": fault["expect"], "oracle_expected": fault["oracle"]}
        try:
            plant(repo, fault)
        except (LookupError, AssertionError) as err:
            row.update(result="not applicable", why=str(err))
            rows.append(row)
            print(f"{fault['name']}: not applicable ({err})")
            continue
        results, oracle = check_and_judge(work, repo, folder, conf, env)
        new = sorted(failing(results) - base_failing)
        new_checks = sorted({c for c, _ in new})
        status = {r["id"]: r["status"] for r in results["requirements"]}
        moved = {i: f"{base_status[i]} → {s}" for i, s in status.items() if s != base_status.get(i)}
        caught = bool(new_checks) and all(c in new_checks for c in fault["expect"])
        row.update(result="caught" if caught else "missed", new_failures=[f"{c} {s}" for c, s in new],
                   new_checks=new_checks, statuses_moved=moved,
                   oracle="could not run: " + oracle if isinstance(oracle, str) and oracle else
                   ("fails" if oracle and oracle != base_oracle else "passes"))
        rows.append(row)
        print(f"{fault['name']}: {row['result']} (new failures: {', '.join(new_checks) or 'none'}; oracle {row['oracle']})")
        shutil.rmtree(repo, ignore_errors=True)

    judged = [r for r in rows if r["result"] != "not applicable"]
    targeted = [r for r in judged if r["expect"]]
    probes = [r for r in judged if not r["expect"]]
    only_verifier = [r for r in judged if r["result"] == "caught" and r.get("oracle") == "passes"]
    summary = {"baseline_failing": sorted(f"{c} {s}" for c, s in base_failing), "baseline_oracle_failures": base_oracle,
               "targeted": len(targeted), "targeted_caught": sum(r["result"] == "caught" for r in targeted),
               "probes": len(probes), "probes_caught": sum(r["result"] == "caught" for r in probes),
               "caught_where_held_out_tests_pass": len(only_verifier), "faults": rows}
    (run_dir / "faults.json").write_text(json.dumps(summary, indent=2))
    lines = [f"# Seeded faults: {meta['problem']} · {meta['stack']}", "",
             f"- Faults with a check written for them: **{summary['targeted_caught']} of {summary['targeted']} caught**",
             f"- Probes (behaviour changes only the agent's own tests can notice): "
             f"**{summary['probes_caught']} of {summary['probes']} caught**",
             f"- Caught by the verifier while the held-out black-box tests still pass: {len(only_verifier)}", ""]
    if base_failing or base_oracle:
        lines += ["The run was not clean before any fault was planted, so read the results with care: "
                  f"{len(base_failing)} check failure(s), held-out tests: {base_oracle or 'pass'}.", ""]
    lines += ["| Fault | What the agent did | Expected | Newly failing | Statuses | Held-out tests | Result |",
              "|---|---|---|---|---|---|---|"]
    for r in rows:
        if r["result"] == "not applicable":
            lines.append(f"| {r['name']} | {r['what']} | {', '.join(r['expect']) or 'probe'} | - | - | - | not applicable: {r['why']} |")
            continue
        moved = "; ".join(f"{i} {m}" for i, m in r["statuses_moved"].items()) or "-"
        lines.append(f"| {r['name']} | {r['what']} | {', '.join(r['expect']) or 'probe'} | "
                     f"{', '.join(r['new_checks']) or 'none'} | {moved} | {r['oracle']} | **{r['result']}** |")
    (run_dir / "faults.md").write_text("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines))


if __name__ == "__main__":
    main()
