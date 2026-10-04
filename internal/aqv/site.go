package aqv

// The site home (index.html) and the two comparison pages (docs/compare/*.html): ports of
// aqv/html.py's site_index and our_goals and of experiments/report.py. `aqv site` writes them.
// The text is copied from the Python so the pages are byte-identical.

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// ComparePage describes one comparison page listed on the home page.
type ComparePage struct{ HTML, MD, Title, Desc string }

// ComparePages lists the comparison pages the home page links to.
var ComparePages = []ComparePage{
	{"docs/compare/openfasttrace.html", "experiments/openfasttrace/README.md", "OpenFastTrace",
		"Requirement tracing through a document hierarchy, on the same 26 attacks."},
	{"docs/compare/intentbond.html", "experiments/intentbond/README.md", "IntentBond",
		"Links, tests and a review gate against a git baseline, with retained evidence, on the same 26 attacks."},
}

// SiteOptions configures WriteSite.
type SiteOptions struct {
	Root   string // repository root
	Meta   string // demo/langs.json
	PyWork string // the Python demo run (demo/.work)
	GoWork string // the Go demo run (demo/.work-go)
}

// WriteSite writes the comparison pages, then the site home.
func WriteSite(o SiteOptions) error {
	root := absPath(o.Root)
	exp := filepath.Join(root, "experiments")
	variants, err := loadFile(filepath.Join(exp, "ours-variants.json"))
	if err != nil {
		return err
	}
	meta, err := loadScenarioMeta(root)
	if err != nil {
		return err
	}
	oft, err := loadFile(filepath.Join(exp, "openfasttrace/results/openfasttrace.json"))
	if err != nil {
		return err
	}
	oftProbes, err := loadFile(filepath.Join(exp, "openfasttrace/results/probes.json"))
	if err != nil {
		return err
	}
	ib, err := loadFile(filepath.Join(exp, "intentbond/results/intentbond.json"))
	if err != nil {
		return err
	}
	ibProbes, err := loadFile(filepath.Join(exp, "intentbond/results/probes.json"))
	if err != nil {
		return err
	}
	cp := &comparePages{meta: meta, variants: variants.(*OMap)}
	if err := writeFile2(filepath.Join(root, "docs/compare/openfasttrace.html"),
		cp.oftPage(oft.(*OMap), oftProbes.(*OMap))); err != nil {
		return err
	}
	if err := writeFile2(filepath.Join(root, "docs/compare/intentbond.html"),
		cp.ibPage(ib.(*OMap), ibProbes.(*OMap))); err != nil {
		return err
	}
	pyLangs, err := LoadLangs(o.Meta, o.PyWork)
	if err != nil {
		return err
	}
	var goLangs []*Lang
	if exists(filepath.Join(root, "demo/results-go/index.html")) {
		goLangs, err = LoadLangs(o.Meta, o.GoWork)
		if err != nil {
			return err
		}
	}
	var compare []ComparePage
	for _, c := range ComparePages {
		if exists(filepath.Join(root, c.HTML)) {
			compare = append(compare, c)
		}
	}
	return writeFile2(filepath.Join(root, "index.html"), SiteIndex(pyLangs, compare, goLangs))
}

func loadFile(path string) (any, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	v, err := loadJSON(data)
	if err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	return v, nil
}

// scenarioMeta holds each scenario's title and expected check, read from the "# title:" and
// "# expect:" lines at the top of its script.
type scenarioMeta struct{ titles, expect map[string]string }

func loadScenarioMeta(root string) (*scenarioMeta, error) {
	m := &scenarioMeta{map[string]string{"baseline": "The clean baseline: six requirements, built the right way"},
		map[string]string{}}
	for _, dir := range []string{"demo/scenarios", "experiments/variants"} {
		files := glob(filepath.Join(root, dir, "*.sh"))
		for _, f := range files {
			data, err := os.ReadFile(f)
			if err != nil {
				return nil, err
			}
			id := strings.TrimSuffix(filepath.Base(f), ".sh")
			for _, line := range splitlines(string(data)) {
				if strings.HasPrefix(line, "# title: ") {
					if _, ok := m.titles[id]; !ok || id != "baseline" {
						m.titles[id] = line[len("# title: "):]
					}
				}
				if strings.HasPrefix(line, "# expect: ") {
					if _, ok := m.expect[id]; !ok {
						m.expect[id] = line[len("# expect: "):]
					}
				}
			}
		}
	}
	return m, nil
}

// ---------------------------------------------------------------- home page

// OurGoals is the "what this verifier is for" block shared by the home and comparison pages.
func OurGoals() string {
	fams := [][3]string{
		{"T1–T8", "Tests prove the spec", "Each requirement has tagged tests that pass, run its code and fail when that " +
			"code is broken, and the evidence is about its current wording."},
		{"A1–A7", "The API matches its contract", "Every API requirement is documented in OpenAPI, and the routes, test " +
			"responses and the running service all match that contract."},
		{"H1–H9", "The history can be trusted", "Commits are readable, cite one requirement, are honestly labelled, " +
			"attributed to the agent, signed, and main is never rewritten."},
	}
	var cards strings.Builder
	for _, f := range fams {
		cards.WriteString(`<div class="fam"><span class="k">` + f[0] + `</span><h3>` + escapeHTML(f[1]) + `</h3><p>` +
			escapeHTML(f[2]) + `</p></div>`)
	}
	return `<div class="goal"><p class="big">Let a person judge an agent's work without reading its code.</p>` +
		`<p>For every requirement the verifier answers three questions with checks that give the same answer for the ` +
		`same commit every time: no AI judges, no scores, no opinions. Where a check can't see, it says ` +
		`<b>not covered</b>, never <b>pass</b>.</p></div>` +
		`<div class="fams">` + cards.String() + `</div>` +
		`<div class="panel" style="padding:14px 18px;display:grid;gap:8px"><h3 style="padding:0">Deliberately not its goals</h3>` +
		`<ul class="plain small"><li>Managing requirement documents or a feature → requirement → design hierarchy.</li>` +
		`<li>Approving what a requirement should say. People decide intent; the verifier checks the code against it.</li>` +
		`<li>Storing signed evidence for audits (not yet: results are recomputed on every run).</li>` +
		`<li>Formal proofs of behaviour.</li></ul>` +
		`<p class="small muted">Other tools are built for exactly these. The comparison pages show where they fit.</p></div>`
}

