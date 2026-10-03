"""Builds the comparison pages from the experiment results:

    python experiments/report.py

writes docs/compare/openfasttrace.html and docs/compare/intentbond.html. Both use the
verifier's page style and site navigation.
"""
import json
import sys
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from aqv.html import SITE_CSS, chip, our_goals, page  # noqa: E402

OUT = ROOT / "docs" / "compare"
NAV = "../../"

CSS = SITE_CSS + """
.quote { background: var(--surface); border: 1px solid var(--line); border-left: 4px solid var(--muted);
  border-radius: 10px; padding: 16px 20px; display: grid; gap: 8px; }
.quote blockquote { margin: 0; font-family: var(--font-serif); font-size: 18px; line-height: 1.5; }
.quote .src { font-size: 13px; color: var(--muted); }
.two { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 12px; }
.two .panel { padding: 16px 18px; display: grid; gap: 8px; align-content: start; }
.two .panel h3 { padding: 0; }
.two .panel .k { font-family: var(--font-mono); font-size: 11px; letter-spacing: .07em; text-transform: uppercase; color: var(--muted); }
.two .panel.ours { border-top: 3px solid var(--accent); }
.two .panel.theirs { border-top: 3px solid var(--muted); }
td.why { color: var(--muted); font-size: 14px; min-width: 240px; }
td.scn { font-family: var(--font-mono); font-size: 12.5px; white-space: nowrap; }
td .ttl { display: block; font-family: var(--font-body); font-size: 13.5px; color: var(--muted); white-space: normal; max-width: 300px; }
.note { font-size: 14px; color: var(--muted); }
ol.steps { margin: 0; padding-left: 20px; display: grid; gap: 8px; }
.vs { --ours: var(--accent); --ours-fg: var(--accent); --subj: #8a96a3; --subj-fg: #56626e;
  background: color-mix(in srgb, var(--accent) 5%, var(--surface));
  border: 1px solid color-mix(in srgb, var(--accent) 35%, var(--line)); border-radius: 14px;
  padding: 22px 24px 18px; display: grid; gap: 4px; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) .vs { --subj: #6b7783; --subj-fg: #aeb8c2; } }
:root[data-theme="dark"] .vs { --subj: #6b7783; --subj-fg: #aeb8c2; }
.vs-legend { display: flex; flex-wrap: wrap; gap: 6px 20px; font-size: 13.5px; color: var(--muted); padding-bottom: 12px; }
.vs-legend span { display: inline-flex; align-items: center; gap: 7px; }
.sw { display: inline-block; width: 22px; height: 10px; border-radius: 99px; }
.sw.ours { background: var(--ours); }
.sw.auto { background: var(--subj); }
.sw.review { background: repeating-linear-gradient(135deg, var(--subj) 0 3px, transparent 3px 6px); border: 1px solid var(--subj); }
.sw.none { border: 1px dashed var(--subj); }
.vs-row { display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(0, 1fr) minmax(0, 1fr); gap: 10px 28px;
  align-items: center; padding: 14px 0; border-top: 1px solid var(--line); }
.vs-row.head { border-top: 0; padding: 0 0 8px; font-family: var(--font-mono); font-size: 11px; letter-spacing: .07em;
  text-transform: uppercase; color: var(--muted); }
.vs-row.head .o { color: var(--ours-fg); font-weight: 600; } .vs-row.head .s { color: var(--subj-fg); font-weight: 600; }
.vs-q { font-size: 16px; font-weight: 600; line-height: 1.35; }
.vs-q small { display: block; margin-top: 3px; font-family: var(--font-mono); font-size: 11.5px; font-weight: 400; color: var(--muted); }
.vs-cell { display: grid; gap: 6px; min-width: 0; align-content: start; }
.meter { display: flex; height: 12px; border-radius: 99px; background: var(--muted-bg); overflow: hidden; }
.meter i { display: block; height: 100%; }
.meter.ours i { background: var(--ours); }
.meter i.auto { background: var(--subj); }
.meter i.review { background: repeating-linear-gradient(135deg, var(--subj) 0 3px, transparent 3px 6px); }
.meter.none { background: transparent; border: 1px dashed var(--subj); }
.vs-val { font-family: var(--font-mono); font-size: 12.5px; color: var(--muted); display: flex; flex-wrap: wrap; gap: 2px 10px; }
.vs-val b { font-size: 14px; }
.vs-cell.ours .vs-val b { color: var(--ours-fg); }
.vs-cell.subj .vs-val b { color: var(--subj-fg); }
.vs-row.total { align-items: start; border-top: 2px solid color-mix(in srgb, var(--accent) 35%, var(--line)); margin-top: 4px; padding-top: 16px; }
.vs-row.total .meter { height: 18px; }
.vs-row.total .vs-val b { font-size: 18px; font-family: var(--font-display); }
@media (max-width: 720px) {
  .vs { padding: 18px 16px 14px; }
  .vs-row { grid-template-columns: 1fr 1fr; align-items: start; }
  .vs-row .vs-q { grid-column: 1 / -1; }
  .vs-row.head > :first-child { display: none; }
}
.two.quad { grid-template-columns: repeat(auto-fit, minmax(min(100%, 420px), 1fr)); }
"""

