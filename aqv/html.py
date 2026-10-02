"""HTML pages: one verifier run (report.html), and the whole demo (demo.html).

Both pages are static and self-contained: inline CSS, no scripts, so they open
straight from disk.
"""
from html import escape

from .engine import CHECKS

GOALS = [("T", "Tests prove the spec"), ("A", "The API matches its OpenAPI contract"),
         ("H", "Git follows the conventions")]

STATUS_TONE = {"Sync": "ok", "Drift": "warn", "Untested": "warn", "Unexercised": "warn", "Weak": "warn",
               "Missing": "muted", "Gone": "bad", "Failing": "bad", "Contract": "bad"}
STATUS_MEANS = {
    "Missing": "No commit references it", "Gone": "Its code was never written or was deleted",
    "Untested": "No tagged test", "Failing": "Tagged tests fail, or the suite won't load",
    "Unexercised": "Tests pass but don't run its code", "Weak": "Tests miss broken versions of its code",
    "Contract": "The API doesn't match the contract", "Drift": "Wording changed since it was implemented",
    "Sync": "Every check passes",
}
VERDICT_TONE = {"pass": "ok", "fail": "bad", "error": "bad", "skip": "muted", "not_covered": "warn",
                "not_run": "muted"}
VERDICT_LABEL = {"pass": "pass", "fail": "fail", "error": "error", "skip": "skip", "not_covered": "not covered",
                 "not_run": "not run"}