func dirItem(href, title, desc string, alt ...string) string {
	a := ""
	if len(alt) == 2 {
		a = ` <a class="alt" href="` + alt[0] + `">` + escapeHTML(alt[1]) + `</a>`
	}
	return `<li><a class="t" href="` + href + `">` + escapeHTML(title) + `</a><span class="d">` + escapeHTML(desc) + `</span>` + a + `</li>`
}

func scenarioLinks(base string, l *Lang) string {
	var links, details strings.Builder
	for _, r := range l.Results {
		if r.Has("name") {
			links.WriteString(`<li><a href="` + base + `/` + l.Lang + `/runs/` + escapeHTML(r.Str("name")) + `.html"><code>` +
				escapeHTML(r.Str("name")) + `</code></a> <span class="muted">` + escapeHTML(r.Str("title")) + `</span></li>`)
		}
	}
	details.WriteString(`<details><summary>` + escapeHTML(l.Name) + `: ` + fmt.Sprint(len(l.Results)) +
		` scenario pages</summary><ul>` + links.String() + `</ul></details>`)
	return details.String()
}

// SiteIndex renders the home page.
func SiteIndex(langs []*Lang, compare []ComparePage, goLangs []*Lang) string {
	total, good := 0, 0
	for _, l := range langs {
		total += len(l.Results)
		good += l.ok()
	}
	body := []string{
		`<header class="top"><span class="eyebrow">Agent Quality Verifier</span>` +
			`<h1>Check an agent's work against the spec without reading its code</h1>` +
			`<p class="lede">24 repeatable checks turn "is this code good?" into evidence a person can read: each ` +
			`requirement with four vital signs (spec, code, api, tests), the commits behind it, and one sentence ` +
			`saying what's wrong.</p></header>`,
		`<div class="stats">` +
			`<div class="stat"><b>24</b><span>repeatable checks in three families</span></div>` +
			fmt.Sprintf(`<div class="stat"><b>%d</b><span>languages in the demo</span></div>`, len(langs)) +
			fmt.Sprintf(`<div class="stat"><b>%d / %d</b><span>demo scenarios behave as expected</span></div>`, good, total) +
			`<div class="stat"><b>0</b><span>AI judges or subjective scores</span></div></div>`,
		`<section><h2>What it's for</h2>` + OurGoals() + `</section>`,
	}
	type card struct{ href, kind, title, desc string }
	cards := []card{
		{"docs/framework.html", "Guide", "The framework", "Why T, A and H, what each check guards against, " +
			"and what the demo simulates."},
		{"demo/results/index.html", "Results", "Every language, every check", fmt.Sprintf("%d of %d scenarios across ", good, total) +
			fmt.Sprintf("%d languages, with a page per scenario.", len(langs))},
	}
	for _, c := range compare {
		cards = append(cards, card{c.HTML, "Compared", c.Title, c.Desc})
	}
	var cs strings.Builder
	for _, c := range cards {
		cs.WriteString(`<a class="card" href="` + c.href + `"><span class="k">` + c.kind + `</span><b>` + escapeHTML(c.title) +
			`</b><span class="d">` + escapeHTML(c.desc) + `</span></a>`)
	}
	body = append(body, `<section><h2>Start here</h2><div class="cards">`+cs.String()+`</div></section>`)

	var groups []string
	groups = append(groups, `<div class="grp"><h3>Guides</h3><ul>`+
		dirItem("docs/framework.html", "The framework", "T, A and H; every check; the demo, real vs simulated",
			"docs/framework.md", "Markdown")+
		dirItem("README.md", "README", "Quick start, the checks table, conventions and limits")+
		dirItem("docs/go-demo-parity.md", "Go and Python parity", "Two verifiers, two demos: what must match, how it's checked, and the plan")+
		`</ul></div>`)
	if len(compare) > 0 {
		var items strings.Builder
		for _, c := range compare {
			items.WriteString(dirItem(c.HTML, c.Title, c.Desc, c.MD, "Markdown"))
		}
		groups = append(groups, `<div class="grp"><h3>Comparisons</h3><ul>`+items.String()+`</ul></div>`)
	}
	results := func(title, base, allDesc string, ls []*Lang) string {
		var items, runs strings.Builder
		items.WriteString(dirItem(base+"/index.html", "All languages", allDesc))
		for _, l := range ls {
			items.WriteString(dirItem(base+"/"+l.Lang+"/demo.html", l.Name, l.Stack, base+"/"+l.Lang+"/RESULTS.md", "Markdown"))
			runs.WriteString(scenarioLinks(base, l))
		}
		return `<div class="grp"><h3>` + title + `</h3><ul>` + items.String() + `</ul>` + runs.String() + `</div>`
	}
	groups = append(groups, results("Demo results", "demo/results", "Every check in every language, and how each "+
		"language does the stack-specific checks", langs))
	if len(goLangs) > 0 {
		groups = append(groups, results("Demo results, Go verifier", "demo/results-go",
			"The same demo, checked by the Go verifier (bin/aqv)", goLangs))
	}
	body = append(body, `<section><h2>Every page</h2><div class="dir">`+strings.Join(groups, "")+`</div></section>`)
	body = append(body, `<footer>Generated by <code>python demo/run_demo.py --html-only</code>. Every page is static: `+
		`open it from disk or from GitHub Pages.</footer>`)
	empty := ""
	return pageHTML("Agent Quality Verifier", strings.Join(body, "\n"), homeCSS, &empty, "index.html")
}

// ---------------------------------------------------------------- comparison pages

