package aqv

// review.html: the report laid out for an engineer who has to decide whether to accept the work.
// It answers, in this order: can I accept it, what needs a decision from me, what the agent must
// still fix, and what evidence stands behind each requirement that is marked proven.
// report.html keeps the spec-as-a-document view; this page is the working view.

import (
	"fmt"
	"regexp"
	"strings"
)

// personChecks fail on things only a person may change: the spec, the contracts, the design and
// the history of main. Everything else is the agent's to fix.
var personChecks = map[string]bool{"C1": true, "C2": true, "C3": true, "C4": true, "C6": true, "C7": true, "A3": true,
	"A4": true, "D3": true, "D4": true, "H7": true, "H10": true}

// whatToDo says what settles a failure of each check a person owns.
var whatToDo = map[string]string{
	"C1":  "Decide which is right, then change the requirement or the API contract so they agree. The agent may not edit either.",
	"C2":  "Decide which is right, then change the requirement or the contract's allowed values so they agree.",
	"C3":  "Decide the field's type and allowed values once, then make both contracts say it.",
	"C4":  "Bring the design document up to date with the contracts, or add what it describes to the spec.",
	"C6":  "Carry the design change into the requirements or contracts, or mark the commit Spec-Impact: none.",
	"C7":  "Nothing to decide here: settle the disagreement it points to, then have the agent check this requirement again.",
	"A3":  "Fix the API contract so it passes the lint rules.",
	"A4":  "A breaking API change needs a changed requirement. Change the spec, or take the change back.",
	"D3":  "Complete the data contract: every column needs a type, nullability and, when derived, its sources.",
	"D4":  "A breaking data change needs a changed requirement. Change the spec, or take the change back.",
	"H7":  "Main was rewritten. Find out why before trusting earlier results.",
	"H10": "An agent changed a file it is checked against. Review the change yourself: keep it under your name or revert it.",
}

var triageNames = map[string]string{"person": "Needs a person", "agent": "Needs the agent", "todo": "Not started", "proven": "Proven"}
var triageTone = map[string]string{"person": "bad", "agent": "warn", "todo": "muted", "proven": "ok"}

// triage sorts a requirement by who has to act on it next.
func triage(status string) string {
	switch status {
	case "Conflict":
		return "person"
	case "Sync":
		return "proven"
	case "Missing":
		return "todo"
	}
	return "agent"
}

var familyTitle = map[string]string{"C": "The spec, the contracts and the design agree", "T": "Tests prove the spec",
	"A": "The API matches its OpenAPI contract", "D": "The database matches its data contract", "H": "Git follows the conventions"}

