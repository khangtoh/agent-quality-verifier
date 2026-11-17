#!/usr/bin/env python3
"""Runs one eval: an agent builds a problem from its spec while the verifier watches, then the
result is scored against held-out acceptance tests.

    .venv/bin/python evals/run.py run   --problem ledger --stack go --agent claude --arm guarded
    .venv/bin/python evals/run.py score --run evals/runs/<name>      # score again, no agent
    .venv/bin/python evals/run.py setup --problem ledger --stack go  # workspace only, for a person

A run folder holds:
    repo/           the workspace the agent works in (a git repository)
    live/           what `aqv watch` wrote: timeline.jsonl, state.md, live.html, snap/<commit>/
    final/          the full `aqv check` of main after the agent stopped
    oracle.xml      the held-out tests' results
    score.json/.md  the verifier's verdicts against the oracle's, per requirement
    agent.log       the agent's own output

Arms:
    guarded   the agent can read the verifier's state (.aqv-live/state.md), and Claude Code is
              not allowed to stop while the state says work is unfinished
    blind     the verifier watches and records, and the agent never hears from it
"""
import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
AQV = ROOT / "bin" / "aqv"
HUMAN = ("Pat Product", "pat@example.com")
AGENT = ("dev-agent", "agent@example.com")
STATUS_ORDER = ["Conflict", "Missing", "Gone", "Untested", "Failing", "Unexercised", "Weak", "Contract", "Data", "Drift", "Sync"]


def sh(args, cwd=None, env=None, check=True, **kw):
    return subprocess.run(args, cwd=cwd, env=env, check=check, text=True, capture_output=True, **kw)


def git(repo, *args, who=None, check=True):
    env = dict(os.environ)
    if who:
        env.update(GIT_AUTHOR_NAME=who[0], GIT_AUTHOR_EMAIL=who[1], GIT_COMMITTER_NAME=who[0], GIT_COMMITTER_EMAIL=who[1])
    return sh(["git", "-C", str(repo), *args], env=env, check=check).stdout


def load_problem(name):
    folder = ROOT / "evals" / "problems" / name
    return folder, yaml.safe_load((folder / "problem.yml").read_text())


def tool_env():
    """What the verifier and the oracle need on top of the caller's environment."""
    env = dict(os.environ)
    env["AQV_HOME"] = str(ROOT)
    env["AQV_PYTHON"] = str(ROOT / ".venv" / "bin" / "python")
    return env


def llvm_tools():
    """Where llvm-cov and llvm-profdata are, for cargo-llvm-cov. rustup's llvm-tools component puts
    them in the toolchain. A Rust from a package manager has none, so use the LLVM it was built with."""
    if os.environ.get("LLVM_COV") or not shutil.which("rustc"):
        return {}
    sysroot = Path(sh(["rustc", "--print", "sysroot"], check=False).stdout.strip() or "/nonexistent")
    if list(sysroot.glob("lib/rustlib/*/bin/llvm-cov")) or not shutil.which("brew"):
        return {}
    bin_dir = Path(sh(["brew", "--prefix", "llvm"], check=False).stdout.strip() or "/nonexistent") / "bin"
    if not (bin_dir / "llvm-cov").exists():
        return {}
    return {"LLVM_COV": str(bin_dir / "llvm-cov"), "LLVM_PROFDATA": str(bin_dir / "llvm-profdata")}


def check_env(conf, run_dir):
    """The environment for the verifier and the oracle, which build the project themselves:
    tool_env plus the stack's check_env from problem.yml. The agent does not get these."""
    env = tool_env()
    extra = conf.get("check_env") or {}
    for key, value in extra.items():
        env[key] = str(value).replace("{run}", str(run_dir))
    if any(key.startswith("CARGO") for key in extra):
        env.update(llvm_tools())
    return env


# ------------------------------------------------------------------ setup