var (
	orderT = []string{"T1-duplicate-id", "T2-not-implemented", "T3-comment-only", "T4-no-tests", "T5-failing-test",
		"T5-suite-broken", "T6-assert-true", "T7-weak-tests", "T8-spec-changed"}
	orderA = []string{"A1-operation-missing", "A2-unlinked-operation", "A3-lint", "A4-breaking-change", "A5-shadow-route",
		"A6-leaked-field", "A6-undocumented-status", "A7-server-error"}
	orderH = []string{"H1-wip-commit", "H2-no-refs", "H3-two-requirements", "H4-refactor-changes-behavior", "H5-huge-commit",
		"H6-branch-name", "H7-rewrite-main", "H8-no-attribution", "H9-unsigned"}
	orderX = []string{"X1-claims-only", "X2-spec-changed-no-bump", "X3-weak-tests-same-names"}
)

type scenarioGroup struct {
	name string
	ids  []string
}

var scenarioGroups = []scenarioGroup{
	{"Clean runs", []string{"baseline", "00-clean-pr"}}, {"T · tests prove the spec", orderT},
	{"A · the API matches its contract", orderA}, {"H · the history can be trusted", orderH},
	{"Isolating variants", orderX},
}

type kindDef struct {
	key, question string
	ids           []string
}

func withoutH4() []string {
	var out []string
	for _, h := range orderH {
		if !strings.HasPrefix(h, "H4") {
			out = append(out, h)
		}
	}
	return out
}

var kinds = []kindDef{
	{"links", "Is every requirement linked to code and tests, at its current revision?",
		[]string{"T1-duplicate-id", "T2-not-implemented", "T4-no-tests", "T8-spec-changed"}},
	{"run", "Do the linked tests run and pass?", []string{"T5-failing-test", "T5-suite-broken", "H4-refactor-changes-behavior"}},
	{"claims", "Is the linked evidence real: code that exists, tests that run it and would catch it breaking?",
		[]string{"T3-comment-only", "T6-assert-true", "T7-weak-tests", "X1-claims-only", "X3-weak-tests-same-names"}},
	{"revision", "Is a reworded requirement noticed when nobody marks it as changed?", []string{"X2-spec-changed-no-bump"}},
	{"api", "Does the API match its OpenAPI contract?", orderA},
	{"git", "Does the history follow the conventions?", withoutH4()},
}

type comparePages struct {
	meta     *scenarioMeta
	variants *OMap
}

type kindCell struct {
	auto, review int
	goal         bool
	label        string
}

func (c *comparePages) ours(sid string) string {
	if sid == "baseline" || sid == "00-clean-pr" {
		return chip("passes", "ok")
	}
	if c.variants.Has(sid) {
		failing := strList(c.variants.Map(sid).Get("failing"))
		if len(failing) > 0 {
			return chip("caught · "+strings.Join(failing, ", "), "ok")
		}
		return chip("passes", "muted")
	}
	return chip("caught · "+c.meta.expect[sid], "ok")
}

func (c *comparePages) scnCell(sid string) string {
	return `<td class="scn">` + escapeHTML(sid) + `<span class="ttl">` + escapeHTML(c.meta.titles[sid]) + `</span></td>`
}

func (c *comparePages) resultsTable(cols []string, rowsFor func(sid string) []string) string {
	var head strings.Builder
	head.WriteString("<th>Scenario</th>")
	for _, col := range cols {
		head.WriteString("<th>" + escapeHTML(col) + "</th>")
	}
	var body strings.Builder
	for _, g := range scenarioGroups {
		body.WriteString(fmt.Sprintf(`<tr class="group"><td colspan="%d">%s</td></tr>`, len(cols)+1, escapeHTML(g.name)))
		for _, sid := range g.ids {
			body.WriteString("<tr>" + c.scnCell(sid) + strings.Join(rowsFor(sid), "") + "</tr>")
		}
	}
	return `<div class="table-wrap"><table><thead><tr>` + head.String() + `</tr></thead><tbody>` + body.String() +
		`</tbody></table></div>`
}

func liList(xs []string) string {
	var b strings.Builder
	for _, x := range xs {
		b.WriteString("<li>" + x + "</li>")
	}
	return b.String()
}

func twoPanels(theirsTitle, theirsQ string, theirsItems []string, oursQ string, oursItems []string) string {
	return `<div class="two">` +
		`<div class="panel theirs"><span class="k">` + escapeHTML(theirsTitle) + ` answers</span><h3>` + theirsQ + `</h3>` +
		`<ul class="plain small">` + liList(theirsItems) + `</ul></div>` +
		`<div class="panel ours"><span class="k">This verifier answers</span><h3>` + oursQ + `</h3>` +
		`<ul class="plain small">` + liList(oursItems) + `</ul></div></div>`
}

func keyBlock(items [][2]string) string {
	var rows strings.Builder
	for _, it := range items {
		rows.WriteString(`<div class="key-row"><span>` + it[0] + `</span><p>` + it[1] + `</p></div>`)
	}
	return `<div class="key"><span class="key-title">How to read the results</span>` + rows.String() + `</div>`
}

type part struct {
	n   int
	cls string
}

func meter(cls string, parts []part, total int) string {
	var segs strings.Builder
	for _, p := range parts {
		if p.n != 0 {
			segs.WriteString(fmt.Sprintf(`<i class="%s" style="width:%.1f%%"></i>`, p.cls, 100*float64(p.n)/float64(total)))
		}
	}
	return `<div class="meter ` + cls + `" role="presentation">` + segs.String() + `</div>`
}

func short(sid string) string {
	head, rest, _ := strings.Cut(sid, "-")
	if head == "T5" || head == "A6" {
		return head + " " + strings.SplitN(rest, "-", 2)[0]
	}
	return head
}

