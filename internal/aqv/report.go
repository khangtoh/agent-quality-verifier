package aqv

// report.txt and report.html for one run (cli.text_report and html.run_report).

import (
	"fmt"
	"path/filepath"
	"strings"
	"unicode/utf8"
)

var mark = map[string]string{"pass": "pass", "fail": "FAIL", "error": "ERROR", "skip": "skip",
	"not_covered": "not covered", "not_run": "not run"}

var groups = [][2]string{{"Tests prove the spec", "T"}, {"The API matches its OpenAPI contract", "A"},
	{"Git follows the conventions", "H"}}

var statusTone = map[string]string{"Sync": "ok", "Drift": "warn", "Untested": "warn", "Unexercised": "warn",
	"Weak": "warn", "Missing": "muted", "Gone": "bad", "Failing": "bad", "Contract": "bad"}
var verdictTone = map[string]string{"pass": "ok", "fail": "bad", "error": "bad", "skip": "muted",
	"not_covered": "warn", "not_run": "muted"}
var verdictLabel = map[string]string{"pass": "pass", "fail": "fail", "error": "error", "skip": "skip",
	"not_covered": "not covered", "not_run": "not run"}
var goals = [][2]string{{"T", "Tests prove the spec"}, {"A", "The API matches its OpenAPI contract"},
	{"H", "Git follows the conventions"}}

func pad(s string, w int) string {
	n := utf8.RuneCountInString(s)
	if n >= w {
		return s
	}
	return s + strings.Repeat(" ", w-n)
}

func maps(v any) []*OMap {
	var out []*OMap
	for _, x := range asList(v) {
		if m, ok := x.(*OMap); ok {
			out = append(out, m)
		}
	}
	return out
}

func rangeLabel(rep *OMap) string {
	if rep.Get("base") != nil {
		return head(rep.Str("base"), 7) + ".." + head(rep.Str("head"), 7)
	}
	return "all history to " + head(rep.Str("head"), 7)
}

// TextReport renders report.txt.
func TextReport(rep *OMap) string {
	var out []string
	out = append(out, fmt.Sprintf("Agent Quality Verifier: %s (%s, %s)", filepath.Base(rep.Str("repo")),
		rep.Str("head_branch"), rangeLabel(rep)))
	out = append(out, "")
	out = append(out, pad("REQUIREMENT", 13)+pad("STATUS", 13)+"FAILING CHECKS")
	for _, r := range maps(rep.Get("requirements")) {
		fc := strings.Join(strList(r.Get("failing_checks")), ", ")
		if fc == "" {
			fc = "-"
		}
		out = append(out, pad(r.Str("id"), 13)+pad(r.Str("status"), 13)+fc)
	}
	out = append(out, "")
	results := maps(rep.Get("results"))
	checks := rep.Map("checks")
	for _, g := range groups {
		out = append(out, g[0])
		for _, chk := range CheckIDs {
			if !strings.HasPrefix(chk, g[1]) {
				continue
			}
			out = append(out, "  "+pad(chk, 4)+pad(mark[checks.Str(chk)], 13)+Checks[chk])
			for _, r := range results {
				v := r.Str("verdict")
				if r.Str("check") == chk && (v == "fail" || v == "error" || v == "not_covered") {
					subj := r.Str("subject") + ": "
					switch r.Str("subject") {
					case "history", "project", "spec", "contract":
						subj = ""
					}
					out = append(out, "        "+subj+r.Str("summary"))
				}
			}
		}
		out = append(out, "")
	}
	sc := rep.Map("scorecard")
	if sc.Len() > 0 {
		out = append(out, "Agent scorecard (this range)")
		for _, who := range sc.Keys() {
			a := sc.Map(who)
			rate, _ := toFloat(a.Get("git_rule_pass_rate"))
			refs := strings.Join(strList(a.Get("requirements_referenced")), ", ")
			if refs == "" {
				refs = "-"
			}
			out = append(out, fmt.Sprintf("  %s: %s commit(s), git rule pass rate %s, requirements %s", who,
				pyStr(a.Get("commits")), percent(rate), refs))
		}
	}
	return strings.Join(out, "\n")
}