CSS = """
:root {
  --bg: #f6f7f6; --surface: #ffffff; --fg: #1b2226; --muted: #5a666b; --line: #dde2e1;
  --accent: #1d5c63; --code-bg: #eef1f0;
  --ok-fg: #1f6b4a; --ok-bg: #e1f1e8; --warn-fg: #8a5a00; --warn-bg: #fbefd6;
  --bad-fg: #a5332a; --bad-bg: #fbe3e0; --muted-fg: #5a666b; --muted-bg: #eceeed;
  --font-display: "Schibsted Grotesk", "Helvetica Neue", Arial, sans-serif;
  --font-body: "Source Sans 3", "Segoe UI", Roboto, Arial, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  --font-serif: "Source Serif 4", Georgia, "Times New Roman", serif;
  color-scheme: light;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #101517; --surface: #171f22; --fg: #e3e9ea; --muted: #99a6aa; --line: #2a3437;
    --accent: #7cc4c9; --code-bg: #1f292c;
    --ok-fg: #8fd9b2; --ok-bg: #183528; --warn-fg: #f0c46a; --warn-bg: #3a2d12;
    --bad-fg: #f3a198; --bad-bg: #41201d; --muted-fg: #99a6aa; --muted-bg: #222b2e;
    color-scheme: dark;
  }
}
:root[data-theme="dark"] {
  --bg: #101517; --surface: #171f22; --fg: #e3e9ea; --muted: #99a6aa; --line: #2a3437;
  --accent: #7cc4c9; --code-bg: #1f292c;
  --ok-fg: #8fd9b2; --ok-bg: #183528; --warn-fg: #f0c46a; --warn-bg: #3a2d12;
  --bad-fg: #f3a198; --bad-bg: #41201d; --muted-fg: #99a6aa; --muted-bg: #222b2e;
  color-scheme: dark;
}
* { box-sizing: border-box; }
html, body { margin: 0; }
body { background: var(--bg); color: var(--fg); font-family: var(--font-body); font-size: 16px; line-height: 1.55; }
.page { max-width: 1160px; margin: 0 auto; padding-inline: 20px; padding-block: 36px 64px; display: grid; gap: 44px; }
section { display: grid; gap: 16px; min-width: 0; }
h1, h2, h3 { font-family: var(--font-display); margin: 0; line-height: 1.15; text-wrap: balance; }
h1 { font-size: clamp(28px, 5vw, 40px); }
h2 { font-size: 24px; }
h3 { font-size: 17px; }
p { margin: 0; }
a { color: var(--accent); }
code { font-family: var(--font-mono); font-size: 0.85em; background: var(--code-bg); padding: 0.08em 0.35em; border-radius: 4px; overflow-wrap: anywhere; }
.eyebrow { font-family: var(--font-mono); font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); }
.lede { font-size: 19px; max-width: 70ch; }
.muted { color: var(--muted); }
.small { font-size: 14px; }
header.top { display: grid; gap: 12px; }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }
.stat { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 16px 18px; display: grid; gap: 4px; min-width: 0; }
.stat b { font-family: var(--font-display); font-size: 28px; font-variant-numeric: tabular-nums; }
.stat span { font-size: 14px; color: var(--muted); }
.chip { display: inline-flex; align-items: center; height: 22px; padding: 0 8px; border-radius: 5px; font-family: var(--font-mono); font-size: 12px; font-weight: 600; white-space: nowrap; }
.chip.ok { color: var(--ok-fg); background: var(--ok-bg); }
.chip.warn { color: var(--warn-fg); background: var(--warn-bg); }
.chip.bad { color: var(--bad-fg); background: var(--bad-bg); }
.chip.muted { color: var(--muted-fg); background: var(--muted-bg); }
.chip.id { color: var(--fg); background: var(--code-bg); }
.chips { display: flex; flex-wrap: wrap; gap: 4px; }
.table-wrap { overflow-x: auto; border: 1px solid var(--line); border-radius: 10px; background: var(--surface); }
table { width: 100%; border-collapse: collapse; font-size: 14.5px; }
th, td { text-align: left; vertical-align: top; padding: 10px 12px; border-bottom: 1px solid var(--line); }
thead th { font-family: var(--font-mono); font-size: 11px; font-weight: 600; letter-spacing: 0.07em; text-transform: uppercase; color: var(--muted); background: var(--bg); }
tbody tr:last-child td { border-bottom: 0; }
tr.group td { font-family: var(--font-display); font-weight: 700; color: var(--accent); background: var(--bg); padding-block: 8px; }
td.id { font-family: var(--font-mono); font-weight: 600; white-space: nowrap; }
td.name { font-weight: 600; }
.matrix th, .matrix td { padding: 6px 4px; text-align: center; border-bottom: 1px solid var(--line); }
.matrix th.check { font-family: var(--font-mono); font-size: 11px; color: var(--muted); writing-mode: vertical-rl; transform: rotate(180deg); height: 44px; padding: 6px 2px; }
.matrix th.scn, .matrix td.scn { text-align: left; position: sticky; left: 0; background: var(--surface); white-space: nowrap; padding-inline: 12px; font-family: var(--font-mono); font-size: 12.5px; z-index: 1; }
.matrix thead th.scn { background: var(--bg); }
.matrix td.gap, .matrix th.gap { border-left: 2px solid var(--line); }
.cell { display: inline-block; width: 16px; height: 16px; border-radius: 4px; vertical-align: middle; }
.cell.hit { background: var(--bad-fg); }
.cell.good { background: var(--ok-fg); }
.cell.also { border: 2px solid var(--bad-fg); }
.cell.pass { width: 6px; height: 6px; border-radius: 50%; background: var(--ok-fg); opacity: 0.55; }
.cell.skip { width: 6px; height: 6px; border-radius: 50%; background: var(--muted); opacity: 0.4; }
.legend { display: flex; flex-wrap: wrap; gap: 16px; font-size: 14px; color: var(--muted); align-items: center; }
.legend span { display: inline-flex; gap: 6px; align-items: center; }
details.scenario { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; }
details.scenario > summary { cursor: pointer; padding: 12px 16px; display: flex; flex-wrap: wrap; gap: 8px 12px; align-items: center; list-style: none; }
details.scenario > summary::-webkit-details-marker { display: none; }
details.scenario > summary .nm { font-family: var(--font-mono); font-weight: 600; font-size: 14px; }
details.scenario > summary .tt { flex: 1 1 280px; min-width: 0; }
details.scenario[open] > summary { border-bottom: 1px solid var(--line); }
details.scenario .inner { padding: 14px 16px 16px; display: grid; gap: 12px; }
summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 10px; }
ul.findings { margin: 0; padding-left: 0; list-style: none; display: grid; gap: 6px; font-size: 14.5px; }
ul.findings li { display: grid; grid-template-columns: 44px 1fr; gap: 8px; }
ul.findings li .ck { font-family: var(--font-mono); font-weight: 600; color: var(--bad-fg); }
.reqs { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 10px; }
.req { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 14px; display: grid; gap: 6px; align-content: start; min-width: 0; }
.req .top { display: flex; justify-content: space-between; gap: 8px; align-items: center; }
.req .id { font-family: var(--font-mono); font-weight: 600; font-size: 13px; }
.req p { font-size: 14.5px; }
.req .why { font-size: 13px; color: var(--muted); }
.req.ok { border-top: 3px solid var(--ok-fg); } .req.warn { border-top: 3px solid var(--warn-fg); }
.req.bad { border-top: 3px solid var(--bad-fg); } .req.muted { border-top: 3px solid var(--muted); }
.goal-list { display: grid; gap: 4px; }
.goal-list .row { display: grid; grid-template-columns: 40px 100px 1fr; gap: 10px; padding: 8px 12px; border-bottom: 1px solid var(--line); align-items: start; }
.goal-list .row:last-child { border-bottom: 0; }
.goal-list .row .ck { font-family: var(--font-mono); font-weight: 600; }
.goal-list .msg { display: block; font-size: 13.5px; color: var(--muted); margin-top: 2px; overflow-wrap: anywhere; }
.panel { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; }
.panel h3 { padding: 12px 12px 4px; }
footer { font-size: 14px; color: var(--muted); border-top: 1px solid var(--line); padding-top: 16px; }
@media (max-width: 640px) { .goal-list .row { grid-template-columns: 36px 1fr; } .goal-list .row > :nth-child(3) { grid-column: 1 / -1; } }
"""

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Schibsted+Grotesk:wght@500;700'
         '&family=Source+Sans+3:wght@400;600&family=JetBrains+Mono:wght@400;600&family=Source+Serif+4:opsz,wght@8..60,400;8..60,500&display=swap">')