func versus(tool string, cell func(key string, ids []string) kindCell, reviewLegend bool) string {
	legend := []string{`<span><i class="sw ours"></i>This verifier: answered by a check</span>`,
		`<span><i class="sw auto"></i>` + escapeHTML(tool) + `: answered by a check</span>`}
	if reviewLegend {
		legend = append(legend, `<span><i class="sw review"></i>`+escapeHTML(tool)+`: handed to a person</span>`)
	}
	legend = append(legend, `<span><i class="sw none"></i>not what it's designed to answer</span>`)
	rows := []string{`<div class="vs-legend">` + strings.Join(legend, "") + `</div>`,
		`<div class="vs-row head"><span>Question the scenarios ask</span><span class="o">This verifier</span>` +
			`<span class="s">` + escapeHTML(tool) + `</span></div>`}
	totN, totAuto, totReview, totOff := 0, 0, 0, 0
	for _, k := range kinds {
		n, c := len(k.ids), cell(k.key, k.ids)
		totN += n
		totAuto += c.auto
		totReview += c.review
		if !c.goal {
			totOff += n
		}
		bar := `<div class="meter none" role="presentation"></div>`
		if c.goal {
			bar = meter("subj", []part{{c.auto, "auto"}, {c.review, "review"}}, n)
		}
		shorts := make([]string, len(k.ids))
		for i, id := range k.ids {
			shorts[i] = short(id)
		}
		rows = append(rows, `<div class="vs-row"><div class="vs-q">`+escapeHTML(k.question)+`<small>`+
			escapeHTML(strings.Join(shorts, ", "))+`</small></div>`+
			`<div class="vs-cell ours">`+meter("ours", []part{{n, ""}}, n)+fmt.Sprintf(`<div class="vs-val"><b>%d of %d</b></div></div>`, n, n)+
			`<div class="vs-cell subj">`+bar+`<div class="vs-val">`+c.label+`</div></div></div>`)
	}
	n := totN
	subj := fmt.Sprintf(`<b>%d of %d</b><span>answered by a check</span>`, totAuto, n)
	if totReview > 0 {
		subj += fmt.Sprintf(`<span>%d handed to a person</span>`, totReview)
	}
	subj += fmt.Sprintf(`<span>%d outside its goals</span>`, totOff)
	rows = append(rows, fmt.Sprintf(`<div class="vs-row total"><div class="vs-q">All %d scenarios and variants</div>`, n)+
		`<div class="vs-cell ours">`+meter("ours", []part{{n, ""}}, n)+fmt.Sprintf(`<div class="vs-val"><b>%d of %d</b>`, n, n)+
		`<span>answered by a check</span></div></div>`+
		`<div class="vs-cell subj">`+meter("subj", []part{{totAuto, "auto"}, {totReview, "review"}}, n)+
		`<div class="vs-val">`+subj+`</div></div></div>`)
	return `<div class="vs">` + strings.Join(rows, "") + `</div>`
}

func compareFooter(md string, results []string) string {
	var rs []string
	for _, r := range results {
		rs = append(rs, `<a href="../../`+r+`"><code>`+escapeHTML(r)+`</code></a>`)
	}
	return `<footer>Markdown version: <a href="../../` + md + `">` + escapeHTML(md) + `</a>. Raw results: ` +
		strings.Join(rs, ", ") + `. Rebuild with <code>python experiments/report.py</code>.</footer>`
}

func comparePage(title, body, current string) string {
	nav := "../../"
	return pageHTML(title, body, compareCSS, &nav, current)
}

var oftWhy = map[string]string{
	"baseline":                 "Every requirement has its implementation and test links.",
	"00-clean-pr":              "The new requirement is linked to its code and tests.",
	"T1-duplicate-id":          "The reused ID appears as a second item without links. An exact duplicate is reported as a duplicate too (probe below).",
	"T2-not-implemented":       "No implementation or test links for the new requirement.",
	"T3-comment-only":          "Reported for the missing test link. The implementation tag sits on a comment, and a tag is a declaration, so that link counts (see X1).",
	"T4-no-tests":              "No test link for the new requirement.",
	"T5-failing-test":          "Tracing reads tags; running tests is left to the build.",
	"T5-suite-broken":          "Tracing reads tags; running tests is left to the build.",
	"T6-assert-true":           "The test is tagged, so the link exists. What the test asserts is outside tracing.",
	"T7-weak-tests":            "The rewritten tests still carry their links.",
	"T8-spec-changed":          "Revision 2 leaves the code and test links on revision 1 outdated.",
	"X1-claims-only":           "Both links are declared, so the trace is complete.",
	"X2-spec-changed-no-bump":  "Without a new revision the change isn't visible to tracing. OFT's model relies on the editor raising it.",
	"X3-weak-tests-same-names": "Same tests, same links.",
}

func exitCode(m *OMap) float64 {
	f, _ := toFloat(m.Get("exit"))
	return f
}