// ---------------------------------------------------------------- report.html

// navLinks are the site navigation entries; paths are relative to the repository root.
var navLinks = [][2]string{{"index.html", "Home"}, {"docs/framework.html", "Framework"},
	{"demo/results/index.html", "Results"}, {"demo/results-go/index.html", "Results (Go)"},
	{"docs/compare/openfasttrace.html", "vs OpenFastTrace"}, {"docs/compare/intentbond.html", "vs IntentBond"}}

// siteNav renders the navigation bar; root is the relative path from the page to the repo root.
func siteNav(root, current string) string {
	var links strings.Builder
	for _, l := range navLinks {
		cur := ""
		if l[0] == current {
			cur = ` aria-current="page"`
		}
		links.WriteString(`<a class="lk" href="` + root + l[0] + `"` + cur + `>` + escapeHTML(l[1]) + `</a>`)
	}
	return `<nav class="site-nav" aria-label="Site"><div class="in"><a class="brand" href="` + root +
		`index.html">Agent Quality Verifier</a>` + links.String() + `</div></nav>`
}

// pageHTML wraps a body in the shared page. nav is the relative path to the repository root
// for the site navigation, or nil for a standalone report.
func pageHTML(title, body, extraCSS string, nav *string, current string) string {
	top := ""
	if nav != nil {
		top = siteNav(*nav, current) + "\n"
	}
	return "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n" +
		"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n" +
		"<title>" + escapeHTML(title) + "</title>\n" + fontsHTML + "\n<style>" + siteCSS + extraCSS +
		"</style>\n</head>\n<body>\n" + top + "<main class=\"page\">\n" + body + "\n</main>\n</body>\n</html>\n"
}

func chip(text, tone string) string {
	return `<span class="chip ` + tone + `">` + escapeHTML(text) + `</span>`
}

func verdictChip(v string) string {
	label, ok := verdictLabel[v]
	if !ok {
		label = v
	}
	tone, ok := verdictTone[v]
	if !ok {
		tone = "muted"
	}
	return chip(label, tone)
}

var dot = map[string]string{"ok": "var(--ok-fg)", "warn": "var(--warn-fg)", "bad": "var(--bad-fg)",
	"none": "var(--muted-bg)", "neutral": "var(--muted-bg)"}
var vitalNames = []string{"spec", "code", "api", "tests"}
var phrase = map[string]string{"Missing": "not implemented", "Gone": "with their code gone", "Untested": "untested",
	"Failing": "failing", "Unexercised": "not exercised by their tests", "Weak": "with weak tests",
	"Contract": "breaking the API contract", "Drift": "changed in the spec since implemented"}

func dotFor(state string) string {
	if d, ok := dot[state]; ok {
		return d
	}
	return dot["none"]
}

