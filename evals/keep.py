"""Copies what is worth keeping from evals/runs/ into evals/results/, which is committed.

    .venv/bin/python evals/keep.py [RUN_NAME ...]     # default: every run, and _conflicts

Kept: the scores, faults.md, oracle.xml, meta.json, each final check's pages and results.json, each
watch folder's live.html, state, timeline and per-commit pages, and the agent's final message.
Left out: the workspace (a git repository), the signing key, binaries, coverage and the agent log,
which holds the agent session's own metadata. Local paths are made relative to the repository.
"""
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS, OUT = ROOT / "evals" / "runs", ROOT / "evals" / "results"


def copy(src, dst):
    if not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.suffix in (".json", ".jsonl", ".md", ".txt", ".html", ".xml"):
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


def keep(run):
    dst = OUT / run.name
    shutil.rmtree(dst, ignore_errors=True)
    if run.name == "_conflicts":
        for name in ("conflicts.md", "conflicts.json"):
            copy(run / name, dst / name)
        return
    for f in run.iterdir():
        if f.is_file() and (re.match(r"(score.*|faults)\.(md|json)$", f.name) or f.name in ("meta.json", "oracle.xml")):
            copy(f, dst / f.name)
    for d in sorted(p for p in run.iterdir() if p.is_dir()):
        if d.name.startswith("final") and d.name != "final-tree":
            for name in ("review.html", "report.html", "report.txt", "results.json"):
                copy(d / name, dst / d.name / name)
        elif d.name.startswith("live"):
            for name in ("live.html", "state.md", "state.json", "timeline.jsonl"):
                copy(d / name, dst / d.name / name)
            for snap in sorted((d / "snap").glob("*")):
                for name in ("review.html", "report.html"):
                    copy(snap / name, dst / d.name / "snap" / snap.name / name)
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