func (c *comparePages) oftPage(res, probes *OMap) string {
	toolCell := func(sid string) []string {
		r := res.Map(sid)
		clean := sid == "baseline" || sid == "00-clean-pr"
		var ch string
		if exitCode(r) == 0 {
			if clean {
				ch = chip("clean trace", "ok")
			} else {
				ch = chip("clean trace · not flagged", "muted")
			}
		} else {
			if !clean {
				ch = chip("reported · caught", "ok")
			} else {
				ch = chip("reported", "bad")
			}
		}
		why, ok := oftWhy[sid]
		if !ok {
			switch {
			case strings.HasPrefix(sid, "A"):
				why = "The API contract isn't part of the trace."
			case strings.HasPrefix(sid, "H4"):
				why = "A behaviour change only shows when tests run."
			default:
				why = "Git history isn't part of the trace."
			}
		}
		defects := strList(r.Get("defects"))
		if len(defects) > 2 {
			defects = defects[:2]
		}
		var ds strings.Builder
		for _, d := range defects {
			ds.WriteString("<br><code>" + escapeHTML(d) + "</code>")
		}
		return []string{"<td>" + c.ours(sid) + "</td>", "<td>" + ch + "</td>", `<td class="why">` + escapeHTML(why) + ds.String() + `</td>`}
	}
	kindCellFn := func(key string, ids []string) kindCell {
		n := 0
		for _, i := range ids {
			if exitCode(res.Map(i)) != 0 {
				n++
			}
		}
		switch key {
		case "api", "git", "run":
			return kindCell{0, 0, false, "<b>not its goal</b>"}
		case "revision":
			return kindCell{0, 0, false, "<b>relies on the revision rule</b>"}
		}
		return kindCell{n, 0, true, fmt.Sprintf("<b>%d of %d</b>", n, len(ids))}
	}
	ext := probes.Map("extensions")
	var extChips []string
	extOK := 0
	for _, e := range ext.Keys() {
		tone := "muted"
		if ext.Truthy(e) {
			tone = "ok"
			extOK++
		}
		extChips = append(extChips, chip("."+e, tone))
	}
	hier := probes.Map("hierarchy")
	firstDefect := "—"
	if d := strList(hier.Map("design_without_test").Get("defects")); len(d) > 0 {
		firstDefect = d[0]
	}
	items := hier.Map("complete_chain").Get("items")
	body := []string{
		`<header class="top"><span class="eyebrow">Compared · OpenFastTrace 4.10.0 on the Python demo</span>` +
			`<h1>OpenFastTrace traces what you planned. This verifier tests what the agent delivered.</h1>` +
			`<p class="lede">Both start from requirements with stable IDs. OpenFastTrace (OFT) checks that every planned ` +
			`requirement is linked through the levels of your specification to code and tests. This verifier checks that ` +
			`the evidence behind each requirement holds up when you run it. We ran OFT on the same 26 attacks the verifier ` +
			`is tested against, to show where the two overlap and where they answer different questions.</p></header>`,
		`<div class="stats">` +
			fmt.Sprintf(`<div class="stat"><b>%d</b><span>scenarios and variants, run unchanged</span></div>`, res.Len()-1) +
			`<div class="stat"><b>4 of 4</b><span>link questions answered by both</span></div>` +
			`<div class="stat"><b>3 levels</b><span>feature → requirement → design, traced by OFT only</span></div>` +
			fmt.Sprintf(`<div class="stat"><b>%d of %d</b><span>file types OFT reads tags from out of the box</span></div></div>`, extOK, ext.Len()),
		`<section><h2>Two goals</h2>` +
			`<div class="quote"><blockquote>“Requirement tracing keeps track of whether you actually implemented everything ` +
			`you planned to in your specifications. It also identifies obsolete parts of your product and helps you to get ` +
			`rid of them.”</blockquote><span class="src">OpenFastTrace README</span></div>` +
			twoPanels("OpenFastTrace",
				"Is everything we specified covered, at every level, at its current revision?",
				[]string{"Features, requirements, designs, code and tests as linked items, each with a revision.",
					"<code>Needs:</code> says what must cover an item; <code>Covers:</code> links it upward.",
					"Missing coverage, outdated revisions, duplicates and orphaned tags are defects.",
					"Works on any file type, as a CLI, Maven or Gradle plugin, with HTML and XML reports."},
				"Does the evidence behind each requirement hold up, so nobody has to read the code?",
				[]string{"The links come from conventions (commit trailers, test names, OpenAPI <code>x-requirements</code>), not tags.",
					"Each claim is then tested: the code exists, the tests pass, run it and catch broken versions of it.",
					"The API is checked against its contract, and the history against git conventions.",
					"A wording change is read from git, without anyone marking it."}) +
			`</section>`,
		`<section><h2>What this verifier is for</h2>` + OurGoals() + `</section>`,
		`<section><h2>The same scenarios, by the question they ask</h2>` +
			`<p class="note">Each scenario attacks one question. A dashed track means OFT isn't designed to answer that ` +
			`question, so a clean trace there says nothing against OFT.</p>` + versus("OpenFastTrace", kindCellFn, false) +
			`</section>`,
		`<section><h2>How it was run</h2><ol class="steps">` +
			`<li>The Python demo baseline gets OFT notation the way an agent following OFT's skill would write it: an item ` +
			`per requirement with <code>Needs: impl, utest</code>, ten <code>[impl-&gt;req~…]</code> tags beside the code, ` +
			`and a named <code>utest</code> tag on each test.</li>` +
			`<li>Each scenario script from <code>demo/scenarios/</code> runs unchanged. Whatever it added then gets tagged the ` +
			`same way: new requirement items, new tests, and code for a requirement that had no tag yet. A reworded ` +
			`requirement gets revision 2, as OFT asks of whoever edits it; variant X2 leaves it at 1.</li>` +
			`<li><code>oft trace specs src tests</code> on the result. Exit 1 means OFT reported a defect.</li></ol></section>`,
		`<section><h2>Every scenario</h2>` +
			keyBlock([][2]string{
				{chip("caught · T3", "ok"), "This verifier failed the check written for that attack."},
				{chip("reported · caught", "ok"), "OFT found a trace defect (a missing, duplicate or outdated link), " +
					"so it caught the attack."},
				{chip("clean trace · not flagged", "muted"), "Every link OFT knows about is in place. On rows about " +
					"running tests, the API or git history that's expected: those questions are outside tracing."},
				{chip("clean trace", "ok"), "On the two clean runs: the correct result, nothing is wrong."}}) +
			c.resultsTable([]string{"This verifier", "OpenFastTrace", "What OFT saw"}, toolCell) +
			`</section>`,
		`<section><h2>What OFT does that this verifier doesn't</h2><div class="two quad">` +
			`<div class="panel"><h3>Traces a hierarchy</h3><p class="small">A feature needs a requirement, the requirement ` +
			`needs a design, the design needs code and a test. With the design's test missing, OFT reports ` +
			`<code>` + escapeHTML(firstDefect) + `</code>; with it added the trace is clean ` +
			`(` + pyStr(items) + ` items). This verifier has one level: requirement → code and tests.</p></div>` +
			`<div class="panel"><h3>Makes revisions explicit</h3><p class="small">Every item carries a revision, and links ` +
			`name the revision they cover, so a reviewed change in meaning is visible in the spec itself. This verifier ` +
			`infers changes from git instead (T8).</p></div>` +
			`<div class="panel"><h3>Reads tags from almost anything</h3><p class="small">One tag syntax across languages, ` +
			`documents and build files.</p><div class="chips">` + strings.Join(extChips, " ") + `</div><p class="small muted">.tsx needs a ` +
			`workaround (IntentBond adds one).</p></div>` +
			`<div class="panel"><h3>Fits documentation-heavy work</h3><p class="small">Mature (version 4.10, Maven and Gradle ` +
			`plugins, an IntelliJ plugin, HTML reports), and it now ships agent skills for writing traced specs. It fits ` +
			`teams that must show coverage of a written specification, such as safety or regulated work.</p></div>` +
			`</div></section>`,
		`<section><h2>What the runs show</h2><ul class="plain">` +
			`<li><b>On links they agree.</b> Missing implementation, missing tests, a reused ID and a requirement whose ` +
			`revision moved on: OFT reports all four, as does this verifier.</li>` +
			`<li><b>A tag is a declaration; this verifier's links are tested claims.</b> OFT accepts a tag on a comment or ` +
			`on an <code>assert True</code> test (X1), because whether the tagged code works is a question for the build, ` +
			`not for tracing. That question is this verifier's main job: T3, T6 and T7.</li>` +
			`<li><b>Running tests is left to the build.</b> Failing tests, a broken suite and a behaviour change (T5, H4) ` +
			`aren't part of a trace.</li>` +
			`<li><b>Revisions are a process, not a detection.</b> OFT notices a reworded requirement when its revision is ` +
			`raised (T8) and not otherwise (X2). This verifier reads the change from git.</li>` +
			`<li><b>The API contract and git history</b> aren't part of OFT's model.</li></ul></section>`,
		`<section><h2>Using them together</h2><ol class="steps">` +
			`<li><b>OFT as the specification format.</b> Teams that already write OFT items keep them, including the ` +
			`feature and design levels this verifier doesn't model.</li>` +
			`<li><b>OFT tags as this verifier's claims.</b> An <code>[impl-&gt;req~…]</code> tag says the same thing as a ` +
			`<code>Refs:</code> trailer. Reading OFT tags would let the verifier test those claims with T3–T8 without any ` +
			`re-tagging. Not built yet.</li>` +
			`<li><b>Each where it's strongest.</b> OFT shows the specification is fully covered; this verifier shows the ` +
			`coverage is real.</li></ol>` +
			`<p class="note">When to pick which: OFT when you must demonstrate coverage of a written, multi-level ` +
			`specification. This verifier when you need to judge an agent's output without reading it. Both when you ` +
			`need both.</p></section>`,
		`<section><h2>Limits of this comparison</h2><ul class="plain small">` +
			`<li>Python only, OFT 4.10.0. The tags were written by a script acting as a careful agent, not by a real agent.</li>` +
			`<li>The scenarios were written to test this verifier, so most of them ask its questions. The probes above ask OFT's.</li>` +
			`<li>OFT's HTML report and IDE plugin weren't evaluated.</li></ul></section>`,
		compareFooter("experiments/openfasttrace/README.md",
			[]string{"experiments/openfasttrace/results/openfasttrace.json", "experiments/openfasttrace/results/probes.json",
				"experiments/ours-variants.json"}),
	}
	return comparePage("Compared: OpenFastTrace", strings.Join(body, "\n"), "docs/compare/openfasttrace.html")
}