def page(title, body, extra_css=""):
    return (f"<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
            f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n"
            f"<title>{escape(title)}</title>\n{FONTS}\n<style>{CSS}{extra_css}</style>\n</head>\n<body>\n"
            f"<main class=\"page\">\n{body}\n</main>\n</body>\n</html>\n")


def chip(text, tone):
    return f'<span class="chip {tone}">{escape(text)}</span>'


def status_chip(status):
    return chip(status, STATUS_TONE.get(status, "muted"))


def verdict_chip(v):
    return chip(VERDICT_LABEL.get(v, v), VERDICT_TONE.get(v, "muted"))


def requirement_cards(reqs):
    cards = []
    for r in reqs:
        tone = STATUS_TONE.get(r["status"], "muted")
        api = f'<span class="small muted">{escape(", ".join(r["api"]))}</span>' if r.get("api") else ""
        why = STATUS_MEANS.get(r["status"], "")
        if r.get("failing_checks"):
            why += " · " + ", ".join(r["failing_checks"])
        cards.append(f'<div class="req {tone}"><div class="top"><span class="id">{escape(r["id"])}</span>'
                     f'{status_chip(r["status"])}</div><p>{escape(r.get("text", ""))}</p>{api}'
                     f'<span class="why">{escape(why)}</span></div>')
    return '<div class="reqs">' + "".join(cards) + "</div>"


def findings(results, limit=None):
    rows = []
    for r in results:
        if r["verdict"] not in ("fail", "error"):
            continue
        subj = "" if r["subject"] in ("history", "project", "spec", "contract", "routes", "service") else f'{r["subject"]}: '
        rows.append(f'<li><span class="ck">{escape(r["check"])}</span><span>{escape(subj + r["summary"])}</span></li>')
    if limit:
        rows = rows[:limit]
    return '<ul class="findings">' + "".join(rows) + "</ul>" if rows else '<p class="small muted">No failing checks.</p>'


# ---------------------------------------------------------------------------- one run