// requirementBlock renders one requirement; open is nil to open it only when it isn't Sync.
func requirementBlock(r *OMap, open *bool) string {
	v := r.Map("vitals")
	val := func(k string) string {
		if v.Has(k) {
			return v.Str(k)
		}
		return "none"
	}
	tone, ok := statusTone[r.Str("status")]
	if !ok || tone == "muted" {
		tone = "bad"
	}
	var rail, chips strings.Builder
	for _, k := range vitalNames {
		fmt.Fprintf(&rail, `<span class="v-%s" title="%s: %s"></span>`, val(k), k, val(k))
		fmt.Fprintf(&chips, `<span><i style="background:%s"></i>%s</span>`, dot[val(k)], k)
	}
	segs := maps(r.Get("segments"))
	if len(segs) == 0 {
		segs = []*OMap{om("t", r.Str("text"), "m", false)}
	}
	parts := make([]string, len(segs))
	for i, s := range segs {
		if s.Truthy("m") {
			parts[i] = "<mark>" + escapeHTML(s.Str("t")) + "</mark>"
		} else {
			parts[i] = escapeHTML(s.Str("t"))
		}
	}
	text := strings.Join(parts, " ")
	var items []string
	for _, e := range maps(r.Get("timeline")) {
		items = append(items, `<li style="--dot:`+dotFor(e.Str("state"))+`"><code>`+escapeHTML(e.Str("sha"))+`</code>`+
			escapeHTML(e.Str("label"))+`</li>`)
	}
	if now := maps(r.Get("now")); len(now) > 0 {
		items = append(items, `<li class="now-sep">Now</li>`)
		for _, e := range now {
			items = append(items, `<li style="--dot:`+dotFor(e.Str("state"))+`">`+escapeHTML(e.Str("label"))+`</li>`)
		}
	}
	openAttr := ""
	if (open == nil && r.Str("status") != "Sync") || (open != nil && *open) {
		openAttr = " open"
	}
	api := ""
	if a := strList(r.Get("api")); len(a) > 0 {
		api = " · " + escapeHTML(strings.Join(a, ", "))
	}
	return `<div class="clause" id="` + escapeHTML(r.Str("id")) + `"><div class="rail" aria-hidden="true">` + rail.String() +
		`</div><details` + openAttr + `><summary><div class="head"><span class="rid">` + escapeHTML(r.Str("id")) + api +
		`</span><span class="vitals">` + chips.String() + `</span></div><p class="text">` + text + `</p></summary>` +
		`<div class="inner"><p class="note ` + tone + `">` + escapeHTML(r.Str("note")) + `</p>` +
		`<ol class="tl">` + strings.Join(items, "") + `</ol></div></details></div>`
}

func headline(reqs []*OMap) (string, string) {
	proven := 0
	counts := NewOMap()
	for _, r := range reqs {
		st := r.Str("status")
		if st == "Sync" {
			proven++
			continue
		}
		n, _ := counts.Get(st).(int)
		counts.Set(st, n+1)
	}
	h := fmt.Sprintf("%d of %d requirements are proven by running code.", proven, len(reqs))
	var parts []string
	for _, st := range counts.Keys() {
		p, ok := phrase[st]
		if !ok {
			p = strings.ToLower(st)
		}
		parts = append(parts, fmt.Sprintf("%d %s", counts.Get(st).(int), p))
	}
	sub := strings.Join(parts, ", ")
	if sub == "" {
		return h, "Every requirement is implemented, tested and matches the contract."
	}
	return h, upperFirst(sub) + "."
}