var ibWhy = map[string]string{
	"baseline":                     "Coverage complete; 15 linked tests pass.",
	"00-clean-pr":                  "Any specification or test change goes to a person, by design.",
	"T1-duplicate-id":              "Two active items for <code>req~auth-006</code>.",
	"T2-not-implemented":           "No implementation or test links for the new requirement.",
	"T3-comment-only":              "Rejected for the missing test link. The comment counts as the implementation link (see X1).",
	"T4-no-tests":                  "No test link for the new requirement.",
	"T5-failing-test":              "The suite failed; the linked lockout test failed.",
	"T5-suite-broken":              "Collection error; no linked test was observed.",
	"T6-assert-true":               "The test passes and is linked. Whether it checks anything is the reviewer's call, with the diff in <code>review.patch</code>.",
	"T7-weak-tests":                "Default: the changed tests go to review. Strict: the pinned test names are gone.",
	"T8-spec-changed":              "Revision 2 leaves the links on revision 1 outdated.",
	"A1-operation-missing":         "The new requirement and test go to review. The contract isn't an input.",
	"A4-breaking-change":           "A test was edited, so the change goes to review. The contract isn't an input.",
	"A6-undocumented-status":       "A test was edited, so the change goes to review. The contract isn't an input.",
	"H4-refactor-changes-behavior": "A lockout test failed: the tests caught the behaviour change.",
	"X1-claims-only":               "Both links exist and the test passes. The reviewer decides.",
	"X2-spec-changed-no-bump":      "Default: the spec edit goes to review. Strict: changed content without a higher revision is rejected.",
	"X3-weak-tests-same-names":     "Same pinned names, still passing. The reviewer sees the weaker assertions.",
}

func ibChip(code int, clean bool) string {
	type lt struct{ label, tone string }
	label := map[int]lt{0: {"passed · not flagged", "muted"}, 1: {"rejected · caught", "ok"}, 4: {"review · to a person", "warn"}}
	if clean {
		label = map[int]lt{0: {"passed", "ok"}, 1: {"rejected", "bad"}, 4: {"review · to a person", "ok"}}
	}
	if l, ok := label[code]; ok {
		return chip(l.label, l.tone)
	}
	return chip(fmt.Sprintf("exit %d", code), "bad")
}

