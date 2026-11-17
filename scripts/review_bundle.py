"""Builds the review bundle that CI uploads: the pages of every eval run kept in evals/results/,
written again by the verifier built from this commit, behind one index page.

    python scripts/review_bundle.py --out review-bundle [--summary FILE]

Each run's review.html, report.html and live.html are rendered from its recorded results.json and
timeline.jsonl with `bin/aqv render`, so the bundle shows what the current verifier says about the
recorded results, and the script fails if the verifier can no longer read one of them.
--summary appends a Markdown table of the runs (CI passes $GITHUB_STEP_SUMMARY).
"""
import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "evals" / "results"
AQV = ROOT / "bin" / "aqv"
AGENTS = {"claude": "Claude Code", "codex": "Codex"}
CELLS = [("confirmed", "Sync and working"), ("false_assurance", "False assurance"), ("caught", "Caught"),
         ("unproven_but_working", "Unproven but working")]

CSS = """
:root { --bg: #f7f6f2; --card: #ffffff; --fg: #1d1c1a; --muted: #6a6760; --line: #dedbd3; --link: #1f5fa8;
        --bad: #b3261e; --ok: #1e6b3a; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #171614; --card: #201f1c; --fg: #ecebe6; --muted: #a09c93; --line: #37352f; --link: #8ab8f0;
          --bad: #f2a29b; --ok: #8fd3a5; color-scheme: dark; }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--fg); font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 920px; margin: 0 auto; padding: 32px max(16px, env(safe-area-inset-right, 0px)) 64px max(16px, env(safe-area-inset-left, 0px)); display: grid; gap: 20px; }
h1 { font-size: 28px; line-height: 1.2; margin: 0; text-wrap: balance; }
h2 { font-size: 19px; margin: 0; text-wrap: balance; }
p { margin: 0; max-width: 68ch; }
a { color: var(--link); }
code { font: 14px ui-monospace, "SF Mono", Menlo, monospace; }
.muted { color: var(--muted); }
.run { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 18px 20px; display: grid; gap: 12px; min-width: 0; }
.facts { display: flex; flex-wrap: wrap; gap: 8px 24px; margin: 0; }
.facts div { display: grid; }
.facts dt { font-size: 12px; letter-spacing: .04em; text-transform: uppercase; color: var(--muted); }
.facts dd { margin: 0; font-size: 20px; font-variant-numeric: tabular-nums; }
.facts dd.bad { color: var(--bad); }
.facts dd.ok { color: var(--ok); }
.links { display: flex; flex-wrap: wrap; gap: 6px 18px; margin: 0; padding: 0; list-style: none; }
.more { font-size: 14px; }
"""


def esc(text):
    return html.escape(str(text), quote=True)


def render_all(out):
    """Every folder with recorded results gets its pages written again by this commit's verifier."""
    folders = sorted({p.parent for name in ("results.json", "timeline.jsonl") for p in out.rglob(name)})
    for folder in folders:
        done = subprocess.run([str(AQV), "render", str(folder)], capture_output=True, text=True)
        if done.returncode != 0:
            raise SystemExit(f"aqv render failed on {folder.relative_to(out)}: {(done.stdout + done.stderr).strip()[-400:]}")
    return len(folders)


def problem_title(name):
    """The problem's title from its problem.yml, read without a YAML library."""
    path = ROOT / "evals" / "problems" / name / "problem.yml"
    found = re.search(r"^title:\s*(.+)$", path.read_text(), re.M) if path.exists() else None
    return found.group(1).strip() if found else name.capitalize()


def title_of(meta):
    parts = [problem_title(meta.get("problem", "")), {"go": "Go", "rust": "Rust"}.get(meta.get("stack"), meta.get("stack", ""))]
    if meta.get("agent"):
        parts += [AGENTS.get(meta["agent"], meta["agent"]), meta.get("arm", "")]
    else:
        parts.append("no agent")
    if meta.get("variant"):
        parts.append(f"variant {meta['variant']}")
    return " · ".join(p for p in parts if p)


def load(path):
    return json.loads(path.read_text()) if path.exists() else None


def run_of(folder):
    meta = load(folder / "meta.json") or {}
    score, faults = load(folder / "score.json"), load(folder / "faults.json")
    links = [(label, rel) for label, rel in [
        ("Review", "final/review.html"), ("Requirement report", "final/report.html"), ("Live view", "live/live.html"),
        ("Score", "score.md"), ("Seeded faults", "faults.md"), ("Agent's final message", "agent-final-message.md"),
    ] if (folder / rel).exists()]
    more = []
    for path in sorted(folder.glob("score-*.md")):
        label = path.stem[len("score-"):]
        review = f"final-{label}/review.html"
        more.append((label, review if (folder / review).exists() else path.name))
    return {"name": folder.name, "title": title_of(meta), "minutes": meta.get("minutes"),
            "cells": (score or {}).get("cells"), "faults": faults, "links": links, "more": more}