const reviewCSS = `
/* Layout: verdict, then who must act, then one dense table, then evidence per requirement. */
.page { padding-left: max(20px, env(safe-area-inset-left, 0px)); padding-right: max(20px, env(safe-area-inset-right, 0px)); gap: 36px; }
.page > * { min-width: 0; }
.rv-verdict { display: grid; gap: 10px; }
.rv-verdict h1 { font-size: clamp(26px, 4.2vw, 36px); max-width: 26ch; }
.rv-verdict .rv-tag { display: inline-flex; align-items: center; gap: 8px; font-family: var(--font-mono); font-size: 12px; letter-spacing: .06em; text-transform: uppercase; }
.rv-verdict .rv-tag i { width: 10px; height: 10px; border-radius: 50%; }
.rv-bar { display: flex; height: 8px; border-radius: 4px; overflow: hidden; background: var(--muted-bg); }
.rv-bar i { display: block; height: 100%; }
.rv-triage { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0; border: 1px solid var(--line); border-radius: 10px; background: var(--surface); overflow: hidden; }
.rv-triage a { display: grid; gap: 2px; padding: 14px 16px; color: inherit; text-decoration: none; border-left: 1px solid var(--line); min-width: 0; }
.rv-triage a:first-child { border-left: 0; }
.rv-triage a:hover { background: var(--code-bg); }
.rv-triage a:focus-visible, .rv-filter button:focus-visible, .rv-search:focus-visible, .rv-table tr:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
.rv-triage b { font-family: var(--font-display); font-size: 30px; line-height: 1; font-variant-numeric: tabular-nums; }
.rv-triage span { font-size: 13px; color: var(--muted); }
.rv-triage .rv-k { font-weight: 600; color: var(--fg); font-size: 14px; }
.rv-triage .bad b { color: var(--bad-fg); } .rv-triage .warn b { color: var(--warn-fg); } .rv-triage .ok b { color: var(--ok-fg); }
.rv-triage .zero b { color: var(--muted); }
@media (max-width: 640px) { .rv-triage { grid-template-columns: repeat(2, minmax(0, 1fr)); } .rv-triage a:nth-child(3) { border-left: 0; } .rv-triage a:nth-child(n+3) { border-top: 1px solid var(--line); } }
.rv-h { display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px; }
.rv-h h2 { font-size: 20px; }
.rv-h .rv-n { font-family: var(--font-mono); font-size: 12px; color: var(--muted); }
.rv-cards { display: grid; gap: 12px; }
.rv-card { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 16px; display: grid; gap: 12px; min-width: 0; }
.rv-card.person { border-color: var(--bad-fg); }
.rv-card .rv-top { display: flex; flex-wrap: wrap; gap: 8px 10px; align-items: baseline; }
.rv-card .rv-id { font-family: var(--font-mono); font-size: 13px; font-weight: 600; }
.rv-card .rv-what { font-weight: 600; }
.rv-sides { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
@media (max-width: 720px) { .rv-sides { grid-template-columns: minmax(0, 1fr); } }
.rv-side { border-radius: 8px; background: var(--code-bg); padding: 12px 14px; display: grid; gap: 6px; align-content: start; min-width: 0; }
.rv-side .rv-lab { font-family: var(--font-mono); font-size: 11px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
.rv-side .rv-val { font-family: var(--font-mono); font-size: 14px; font-weight: 600; overflow-wrap: anywhere; }
.rv-side p { margin: 0; font-family: var(--font-serif); font-size: 15px; line-height: 1.5; }
.rv-side mark, .rv-req mark { background: var(--warn-bg); color: var(--warn-fg); padding: 0 3px; border-radius: 3px; }
.rv-side ul { margin: 0; padding-left: 18px; font-size: 14px; overflow-wrap: anywhere; }
.rv-do { font-size: 14px; color: var(--muted); margin: 0; }
.rv-do b { color: var(--fg); font-weight: 600; }
.rv-also { font-size: 14px; margin: 0; display: flex; flex-wrap: wrap; gap: 4px 8px; align-items: baseline; }
.rv-also b { font-weight: 600; }
.rv-list { display: grid; gap: 0; background: var(--surface); border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
.rv-item { display: grid; grid-template-columns: 118px 104px minmax(0, 1fr); gap: 4px 14px; padding: 10px 16px; border-top: 1px solid var(--line); align-items: baseline; font-size: 14px; }
.rv-item:first-child { border-top: 0; }
.rv-item a { font-family: var(--font-mono); font-size: 13px; font-weight: 600; color: var(--accent); }
.rv-item ul { margin: 0; padding: 0; list-style: none; display: grid; gap: 3px; overflow-wrap: anywhere; }
.rv-item li code, .rv-checks code, .rv-proj code { font-size: 12px; }
@media (max-width: 640px) { .rv-item { grid-template-columns: minmax(0, 1fr); } }
.rv-tools { display: flex; flex-wrap: wrap; gap: 8px 12px; align-items: center; }
.rv-filter { display: flex; flex-wrap: wrap; gap: 6px; }
.rv-filter button { font: inherit; font-size: 13px; padding: 5px 12px; border-radius: 999px; border: 1px solid var(--line); background: var(--surface); color: var(--fg); cursor: pointer; }
.rv-filter button[aria-pressed="true"] { background: var(--fg); color: var(--bg); border-color: var(--fg); }
.rv-search { font: inherit; font-size: 14px; padding: 6px 10px; border-radius: 8px; border: 1px solid var(--line); background: var(--surface); color: var(--fg); min-width: 0; flex: 1 1 180px; max-width: 320px; }
.rv-scroll { overflow-x: auto; border: 1px solid var(--line); border-radius: 10px; background: var(--surface); }
table.rv-table { border-collapse: collapse; width: 100%; min-width: 1040px; font-size: 13px; table-layout: fixed; }
.rv-table th:nth-child(1) { width: 112px; } .rv-table th:nth-child(2) { width: 100px; } .rv-table th:nth-child(4) { width: 132px; }
.rv-table th:nth-child(5) { width: 124px; } .rv-table th:nth-child(6) { width: 150px; } .rv-table th:nth-child(7) { width: 190px; } .rv-table th:nth-child(8) { width: 140px; }
.rv-fact > div { min-width: 0; overflow-wrap: anywhere; }
.rv-table th { text-align: left; font-family: var(--font-mono); font-size: 11px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); font-weight: 400; padding: 10px 12px; border-bottom: 1px solid var(--line); white-space: nowrap; }
.rv-table td { padding: 10px 12px; border-bottom: 1px solid var(--line); vertical-align: top; }
.rv-table tbody tr:last-child td { border-bottom: 0; }
.rv-table tbody tr { cursor: pointer; }
.rv-table tbody tr:hover { background: var(--code-bg); }
.rv-table td.rv-rid { font-family: var(--font-mono); font-weight: 600; white-space: nowrap; }
.rv-table td.rv-txt { color: var(--muted); }
.rv-table td.rv-txt span { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.rv-fact { display: grid; grid-template-columns: 10px minmax(0, 1fr); gap: 7px; align-items: baseline; font-variant-numeric: tabular-nums; }
.rv-fact i { width: 8px; height: 8px; border-radius: 50%; transform: translateY(-1px); }
.rv-fact small { display: block; color: var(--muted); font-size: 12px; }
.rv-reqs { display: grid; gap: 8px; }
details.rv-req { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; min-width: 0; }
details.rv-req > summary { list-style: none; cursor: pointer; padding: 12px 16px; display: grid; grid-template-columns: 118px 104px minmax(0, 1fr); gap: 4px 14px; align-items: baseline; }
details.rv-req > summary::-webkit-details-marker { display: none; }
details.rv-req > summary .rv-id { font-family: var(--font-mono); font-size: 13px; font-weight: 600; }
details.rv-req > summary .rv-line { font-family: var(--font-serif); font-size: 15px; line-height: 1.45; }
details.rv-req[open] > summary { border-bottom: 1px solid var(--line); }
@media (max-width: 640px) { details.rv-req > summary { grid-template-columns: minmax(0, 1fr); } }
.rv-body { display: grid; grid-template-columns: minmax(0, 5fr) minmax(0, 7fr); gap: 20px; padding: 16px; }
@media (max-width: 860px) { .rv-body { grid-template-columns: minmax(0, 1fr); } }
.rv-col { display: grid; gap: 14px; align-content: start; min-width: 0; }
.rv-sub { font-family: var(--font-mono); font-size: 11px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); margin: 0; }
.rv-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.rv-tags code { font-size: 12px; }
.rv-hist { margin: 0; padding: 0; list-style: none; display: grid; gap: 6px; font-size: 13px; }
.rv-hist li { display: grid; grid-template-columns: 10px 62px minmax(0, 1fr); gap: 8px; align-items: baseline; overflow-wrap: anywhere; }
.rv-hist i, .rv-ev i { width: 8px; height: 8px; border-radius: 50%; }
.rv-hist code { font-size: 12px; }
table.rv-checks { border-collapse: collapse; width: 100%; font-size: 13px; }
.rv-checks td { padding: 6px 8px 6px 0; border-bottom: 1px solid var(--line); vertical-align: baseline; overflow-wrap: anywhere; }
.rv-checks tr:last-child td { border-bottom: 0; }
.rv-checks td.rv-ck { font-family: var(--font-mono); font-weight: 600; white-space: nowrap; width: 38px; }
.rv-checks td.rv-vd { white-space: nowrap; width: 92px; }
.rv-checks tr.rv-quiet td { color: var(--muted); }
.rv-checks small { display: block; color: var(--muted); }
.rv-ev { margin: 0; padding: 10px 12px; list-style: none; display: grid; gap: 4px; font-size: 12px; font-family: var(--font-mono); max-height: 220px; overflow: auto; background: var(--code-bg); border-radius: 8px; }
.rv-ev li { display: grid; grid-template-columns: 10px minmax(0, 1fr); gap: 8px; align-items: baseline; overflow-wrap: anywhere; }
table.rv-proj { border-collapse: collapse; width: 100%; min-width: 640px; font-size: 13px; }
.rv-proj td { padding: 8px 12px; border-bottom: 1px solid var(--line); vertical-align: baseline; }
.rv-proj tr:last-child td { border-bottom: 0; }
.rv-proj tr.rv-fam td { font-family: var(--font-display); font-size: 14px; font-weight: 700; background: var(--code-bg); }
.rv-proj td.rv-ck { font-family: var(--font-mono); font-weight: 600; width: 44px; white-space: nowrap; }
.rv-proj td.rv-vd { width: 104px; white-space: nowrap; }
.rv-proj small { display: block; color: var(--muted); overflow-wrap: anywhere; }
.rv-proj small.bad { color: var(--bad-fg); } .rv-proj small.warn { color: var(--warn-fg); }
.rv-empty { color: var(--muted); font-size: 14px; margin: 0; }
[data-rv-hide] { display: none !important; }
`