VIEW_CSS = """
.sheet { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; }
.clause { display: grid; grid-template-columns: 28px 1fr; border-bottom: 1px solid var(--line); }
.clause:last-child { border-bottom: 0; }
.rail { display: flex; flex-direction: column; gap: 3px; padding: 18px 0 18px 12px; }
.rail span { flex: 1; width: 6px; border-radius: 3px; min-height: 10px; }
.v-ok { background: var(--ok-fg); } .v-warn { background: var(--warn-fg); }
.v-bad { background: var(--bad-fg); } .v-none { background: var(--muted-bg); }
.clause details > summary { list-style: none; cursor: pointer; padding: 14px 20px 14px 10px; }
.clause details > summary::-webkit-details-marker { display: none; }
.clause details[open] > summary { padding-bottom: 4px; }
.clause .head { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.clause .rid { font-family: var(--font-mono); font-size: 13px; color: var(--muted); }
.vitals { display: flex; gap: 10px; font-size: 12px; color: var(--muted); flex-wrap: wrap; }
.vitals span { display: inline-flex; align-items: center; gap: 5px; }
.vitals i { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }
.clause .text { font: 19px/1.5 var(--font-serif); margin: 6px 0 0; }
.clause .text mark { background: none; color: inherit; text-decoration: underline wavy var(--warn-fg);
  text-decoration-thickness: 2px; text-underline-offset: 4px; }
.clause .inner { padding: 0 20px 14px 10px; }
.clause .note { font-size: 14px; margin: 8px 0 8px; }
.note.ok { color: var(--ok-fg); } .note.warn { color: var(--warn-fg); } .note.bad { color: var(--bad-fg); }
.tl { list-style: none; margin: 0; padding: 0 0 4px 3px; border-left: 1px solid var(--line); }
.tl li { position: relative; padding: 4px 0 4px 18px; font-size: 14px; color: var(--muted); overflow-wrap: anywhere; }
.tl li::before { content: ""; position: absolute; left: -5px; top: 12px; width: 9px; height: 9px; border-radius: 50%;
  background: var(--dot, var(--muted-bg)); }
.tl li.now-sep { padding: 8px 0 2px 18px; font-family: var(--font-mono); font-size: 11px; letter-spacing: .07em;
  text-transform: uppercase; }
.tl li.now-sep::before { display: none; }
.tl code { font-family: var(--font-mono); font-size: 12px; margin-right: 8px; color: var(--fg); background: none; padding: 0; }
.orow { display: flex; align-items: baseline; gap: 10px; padding: 11px 18px; border-bottom: 1px solid var(--line);
  font-size: 15px; flex-wrap: wrap; }
.orow:last-child { border-bottom: 0; }
.orow .dot { width: 8px; height: 8px; border-radius: 50%; flex: none; align-self: center; }
.orow code { font-family: var(--font-mono); font-size: 13px; background: none; padding: 0; }
.orow span.msg { color: var(--muted); }
.vlegend { display: flex; gap: 18px; flex-wrap: wrap; font-size: 13px; color: var(--muted); }
.vlegend span { display: inline-flex; align-items: center; gap: 6px; }
.vlegend i { width: 6px; height: 14px; border-radius: 3px; display: inline-block; }
details.all > summary { cursor: pointer; font-family: var(--font-display); font-size: 20px; font-weight: 700; }
"""

DOT = {"ok": "var(--ok-fg)", "warn": "var(--warn-fg)", "bad": "var(--bad-fg)", "none": "var(--muted-bg)",
       "neutral": "var(--muted-bg)"}
VITALS = ["spec", "code", "api", "tests"]
PHRASE = {"Missing": "not implemented", "Gone": "with their code gone", "Untested": "untested",
          "Failing": "failing", "Unexercised": "not exercised by their tests", "Weak": "with weak tests",
          "Contract": "breaking the API contract", "Drift": "changed in the spec since implemented"}