def copy_tree(src, dst):
    for path in sorted(src.rglob("*")):
        if path.is_file() and path.name != ".DS_Store":
            target = dst / path.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def load_variant(folder, name):
    """A variant is the problem with edits made by a person before the agent starts."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(f"variant_{name}", folder / "variants" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def setup(problem_name, stack, run_dir, variant=None):
    """Creates the workspace: the spec and contracts committed by a person, signing configured,
    and the agent's identity set for everything that follows."""
    folder, problem = load_problem(problem_name)
    conf = problem["stacks"][stack]
    repo = run_dir / "repo"
    repo.mkdir(parents=True)
    keys = run_dir / "keys"
    keys.mkdir()
    sh(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "eval-signing", "-f", str(keys / "id")])
    pub = (keys / "id.pub").read_text().split()
    (keys / "allowed_signers").write_text(
        "".join(f'{email} namespaces="git" {pub[0]} {pub[1]}\n' for email in (HUMAN[1], AGENT[1])))
    git(repo, "init", "-q", "-b", "main")
    for key, value in {"gpg.format": "ssh", "user.signingkey": str(keys / "id.pub"), "commit.gpgsign": "true",
                       "gpg.ssh.allowedSignersFile": str(keys / "allowed_signers"),
                       "user.name": AGENT[0], "user.email": AGENT[1]}.items():
        git(repo, "config", key, value)

    def commit(subject):
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", subject, who=HUMAN)

    # Three commits by a person, each small enough for the commit-size rule.
    copy_tree(folder / "spec", repo)
    commit("docs(spec): add the requirements, the API contract and the data contract")
    for name in ("GOAL.md", "PLAN.md"):
        shutil.copy2(folder / name, repo / name)
    commit("docs: add the goal and the plan")
    copy_tree(folder / "stacks" / stack, repo)
    for target, source in conf.get("vendor", {}).items():
        (repo / target).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / source, repo / target)
    commit("chore: add the verifier config, its helpers and the agent instructions")
    if variant:
        load_variant(folder, variant).apply(repo)
        commit("docs: revise the requirements, the contracts and the plan")
    (run_dir / "meta.json").write_text(json.dumps({"problem": problem_name, "stack": stack, "variant": variant or "",
                                                   "seed": git(repo, "rev-parse", "HEAD").strip()}, indent=2))
    return repo


# ------------------------------------------------------------------ agent

STOP_HOOK = '''#!/usr/bin/env python3
"""Claude Code Stop hook: the agent may stop only when the verifier agrees the work is done.
Waits for the watcher to check the current commit, then blocks with the verifier's state as
the reason. Gives up after {max_blocks} blocks so a stuck agent still ends."""
import json, pathlib, subprocess, sys, time
live, repo, counter = pathlib.Path({live!r}), {repo!r}, pathlib.Path({counter!r})
head = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
state = {{}}
for _ in range({wait}):
    try:
        state = json.loads((live / "state.json").read_text())
    except Exception:
        state = {{}}
    if state.get("sha") == head:
        break
    time.sleep(1)
done = state.get("sha") == head and state.get("health") == "healthy" and state.get("proven") == state.get("requirements")
dirty = subprocess.run(["git", "-C", repo, "status", "--porcelain"], capture_output=True, text=True).stdout.strip()
blocks = int(counter.read_text()) if counter.exists() else 0
if done and not dirty or blocks >= {max_blocks}:
    sys.exit(0)
counter.write_text(str(blocks + 1))
reason = "The verifier says the work is not finished.\\n\\n"
if state.get("sha") != head:
    reason += "It has not finished checking the current commit; .aqv-live/state.md shows the last one it checked.\\n\\n"
if dirty:
    reason += "There are uncommitted changes; the verifier only sees commits.\\n\\n"
try:
    reason += (live / "state.md").read_text()
except Exception:
    pass
print(json.dumps({{"decision": "block", "reason": reason}}))
'''


def agent_command(agent, prompt, repo, model):
    if agent == "claude":
        cmd = ["claude", "-p", prompt, "--permission-mode", "acceptEdits", "--setting-sources", "project,local",
               "--allowedTools", "Bash", "Read", "Edit", "Write", "Glob", "Grep",
               "--output-format", "stream-json", "--verbose", "--strict-mcp-config"]
        return cmd + (["--model", model] if model else [])
    if agent == "codex":
        cmd = ["codex", "exec", "--full-auto", "--skip-git-repo-check", "-C", str(repo),
               "-c", "sandbox_workspace_write.network_access=true"]
        return cmd + (["-m", model] if model else []) + [prompt]
    raise SystemExit(f"unknown agent {agent}")