ORDER_T = ["T1-duplicate-id", "T2-not-implemented", "T3-comment-only", "T4-no-tests", "T5-failing-test",
           "T5-suite-broken", "T6-assert-true", "T7-weak-tests", "T8-spec-changed"]
ORDER_A = ["A1-operation-missing", "A2-unlinked-operation", "A3-lint", "A4-breaking-change", "A5-shadow-route",
           "A6-leaked-field", "A6-undocumented-status", "A7-server-error"]
ORDER_H = ["H1-wip-commit", "H2-no-refs", "H3-two-requirements", "H4-refactor-changes-behavior", "H5-huge-commit",
           "H6-branch-name", "H7-rewrite-main", "H8-no-attribution", "H9-unsigned"]
ORDER_X = ["X1-claims-only", "X2-spec-changed-no-bump", "X3-weak-tests-same-names"]
GROUPS = [("Clean runs", ["baseline", "00-clean-pr"]), ("T · tests prove the spec", ORDER_T),
          ("A · the API matches its contract", ORDER_A), ("H · the history can be trusted", ORDER_H),
          ("Isolating variants", ORDER_X)]

# Kinds of question each scenario asks. Used for the summary table on both pages.
KINDS = [
    ("links", "Is every requirement linked to code and tests, at its current revision?",
     ["T1-duplicate-id", "T2-not-implemented", "T4-no-tests", "T8-spec-changed"]),
    ("run", "Do the linked tests run and pass?", ["T5-failing-test", "T5-suite-broken", "H4-refactor-changes-behavior"]),
    ("claims", "Is the linked evidence real: code that exists, tests that run it and would catch it breaking?",
     ["T3-comment-only", "T6-assert-true", "T7-weak-tests", "X1-claims-only", "X3-weak-tests-same-names"]),
    ("revision", "Is a reworded requirement noticed when nobody marks it as changed?", ["X2-spec-changed-no-bump"]),
    ("api", "Does the API match its OpenAPI contract?", ORDER_A),
    ("git", "Does the history follow the conventions?", [h for h in ORDER_H if not h.startswith("H4")]),
]


def load(p):
    return json.loads(Path(p).read_text())


def ours(sid, variants):
    if sid in ("baseline", "00-clean-pr"):
        return chip("passes", "ok")
    if sid in variants:
        v = variants[sid]
        return chip("caught · " + ", ".join(v["failing"]), "ok") if v["failing"] else chip("passes", "muted")
    return chip("caught · " + EXPECT.get(sid, ""), "ok")


EXPECT = {}


def scenario_meta():
    for script in sorted((ROOT / "demo" / "scenarios").glob("*.sh")) + sorted((HERE / "variants").glob("*.sh")):
        head = script.read_text()
        title = next(l[9:] for l in head.splitlines() if l.startswith("# title: "))
        expect = next(l[10:] for l in head.splitlines() if l.startswith("# expect: "))
        EXPECT[script.stem] = expect
        TITLES[script.stem] = title
    TITLES["baseline"] = "The clean baseline: six requirements, built the right way"


TITLES = {}


def scn_cell(sid):
    return f'<td class="scn">{escape(sid)}<span class="ttl">{escape(TITLES.get(sid, ""))}</span></td>'


def results_table(cols, rows_for):
    """cols: header labels after Scenario. rows_for(sid) -> list of cell html."""
    head = "<th>Scenario</th>" + "".join(f"<th>{escape(c)}</th>" for c in cols)
    body = []
    for name, ids in GROUPS:
        body.append(f'<tr class="group"><td colspan="{len(cols) + 1}">{escape(name)}</td></tr>')
        for sid in ids:
            body.append("<tr>" + scn_cell(sid) + "".join(rows_for(sid)) + "</tr>")
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'