def requirement_block(r, open_=None):
    """One requirement in the viewer style: vital-sign rail, text, plain note, history in order."""
    v = r.get("vitals") or {}
    tone = STATUS_TONE.get(r["status"], "muted")
    tone = {"muted": "bad"}.get(tone, tone)
    rail = "".join(f'<span class="v-{v.get(k, "none")}" title="{k}: {v.get(k, "none")}"></span>' for k in VITALS)
    chips = "".join(f'<span><i style="background:{DOT[v.get(k, "none")]}"></i>{k}</span>' for k in VITALS)
    segs = r.get("segments") or [{"t": r.get("text", ""), "m": False}]
    text = " ".join(f"<mark>{escape(x['t'])}</mark>" if x["m"] else escape(x["t"]) for x in segs)
    items = []
    for e in r.get("timeline", []):
        items.append(f'<li style="--dot:{DOT.get(e["state"], DOT["none"])}"><code>{escape(e["sha"])}</code>'
                     f'{escape(e["label"])}</li>')
    if r.get("now"):
        items.append('<li class="now-sep">Now</li>')
        items += [f'<li style="--dot:{DOT.get(e["state"], DOT["none"])}">{escape(e["label"])}</li>' for e in r["now"]]
    if open_ is None:
        open_ = r["status"] != "Sync"
    return (f'<div class="clause" id="{escape(r["id"])}"><div class="rail" aria-hidden="true">{rail}</div>'
            f'<details{" open" if open_ else ""}><summary><div class="head"><span class="rid">{escape(r["id"])}'
            f'{" · " + escape(", ".join(r["api"])) if r.get("api") else ""}</span>'
            f'<span class="vitals">{chips}</span></div><p class="text">{text}</p></summary>'
            f'<div class="inner"><p class="note {tone}">{escape(r.get("note", ""))}</p>'
            f'<ol class="tl">{"".join(items)}</ol></div></details></div>')


def headline(reqs):
    proven = sum(1 for r in reqs if r["status"] == "Sync")
    counts = {}
    for r in reqs:
        if r["status"] != "Sync":
            counts[r["status"]] = counts.get(r["status"], 0) + 1
    h = f"{proven} of {len(reqs)} requirements are proven by running code."
    sub = ", ".join(f"{n} {PHRASE.get(st, st.lower())}" for st, n in counts.items())
    return h, (sub[0].upper() + sub[1:] + ".") if sub else "Every requirement is implemented, tested and matches the contract."


def run_report(rep):
    rng = f'{rep["base"][:7]}..{rep["head"][:7]}' if rep.get("base") else f'all history to {rep["head"][:7]}'
    reqs = rep["requirements"]
    h, sub = headline(reqs)
    body = [f'<header class="top"><span class="eyebrow">{escape(rep["head_branch"])} · {rng} · specs/</span>'
            f'<h1>{escape(h)}</h1><p class="lede muted">{escape(sub)}</p></header>']
    body.append('<section><div class="sheet">' + "".join(requirement_block(r) for r in reqs) + "</div>"
                '<div class="vlegend"><span>Rail, top to bottom: spec, code, api, tests</span>'
                '<span><i class="v-ok"></i>Proven</span><span><i class="v-warn"></i>Needs attention</span>'
                '<span><i class="v-bad"></i>Missing or failing</span><span><i class="v-none"></i>Not applicable</span>'
                '</div></section>')

    outside = rep.get("outside") or []
    rows = "".join(f'<div class="orow"><span class="dot" style="background:var(--bad-fg)"></span>'
                   f'<code>{escape(o["check"])}</code><span>{escape(o["summary"])}</span></div>' for o in outside)
    body.append('<section><h2>Outside the spec</h2>'
                + (f'<div class="sheet">{rows}</div>' if rows else
                   '<p class="muted small">Nothing outside the spec: every route and operation is accounted for.</p>')
                + "</section>")

    git = [(c, rep["checks"][c]) for c in CHECKS if c.startswith("H")]
    bad = [r for r in rep["results"] if r["check"].startswith("H") and r["verdict"] in ("fail", "error")]
    passing = sum(1 for _, v in git if v in ("pass", "skip"))
    grows = "".join(f'<div class="orow"><span class="dot" style="background:var(--bad-fg)"></span>'
                    f'<code>{escape(r["check"])}</code><span>{escape(CHECKS[r["check"]])}:</span>'
                    f'<span class="msg">{escape(r["summary"])}</span></div>' for r in bad)
    body.append(f'<section><h2>Git practices · {passing} of {len(git)} rules pass</h2>'
                + (f'<div class="sheet">{grows}</div>' if grows else
                   '<p class="muted small">Conventional Commits, Refs trailers, one requirement per commit, '
                   'commit size, branch names, history, attribution and signatures all pass.</p>')
                + "</section>")

    rows = []
    for prefix, title in GOALS:
        for chk, name in CHECKS.items():
            if not chk.startswith(prefix):
                continue
            v = rep["checks"][chk]
            msgs = [r for r in rep["results"] if r["check"] == chk and r["verdict"] in ("fail", "error", "not_covered")]
            msg_html = "".join(f'<span class="msg">{escape(m["summary"])}</span>' for m in msgs[:4])
            rows.append(f'<div class="row"><span class="ck">{chk}</span><span>{verdict_chip(v)}</span>'
                        f'<span>{escape(name)}{msg_html}</span></div>')
    body.append(f'<section><details class="all"><summary>All {len(CHECKS)} checks</summary>'
                f'<div class="panel goal-list" style="margin-top:12px">{"".join(rows)}</div></details></section>')
    if rep.get("scorecard"):
        rows = "".join(
            f'<tr><td class="name">{escape(who)}</td><td>{a["commits"]}</td><td>{a["git_rule_pass_rate"]:.0%}</td>'
            f'<td>{escape(", ".join(a["requirements_referenced"]) or "-")}</td></tr>'
            for who, a in rep["scorecard"].items())
        body.append('<section><h2>Agent scorecard</h2><div class="table-wrap"><table><thead><tr><th>Agent</th>'
                    '<th>Commits</th><th>Git rule pass rate</th><th>Requirements</th></tr></thead>'
                    f"<tbody>{rows}</tbody></table></div></section>")
    body.append('<footer>Generated by <code>aqv check</code>. Every result is repeatable: rerun the same command on '
                'the same commit to get the same answer.</footer>')
    return page("Spec Health", "\n".join(body), extra_css=VIEW_CSS)