const reviewJS = `<script>
(function () {
  var rows = [].slice.call(document.querySelectorAll('[data-triage]'));
  var buttons = [].slice.call(document.querySelectorAll('.rv-filter button'));
  var search = document.getElementById('rv-search');
  var want = 'all';
  function apply() {
    var q = (search && search.value || '').toLowerCase();
    rows.forEach(function (r) {
      var show = (want === 'all' || r.getAttribute('data-triage') === want) &&
        (!q || r.textContent.toLowerCase().indexOf(q) >= 0);
      if (show) { r.removeAttribute('data-rv-hide'); } else { r.setAttribute('data-rv-hide', ''); }
    });
  }
  buttons.forEach(function (b) {
    b.addEventListener('click', function () {
      want = b.getAttribute('data-want');
      buttons.forEach(function (x) { x.setAttribute('aria-pressed', x === b ? 'true' : 'false'); });
      apply();
    });
  });
  if (search) { search.addEventListener('input', apply); }
  function openReq(id) {
    var d = document.getElementById(id);
    if (!d) { return; }
    d.removeAttribute('data-rv-hide');
    d.open = true;
    d.scrollIntoView({ block: 'start' });
  }
  [].slice.call(document.querySelectorAll('tr[data-open]')).forEach(function (tr) {
    tr.addEventListener('click', function () { openReq(tr.getAttribute('data-open')); });
    tr.addEventListener('keydown', function (e) { if (e.key === 'Enter') { openReq(tr.getAttribute('data-open')); } });
  });
  [].slice.call(document.querySelectorAll('a[data-open]')).forEach(function (a) {
    a.addEventListener('click', function () { openReq(a.getAttribute('data-open')); });
  });
})();
</script>`

var (
	leadingInt = regexp.MustCompile(`^(\d+)`)
	nOfM       = regexp.MustCompile(`(\d+) of (?:its )?(\d+)`)
)

type reqResults map[string][]*OMap

func (rr reqResults) first(check string) *OMap {
	if rs := rr[check]; len(rs) > 0 {
		return rs[0]
	}
	return NewOMap()
}

func (rr reqResults) verdict(check string) string { return rr.first(check).Str("verdict") }

// worst is the tone of a group of checks: bad if one fails, ok if one passes, none otherwise.
func (rr reqResults) worst(warn bool, checks ...string) string {
	tone := "none"
	for _, c := range checks {
		for _, r := range rr[c] {
			switch r.Str("verdict") {
			case "fail", "error":
				if warn {
					return "warn"
				}
				return "bad"
			case "pass":
				tone = "ok"
			}
		}
	}
	return tone
}