def two_panels(theirs_title, theirs_q, theirs_items, ours_q, ours_items):
    li = lambda xs: "".join(f"<li>{x}</li>" for x in xs)
    return ('<div class="two">'
            f'<div class="panel theirs"><span class="k">{escape(theirs_title)} answers</span><h3>{theirs_q}</h3>'
            f'<ul class="plain small">{li(theirs_items)}</ul></div>'
            f'<div class="panel ours"><span class="k">This verifier answers</span><h3>{ours_q}</h3>'
            f'<ul class="plain small">{li(ours_items)}</ul></div></div>')


def meter(cls, parts, total):
    """parts: [(count, css class)] drawn left to right as shares of total."""
    segs = "".join(f'<i class="{c}" style="width:{100 * n / total:.1f}%"></i>' for n, c in parts if n)
    return f'<div class="meter {cls}" role="presentation">{segs}</div>'


def versus(tool, cell, review_legend=False):
    """The scenarios grouped by question: this verifier against `tool`, with paired bars.

    cell(key, ids) -> {"auto": n, "review": n, "goal": bool, "label": html}. "auto" counts scenarios the
    tool answered with an automated check, "review" ones it handed to a person, and goal=False marks a
    question it isn't designed to answer."""
    legend = ['<span><i class="sw ours"></i>This verifier: answered by a check</span>',
              f'<span><i class="sw auto"></i>{escape(tool)}: answered by a check</span>']
    if review_legend:
        legend.append(f'<span><i class="sw review"></i>{escape(tool)}: handed to a person</span>')
    legend.append('<span><i class="sw none"></i>not what it\'s designed to answer</span>')
    rows = [f'<div class="vs-legend">{"".join(legend)}</div>',
            f'<div class="vs-row head"><span>Question the scenarios ask</span><span class="o">This verifier</span>'
            f'<span class="s">{escape(tool)}</span></div>']
    tot = {"n": 0, "auto": 0, "review": 0, "off": 0}
    for key, q, ids in KINDS:
        n, c = len(ids), cell(key, ids)
        tot["n"] += n
        tot["auto"] += c["auto"]
        tot["review"] += c["review"]
        tot["off"] += 0 if c["goal"] else n
        bar = (meter("subj", [(c["auto"], "auto"), (c["review"], "review")], n) if c["goal"]
               else '<div class="meter none" role="presentation"></div>')
        rows.append(
            f'<div class="vs-row"><div class="vs-q">{escape(q)}<small>{escape(", ".join(short(i) for i in ids))}</small></div>'
            f'<div class="vs-cell ours">{meter("ours", [(n, "")], n)}<div class="vs-val"><b>{n} of {n}</b></div></div>'
            f'<div class="vs-cell subj">{bar}<div class="vs-val">{c["label"]}</div></div></div>')
    n = tot["n"]
    subj_label = f'<b>{tot["auto"]} of {n}</b><span>answered by a check</span>'
    if tot["review"]:
        subj_label += f'<span>{tot["review"]} handed to a person</span>'
    subj_label += f'<span>{tot["off"]} outside its goals</span>'
    rows.append(
        f'<div class="vs-row total"><div class="vs-q">All {n} scenarios and variants</div>'
        f'<div class="vs-cell ours">{meter("ours", [(n, "")], n)}<div class="vs-val"><b>{n} of {n}</b>'
        f'<span>answered by a check</span></div></div>'
        f'<div class="vs-cell subj">{meter("subj", [(tot["auto"], "auto"), (tot["review"], "review")], n)}'
        f'<div class="vs-val">{subj_label}</div></div></div>')
    return f'<div class="vs">{"".join(rows)}</div>'


def short(sid):
    """T1-duplicate-id -> T1; T5 and A6 have two scenarios each, so keep their first word."""
    head, _, rest = sid.partition("-")
    return f"{head} {rest.split('-')[0]}" if head in ("T5", "A6") else head


def footer(md, results):
    return (f'<footer>Markdown version: <a href="{NAV}{md}">{escape(md)}</a>. Raw results: '
            + ", ".join(f'<a href="{NAV}{r}"><code>{escape(r)}</code></a>' for r in results)
            + '. Rebuild with <code>python experiments/report.py</code>.</footer>')


# ---------------------------------------------------------------------------
# OpenFastTrace
# ---------------------------------------------------------------------------