func tidy(lines []string) string {
	out := make([]string, len(lines))
	for i, l := range lines {
		out[i] = strings.ReplaceAll(strings.TrimRight(strip(l), ","), `"`, "")
	}
	return strings.Join(out, ", ")
}

func countOf(xs []int, v int) int {
	n := 0
	for _, x := range xs {
		if x == v {
			n++
		}
	}
	return n
}

func (c *comparePages) ibPage(res, probes *OMap) string {
	toolCell := func(sid string) []string {
		r := res.Map(sid)
		clean := sid == "baseline" || sid == "00-clean-pr"
		why := ibWhy[sid]
		if why == "" {
			if strings.HasPrefix(sid, "A") {
				why = "API contracts are outside its scope."
			} else {
				why = "Git history conventions are outside its scope."
			}
		}
		return []string{"<td>" + c.ours(sid) + "</td>", "<td>" + ibChip(int(exitCode(r.Map("default"))), clean) + "</td>",
			"<td>" + ibChip(int(exitCode(r.Map("strict"))), clean) + "</td>", `<td class="why">` + why + `</td>`}
	}
	kindCellFn := func(key string, ids []string) kindCell {
		var d, s []int
		for _, i := range ids {
			d = append(d, int(exitCode(res.Map(i).Map("default"))))
			s = append(s, int(exitCode(res.Map(i).Map("strict"))))
		}
		if key == "api" || key == "git" {
			extra := ""
			if n := countOf(d, 4); n > 0 {
				extra = fmt.Sprintf("<span>%d reach review</span>", n)
			}
			return kindCell{0, 0, false, "<b>not its goal</b>" + extra}
		}
		label := fmt.Sprintf("<b>%d of %d</b>", countOf(d, 1), len(ids))
		if n := countOf(d, 4); n > 0 {
			label += fmt.Sprintf("<span>%d to a person</span>", n)
		}
		if countOf(s, 1) != countOf(d, 1) {
			label += fmt.Sprintf("<span>strict: %d of %d</span>", countOf(s, 1), len(ids))
		}
		return kindCell{countOf(d, 1), countOf(d, 4), true, label}
	}
	v := probes.Map("verify")
	matched := "?"
	if exitCode(v.Map("same_commit")) == 0 {
		matched = "matched"
	}
	body := []string{
		`<header class="top"><span class="eyebrow">Compared · IntentBond on the Python demo</span>` +
			`<h1>IntentBond keeps a change reviewable and its evidence verifiable. This verifier makes the evidence ` +
			`the review.</h1>` +
			`<p class="lede">IntentBond links requirements to code and tests with OpenFastTrace tags, runs the tests against a ` +
			`git baseline, keeps evidence tied to the exact source it checked, and sends every specification or test change ` +
			`to a person. This verifier turns the questions that review would ask into checks. We ran IntentBond on the same ` +
			`26 attacks, with its documented settings and with its strictest options.</p></header>`,
		`<div class="stats">` +
			fmt.Sprintf(`<div class="stat"><b>%d</b><span>scenarios and variants, two configurations each</span></div>`, res.Len()-1) +
			`<div class="stat"><b>7 of 7</b><span>link and test-run questions answered by both</span></div>` +
			`<div class="stat"><b>` + matched + `</b><span>saved evidence matched to ` +
			`its commit by <code>ib verify</code>; a later edit is refused</span></div>` +
			`<div class="stat"><b>0</b><span>AI calls in either tool</span></div></div>`,
		`<section><h2>Two goals</h2>` +
			`<div class="quote"><blockquote>“IntentBond connects intent and specifications to code, tests, and verification ` +
			`evidence. Follow explicit links to find what a change affects and keep the related artifacts consistent as ` +
			`software changes.” … “Review determines whether the linked code and checks satisfy the requirement.”` +
			`</blockquote><span class="src">IntentBond README</span></div>` +
			twoPanels("IntentBond",
				"Did this change keep requirements, code and tests linked and passing, and what must a person review?",
				[]string{"OFT links checked on the base and the candidate, with the rules read from the base.",
					"The project's tests run; named tests can be required to run and pass.",
					"Every specification or test change produces a review record (<code>review.patch</code>, " +
						"<code>summary.md</code>); passing checks don't approve it.",
					"Evidence is saved with source hashes, and <code>ib verify</code> later matches a commit to it."},
				"Which requirements are proven, by checks alone, so review doesn't have to find the problems?",
				[]string{"The same link and test-run questions, from conventions instead of tags.",
					"Plus the questions a reviewer would otherwise ask: is the code real, do the tests run it, would " +
						"they catch it breaking, has the wording moved on?",
					"Plus the API contract and the git history.",
					"People still decide intent; they read evidence instead of code."}) +
			`</section>`,
		`<section><h2>What this verifier is for</h2>` + OurGoals() + `</section>`,
		`<section><h2>The same scenarios, by the question they ask</h2>` +
			`<p class="note">"Review" is IntentBond's deliberate answer for any change to specifications or tests: the clean ` +
			`pull request gets it too. It hands the question to a person rather than answering it.</p>` +
			versus("IntentBond", kindCellFn, true) + `</section>`,
		`<section><h2>How it was run</h2><ol class="steps">` +
			`<li>IntentBond <code>5a1200a</code> (2026-09-29) with its pinned OpenFastTrace 4.9.0.</li>` +
			`<li>The Python demo baseline gets IntentBond's notation the way an agent following its skill would write it: ` +
			`an OFT item per requirement, implementation tags, a named <code>utest</code> tag and ` +
			`<code>@pytest.mark.oft_id</code> marker per test, the pytest hook from IntentBond's example, and ` +
			`<code>scope.json</code>.</li>` +
			`<li>Each scenario script runs unchanged; what it added is tagged the same way. A reworded requirement gets ` +
			`revision 2; variant X2 leaves it at 1.</li>` +
			`<li><code>ib check --base &lt;main before the scenario&gt; --candidate HEAD</code> with two scopes. ` +
			`<b>Default</b>: the documented example (links required, JUnit execution links). <b>Strict</b>: also a required ` +
			`revision increase for changed content, no skipped tests, and every baseline test pinned in ` +
			`<code>required_artifacts</code>.</li>` +
			`<li>Exit 1 is <b>rejected</b>, 4 is <b>review</b> (checks passed, a person must review), 0 is <b>passed</b>.</li>` +
			`</ol></section>`,
		`<section><h2>Every scenario</h2>` +
			keyBlock([][2]string{
				{chip("caught · T3", "ok"), "This verifier failed the check written for that attack."},
				{chip("rejected · caught", "ok"), "<code>ib check</code> exit 1: an automated check failed, so " +
					"IntentBond blocks the change. On an attack, that means it caught it."},
				{chip("review · to a person", "warn"), "Exit 4: every check passed, but the change touched a " +
					"specification or test, so a person must approve it. The clean pull request gets this too."},
				{chip("passed · not flagged", "muted"), "Exit 0: every check passed and nothing needs review. On the " +
					"API and git rows that's expected: those questions are outside IntentBond's goals."},
				{chip("passed", "ok"), "On the baseline: the correct result, nothing is wrong."},
				{`<span class="small"><b>Default / Strict</b></span>`, "The same run with IntentBond's documented " +
					"settings, and with three extra rules: a changed requirement needs a higher revision, no skipped " +
					"tests, and every baseline test must still exist and pass."}}) +
			c.resultsTable([]string{"This verifier", "IntentBond default", "IntentBond strict", "What IntentBond saw"}, toolCell) +
			`</section>`,
		`<section><h2>What IntentBond does that this verifier doesn't</h2><div class="two quad">` +
			`<div class="panel"><h3>Evidence you can check later</h3><p class="small">Each check saves its results with the ` +
			`hashes of the source it ran on. <code>ib verify</code> on the checked commit returned ` +
			`<code>` + escapeHTML(tidy(strList(v.Map("same_commit").Get("output")))) + `</code>; after a later code edit it returned ` +
			`<code>` + escapeHTML(tidy(strList(v.Map("after_code_edit").Get("output")))) + `</code>. This verifier recomputes everything on each ` +
			`run and keeps nothing.</p></div>` +
			`<div class="panel"><h3>Pinned tests</h3><p class="small">Named tests listed in the trusted scope must run and ` +
			`pass. In T7 (strict) that rejected the rewrite because the pinned tests disappeared, even though other tagged ` +
			`tests remained.</p></div>` +
			`<div class="panel"><h3>A review step built in</h3><p class="small">Every specification or test change is ` +
			`collected into <code>review.patch</code> with a summary of changed items, so the person reviewing sees exactly ` +
			`what moved.</p></div>` +
			`<div class="panel"><h3>More ways to prove things</h3><p class="small">An explicit revision policy (rejected X2 ` +
			`in strict mode), tags read with Python's tokenizer so strings don't count, and optional Alloy and Z3 checks ` +
			`for selected properties (not exercised here).</p></div>` +
			`</div></section>`,
		`<section><h2>What the runs show</h2><ul class="plain">` +
			`<li><b>On links and test runs they agree.</b> Reused ID, missing implementation, missing tests, a failing test, ` +
			`a broken suite, a stale revision and a "refactor" that broke a test: both reject all seven.</li>` +
			`<li><b>Both distrust the change being checked.</b> IntentBond reads its scope from the base, as this verifier ` +
			`reads its config from the base branch, so an agent can't relax the rules in its own pull request.</li>` +
			`<li><b>Where the answer needs judgement, IntentBond asks a person.</b> Code that is only a comment, an ` +
			`<code>assert True</code> test and weakened tests (T6, X1, X3) pass its checks and go to review, as designed. ` +
			`This verifier answers those with T3, T6 and T7, so the reviewer reads a finding instead of hunting for it.</li>` +
			`<li><b>Revisions are a policy.</b> Strict mode rejects reworded content without a higher revision (X2); the ` +
			`default sends it to review. This verifier reads the change from git.</li>` +
			`<li><b>The API contract and git history</b> are outside IntentBond's scope.</li></ul></section>`,
		`<section><h2>Using them together</h2><ol class="steps">` +
			`<li><b>This verifier's findings in IntentBond's review.</b> IntentBond decides what a person must review; ` +
			`this verifier tells them what's wrong before they start.</li>` +
			`<li><b>IntentBond's evidence for this verifier's results.</b> Saving results tied to source hashes is this ` +
			`verifier's open gap. IntentBond's bundle and <code>verify</code> are a model for it.</li>` +
			`<li><b>Pinned tests as a T4 option.</b> "These named tests must exist and pass" is a stronger rule than ` +
			`"at least one tagged test" and would suit critical requirements.</li></ol>` +
			`<p class="note">When to pick which: IntentBond when people review every change and you want that review ` +
			`focused and its evidence kept. This verifier when you need to know what's wrong without reading the code. ` +
			`Both when you want both.</p></section>`,
		`<section><h2>Limits of this comparison</h2><ul class="plain small">` +
			`<li>Python only. The tags were written by a script acting as a careful agent, not by a real agent.</li>` +
			`<li>The scenarios were written to test this verifier, so most of them ask its questions. The probes above ask ` +
			`IntentBond's.</li>` +
			`<li>Exit 4 counts as "review", not as a detection or a miss: a careful reviewer may well catch T6, X1 and X3 in ` +
			`<code>review.patch</code>.</li>` +
			`<li>In some containers Java prints a notice when <code>JAVA_TOOL_OPTIONS</code> is set, and IntentBond treats ` +
			`it as an OpenFastTrace error. The runner removes that variable for <code>ib</code>.</li></ul></section>`,
		compareFooter("experiments/intentbond/README.md",
			[]string{"experiments/intentbond/results/intentbond.json", "experiments/intentbond/results/probes.json",
				"experiments/ours-variants.json"}),
	}
	return comparePage("Compared: IntentBond", strings.Join(body, "\n"), "docs/compare/intentbond.html")
}