func fact(tone, main, sub string) string {
	s := `<div class="rv-fact"><i style="background:` + dotFor(tone) + `"></i><div>` + escapeHTML(main)
	if sub != "" {
		s += `<small>` + escapeHTML(sub) + `</small>`
	}
	return s + `</div></div>`
}

func plural(n, word string) string {
	if n == "1" {
		return n + " " + word
	}
	return n + " " + word + "s"
}

// matrixCells are the five facts shown for a requirement: spec, code, tests, API, data.
func matrixCells(r *OMap, rr reqResults) []string {
	na := fact("none", "—", "")
	// Spec
	spec := fact("ok", "Current", "")
	switch {
	case r.Str("status") == "Conflict":
		spec = fact("bad", "Conflict", strings.Join(failingOf(rr, "C1", "C2", "C3", "C7"), ", "))
	case rr.verdict("T8") == "fail":
		spec = fact("warn", "Reworded since built", "")
	case rr.verdict("C5") == "fail":
		spec = fact("warn", "Contract changed since built", "")
	}
	// Code
	code := fact("none", "None yet", "")
	switch rr.verdict("T2") {
	case "pass":
		commits := leadingInt.FindString(rr.first("T2").Str("summary"))
		lines := leadingInt.FindString(rr.first("T3").Str("summary"))
		sub := ""
		if rr.verdict("T3") == "pass" && lines != "" {
			sub = plural(lines, "line") + " still in the code"
		}
		tone := "ok"
		if rr.verdict("T3") == "fail" {
			tone, sub = "bad", "none of its code is left"
		}
		code = fact(tone, plural(commits, "commit"), sub)
	}
	// Tests
	tests := fact("none", "None yet", "")
	if v := rr.verdict("T4"); v == "pass" || v == "error" || rr.verdict("T5") != "" && rr.verdict("T5") != "skip" {
		n := leadingInt.FindString(rr.first("T4").Str("summary"))
		main, tone := plural(n, "tagged test"), rr.worst(false, "T5")
		if n == "" {
			main = "Tagged tests"
		}
		if rr.verdict("T5") == "fail" || v == "error" {
			main, tone = "Failing", "bad"
		}
		var subs []string
		if m := nOfM.FindStringSubmatch(rr.first("T6").Str("summary")); m != nil && rr.verdict("T6") != "skip" {
			subs = append(subs, m[1]+"/"+m[2]+" lines run")
			if rr.verdict("T6") == "fail" && tone == "ok" {
				tone = "warn"
			}
		}
		if m := nOfM.FindStringSubmatch(rr.first("T7").Str("summary")); m != nil && (rr.verdict("T7") == "pass" || rr.verdict("T7") == "fail") {
			subs = append(subs, m[1]+"/"+m[2]+" broken versions caught")
			if rr.verdict("T7") == "fail" && tone == "ok" {
				tone = "warn"
			}
		}
		if rr.verdict("A8") == "fail" {
			d, _ := rr.first("A8").Get("details").(*OMap)
			subs = append(subs, "never saw "+strings.Join(strList(d.Get("never_seen")), ", "))
			if tone == "ok" {
				tone = "warn"
			}
		}
		tests = fact(tone, main, strings.Join(subs, " · "))
	} else if rr.verdict("T4") == "fail" && rr.verdict("T2") == "pass" {
		tests = fact("warn", "No tagged test", "")
	}
	// Before there is code, the API and data columns only say what the requirement will touch.
	started := rr.verdict("T2") == "pass"
	// API
	api := na
	if ops := strList(r.Get("api")); len(ops) > 0 && !started {
		tone := "none"
		if rr.verdict("A1") == "fail" {
			tone = "bad"
		}
		api = fact(tone, strings.Join(ops, ", "), map[string]string{"none": "in the contract, not built", "bad": "not in the contract"}[tone])
	} else if len(ops) > 0 {
		tone := rr.worst(false, "A1", "A5", "A6", "A7")
		sub := ""
		if n := leadingInt.FindString(rr.first("A6").Str("summary")); n != "" && rr.verdict("A6") == "pass" {
			sub = plural(n, "response") + " checked"
		} else if tone == "bad" {
			sub = strings.Join(failingOf(rr, "A1", "A5", "A6", "A7"), ", ") + " failing"
		}
		api = fact(tone, strings.Join(ops, ", "), sub)
	}
	// Data
	data := na
	if ds := strList(r.Get("data")); len(ds) > 0 && !started {
		tone := "none"
		if rr.verdict("D1") == "fail" {
			tone = "bad"
		}
		data = fact(tone, strings.Join(ds, ", "), map[string]string{"none": "in the contract, not built", "bad": "not in the data contract"}[tone])
	} else if len(ds) > 0 {
		tone := rr.worst(false, "D1", "D5", "D6")
		sub := ""
		switch {
		case tone == "bad":
			sub = strings.Join(failingOf(rr, "D1", "D5", "D6"), ", ") + " failing"
		case rr.verdict("D6") == "pass":
			sub = "schema and lineage match"
		case rr.verdict("D5") == "pass":
			sub = "schema matches"
		}
		data = fact(tone, strings.Join(ds, ", "), sub)
	}
	return []string{spec, code, tests, api, data}
}

