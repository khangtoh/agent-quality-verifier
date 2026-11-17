"""Copies what is worth keeping from evals/runs/ into evals/results/, which is committed.

    .venv/bin/python evals/keep.py [RUN_NAME ...]     # default: every run, and _conflicts

Kept: the scores, faults.md, redteam.md, oracle.xml, meta.json, each final check's pages and
results.json, each watch folder's live.html, state, timeline and per-commit pages, the agent's final
message, and for each red-team attempt its final check, what it changed and its own report.
Left out: the workspace (a git repository), the signing key, binaries, coverage and the agent log,
which holds the agent session's own metadata. Local paths are made relative to the repository.

A run with red-team attempts also keeps what `evals/redteam.py replay` needs to judge them again
without an agent (see docs/redteam.md):
    base.bundle                      the run's workspace history: every branch, signed commits as made
    allowed_signers                  the public half of the run's signing key, to verify those signatures
    redteam/<defect>/attack.bundle   the commits the attempt added, on the branches it added them to
    redteam/<defect>/attack.json     where the attempt started, its branches, and the recorded verdict
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS, OUT = ROOT / "evals" / "runs", ROOT / "evals" / "results"


def copy(src, dst):
    if not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.suffix in (".json", ".jsonl", ".md", ".txt", ".html", ".xml", ".diff"):
        dst.write_text(src.read_text().replace(str(ROOT) + "/", ""))
    else:
        shutil.copy2(src, dst)


def final_message(log):
    final = None
    for line in log.read_text().splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "result":
            final = event.get("result")
    return final


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


def branches(repo):
    return dict(line.split() for line in git(repo, "for-each-ref", "--format=%(refname) %(objectname)",
                                             "refs/heads").splitlines())


def keep_attacks(run, dst):
    """The red-team attempts as git bundles, so they can be judged again on any machine."""
    recorded = {r["name"]: r for r in json.loads((run / "redteam.json").read_text())["attempts"]}
    git(run / "repo", "bundle", "create", str(dst / "base.bundle"), "--all")
    pub = (run / "keys" / "allowed_signers").read_text()
    assert "PRIVATE KEY" not in pub
    (dst / "allowed_signers").write_text(pub)
    base_refs = branches(run / "repo")
    for name, row in recorded.items():
        repo = run / "redteam" / name / "repo"
        start = json.loads((run / "redteam" / name / "job.json").read_text())["start"]
        moved = {ref: sha for ref, sha in branches(repo).items() if base_refs.get(ref) != sha}
        out = dst / "redteam" / name
        out.mkdir(parents=True, exist_ok=True)
        if moved:
            git(repo, "bundle", "create", str(out / "attack.bundle"), *moved, "--not", start)
        (out / "attack.json").write_text(json.dumps({
            "defect": name, "start": start, "main": git(repo, "rev-parse", "main").strip(), "branches": moved,
            "recorded": {k: row.get(k) for k in ("outcome", "why", "defect_built", "green", "tells_failed",
                                                  "oracle_failed", "new_checks", "statuses_moved", "minutes")}},
            indent=2) + "\n")


def keep(run):
    dst = OUT / run.name
    shutil.rmtree(dst, ignore_errors=True)
    if run.name == "_conflicts":
        for name in ("conflicts.md", "conflicts.json"):
            copy(run / name, dst / name)
        return
    for f in run.iterdir():
        if f.is_file() and (re.match(r"(score.*|faults|redteam)\.(md|json)$", f.name) or f.name in ("meta.json", "oracle.xml")):
            copy(f, dst / f.name)
    for d in sorted(p for p in run.iterdir() if p.is_dir()):
        if d.name.startswith("final") and d.name != "final-tree":
            for name in ("review.html", "report.html", "report.txt", "results.json"):
                copy(d / name, dst / d.name / name)
        elif d.name == "redteam":
            for attempt in sorted(a for a in d.iterdir() if a.is_dir() and not a.name.startswith("_")):
                for name in ("review.html", "report.html", "report.txt", "results.json"):
                    copy(attempt / "final" / name, dst / d.name / attempt.name / "final" / name)
                for name in ("changes.diff", "agent-final-message.md", "oracle.xml"):
                    copy(attempt / name, dst / d.name / attempt.name / name)
        elif d.name.startswith("live"):
            for name in ("live.html", "state.md", "state.json", "timeline.jsonl"):
                copy(d / name, dst / d.name / name)
            for snap in sorted((d / "snap").glob("*")):
                for name in ("review.html", "report.html"):
                    copy(snap / name, dst / d.name / "snap" / snap.name / name)
    if (run / "redteam.json").exists():
        keep_attacks(run, dst)
    if (run / "agent.log").exists() and (text := final_message(run / "agent.log")):
        (dst / "agent-final-message.md").write_text(
            "# The agent's final message\n\nCopied from the run's agent log, which is not committed.\n\n---\n\n"
            + text.strip() + "\n")


def main():
    names = sys.argv[1:] or sorted(p.name for p in RUNS.iterdir() if p.is_dir())
    for name in names:
        keep(RUNS / name)
        print("kept", name)


if __name__ == "__main__":
    main()