// HTMLReport renders report.html. nav is nil for a standalone report.
func HTMLReport(rep *OMap, nav *string) string {
	reqs := maps(rep.Get("requirements"))
	h, sub := headline(reqs)
	var body []string
	body = append(body, `<header class="top"><span class="eyebrow">`+escapeHTML(rep.Str("head_branch"))+` · `+
		rangeLabel(rep)+` · specs/</span><h1>`+escapeHTML(h)+`</h1><p class="lede muted">`+escapeHTML(sub)+`</p></header>`)
	var blocks strings.Builder
	for _, r := range reqs {
		blocks.WriteString(requirementBlock(r, nil))
	}
	body = append(body, `<section><div class="sheet">`+blocks.String()+`</div>`+
		`<div class="vlegend"><span>Rail, top to bottom: spec, code, api, tests</span>`+
		`<span><i class="v-ok"></i>Proven</span><span><i class="v-warn"></i>Needs attention</span>`+
		`<span><i class="v-bad"></i>Missing or failing</span><span><i class="v-none"></i>Not applicable</span>`+
		`</div></section>`)

	var rows strings.Builder
	for _, o := range maps(rep.Get("outside")) {
		rows.WriteString(`<div class="orow"><span class="dot" style="background:var(--bad-fg)"></span>` +
			`<code>` + escapeHTML(o.Str("check")) + `</code><span>` + escapeHTML(o.Str("summary")) + `</span></div>`)
	}
	if rows.Len() > 0 {
		body = append(body, `<section><h2>Outside the spec</h2><div class="sheet">`+rows.String()+`</div></section>`)
	} else {
		body = append(body, `<section><h2>Outside the spec</h2><p class="muted small">Nothing outside the spec: every route `+
			`and operation is accounted for.</p></section>`)
	}

	checks := rep.Map("checks")
	results := maps(rep.Get("results"))
	gitN, passing := 0, 0
	for _, c := range CheckIDs {
		if strings.HasPrefix(c, "H") {
			gitN++
			if v := checks.Str(c); v == "pass" || v == "skip" {
				passing++
			}
		}
	}
	var grows strings.Builder
	for _, r := range results {
		v := r.Str("verdict")
		if strings.HasPrefix(r.Str("check"), "H") && (v == "fail" || v == "error") {
			grows.WriteString(`<div class="orow"><span class="dot" style="background:var(--bad-fg)"></span>` +
				`<code>` + escapeHTML(r.Str("check")) + `</code><span>` + escapeHTML(Checks[r.Str("check")]) + `:</span>` +
				`<span class="msg">` + escapeHTML(r.Str("summary")) + `</span></div>`)
		}
	}
	gitHead := fmt.Sprintf(`<section><h2>Git practices · %d of %d rules pass</h2>`, passing, gitN)
	if grows.Len() > 0 {
		body = append(body, gitHead+`<div class="sheet">`+grows.String()+`</div></section>`)
	} else {
		body = append(body, gitHead+`<p class="muted small">Conventional Commits, Refs trailers, one requirement per commit, `+
			`commit size, branch names, history, attribution and signatures all pass.</p></section>`)
	}

	var crow strings.Builder
	for _, g := range goals {
		for _, chk := range CheckIDs {
			if !strings.HasPrefix(chk, g[0]) {
				continue
			}
			var msgs []string
			for _, r := range results {
				v := r.Str("verdict")
				if r.Str("check") == chk && (v == "fail" || v == "error" || v == "not_covered") {
					msgs = append(msgs, `<span class="msg">`+escapeHTML(r.Str("summary"))+`</span>`)
				}
			}
			if len(msgs) > 4 {
				msgs = msgs[:4]
			}
			crow.WriteString(`<div class="row"><span class="ck">` + chk + `</span><span>` + verdictChip(checks.Str(chk)) +
				`</span><span>` + escapeHTML(Checks[chk]) + strings.Join(msgs, "") + `</span></div>`)
		}
	}
	body = append(body, fmt.Sprintf(`<section><details class="all"><summary>All %d checks</summary>`, len(CheckIDs))+
		`<div class="panel goal-list" style="margin-top:12px">`+crow.String()+`</div></details></section>`)
	if sc := rep.Map("scorecard"); sc.Len() > 0 {
		var srows strings.Builder
		for _, who := range sc.Keys() {
			a := sc.Map(who)
			rate, _ := toFloat(a.Get("git_rule_pass_rate"))
			refs := strings.Join(strList(a.Get("requirements_referenced")), ", ")
			if refs == "" {
				refs = "-"
			}
			srows.WriteString(`<tr><td class="name">` + escapeHTML(who) + `</td><td>` + pyStr(a.Get("commits")) +
				`</td><td>` + percent(rate) + `</td><td>` + escapeHTML(refs) + `</td></tr>`)
		}
		body = append(body, `<section><h2>Agent scorecard</h2><div class="table-wrap"><table><thead><tr><th>Agent</th>`+
			`<th>Commits</th><th>Git rule pass rate</th><th>Requirements</th></tr></thead>`+
			`<tbody>`+srows.String()+`</tbody></table></div></section>`)
	}
	body = append(body, `<footer>Generated by <code>aqv check</code>. Every result is repeatable: rerun the same command on `+
		`the same commit to get the same answer.</footer>`)
	return pageHTML("Spec Health", strings.Join(body, "\n"), viewCSS, nav, "")
}

// WriteOutputs writes results.json, report.txt and report.html into dir.
func WriteOutputs(dir string, rep *OMap) (string, error) {
	if err := writeFile(filepath.Join(dir, "results.json"), dumpJSON(rep)); err != nil {
		return "", err
	}
	txt := TextReport(rep)
	if err := writeFile(filepath.Join(dir, "report.txt"), txt+"\n"); err != nil {
		return "", err
	}
	return txt, writeFile(filepath.Join(dir, "report.html"), HTMLReport(rep, nil))
}