func failingOf(rr reqResults, checks ...string) []string {
	var out []string
	for _, c := range checks {
		if v := rr.verdict(c); v == "fail" || v == "error" {
			out = append(out, c)
		}
	}
	return out
}

// markTokens wraps each of the given words in <mark> inside already-escaped text.
func markTokens(text string, tokens []string) string {
	out := escapeHTML(text)
	for _, t := range tokens {
		e := escapeHTML(t)
		if e != "" {
			out = strings.ReplaceAll(out, e, "<mark>"+e+"</mark>")
		}
	}
	return out
}

func detailList(v any) []string {
	if s, ok := v.(string); ok && s != "" {
		return []string{s}
	}
	return strList(v)
}

func ulHTML(items []string) string {
	var b strings.Builder
	b.WriteString("<ul>")
	for _, it := range items {
		b.WriteString("<li>" + escapeHTML(it) + "</li>")
	}
	return b.String() + "</ul>"
}

// decisionCard shows one failure a person has to settle, with both sides where there are two.
// also lists the other requirements the same disagreement holds up (C7).
func decisionCard(r, req *OMap, also []string) string {
	chk := r.Str("check")
	d, _ := r.Get("details").(*OMap)
	var b strings.Builder
	b.WriteString(`<div class="rv-card person"><div class="rv-top">` + chip(chk, "bad"))
	if req != nil {
		b.WriteString(`<a class="rv-id" href="#` + escapeHTML(req.Str("id")) + `" data-open="` + escapeHTML(req.Str("id")) + `">` +
			escapeHTML(req.Str("id")) + `</a>`)
	}
	b.WriteString(`<span class="rv-what">` + escapeHTML(Checks[chk]) + `</span></div>`)
	says, other := detailList(d.Get("requirement_says")), detailList(d.Get("contract_says"))
	switch {
	case req != nil && len(says) > 0:
		quoted := says
		if chk == "C2" {
			quoted = make([]string, len(says))
			for i, s := range says {
				quoted[i] = `"` + s + `"`
			}
		}
		b.WriteString(`<div class="rv-sides"><div class="rv-side"><span class="rv-lab">The requirement says</span>` +
			`<span class="rv-val">` + escapeHTML(strings.Join(quoted, ", ")) + `</span><p>` + markTokens(req.Str("text"), quoted) +
			`</p></div><div class="rv-side"><span class="rv-lab">The contract says</span>` + ulHTML(other) + `</div></div>`)
	case len(detailList(d.Get("problems"))) > 0:
		b.WriteString(`<div class="rv-side">` + ulHTML(detailList(d.Get("problems"))) + `</div>`)
	case len(detailList(d.Get("offenders"))) > 0:
		b.WriteString(`<div class="rv-side">` + ulHTML(detailList(d.Get("offenders"))) + `</div>`)
	default:
		b.WriteString(`<div class="rv-side"><p>` + escapeHTML(r.Str("summary")) + `</p></div>`)
	}
	if len(also) > 0 {
		links := make([]string, len(also))
		for i, id := range also {
			links[i] = `<a class="rv-id" href="#` + escapeHTML(id) + `" data-open="` + escapeHTML(id) + `">` + escapeHTML(id) + `</a>`
		}
		b.WriteString(`<p class="rv-also"><b>Also holds up:</b> ` + strings.Join(links, " ") +
			` <span class="muted">They carry the same field, so they can't be proven until this is settled.</span></p>`)
	}
	if todo := whatToDo[chk]; todo != "" {
		b.WriteString(`<p class="rv-do"><b>To settle it:</b> ` + escapeHTML(todo) + `</p>`)
	}
	return b.String() + `</div>`
}

var verdictRank = map[string]int{"fail": 0, "error": 0, "not_covered": 1, "pass": 2, "not_run": 3, "skip": 4}