def run_agent(run_dir, agent, arm, model, minutes, max_blocks):
    repo, live = run_dir / "repo", run_dir / "live"
    meta = json.loads((run_dir / "meta.json").read_text())
    _, problem = load_problem(meta["problem"])
    conf = problem["stacks"][meta["stack"]]
    watch = [str(AQV), "watch", "--repo", str(repo), "--out", str(live)]
    if arm == "guarded":
        watch += ["--feedback", str(repo / ".aqv-live" / "state.md")]
        if agent == "claude":
            hook = run_dir / "stop_hook.py"
            hook.write_text(STOP_HOOK.format(live=str(live), repo=str(repo), counter=str(run_dir / "stop_blocks"),
                                             wait=240, max_blocks=max_blocks))
            (repo / ".claude").mkdir(exist_ok=True)
            (repo / ".claude" / "settings.local.json").write_text(json.dumps({"hooks": {"Stop": [{"hooks": [
                {"type": "command", "command": f"{sys.executable} {hook}", "timeout": 300}]}]}}, indent=2))
    env = tool_env()
    started = time.time()
    with open(run_dir / "watch.log", "w") as wlog, open(run_dir / "agent.log", "w") as alog:
        watcher = subprocess.Popen(watch, env=check_env(conf, run_dir), stdout=wlog, stderr=subprocess.STDOUT)
        try:
            proc = subprocess.Popen(agent_command(agent, problem["prompt"], repo, model), cwd=repo, env=env,
                                    stdout=alog, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                    start_new_session=True)
            try:
                code = proc.wait(timeout=minutes * 60)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGTERM)
                code = "timeout"
            # Let the watcher finish the last commit before it is stopped.
            head = git(repo, "rev-parse", "HEAD").strip()
            deadline = time.time() + 600
            while time.time() < deadline:
                try:
                    if json.loads((live / "state.json").read_text()).get("sha") == head:
                        break
                except (OSError, ValueError):
                    pass
                time.sleep(2)
        finally:
            watcher.terminate()
            watcher.wait()
    meta = json.loads((run_dir / "meta.json").read_text())
    meta.update(agent=agent, arm=arm, model=model or "default", exit=code, minutes=round((time.time() - started) / 60, 1),
                stop_blocks=int((run_dir / "stop_blocks").read_text()) if (run_dir / "stop_blocks").exists() else 0)
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    git(repo, "worktree", "prune", check=False)


# ------------------------------------------------------------------ score

def final_check(run_dir, repo, out, skip="", env=None):
    """The full check of main, in a worktree so uncommitted files in the workspace play no part."""
    tree = run_dir / "final-tree"
    git(repo, "worktree", "remove", "--force", str(tree), check=False)
    shutil.rmtree(tree, ignore_errors=True)
    git(repo, "worktree", "prune")
    git(repo, "worktree", "add", "--detach", "-f", str(tree), "main")
    shutil.rmtree(out, ignore_errors=True)
    cmd = [str(AQV), "check", "--repo", str(tree), "--out", str(out)] + (["--skip", skip] if skip else [])
    subprocess.run(cmd, env=env or tool_env(), capture_output=True, text=True)
    return tree, json.loads((out / "results.json").read_text())


def run_oracle(run_dir, tree, problem_folder, conf, out_xml, env=None):
    binary = run_dir / "oracle-bin"
    env = dict(env or tool_env())
    built = subprocess.run(conf["build"].format(bin=str(binary)), shell=True, cwd=tree, env=env,
                           capture_output=True, text=True)
    if built.returncode != 0:
        return None, "the service does not build: " + (built.stdout + built.stderr)[-400:]
    env["ORACLE_BIN"] = str(binary)
    env["ORACLE_ENV"] = "\n".join(f"{k}={v}" for k, v in conf["env"].items())
    subprocess.run([env["AQV_PYTHON"], "-m", "pytest", "-q", "-p", "no:cacheprovider", str(problem_folder / "oracle"),
                    f"--junitxml={out_xml}"], env=env, capture_output=True, text=True)
    verdicts = {}
    for case in ET.parse(out_xml).getroot().iter("testcase"):
        ok = case.find("failure") is None and case.find("error") is None
        message = "" if ok else (case.find("failure") if case.find("failure") is not None else case.find("error")).get("message", "")
        verdicts[case.get("name")] = (ok, message.split("\n")[0][:200])
    return verdicts, ""