# ---------------------------------------------------------------------------- the demo


def demo_report(scenarios, language=None):
    """`scenarios`: dicts with name, title, expect, ok, checks, failing, report (full results.json)."""
    total = len(scenarios)
    ok = sum(1 for s in scenarios if s.get("ok"))
    attacks = [s for s in scenarios if s["expect"]]
    clean = [s for s in scenarios if not s["expect"]]
    caught_checks = {c for s in attacks if s.get("ok") for c in s["expect"]}
    clean_ok = all(not s["failing"] for s in clean)

    body = [
        '<header class="top"><span class="eyebrow">Agent Quality Verifier · demo results'
        + (f' · {escape(language)}' if language else '') + '</span>'
        f'<h1>{ok} of {total} scenarios behave as expected</h1>'
        '<p class="lede">A small auth service is built the right way, then an agent gets it wrong in '
        f'{len(attacks)} different ways. Each attack runs in its own copy of the repo and is checked like a '
        'pull request against main. Every attack must be caught by the check written for it, and the clean '
        'runs must pass everything.</p></header>',
    ]
    attacks_label = "attacks, all caught" if all(s.get("ok") for s in attacks) else "attacks"
    body.append(
        '<div class="stats">'
        f'<div class="stat"><b>{len(caught_checks)} / {len(CHECKS)}</b><span>checks caught their attack</span></div>'
        f'<div class="stat"><b>{len(attacks)}</b><span>{attacks_label}</span></div>'
        f'<div class="stat"><b>{"all pass" if clean_ok else "failing"}</b>'
        f'<span>{len(clean)} clean runs (baseline and a clean PR)</span></div></div>')

    # Every check, clean and attacked
    rows = []
    for prefix, title in GOALS:
        rows.append(f'<tr class="group"><td colspan="4">{escape(title)}</td></tr>')
        for chk, name in CHECKS.items():
            if not chk.startswith(prefix):
                continue
            verdicts = sorted({s["checks"][chk] for s in clean})
            by = [s["name"] for s in attacks if chk in s["expect"] and s.get("ok")]
            missed = [s["name"] for s in attacks if chk in s["expect"] and not s.get("ok")]
            links = ", ".join(f'<a href="#{escape(n)}">{escape(n)}</a>' for n in by) or "—"
            if missed:
                links += ' · missed: ' + ", ".join(escape(m) for m in missed)
            rows.append(f'<tr><td class="id">{chk}</td><td class="name">{escape(name)}</td>'
                        f'<td><div class="chips">{"".join(verdict_chip(v) for v in verdicts)}</div></td>'
                        f'<td>{links}</td></tr>')
    body.append('<section><h2>Every check, clean and attacked</h2>'
                '<div class="table-wrap"><table><thead><tr><th>ID</th><th>Check</th><th>Clean runs</th>'
                f'<th>Caught by</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div></section>')

    # Matrix
    checks = list(CHECKS)
    head = '<th class="scn">Scenario</th>' + "".join(
        f'<th class="check{" gap" if i and checks[i - 1][0] != c[0] else ""}">{c}</th>' for i, c in enumerate(checks))
    mrows = []
    for s in scenarios:
        cells = []
        for i, c in enumerate(checks):
            gap = " gap" if i and checks[i - 1][0] != c[0] else ""
            v = s["checks"].get(c)
            if c in s["expect"] and v in ("fail", "error"):
                mark = '<span class="cell hit" title="expected, caught"></span>'
            elif v in ("fail", "error"):
                mark = '<span class="cell also" title="also failed"></span>'
            elif v == "pass":
                mark = '<span class="cell pass" title="pass"></span>'
            else:
                mark = '<span class="cell skip" title="skip"></span>'
            cells.append(f'<td class="{gap.strip()}">{mark}</td>')
        mrows.append(f'<tr><td class="scn"><a href="#{escape(s["name"])}">{escape(s["name"])}</a></td>{"".join(cells)}</tr>')
    body.append(
        '<section><h2>Which checks fired, per scenario</h2>'
        '<div class="legend"><span><span class="cell hit"></span>the check this attack targets</span>'
        '<span><span class="cell also"></span>also failed</span><span><span class="cell pass"></span>passed</span>'
        '<span><span class="cell skip"></span>skipped or not applicable</span></div>'
        f'<div class="table-wrap"><table class="matrix"><thead><tr>{head}</tr></thead><tbody>{"".join(mrows)}</tbody>'
        '</table></div></section>')

    # Scenarios
    det = []
    for s in scenarios:
        rep = s["report"]
        exp = ", ".join(s["expect"]) or "all pass"
        result = chip("as expected", "ok") if s.get("ok") else chip("missed", "bad")
        changed = [r for r in rep["requirements"] if r["status"] != "Sync"]
        blocks = ('<div class="sheet">' + "".join(requirement_block(r, open_=True) for r in changed) + "</div>"
                  if changed else '<p class="small muted">Every requirement stays proven.</p>')
        link = f'<a class="small" href="runs/{escape(s["name"])}.html">Open the full report for this run</a>'
        det.append(
            f'<details class="scenario" id="{escape(s["name"])}"><summary><span class="nm">{escape(s["name"])}</span>'
            f'<span class="tt">{escape(s["title"])}</span><span class="small muted">expects {escape(exp)}</span>{result}'
            '</summary><div class="inner">' + blocks
            + "<h3>Every failing result</h3>" + findings(rep["results"]) + link + "</div></details>")
    body.append('<section><h2>Scenarios</h2><p class="small muted">Open a scenario to see the requirement '
                'statuses it changed and every failing result.</p>' + "".join(det) + "</section>")
    body.append('<footer>Generated by <code>python demo/run_demo.py</code>. Rerun it to rebuild the demo repo, '
                'replay every scenario and regenerate this page.</footer>')
    return page("Agent Quality Demo", "\n".join(body), extra_css=VIEW_CSS)