// ReviewHTML renders review.html from a report.
func ReviewHTML(rep *OMap) string {
	reqs := maps(rep.Get("requirements"))
	results := maps(rep.Get("results"))
	checks := rep.Map("checks")
	ids := reportCheckIDs(rep)
	byReq := map[string]reqResults{}
	reqByID := map[string]*OMap{}
	for _, r := range reqs {
		byReq[r.Str("id")] = reqResults{}
		reqByID[r.Str("id")] = r
	}
	var project []*OMap // failures not tied to one requirement
	for _, r := range results {
		if rr, ok := byReq[r.Str("subject")]; ok && r.Str("scope") == "requirement" {
			rr[r.Str("check")] = append(rr[r.Str("check")], r)
		} else if v := r.Str("verdict"); v == "fail" || v == "error" {
			project = append(project, r)
		}
	}
	counts := map[string]int{}
	for _, r := range reqs {
		counts[triage(r.Str("status"))]++
	}
	// Decisions: conflicts on requirements, then project-level failures a person owns.
	var decisions, agentProject []string
	nDecisions := 0
	heldUp := map[string][]string{} // "C2 AC-x-001" -> requirements that disagreement also holds up
	for _, r := range reqs {
		for _, x := range byReq[r.Str("id")]["C7"] {
			if d, _ := x.Get("details").(*OMap); x.Str("verdict") == "fail" && d != nil {
				for _, ref := range detailList(d.Get("because")) {
					heldUp[ref] = append(heldUp[ref], r.Str("id"))
				}
			}
		}
	}
	for _, r := range reqs {
		if r.Str("status") != "Conflict" {
			continue
		}
		for _, chk := range []string{"C1", "C2", "C3"} {
			for _, x := range byReq[r.Str("id")][chk] {
				if x.Str("verdict") == "fail" {
					decisions = append(decisions, decisionCard(x, r, heldUp[chk+" "+r.Str("id")]))
					nDecisions++
				}
			}
		}
	}
	built := 0
	for _, r := range reqs {
		if byReq[r.Str("id")].verdict("T2") == "pass" {
			built++
		}
	}
	waiting := 0
	for _, x := range project {
		if x.Str("verdict") == "error" && built == 0 {
			waiting++ // a check that needs code to run says nothing before there is code
			continue
		}
		if personChecks[x.Str("check")] {
			decisions = append(decisions, decisionCard(x, nil, nil))
			nDecisions++
		} else {
			subj := ""
			switch x.Str("subject") {
			case "history", "project", "spec", "contract", "data contract", "database", "migrations", "design", "routes", "service":
			default:
				subj = `<code>` + escapeHTML(x.Str("subject")) + `</code> `
			}
			agentProject = append(agentProject, `<div class="rv-item"><span>`+chip(x.Str("check"), "bad")+`</span><span class="muted small">project</span><ul><li>`+
				subj+escapeHTML(x.Str("summary"))+`</li></ul></div>`)
		}
	}
	notChecked := []string{}
	for _, c := range ids {
		if v := checks.Str(c); v == "not_covered" || v == "not_run" {
			notChecked = append(notChecked, c)
		}
	}

	// ---- verdict
	n := len(reqs)
	agentN := counts["agent"] + len(agentProject)
	tone, tag, h := "ok", "Ready to accept", fmt.Sprintf("All %d requirements are proven and no check fails.", n)
	switch {
	case nDecisions > 0:
		tone, tag = "bad", "Blocked on a person"
		h = fmt.Sprintf("%s for a person before this can be trusted.", upperFirst(plural(fmt.Sprint(nDecisions), "decision")))
	case agentN > 0:
		tone, tag = "warn", "Not ready"
		h = fmt.Sprintf("%s for the agent to fix.", upperFirst(plural(fmt.Sprint(agentN), "problem")))
	case counts["todo"] > 0:
		tone, tag = "muted", "In progress"
		h = fmt.Sprintf("%d of %d requirements proven. Nothing built so far breaks a check.", counts["proven"], n)
	}
	sub := fmt.Sprintf("%d of %d requirements proven by running code.", counts["proven"], n)
	if waiting > 0 {
		sub += fmt.Sprintf(" %s can't run until there is code.", upperFirst(plural(fmt.Sprint(waiting), "check")))
	}
	if len(notChecked) > 0 {
		sub += fmt.Sprintf(" %s not checked in this run (%s) and not counted as passing.", upperFirst(plural(fmt.Sprint(len(notChecked)), "check")),
			strings.Join(notChecked, ", "))
	}
	var bar strings.Builder
	for _, k := range []string{"proven", "agent", "person", "todo"} {
		if counts[k] > 0 && n > 0 {
			fmt.Fprintf(&bar, `<i style="width:%.2f%%;background:%s" title="%s: %d"></i>`, 100*float64(counts[k])/float64(n),
				map[string]string{"proven": "var(--ok-fg)", "agent": "var(--warn-fg)", "person": "var(--bad-fg)", "todo": "var(--muted-bg)"}[k],
				triageNames[k], counts[k])
		}
	}
	var body []string
	body = append(body, `<header class="rv-verdict"><span class="eyebrow">`+escapeHTML(filepathBase(rep.Str("repo")))+` · `+
		escapeHTML(rep.Str("head_branch"))+` · `+rangeLabel(rep)+`</span><span class="rv-tag"><i style="background:`+
		dotFor(map[string]string{"ok": "ok", "warn": "warn", "bad": "bad", "muted": "none"}[tone])+`"></i>`+tag+
		`</span><h1>`+escapeHTML(h)+`</h1><p class="lede muted">`+escapeHTML(sub)+`</p><div class="rv-bar" role="img" aria-label="Requirements by who must act">`+
		bar.String()+`</div></header>`)

	tile := func(key, anchor string, count int, what string) string {
		cls := triageTone[key]
		if count == 0 {
			cls = "zero"
		}
		return fmt.Sprintf(`<a class="%s" href="#%s"><b>%d</b><span class="rv-k">%s</span><span>%s</span></a>`, cls, anchor, count,
			triageNames[key], what)
	}
	body = append(body, `<nav class="rv-triage" aria-label="Who must act">`+
		tile("person", "decisions", nDecisions, "Documents disagree, or a protected file changed")+
		tile("agent", "fixes", agentN, "Built, but a check fails")+
		tile("todo", "requirements", counts["todo"], "No code references them yet")+
		tile("proven", "requirements", counts["proven"], "Code, tests and contracts agree")+`</nav>`)

	// ---- decisions
	if nDecisions > 0 {
		body = append(body, `<section id="decisions"><div class="rv-h"><h2>Decisions for a person</h2><span class="rv-n">`+
			fmt.Sprint(nDecisions)+`</span></div><div class="rv-cards">`+strings.Join(decisions, "")+`</div></section>`)
	}

	// ---- fixes
	var fixes strings.Builder
	for _, r := range reqs {
		if triage(r.Str("status")) != "agent" {
			continue
		}
		var lis strings.Builder
		for _, chk := range ids {
			for _, x := range byReq[r.Str("id")][chk] {
				if v := x.Str("verdict"); v == "fail" || v == "error" {
					lis.WriteString(`<li><code>` + chk + `</code> ` + escapeHTML(x.Str("summary")) + `</li>`)
				}
			}
		}
		fixes.WriteString(`<div class="rv-item"><a href="#` + escapeHTML(r.Str("id")) + `" data-open="` + escapeHTML(r.Str("id")) + `">` +
			escapeHTML(r.Str("id")) + `</a><span>` + chip(r.Str("status"), statusToneOf(r.Str("status"))) + `</span><ul>` + lis.String() + `</ul></div>`)
	}
	if agentN > 0 {
		body = append(body, `<section id="fixes"><div class="rv-h"><h2>For the agent to fix</h2><span class="rv-n">`+fmt.Sprint(agentN)+
			`</span></div><div class="rv-list">`+fixes.String()+strings.Join(agentProject, "")+`</div></section>`)
	}

	// ---- the matrix
	var rows strings.Builder
	for _, r := range reqs {
		id := r.Str("id")
		rows.WriteString(`<tr data-triage="` + triage(r.Str("status")) + `" data-open="` + escapeHTML(id) + `" tabindex="0"><td class="rv-rid">` +
			escapeHTML(id) + `</td><td>` + chip(r.Str("status"), statusToneOf(r.Str("status"))) + `</td><td class="rv-txt"><span>` +
			escapeHTML(r.Str("text")) + `</span></td>`)
		for _, c := range matrixCells(r, byReq[id]) {
			rows.WriteString(`<td>` + c + `</td>`)
		}
		rows.WriteString(`</tr>`)
	}
	filter := `<div class="rv-filter" role="group" aria-label="Show requirements"><button type="button" data-want="all" aria-pressed="true">All ` +
		fmt.Sprint(n) + `</button>`
	for _, k := range []string{"person", "agent", "todo", "proven"} {
		if counts[k] > 0 {
			filter += fmt.Sprintf(`<button type="button" data-want="%s" aria-pressed="false">%s %d</button>`, k, triageNames[k], counts[k])
		}
	}
	body = append(body, `<section id="requirements"><div class="rv-h"><h2>Requirements</h2><span class="rv-n">what stands behind each one</span></div>`+
		`<div class="rv-tools">`+filter+`</div><input class="rv-search" id="rv-search" type="search" placeholder="Filter by ID, word, operation or dataset" aria-label="Filter requirements"></div>`+
		`<div class="rv-scroll"><table class="rv-table"><thead><tr><th>Requirement</th><th>Status</th><th>Says</th><th>Spec</th><th>Code</th><th>Tests</th><th>API</th><th>Data</th></tr></thead><tbody>`+
		rows.String()+`</tbody></table></div></section>`)

	// ---- evidence per requirement
	var blocks strings.Builder
	for _, r := range reqs {
		blocks.WriteString(reviewRequirement(r, byReq[r.Str("id")], ids))
	}
	body = append(body, `<section><div class="rv-h"><h2>Evidence</h2><span class="rv-n">every check, per requirement</span></div><div class="rv-reqs">`+
		blocks.String()+`</div></section>`)

	// ---- project-wide checks
	var proj strings.Builder
	for _, fam := range []string{"C", "T", "A", "D", "H"} {
		var famRows strings.Builder
		for _, chk := range ids {
			if !strings.HasPrefix(chk, fam) {
				continue
			}
			var msgs strings.Builder
			shownN := 0
			for _, x := range results {
				v := x.Str("verdict")
				if x.Str("check") != chk || !(v == "fail" || v == "error" || v == "not_covered") || shownN >= 4 {
					continue
				}
				shownN++
				cls := "bad"
				if v == "not_covered" {
					cls = "warn"
				}
				subj := ""
				if _, ok := reqByID[x.Str("subject")]; ok {
					subj = x.Str("subject") + ": "
				}
				msgs.WriteString(`<small class="` + cls + `">` + escapeHTML(subj+x.Str("summary")) + `</small>`)
			}
			famRows.WriteString(`<tr><td class="rv-ck">` + chk + `</td><td class="rv-vd">` + verdictChip(checks.Str(chk)) + `</td><td>` +
				escapeHTML(Checks[chk]) + msgs.String() + `</td></tr>`)
		}
		if famRows.Len() > 0 {
			proj.WriteString(`<tr class="rv-fam"><td colspan="3">` + escapeHTML(familyTitle[fam]) + `</td></tr>` + famRows.String())
		}
	}
	body = append(body, `<section id="checks"><div class="rv-h"><h2>All `+fmt.Sprint(len(ids))+` checks</h2><span class="rv-n">not covered is never counted as pass</span></div>`+
		`<div class="rv-scroll"><table class="rv-proj"><tbody>`+proj.String()+`</tbody></table></div></section>`)

	if sc := rep.Map("scorecard"); sc.Len() > 0 {
		var srows strings.Builder
		for _, who := range sc.Keys() {
			a := sc.Map(who)
			rate, _ := toFloat(a.Get("git_rule_pass_rate"))
			srows.WriteString(`<tr><td class="name">` + escapeHTML(who) + `</td><td>` + pyStr(a.Get("commits")) + `</td><td>` +
				pyStr(a.Get("commits_breaking_git_rules")) + `</td><td>` + percent(rate) + `</td></tr>`)
		}
		body = append(body, `<section><div class="rv-h"><h2>Who committed</h2></div><div class="table-wrap"><table><thead><tr><th>Author</th>`+
			`<th>Commits</th><th>Breaking a git rule</th><th>Git rule pass rate</th></tr></thead><tbody>`+srows.String()+`</tbody></table></div></section>`)
	}
	body = append(body, `<footer>Generated by <code>aqv check</code> at commit <code>`+head(rep.Str("head"), 12)+
		`</code>. No model judged anything on this page: rerun the same command on the same commit to get the same answer. `+
		`The same results as a document: <a href="report.html">report.html</a>.</footer>`+reviewJS)
	return pageHTML("Agent Work Review", strings.Join(body, "\n"), viewCSS+reviewCSS, nil, "")
}