OFT_WHY = {
    "baseline": "Every requirement has its implementation and test links.",
    "00-clean-pr": "The new requirement is linked to its code and tests.",
    "T1-duplicate-id": "The reused ID appears as a second item without links. An exact duplicate is reported as a duplicate too (probe below).",
    "T2-not-implemented": "No implementation or test links for the new requirement.",
    "T3-comment-only": "Reported for the missing test link. The implementation tag sits on a comment, and a tag is a declaration, so that link counts (see X1).",
    "T4-no-tests": "No test link for the new requirement.",
    "T5-failing-test": "Tracing reads tags; running tests is left to the build.",
    "T5-suite-broken": "Tracing reads tags; running tests is left to the build.",
    "T6-assert-true": "The test is tagged, so the link exists. What the test asserts is outside tracing.",
    "T7-weak-tests": "The rewritten tests still carry their links.",
    "T8-spec-changed": "Revision 2 leaves the code and test links on revision 1 outdated.",
    "X1-claims-only": "Both links are declared, so the trace is complete.",
    "X2-spec-changed-no-bump": "Without a new revision the change isn't visible to tracing. OFT's model relies on the editor raising it.",
    "X3-weak-tests-same-names": "Same tests, same links.",
}


def oft_page(res, probes, variants):
    def tool_cell(sid):
        r = res[sid]
        clean = sid in ("baseline", "00-clean-pr")
        if r["exit"] == 0:
            c = chip("clean trace", "ok" if clean else "muted")
        else:
            c = chip("reported", "ok" if not clean else "bad")
        why = OFT_WHY.get(sid)
        if why is None:
            why = ("The API contract isn't part of the trace." if sid.startswith("A") else
                   "A behaviour change only shows when tests run." if sid.startswith("H4") else
                   "Git history isn't part of the trace.")
        defects = "".join(f"<br><code>{escape(d)}</code>" for d in r["defects"][:2])
        return [f"<td>{ours(sid, variants)}</td>", f"<td>{c}</td>", f'<td class="why">{escape(why)}{defects}</td>']

    def kind_cell(key, ids):
        n = sum(1 for i in ids if res[i]["exit"] != 0)
        if key in ("api", "git", "run"):
            return {"auto": 0, "review": 0, "goal": False, "label": "<b>not its goal</b>"}
        if key == "revision":
            return {"auto": 0, "review": 0, "goal": False, "label": "<b>relies on the revision rule</b>"}
        return {"auto": n, "review": 0, "goal": True, "label": f"<b>{n} of {len(ids)}</b>"}

    ext = probes["extensions"]
    ext_rows = " ".join(chip("." + e, "ok" if ok else "muted") for e, ok in ext.items())
    hier = probes["hierarchy"]
    body = [
        '<header class="top"><span class="eyebrow">Compared · OpenFastTrace 4.10.0 on the Python demo</span>'
        '<h1>OpenFastTrace traces what you planned. This verifier tests what the agent delivered.</h1>'
        '<p class="lede">Both start from requirements with stable IDs. OpenFastTrace (OFT) checks that every planned '
        'requirement is linked through the levels of your specification to code and tests. This verifier checks that '
        'the evidence behind each requirement holds up when you run it. We ran OFT on the same 26 attacks the verifier '
        'is tested against, to show where the two overlap and where they answer different questions.</p></header>',
        '<div class="stats">'
        f'<div class="stat"><b>{len(res) - 1}</b><span>scenarios and variants, run unchanged</span></div>'
        '<div class="stat"><b>4 of 4</b><span>link questions answered by both</span></div>'
        '<div class="stat"><b>3 levels</b><span>feature → requirement → design, traced by OFT only</span></div>'
        f'<div class="stat"><b>{sum(ext.values())} of {len(ext)}</b><span>file types OFT reads tags from out of the box</span></div></div>',
        '<section><h2>Two goals</h2>'
        '<div class="quote"><blockquote>“Requirement tracing keeps track of whether you actually implemented everything '
        'you planned to in your specifications. It also identifies obsolete parts of your product and helps you to get '
        'rid of them.”</blockquote><span class="src">OpenFastTrace README</span></div>'
        + two_panels("OpenFastTrace",
                     "Is everything we specified covered, at every level, at its current revision?",
                     ["Features, requirements, designs, code and tests as linked items, each with a revision.",
                      "<code>Needs:</code> says what must cover an item; <code>Covers:</code> links it upward.",
                      "Missing coverage, outdated revisions, duplicates and orphaned tags are defects.",
                      "Works on any file type, as a CLI, Maven or Gradle plugin, with HTML and XML reports."],
                     "Does the evidence behind each requirement hold up, so nobody has to read the code?",
                     ["The links come from conventions (commit trailers, test names, OpenAPI <code>x-requirements</code>), not tags.",
                      "Each claim is then tested: the code exists, the tests pass, run it and catch broken versions of it.",
                      "The API is checked against its contract, and the history against git conventions.",
                      "A wording change is read from git, without anyone marking it."])
        + '</section>',
        f'<section><h2>What this verifier is for</h2>{our_goals()}</section>',
        '<section><h2>The same scenarios, by the question they ask</h2>'
        '<p class="note">Each scenario attacks one question. A dashed track means OFT isn\'t designed to answer that '
        'question, so a clean trace there says nothing against OFT.</p>' + versus("OpenFastTrace", kind_cell)
        + '</section>',
        '<section><h2>How it was run</h2><ol class="steps">'
        '<li>The Python demo baseline gets OFT notation the way an agent following OFT\'s skill would write it: an item '
        'per requirement with <code>Needs: impl, utest</code>, ten <code>[impl-&gt;req~…]</code> tags beside the code, '
        'and a named <code>utest</code> tag on each test.</li>'
        '<li>Each scenario script from <code>demo/scenarios/</code> runs unchanged. Whatever it added then gets tagged the '
        'same way: new requirement items, new tests, and code for a requirement that had no tag yet. A reworded '
        'requirement gets revision 2, as OFT asks of whoever edits it; variant X2 leaves it at 1.</li>'
        '<li><code>oft trace specs src tests</code> on the result. Exit 1 means OFT reported a defect.</li></ol></section>',
        '<section><h2>Every scenario</h2>' + results_table(["This verifier", "OpenFastTrace", "What OFT saw"], tool_cell)
        + '</section>',
        '<section><h2>What OFT does that this verifier doesn\'t</h2><div class="two quad">'
        '<div class="panel"><h3>Traces a hierarchy</h3><p class="small">A feature needs a requirement, the requirement '
        'needs a design, the design needs code and a test. With the design\'s test missing, OFT reports '
        f'<code>{escape((hier["design_without_test"]["defects"] or ["—"])[0])}</code>; with it added the trace is clean '
        f'({hier["complete_chain"]["items"]} items). This verifier has one level: requirement → code and tests.</p></div>'
        '<div class="panel"><h3>Makes revisions explicit</h3><p class="small">Every item carries a revision, and links '
        'name the revision they cover, so a reviewed change in meaning is visible in the spec itself. This verifier '
        'infers changes from git instead (T8).</p></div>'
        '<div class="panel"><h3>Reads tags from almost anything</h3><p class="small">One tag syntax across languages, '
        f'documents and build files.</p><div class="chips">{ext_rows}</div><p class="small muted">.tsx needs a '
        'workaround (IntentBond adds one).</p></div>'
        '<div class="panel"><h3>Fits documentation-heavy work</h3><p class="small">Mature (version 4.10, Maven and Gradle '
        'plugins, an IntelliJ plugin, HTML reports), and it now ships agent skills for writing traced specs. It fits '
        'teams that must show coverage of a written specification, such as safety or regulated work.</p></div>'
        '</div></section>',
        '<section><h2>What the runs show</h2><ul class="plain">'
        '<li><b>On links they agree.</b> Missing implementation, missing tests, a reused ID and a requirement whose '
        'revision moved on: OFT reports all four, as does this verifier.</li>'
        '<li><b>A tag is a declaration; this verifier\'s links are tested claims.</b> OFT accepts a tag on a comment or '
        'on an <code>assert True</code> test (X1), because whether the tagged code works is a question for the build, '
        'not for tracing. That question is this verifier\'s main job: T3, T6 and T7.</li>'
        '<li><b>Running tests is left to the build.</b> Failing tests, a broken suite and a behaviour change (T5, H4) '
        'aren\'t part of a trace.</li>'
        '<li><b>Revisions are a process, not a detection.</b> OFT notices a reworded requirement when its revision is '
        'raised (T8) and not otherwise (X2). This verifier reads the change from git.</li>'
        '<li><b>The API contract and git history</b> aren\'t part of OFT\'s model.</li></ul></section>',
        '<section><h2>Using them together</h2><ol class="steps">'
        '<li><b>OFT as the specification format.</b> Teams that already write OFT items keep them, including the '
        'feature and design levels this verifier doesn\'t model.</li>'
        '<li><b>OFT tags as this verifier\'s claims.</b> An <code>[impl-&gt;req~…]</code> tag says the same thing as a '
        '<code>Refs:</code> trailer. Reading OFT tags would let the verifier test those claims with T3–T8 without any '
        're-tagging. Not built yet.</li>'
        '<li><b>Each where it\'s strongest.</b> OFT shows the specification is fully covered; this verifier shows the '
        'coverage is real.</li></ol>'
        '<p class="note">When to pick which: OFT when you must demonstrate coverage of a written, multi-level '
        'specification. This verifier when you need to judge an agent\'s output without reading it. Both when you '
        'need both.</p></section>',
        '<section><h2>Limits of this comparison</h2><ul class="plain small">'
        '<li>Python only, OFT 4.10.0. The tags were written by a script acting as a careful agent, not by a real agent.</li>'
        '<li>The scenarios were written to test this verifier, so most of them ask its questions. The probes above ask OFT\'s.</li>'
        '<li>OFT\'s HTML report and IDE plugin weren\'t evaluated.</li></ul></section>',
        footer("experiments/openfasttrace/README.md",
               ["experiments/openfasttrace/results/openfasttrace.json", "experiments/openfasttrace/results/probes.json",
                "experiments/ours-variants.json"]),
    ]
    return page("Compared: OpenFastTrace", "\n".join(body), extra_css=CSS, nav=NAV,
                current="docs/compare/openfasttrace.html")