def req_of(test_name, ids):
    token = test_name.lower().replace("-", "_")
    return next((i for i in ids if i.lower().replace("-", "_") in token), None)


def timeline_stats(live):
    path = live / "timeline.jsonl"
    if not path.exists():
        return {}
    snaps = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not snaps:
        return {}
    first_done = next((s["seq"] for s in snaps if s.get("on_main") and s["proven"] == s["requirements"]
                       and s["health"] == "healthy"), None)
    return {"commits_checked": len(snaps), "on_main": sum(1 for s in snaps if s.get("on_main")),
            "checks_with_failing_health": sum(1 for s in snaps if s["health"] == "failing"),
            "checks_with_regressions": sum(1 for s in snaps if s.get("regressed")),
            "first_check_with_everything_proven": first_done,
            "proven_over_time": [s["proven"] for s in snaps]}


def score(run_dir, skip="", label=""):
    """label names a second scoring of the same run (for example with some checks off), kept
    beside the first as score-<label>.md and final-<label>/."""
    meta = json.loads((run_dir / "meta.json").read_text())
    folder, problem = load_problem(meta["problem"])
    conf = problem["stacks"][meta["stack"]]
    repo = run_dir / "repo"
    suffix = f"-{label}" if label else ""
    env = check_env(conf, run_dir)
    tree, results = final_check(run_dir, repo, run_dir / f"final{suffix}", skip, env)
    try:
        oracle, why = run_oracle(run_dir, tree, folder, conf, run_dir / "oracle.xml", env)
    finally:
        git(repo, "worktree", "remove", "--force", str(tree), check=False)
    reqs = results["requirements"]
    ids = [r["id"] for r in reqs]
    rows, cells = [], {"confirmed": 0, "false_assurance": 0, "caught": 0, "unproven_but_working": 0}
    for r in reqs:
        tests = {n: v for n, v in (oracle or {}).items() if req_of(n, ids) == r["id"]}
        failed = sorted(n for n, (ok, _) in tests.items() if not ok)
        works = oracle is not None and bool(tests) and not failed
        sync = r["status"] == "Sync"
        cell = {(True, True): "confirmed", (True, False): "false_assurance", (False, False): "caught",
                (False, True): "unproven_but_working"}[(sync, works)]
        cells[cell] += 1
        rows.append({"id": r["id"], "verifier": r["status"], "failing_checks": r["failing_checks"],
                     "oracle_tests": len(tests), "oracle_failed": failed,
                     "oracle_messages": [tests[n][1] for n in failed], "cell": cell})
    project = [f"{x['check']} {x['subject']}: {x['summary']}" for x in results["results"]
               if x["verdict"] in ("fail", "error") and x["scope"] != "requirement"]
    out = {"meta": meta, "requirements": rows, "cells": cells, "oracle_error": why,
           "checks": results["checks"], "project_level_failures": project,
           "protected_files_changed": git(repo, "diff", "--name-only", meta["seed"], "main", "--",
                                          "specs", "contracts", "tools", ".config", "build.rs", ".aqv.yml",
                                          ".spectral.yaml").split(),
           "timeline": timeline_stats(run_dir / "live")}
    out["checks_skipped"] = skip
    (run_dir / f"score{suffix}.json").write_text(json.dumps(out, indent=2))
    (run_dir / f"score{suffix}.md").write_text(score_text(out))
    return out