# ---------------------------------------------------------------------------- all languages


def languages_report(langs):
    """`langs`: dicts with lang, name, stack, mechanisms, results (the demo-results.json rows)."""
    checks = list(CHECKS)
    body = []
    total = sum(len(l["results"]) for l in langs)
    good = sum(1 for l in langs for r in l["results"] if r.get("ok"))
    body.append(
        '<header class="top"><span class="eyebrow">Agent Quality Verifier · every language</span>'
        f'<h1>{good} of {total} scenarios behave as expected across {len(langs)} languages</h1>'
        '<p class="lede">The same spec, the same OpenAPI contract and the same 26 attacks, built in each '
        'language with the stack an agent would usually pick. Each language must pass every check on its clean '
        'runs and catch every attack with the check written for it.</p></header>')

    rows = []
    for l in langs:
        res = l["results"]
        ok = sum(1 for r in res if r.get("ok"))
        cells = []
        for i, c in enumerate(checks):
            gap = ' class="gap"' if i and checks[i - 1][0] != c[0] else ""
            attacks = [r for r in res if c in r.get("expect", [])]
            clean = [r for r in res if not r.get("expect")]
            clean_ok = all(r["checks"].get(c) in ("pass", "skip") for r in clean if "checks" in r)
            caught = attacks and all(r.get("ok") for r in attacks)
            if caught and clean_ok:
                mark = '<span class="cell good" title="caught its attack; clean runs pass"></span>'
            elif not clean_ok:
                mark = '<span class="cell also" title="failed on a clean run"></span>'
            else:
                mark = '<span class="cell also" title="missed its attack"></span>'
            cells.append(f"<td{gap}>{mark}</td>")
        rows.append(f'<tr><td class="scn"><a href="{escape(l["lang"])}/demo.html">{escape(l["name"])}</a></td>'
                    f'<td class="small">{ok}/{len(res)}</td>{"".join(cells)}</tr>')
    head = '<th class="scn">Language</th><th>OK</th>' + "".join(
        f'<th class="check{" gap" if i and checks[i - 1][0] != c[0] else ""}">{c}</th>' for i, c in enumerate(checks))
    body.append('<section><h2>Every check in every language</h2>'
                '<div class="legend"><span><span class="cell good"></span>caught its attack, clean runs pass</span>'
                '<span><span class="cell also"></span>missed, or failed a clean run</span></div>'
                f'<div class="table-wrap"><table class="matrix"><thead><tr>{head}</tr></thead>'
                f'<tbody>{"".join(rows)}</tbody></table></div></section>')

    mech_checks = []
    for l in langs:
        for c in l.get("mechanisms", {}):
            if c not in mech_checks:
                mech_checks.append(c)
    mech_checks.sort(key=checks.index)
    if mech_checks:
        hdr = "<th>Check</th>" + "".join(f"<th>{escape(l['name'])}</th>" for l in langs)
        mrows = []
        for c in mech_checks:
            mrows.append(f'<tr><td class="id">{c}<br><span class="small muted" style="font-family:var(--font-body);'
                         f'font-weight:400">{escape(CHECKS[c])}</span></td>'
                         + "".join(f'<td class="small">{escape(l.get("mechanisms", {}).get(c, "—"))}</td>' for l in langs)
                         + "</tr>")
        body.append('<section><h2>How each language does it</h2><p class="small muted">Only the checks that '
                    'depend on the stack. Every other check works the same way in every language: it reads the '
                    'spec, the contract and git history.</p>'
                    f'<div class="table-wrap"><table><thead><tr>{hdr}</tr></thead><tbody>{"".join(mrows)}</tbody>'
                    '</table></div></section>')

    cards = "".join(
        f'<div class="req ok"><div class="top"><span class="id">{escape(l["name"])}</span>'
        f'{chip(str(sum(1 for r in l["results"] if r.get("ok"))) + "/" + str(len(l["results"])), "ok" if all(r.get("ok") for r in l["results"]) else "bad")}'
        f'</div><p>{escape(l["stack"])}</p><a class="small" href="{escape(l["lang"])}/demo.html">Scenario details</a></div>'
        for l in langs)
    body.append(f'<section><h2>Languages</h2><div class="reqs">{cards}</div></section>')
    body.append('<footer>Generated by <code>python demo/run_demo.py --lang all</code>.</footer>')
    return page("Agent Quality Across Languages", "\n".join(body))