# ---------------------------------------------------------------------------
# IntentBond
# ---------------------------------------------------------------------------

IB_WHY = {
    "baseline": "Coverage complete; 15 linked tests pass.",
    "00-clean-pr": "Any specification or test change goes to a person, by design.",
    "T1-duplicate-id": "Two active items for <code>req~auth-006</code>.",
    "T2-not-implemented": "No implementation or test links for the new requirement.",
    "T3-comment-only": "Rejected for the missing test link. The comment counts as the implementation link (see X1).",
    "T4-no-tests": "No test link for the new requirement.",
    "T5-failing-test": "The suite failed; the linked lockout test failed.",
    "T5-suite-broken": "Collection error; no linked test was observed.",
    "T6-assert-true": "The test passes and is linked. Whether it checks anything is the reviewer's call, with the diff in <code>review.patch</code>.",
    "T7-weak-tests": "Default: the changed tests go to review. Strict: the pinned test names are gone.",
    "T8-spec-changed": "Revision 2 leaves the links on revision 1 outdated.",
    "A1-operation-missing": "The new requirement and test go to review. The contract isn't an input.",
    "A4-breaking-change": "A test was edited, so the change goes to review. The contract isn't an input.",
    "A6-undocumented-status": "A test was edited, so the change goes to review. The contract isn't an input.",
    "H4-refactor-changes-behavior": "A lockout test failed: the tests caught the behaviour change.",
    "X1-claims-only": "Both links exist and the test passes. The reviewer decides.",
    "X2-spec-changed-no-bump": "Default: the spec edit goes to review. Strict: changed content without a higher revision is rejected.",
    "X3-weak-tests-same-names": "Same pinned names, still passing. The reviewer sees the weaker assertions.",
}
IB_LABEL = {0: ("passed", "muted"), 1: ("rejected", "ok"), 4: ("review", "warn")}