func statusToneOf(status string) string {
	if t, ok := statusTone[status]; ok {
		return t
	}
	return "muted"
}

func filepathBase(p string) string {
	p = strings.TrimRight(p, "/")
	if i := strings.LastIndex(p, "/"); i >= 0 {
		return p[i+1:]
	}
	return p
}

// reviewRequirement is one requirement's evidence: its wording and history on the left, every
// check that looked at it on the right.
func reviewRequirement(r *OMap, rr reqResults, ids []string) string {
	id := r.Str("id")
	segs := maps(r.Get("segments"))
	text := escapeHTML(r.Str("text"))
	if len(segs) > 0 {
		parts := make([]string, len(segs))
		for i, s := range segs {
			parts[i] = escapeHTML(s.Str("t"))
			if s.Truthy("m") {
				parts[i] = "<mark>" + parts[i] + "</mark>"
			}
		}
		text = strings.Join(parts, " ")
	}
	var tags strings.Builder
	for _, a := range strList(r.Get("api")) {
		tags.WriteString(`<code>` + escapeHTML(a) + `</code>`)
	}
	for _, d := range strList(r.Get("data")) {
		tags.WriteString(`<code>data: ` + escapeHTML(d) + `</code>`)
	}
	var hist strings.Builder
	for _, e := range maps(r.Get("timeline")) {
		hist.WriteString(`<li><i style="background:` + dotFor(e.Str("state")) + `"></i><code>` + escapeHTML(e.Str("sha")) + `</code><span>` +
			escapeHTML(e.Str("label")) + `</span></li>`)
	}
	type row struct {
		rank int
		html string
	}
	var crows []row
	for _, chk := range ids {
		for _, x := range rr[chk] {
			v := x.Str("verdict")
			cls := ""
			if v == "skip" || v == "not_run" {
				cls = ` class="rv-quiet"`
			}
			extra := ""
			if d, ok := x.Get("details").(*OMap); ok && (v == "fail" || v == "error") {
				for _, key := range []string{"violations", "problems", "changes", "survivors"} {
					items := detailList(d.Get(key))
					if len(items) > 4 {
						items = append(items[:4], fmt.Sprintf("and %d more", len(items)-4))
					}
					for _, it := range items {
						extra += `<small>` + escapeHTML(it) + `</small>`
					}
				}
			}
			crows = append(crows, row{verdictRank[v], `<tr` + cls + `><td class="rv-ck">` + chk + `</td><td class="rv-vd">` + verdictChip(v) +
				`</td><td>` + escapeHTML(x.Str("summary")) + `<small>` + escapeHTML(Checks[chk]) + `</small>` + extra + `</td></tr>`})
		}
	}
	var ctable strings.Builder
	for rank := 0; rank <= 4; rank++ {
		for _, c := range crows {
			if c.rank == rank {
				ctable.WriteString(c.html)
			}
		}
	}
	var ev strings.Builder
	now := maps(r.Get("now"))
	for _, e := range now {
		ev.WriteString(`<li><i style="background:` + dotFor(e.Str("state")) + `"></i><span>` + escapeHTML(e.Str("label")) + `</span></li>`)
	}
	open := ""
	if t := triage(r.Str("status")); t == "person" || t == "agent" {
		open = " open"
	}
	left := `<div class="rv-col"><p class="rv-sub">Why it has this status</p><p class="note ` + statusToneOf(r.Str("status")) + `" style="margin:0">` +
		escapeHTML(r.Str("note")) + `</p>`
	if tags.Len() > 0 {
		left += `<p class="rv-sub">Serves</p><div class="rv-tags">` + tags.String() + `</div>`
	}
	if hist.Len() > 0 {
		left += `<p class="rv-sub">History</p><ol class="rv-hist">` + hist.String() + `</ol>`
	}
	left += `</div>`
	right := `<div class="rv-col"><p class="rv-sub">Checks that looked at it</p><table class="rv-checks"><tbody>` + ctable.String() + `</tbody></table>`
	if len(now) > 0 {
		right += fmt.Sprintf(`<p class="rv-sub">Test and contract evidence at this commit (%d lines)</p><ul class="rv-ev">`, len(now)) + ev.String() + `</ul>`
	}
	right += `</div>`
	return `<details class="rv-req" id="` + escapeHTML(id) + `" data-triage="` + triage(r.Str("status")) + `"` + open + `><summary><span class="rv-id">` +
		escapeHTML(id) + `</span><span>` + chip(r.Str("status"), statusToneOf(r.Str("status"))) + `</span><span class="rv-line">` + text +
		`</span></summary><div class="rv-body">` + left + right + `</div></details>`
}