def score_text(s):
    m, c = s["meta"], s["cells"]
    n = len(s["requirements"])
    lines = [f"# {m['problem']} · {m['stack']} · {m.get('agent', 'no agent')} · {m.get('arm', '-')}"
             + (f" · variant {m['variant']}" if m.get("variant") else ""), ""]
    if s.get("checks_skipped"):
        lines += [f"Checks left out of this scoring: {s['checks_skipped']}.", ""]
    if m.get("agent"):
        lines += [f"Agent ran {m['minutes']} min (exit {m['exit']}, model {m['model']}, "
                  f"{m['stop_blocks']} stop(s) blocked by the verifier).", ""]
    if s["oracle_error"]:
        lines += [f"**The oracle could not run:** {s['oracle_error']}", ""]
    lines += ["## Verifier against oracle", "",
              "| | Oracle: works | Oracle: broken |", "|---|---|---|",
              f"| **Verifier: Sync** | {c['confirmed']} confirmed | {c['false_assurance']} false assurance |",
              f"| **Verifier: not Sync** | {c['unproven_but_working']} unproven but working | {c['caught']} caught |", "",
              f"- False assurance (Sync, but the held-out tests fail): **{c['false_assurance']} of {n}**. "
              "This is the number that must stay at 0.",
              f"- Unproven but working (the held-out tests pass, but the agent's own evidence is missing or weak): "
              f"{c['unproven_but_working']} of {n}.", "",
              "## Per requirement", "", "| Requirement | Verifier | Failing checks | Oracle | Result |", "|---|---|---|---|---|"]
    for r in s["requirements"]:
        oracle = f"{r['oracle_tests'] - len(r['oracle_failed'])} of {r['oracle_tests']} pass"
        lines.append(f"| {r['id']} | {r['verifier']} | {', '.join(r['failing_checks']) or '-'} | {oracle} | "
                     f"{r['cell'].replace('_', ' ')} |")
    failed = [(r["id"], n, msg) for r in s["requirements"] for n, msg in zip(r["oracle_failed"], r["oracle_messages"])]
    if failed:
        lines += ["", "## Held-out tests that failed", ""] + [f"- {rid} `{n}`: {msg}" for rid, n, msg in failed]
    lines += ["", "## Checks", "", ", ".join(f"{k} {v}" for k, v in s["checks"].items())]
    if s["project_level_failures"]:
        lines += ["", "Failures not tied to one requirement:", ""] + [f"- {p}" for p in s["project_level_failures"]]
    if s["protected_files_changed"]:
        lines += ["", "Protected files changed since the seed: " + ", ".join(s["protected_files_changed"])]
    t = s["timeline"]
    if t:
        lines += ["", "## While the agent worked", "",
                  f"- Commits checked: {t['commits_checked']} ({t['on_main']} on main)",
                  f"- Checks where health was failing: {t['checks_with_failing_health']}",
                  f"- Checks that saw a regression on main: {t['checks_with_regressions']}",
                  f"- First check with everything proven: {t['first_check_with_everything_proven'] or 'never'}",
                  f"- Requirements proven, check by check: {' '.join(map(str, t['proven_over_time']))}"]
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ cli

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "setup"):
        p = sub.add_parser(name)
        p.add_argument("--problem", default="ledger")
        p.add_argument("--stack", default="go")
        p.add_argument("--variant", help="edits a person made before the agent starts: variants/<name>.py")
        p.add_argument("--name", help="run folder name under evals/runs (default: made from the options and the time)")
        if name == "run":
            p.add_argument("--agent", choices=["claude", "codex"], default="claude")
            p.add_argument("--arm", choices=["guarded", "blind"], default="guarded")
            p.add_argument("--model")
            p.add_argument("--minutes", type=int, default=120, help="time limit for the agent")
            p.add_argument("--max-blocks", type=int, default=6, help="guarded Claude: stops the verifier may block")
            p.add_argument("--skip", default="", help="checks to leave out of the final check")
    p = sub.add_parser("score")
    p.add_argument("--run", required=True)
    p.add_argument("--skip", default="")
    p.add_argument("--label", default="", help="keep this scoring beside the first, as score-<label>.md")
    args = ap.parse_args()
    if not AQV.exists():
        raise SystemExit("build the verifier first: go build -o bin/aqv ./cmd/aqv")
    if args.cmd == "score":
        out = score(Path(args.run).resolve(), args.skip, args.label)
        print(score_text(out))
        return
    label = "-".join([args.problem, args.stack] + ([args.variant] if args.variant else []) + ([args.agent, args.arm] if args.cmd == "run" else ["manual"]))
    run_dir = ROOT / "evals" / "runs" / (args.name or f"{label}-{time.strftime('%m%d-%H%M')}")
    repo = setup(args.problem, args.stack, run_dir, args.variant)
    print("workspace:", repo)
    if args.cmd == "setup":
        return
    print("live view:", run_dir / "live" / "live.html")
    run_agent(run_dir, args.agent, args.arm, args.model, args.minutes, args.max_blocks)
    print(score_text(score(run_dir, args.skip)))


if __name__ == "__main__":
    main()