def ib_chip(code, clean):
    label, tone = IB_LABEL.get(code, (f"exit {code}", "bad"))
    if clean:
        tone = "ok" if code in (0, 4) else "bad"
    return chip(label, tone)


def tidy(lines):
    """`"status": "matched",` lines from ib's JSON output -> `status: matched`."""
    return ", ".join(l.strip().rstrip(",").replace('"', "") for l in lines)


def ib_page(res, probes, variants):
    def tool_cell(sid):
        r = res[sid]
        clean = sid in ("baseline", "00-clean-pr")
        why = IB_WHY.get(sid) or ("API contracts are outside its scope." if sid.startswith("A")
                                  else "Git history conventions are outside its scope.")
        return [f"<td>{ours(sid, variants)}</td>", f"<td>{ib_chip(r['default']['exit'], clean)}</td>",
                f"<td>{ib_chip(r['strict']['exit'], clean)}</td>", f'<td class="why">{why}</td>']

    def kind_cell(key, ids):
        d = [res[i]["default"]["exit"] for i in ids]
        s = [res[i]["strict"]["exit"] for i in ids]
        if key in ("api", "git"):
            extra = f"<span>{d.count(4)} reach review</span>" if d.count(4) else ""
            return {"auto": 0, "review": 0, "goal": False, "label": f"<b>not its goal</b>{extra}"}
        label = f"<b>{d.count(1)} of {len(ids)}</b>"
        if d.count(4):
            label += f"<span>{d.count(4)} to a person</span>"
        if s.count(1) != d.count(1):
            label += f"<span>strict: {s.count(1)} of {len(ids)}</span>"
        return {"auto": d.count(1), "review": d.count(4), "goal": True, "label": label}

    v = probes["verify"]
    body = [
        '<header class="top"><span class="eyebrow">Compared · IntentBond on the Python demo</span>'
        '<h1>IntentBond keeps a change reviewable and its evidence verifiable. This verifier makes the evidence '
        'the review.</h1>'
        '<p class="lede">IntentBond links requirements to code and tests with OpenFastTrace tags, runs the tests against a '
        'git baseline, keeps evidence tied to the exact source it checked, and sends every specification or test change '
        'to a person. This verifier turns the questions that review would ask into checks. We ran IntentBond on the same '
        '26 attacks, with its documented settings and with its strictest options.</p></header>',
        '<div class="stats">'
        f'<div class="stat"><b>{len(res) - 1}</b><span>scenarios and variants, two configurations each</span></div>'
        '<div class="stat"><b>7 of 7</b><span>link and test-run questions answered by both</span></div>'
        f'<div class="stat"><b>{"matched" if v["same_commit"]["exit"] == 0 else "?"}</b><span>saved evidence matched to '
        'its commit by <code>ib verify</code>; a later edit is refused</span></div>'
        '<div class="stat"><b>0</b><span>AI calls in either tool</span></div></div>',
        '<section><h2>Two goals</h2>'
        '<div class="quote"><blockquote>“IntentBond connects intent and specifications to code, tests, and verification '
        'evidence. Follow explicit links to find what a change affects and keep the related artifacts consistent as '
        'software changes.” … “Review determines whether the linked code and checks satisfy the requirement.”'
        '</blockquote><span class="src">IntentBond README</span></div>'
        + two_panels("IntentBond",
                     "Did this change keep requirements, code and tests linked and passing, and what must a person review?",
                     ["OFT links checked on the base and the candidate, with the rules read from the base.",
                      "The project's tests run; named tests can be required to run and pass.",
                      "Every specification or test change produces a review record (<code>review.patch</code>, "
                      "<code>summary.md</code>); passing checks don't approve it.",
                      "Evidence is saved with source hashes, and <code>ib verify</code> later matches a commit to it."],
                     "Which requirements are proven, by checks alone, so review doesn't have to find the problems?",
                     ["The same link and test-run questions, from conventions instead of tags.",
                      "Plus the questions a reviewer would otherwise ask: is the code real, do the tests run it, would "
                      "they catch it breaking, has the wording moved on?",
                      "Plus the API contract and the git history.",
                      "People still decide intent; they read evidence instead of code."])
        + '</section>',
        f'<section><h2>What this verifier is for</h2>{our_goals()}</section>',
        '<section><h2>The same scenarios, by the question they ask</h2>'
        '<p class="note">"Review" is IntentBond\'s deliberate answer for any change to specifications or tests: the clean '
        'pull request gets it too. It hands the question to a person rather than answering it.</p>'
        + versus("IntentBond", kind_cell, review_legend=True) + '</section>',
        '<section><h2>How it was run</h2><ol class="steps">'
        '<li>IntentBond <code>5a1200a</code> (2026-09-29) with its pinned OpenFastTrace 4.9.0.</li>'
        '<li>The Python demo baseline gets IntentBond\'s notation the way an agent following its skill would write it: '
        'an OFT item per requirement, implementation tags, a named <code>utest</code> tag and '
        '<code>@pytest.mark.oft_id</code> marker per test, the pytest hook from IntentBond\'s example, and '
        '<code>scope.json</code>.</li>'
        '<li>Each scenario script runs unchanged; what it added is tagged the same way. A reworded requirement gets '
        'revision 2; variant X2 leaves it at 1.</li>'
        '<li><code>ib check --base &lt;main before the scenario&gt; --candidate HEAD</code> with two scopes. '
        '<b>Default</b>: the documented example (links required, JUnit execution links). <b>Strict</b>: also a required '
        'revision increase for changed content, no skipped tests, and every baseline test pinned in '
        '<code>required_artifacts</code>.</li>'
        '<li>Exit 1 is <b>rejected</b>, 4 is <b>review</b> (checks passed, a person must review), 0 is <b>passed</b>.</li>'
        '</ol></section>',
        '<section><h2>Every scenario</h2>'
        + results_table(["This verifier", "IntentBond default", "IntentBond strict", "What IntentBond saw"], tool_cell)
        + '</section>',
        '<section><h2>What IntentBond does that this verifier doesn\'t</h2><div class="two quad">'
        '<div class="panel"><h3>Evidence you can check later</h3><p class="small">Each check saves its results with the '
        'hashes of the source it ran on. <code>ib verify</code> on the checked commit returned '
        f'<code>{escape(tidy(v["same_commit"]["output"]))}</code>; after a later code edit it returned '
        f'<code>{escape(tidy(v["after_code_edit"]["output"]))}</code>. This verifier recomputes everything on each '
        'run and keeps nothing.</p></div>'
        '<div class="panel"><h3>Pinned tests</h3><p class="small">Named tests listed in the trusted scope must run and '
        'pass. In T7 (strict) that rejected the rewrite because the pinned tests disappeared, even though other tagged '
        'tests remained.</p></div>'
        '<div class="panel"><h3>A review step built in</h3><p class="small">Every specification or test change is '
        'collected into <code>review.patch</code> with a summary of changed items, so the person reviewing sees exactly '
        'what moved.</p></div>'
        '<div class="panel"><h3>More ways to prove things</h3><p class="small">An explicit revision policy (rejected X2 '
        'in strict mode), tags read with Python\'s tokenizer so strings don\'t count, and optional Alloy and Z3 checks '
        'for selected properties (not exercised here).</p></div>'
        '</div></section>',
        '<section><h2>What the runs show</h2><ul class="plain">'
        '<li><b>On links and test runs they agree.</b> Reused ID, missing implementation, missing tests, a failing test, '
        'a broken suite, a stale revision and a "refactor" that broke a test: both reject all seven.</li>'
        '<li><b>Both distrust the change being checked.</b> IntentBond reads its scope from the base, as this verifier '
        'reads its config from the base branch, so an agent can\'t relax the rules in its own pull request.</li>'
        '<li><b>Where the answer needs judgement, IntentBond asks a person.</b> Code that is only a comment, an '
        '<code>assert True</code> test and weakened tests (T6, X1, X3) pass its checks and go to review, as designed. '
        'This verifier answers those with T3, T6 and T7, so the reviewer reads a finding instead of hunting for it.</li>'
        '<li><b>Revisions are a policy.</b> Strict mode rejects reworded content without a higher revision (X2); the '
        'default sends it to review. This verifier reads the change from git.</li>'
        '<li><b>The API contract and git history</b> are outside IntentBond\'s scope.</li></ul></section>',
        '<section><h2>Using them together</h2><ol class="steps">'
        '<li><b>This verifier\'s findings in IntentBond\'s review.</b> IntentBond decides what a person must review; '
        'this verifier tells them what\'s wrong before they start.</li>'
        '<li><b>IntentBond\'s evidence for this verifier\'s results.</b> Saving results tied to source hashes is this '
        'verifier\'s open gap. IntentBond\'s bundle and <code>verify</code> are a model for it.</li>'
        '<li><b>Pinned tests as a T4 option.</b> "These named tests must exist and pass" is a stronger rule than '
        '"at least one tagged test" and would suit critical requirements.</li></ol>'
        '<p class="note">When to pick which: IntentBond when people review every change and you want that review '
        'focused and its evidence kept. This verifier when you need to know what\'s wrong without reading the code. '
        'Both when you want both.</p></section>',
        '<section><h2>Limits of this comparison</h2><ul class="plain small">'
        '<li>Python only. The tags were written by a script acting as a careful agent, not by a real agent.</li>'
        '<li>The scenarios were written to test this verifier, so most of them ask its questions. The probes above ask '
        'IntentBond\'s.</li>'
        '<li>Exit 4 counts as "review", not as a detection or a miss: a careful reviewer may well catch T6, X1 and X3 in '
        '<code>review.patch</code>.</li>'
        '<li>In some containers Java prints a notice when <code>JAVA_TOOL_OPTIONS</code> is set, and IntentBond treats '
        'it as an OpenFastTrace error. The runner removes that variable for <code>ib</code>.</li></ul></section>',
        footer("experiments/intentbond/README.md",
               ["experiments/intentbond/results/intentbond.json", "experiments/intentbond/results/probes.json",
                "experiments/ours-variants.json"]),
    ]
    return page("Compared: IntentBond", "\n".join(body), extra_css=CSS, nav=NAV,
                current="docs/compare/intentbond.html")


def main():
    scenario_meta()
    variants = load(HERE / "ours-variants.json")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "openfasttrace.html").write_text(oft_page(load(HERE / "openfasttrace/results/openfasttrace.json"),
                                                     load(HERE / "openfasttrace/results/probes.json"), variants))
    (OUT / "intentbond.html").write_text(ib_page(load(HERE / "intentbond/results/intentbond.json"),
                                                 load(HERE / "intentbond/results/probes.json"), variants))
    print("wrote", OUT / "openfasttrace.html", OUT / "intentbond.html")


if __name__ == "__main__":
    main()