def faults_text(faults):
    if not faults:
        return ""
    return f"{faults['targeted_caught'] + faults['probes_caught']} of {faults['targeted'] + faults['probes']}"


def index_html(runs, commit, others):
    body = ["<h1>Eval runs for review</h1>",
            f"<p class=\"muted\">Each run's pages were written by the verifier built from commit <code>{esc(commit)}</code>, "
            "from the results recorded when the run was made. Start with a run's <b>Review</b> page.</p>"]
    for r in runs:
        facts = []
        if r["cells"]:
            for key, label in CELLS:
                tone = " class=\"bad\"" if key == "false_assurance" and r["cells"][key] else ""
                facts.append(f"<div><dt>{label}</dt><dd{tone}>{r['cells'][key]}</dd></div>")
        if r["faults"]:
            facts.append(f"<div><dt>Seeded faults caught</dt><dd>{faults_text(r['faults'])}</dd></div>")
        if r["minutes"] is not None:
            facts.append(f"<div><dt>Agent time</dt><dd>{r['minutes']} min</dd></div>")
        links = "".join(f"<li><a href=\"{esc(r['name'])}/{esc(rel)}\">{esc(label)}</a></li>" for label, rel in r["links"])
        more = ""
        if r["more"]:
            more = "<p class=\"more muted\">Other scorings of this run: " + ", ".join(
                f"<a href=\"{esc(r['name'])}/{esc(rel)}\">{esc(label)}</a>" for label, rel in r["more"]) + "</p>"
        body.append(f"<section class=\"run\"><h2>{esc(r['title'])}</h2><p class=\"muted\"><code>{esc(r['name'])}</code></p>"
                    + (f"<dl class=\"facts\">{''.join(facts)}</dl>" if facts else "")
                    + f"<ul class=\"links\">{links}</ul>{more}</section>")
    if others:
        items = "".join(f"<li><a href=\"{esc(rel)}\">{esc(label)}</a></li>" for label, rel in others)
        body.append(f"<section class=\"run\"><h2>Conflicting documents</h2><ul class=\"links\">{items}</ul></section>")
    return ("<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            f"<title>Eval runs for review</title><style>{CSS}</style></head>\n<body><main>\n"
            + "\n".join(body) + "\n</main></body></html>\n")


def summary_md(runs, commit):
    lines = ["## Eval runs for review", "",
             f"Pages written by the verifier built from `{commit}`. Download the **review-pages** artifact of this run "
             "and open `index.html`.", "",
             "| Run | " + " | ".join(label for _, label in CELLS) + " | Seeded faults caught |",
             "|---|" + "---|" * (len(CELLS) + 1)]
    for r in runs:
        cells = [str(r["cells"][key]) if r["cells"] else "-" for key, _ in CELLS]
        lines.append(f"| {r['title']} (`{r['name']}`) | " + " | ".join(cells) + f" | {faults_text(r['faults']) or '-'} |")
    return "\n".join(lines) + "\n"


def broken_links(page):
    bad = []
    for href in re.findall(r'href="([^"#]+)', page.read_text()):
        if not href.startswith(("http", "mailto")) and not (page.parent / href).resolve().exists():
            bad.append(href)
    return bad


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "review-bundle"))
    ap.add_argument("--summary", help="append a Markdown table of the runs to this file")
    args = ap.parse_args()
    if not AQV.exists():
        raise SystemExit("build the verifier first: go build -o bin/aqv ./cmd/aqv")
    out = Path(args.out).resolve()
    shutil.rmtree(out, ignore_errors=True)
    shutil.copytree(RESULTS, out)
    rendered = render_all(out)
    commit = os.environ.get("GITHUB_SHA") or subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    commit = commit[:7] or "unknown"
    runs = [run_of(folder) for folder in sorted(out.iterdir()) if (folder / "meta.json").exists()]
    others = [(label, rel) for label, rel in [("Results page", "conflicts-page/index.html"),
                                              ("Planted conflicts and drift", "_conflicts/conflicts.md")]
              if (out / rel).exists()]
    index = out / "index.html"
    index.write_text(index_html(runs, commit, others))
    bad = broken_links(index)
    if bad:
        raise SystemExit("broken links in the index: " + ", ".join(bad))
    if args.summary:
        with open(args.summary, "a") as f:
            f.write(summary_md(runs, commit))
    print(f"{len(runs)} runs, {rendered} folders rendered, written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
