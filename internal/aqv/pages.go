package aqv

// The demo pages (run_demo.py's write_html, write_markdown and write_index, and html.demo_report
// and html.languages_report): one page per language with every scenario, a page per scenario run,
// RESULTS.md, and the all-languages index. `aqv pages` writes them for a demo run made with
// `run_demo.py --impl go`, so the Go verifier's results have their own set of pages.

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

// Examples are the scenario runs that also get a page and a text report next to demo.html.
var Examples = []string{"baseline", "T7-weak-tests", "A6-leaked-field"}

// PagesOptions configures WritePages.
type PagesOptions struct {
	Work    string // demo run folder: <Work>/<lang>/demo-results.json and the runs it points to
	Meta    string // demo/langs.json
	Out     string // folder to write: <Out>/index.html, <Out>/<lang>/...
	Variant string // shown in the page eyebrows, e.g. "Go verifier"
	Command string // what regenerates the pages, shown in the footers
}

// Lang is one demo language's metadata and results.
type Lang struct {
	Lang, Name, Stack string
	Mechanisms        *OMap
	Results           []*OMap
}

func (l *Lang) ok() int {
	n := 0
	for _, r := range l.Results {
		if r.Truthy("ok") {
			n++
		}
	}
	return n
}

// LoadLangs reads the language metadata and each language's demo-results.json (missing ones are skipped).
func LoadLangs(meta, work string) ([]*Lang, error) {
	data, err := os.ReadFile(meta)
	if err != nil {
		return nil, err
	}
	v, err := loadJSON(data)
	if err != nil {
		return nil, fmt.Errorf("%s: %w", meta, err)
	}
	var langs []*Lang
	for _, m := range maps(v) {
		f := filepath.Join(work, m.Str("lang"), "demo-results.json")
		raw, err := os.ReadFile(f)
		if err != nil {
			continue
		}
		rv, err := loadJSON(raw)
		if err != nil {
			return nil, fmt.Errorf("%s: %w", f, err)
		}
		langs = append(langs, &Lang{m.Str("lang"), m.Str("name"), m.Str("stack"), m.Map("mechanisms"), maps(rv)})
	}
	return langs, nil
}

// scenario is a successful run with its parsed results.json.
type scenario struct {
	row    *OMap
	report *OMap
}

func (s *scenario) name() string { return s.row.Str("name") }

// readReport loads a run's results.json, dropping the machine's work-folder path like scrub().
func readReport(work, lang string, row *OMap) (*OMap, string, error) {
	out := row.Str("out")
	if !exists(filepath.Join(out, "results.json")) {
		out = filepath.Join(work, lang, "runs", row.Str("name"))
		if row.Str("name") != "baseline" {
			out = filepath.Join(out, "out")
		}
	}
	raw, err := os.ReadFile(filepath.Join(out, "results.json"))
	if err != nil {
		return nil, "", err
	}
	text := strings.ReplaceAll(string(raw), work+"/", "")
	v, err := loadJSON([]byte(text))
	if err != nil {
		return nil, "", fmt.Errorf("%s: %w", out, err)
	}
	rep, _ := v.(*OMap)
	txt, _ := os.ReadFile(filepath.Join(out, "report.txt"))
	return rep, strings.ReplaceAll(string(txt), work+"/", ""), nil
}

// WritePages writes the pages for every language found in opts.Work.
func WritePages(opts PagesOptions) error {
	work := absPath(opts.Work)
	opts.Work = work
	langs, err := LoadLangs(opts.Meta, work)
	if err != nil {
		return err
	}
	if len(langs) == 0 {
		return fmt.Errorf("no demo-results.json found under %s", work)
	}
	if opts.Command == "" {
		opts.Command = "python demo/run_demo.py"
	}
	for _, l := range langs {
		if err := writeLang(opts, l); err != nil {
			return err
		}
	}
	nav := "../../"
	return writeFile2(filepath.Join(opts.Out, "index.html"),
		LanguagesReport(langs, &nav, opts.Variant, opts.Command, "demo/results-go/index.html"))
}

func writeFile2(path, content string) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	return writeFile(path, content)
}

func writeLang(opts PagesOptions, l *Lang) error {
	dir := filepath.Join(opts.Out, l.Lang)
	var scenarios []*scenario
	for _, row := range l.Results {
		if row.Has("error") {
			continue
		}
		rep, txt, err := readReport(opts.Work, l.Lang, row)
		if err != nil {
			return err
		}
		scenarios = append(scenarios, &scenario{row, rep})
		runNav := "../../../../"
		if err := writeFile2(filepath.Join(dir, "runs", row.Str("name")+".html"), HTMLReport(rep, &runNav)); err != nil {
			return err
		}
		if contains(Examples, row.Str("name")) {
			exNav := "../../../"
			if err := writeFile2(filepath.Join(dir, row.Str("name")+".html"), HTMLReport(rep, &exNav)); err != nil {
				return err
			}
			if err := writeFile2(filepath.Join(dir, row.Str("name")+".txt"), txt); err != nil {
				return err
			}
		}
	}
	nav := "../../../"
	if err := writeFile2(filepath.Join(dir, "demo.html"),
		DemoReport(scenarios, l.Name+" ("+l.Stack+")", &nav, opts.Variant, opts.Command)); err != nil {
		return err
	}
	return writeFile2(filepath.Join(dir, "RESULTS.md"), ResultsMarkdown(l, opts.Command))
}

// ---------------------------------------------------------------- findings and the per-language page

func findingsHTML(results []*OMap) string {
	var rows []string
	for _, r := range results {
		if v := r.Str("verdict"); v != "fail" && v != "error" {
			continue
		}
		subj := r.Str("subject") + ": "
		switch r.Str("subject") {
		case "history", "project", "spec", "contract", "routes", "service":
			subj = ""
		}
		rows = append(rows, `<li><span class="ck">`+escapeHTML(r.Str("check"))+`</span><span>`+
			escapeHTML(subj+r.Str("summary"))+`</span></li>`)
	}
	if len(rows) == 0 {
		return `<p class="small muted">No failing checks.</p>`
	}
	return `<ul class="findings">` + strings.Join(rows, "") + `</ul>`
}

func rowOK(r *OMap) bool { return r.Truthy("ok") }

// DemoReport renders <lang>/demo.html.
func DemoReport(scenarios []*scenario, language string, nav *string, variant, command string) string {
	total, ok := len(scenarios), 0
	var attacks, clean []*scenario
	caught := map[string]bool{}
	for _, s := range scenarios {
		if rowOK(s.row) {
			ok++
		}
		if len(strList(s.row.Get("expect"))) > 0 {
			attacks = append(attacks, s)
			if rowOK(s.row) {
				for _, c := range strList(s.row.Get("expect")) {
					caught[c] = true
				}
			}
		} else {
			clean = append(clean, s)
		}
	}
	cleanOK := true
	for _, s := range clean {
		if len(strList(s.row.Get("failing"))) > 0 {
			cleanOK = false
		}
	}
	allAttacksOK := true
	for _, s := range attacks {
		if !rowOK(s.row) {
			allAttacksOK = false
		}
	}

	eyebrow := "Agent Quality Verifier · demo results"
	if language != "" {
		eyebrow += " · " + escapeHTML(language)
	}
	if variant != "" {
		eyebrow += " · " + escapeHTML(variant)
	}
	body := []string{
		`<header class="top"><span class="eyebrow">` + eyebrow + `</span>` +
			fmt.Sprintf(`<h1>%d of %d scenarios behave as expected</h1>`, ok, total) +
			`<p class="lede">A small auth service is built the right way, then an agent gets it wrong in ` +
			fmt.Sprintf(`%d different ways. Each attack runs in its own copy of the repo and is checked like a `, len(attacks)) +
			`pull request against main. Every attack must be caught by the check written for it, and the clean ` +
			`runs must pass everything.</p></header>`,
	}
	attacksLabel := "attacks"
	if allAttacksOK {
		attacksLabel = "attacks, all caught"
	}
	cleanLabel := "failing"
	if cleanOK {
		cleanLabel = "all pass"
	}
	body = append(body, `<div class="stats">`+
		fmt.Sprintf(`<div class="stat"><b>%d / %d</b><span>checks caught their attack</span></div>`, len(caught), len(CheckIDs))+
		fmt.Sprintf(`<div class="stat"><b>%d</b><span>%s</span></div>`, len(attacks), attacksLabel)+
		fmt.Sprintf(`<div class="stat"><b>%s</b><span>%d clean runs (baseline and a clean PR)</span></div></div>`, cleanLabel, len(clean)))

	// Every check, clean and attacked
	var rows []string
	for _, g := range goals {
		rows = append(rows, `<tr class="group"><td colspan="4">`+escapeHTML(g[1])+`</td></tr>`)
		for _, chk := range CheckIDs {
			if !strings.HasPrefix(chk, g[0]) {
				continue
			}
			set := map[string]bool{}
			for _, s := range clean {
				set[s.row.Map("checks").Str(chk)] = true
			}
			verdicts := sortedKeys(set)
			var by, missed []string
			for _, s := range attacks {
				if contains(strList(s.row.Get("expect")), chk) {
					if rowOK(s.row) {
						by = append(by, s.name())
					} else {
						missed = append(missed, s.name())
					}
				}
			}
			var linkParts []string
			for _, n := range by {
				linkParts = append(linkParts, `<a href="#`+escapeHTML(n)+`">`+escapeHTML(n)+`</a>`)
			}
			links := strings.Join(linkParts, ", ")
			if links == "" {
				links = "—"
			}
			if len(missed) > 0 {
				ms := make([]string, len(missed))
				for i, m := range missed {
					ms[i] = escapeHTML(m)
				}
				links += " · missed: " + strings.Join(ms, ", ")
			}
			var chips strings.Builder
			for _, v := range verdicts {
				chips.WriteString(verdictChip(v))
			}
			rows = append(rows, `<tr><td class="id">`+chk+`</td><td class="name">`+escapeHTML(Checks[chk])+`</td>`+
				`<td><div class="chips">`+chips.String()+`</div></td><td>`+links+`</td></tr>`)
		}
	}
	body = append(body, `<section><h2>Every check, clean and attacked</h2>`+
		`<div class="table-wrap"><table><thead><tr><th>ID</th><th>Check</th><th>Clean runs</th>`+
		`<th>Caught by</th></tr></thead><tbody>`+strings.Join(rows, "")+`</tbody></table></div></section>`)

	// Matrix
	var head strings.Builder
	head.WriteString(`<th class="scn">Scenario</th>`)
	for i, c := range CheckIDs {
		gap := ""
		if i > 0 && CheckIDs[i-1][0] != c[0] {
			gap = " gap"
		}
		head.WriteString(`<th class="check` + gap + `">` + c + `</th>`)
	}
	var mrows []string
	for _, s := range scenarios {
		var cells strings.Builder
		expect := strList(s.row.Get("expect"))
		for i, c := range CheckIDs {
			gap := ""
			if i > 0 && CheckIDs[i-1][0] != c[0] {
				gap = "gap"
			}
			v := s.row.Map("checks").Str(c)
			var m string
			switch {
			case contains(expect, c) && (v == "fail" || v == "error"):
				m = `<span class="cell hit" title="expected, caught"></span>`
			case v == "fail" || v == "error":
				m = `<span class="cell also" title="also failed"></span>`
			case v == "pass":
				m = `<span class="cell pass" title="pass"></span>`
			default:
				m = `<span class="cell skip" title="skip"></span>`
			}
			cells.WriteString(`<td class="` + gap + `">` + m + `</td>`)
		}
		mrows = append(mrows, `<tr><td class="scn"><a href="#`+escapeHTML(s.name())+`">`+escapeHTML(s.name())+
			`</a></td>`+cells.String()+`</tr>`)
	}
	body = append(body, `<section><h2>Which checks fired, per scenario</h2>`+
		`<div class="legend"><span><span class="cell hit"></span>the check this attack targets</span>`+
		`<span><span class="cell also"></span>also failed</span><span><span class="cell pass"></span>passed</span>`+
		`<span><span class="cell skip"></span>skipped or not applicable</span></div>`+
		`<div class="table-wrap"><table class="matrix"><thead><tr>`+head.String()+`</tr></thead><tbody>`+
		strings.Join(mrows, "")+`</tbody></table></div></section>`)

	// Scenarios
	var det strings.Builder
	yes := true
	for _, s := range scenarios {
		rep := s.report
		exp := strings.Join(strList(s.row.Get("expect")), ", ")
		if exp == "" {
			exp = "all pass"
		}
		result := chip("missed", "bad")
		if rowOK(s.row) {
			result = chip("as expected", "ok")
		}
		var changed strings.Builder
		n := 0
		for _, r := range maps(rep.Get("requirements")) {
			if r.Str("status") != "Sync" {
				changed.WriteString(requirementBlock(r, &yes))
				n++
			}
		}
		blocks := `<p class="small muted">Every requirement stays proven.</p>`
		if n > 0 {
			blocks = `<div class="sheet">` + changed.String() + `</div>`
		}
		link := `<a class="small" href="runs/` + escapeHTML(s.name()) + `.html">Open the full report for this run</a>`
		det.WriteString(`<details class="scenario" id="` + escapeHTML(s.name()) + `"><summary><span class="nm">` +
			escapeHTML(s.name()) + `</span><span class="tt">` + escapeHTML(s.row.Str("title")) +
			`</span><span class="small muted">expects ` + escapeHTML(exp) + `</span>` + result +
			`</summary><div class="inner">` + blocks + `<h3>Every failing result</h3>` +
			findingsHTML(maps(rep.Get("results"))) + link + `</div></details>`)
	}
	body = append(body, `<section><h2>Scenarios</h2><p class="small muted">Open a scenario to see the requirement `+
		`statuses it changed and every failing result.</p>`+det.String()+`</section>`)
	body = append(body, `<footer>Generated by <code>`+escapeHTML(command)+`</code>. Rerun it to rebuild the demo repo, `+
		`replay every scenario and regenerate this page.</footer>`)
	return pageHTML("Agent Quality Demo", strings.Join(body, "\n"), viewCSS, nav, "")
}

// ---------------------------------------------------------------- all languages

// LanguagesReport renders the index of every language.
func LanguagesReport(langs []*Lang, nav *string, variant, command, current string) string {
	total, good := 0, 0
	for _, l := range langs {
		total += len(l.Results)
		good += l.ok()
	}
	eyebrow := "Agent Quality Verifier · every language"
	if variant != "" {
		eyebrow += " · " + escapeHTML(variant)
	}
	body := []string{
		`<header class="top"><span class="eyebrow">` + eyebrow + `</span>` +
			fmt.Sprintf(`<h1>%d of %d scenarios behave as expected across %d languages</h1>`, good, total, len(langs)) +
			`<p class="lede">The same spec, the same OpenAPI contract and the same 26 attacks, built in each ` +
			`language with the stack an agent would usually pick. Each language must pass every check on its clean ` +
			`runs and catch every attack with the check written for it.</p></header>`,
	}
	gapFor := func(i int) string {
		if i > 0 && CheckIDs[i-1][0] != CheckIDs[i][0] {
			return " gap"
		}
		return ""
	}
	var rows []string
	for _, l := range langs {
		var cells strings.Builder
		for i, c := range CheckIDs {
			gap := ""
			if gapFor(i) != "" {
				gap = ` class="gap"`
			}
			var attacks, clean []*OMap
			for _, r := range l.Results {
				if contains(strList(r.Get("expect")), c) {
					attacks = append(attacks, r)
				}
				if len(strList(r.Get("expect"))) == 0 {
					clean = append(clean, r)
				}
			}
			cleanOK := true
			for _, r := range clean {
				if r.Has("checks") {
					if v := r.Map("checks").Str(c); v != "pass" && v != "skip" {
						cleanOK = false
					}
				}
			}
			caught := len(attacks) > 0
			for _, r := range attacks {
				if !rowOK(r) {
					caught = false
				}
			}
			var m string
			switch {
			case caught && cleanOK:
				m = `<span class="cell good" title="caught its attack; clean runs pass"></span>`
			case !cleanOK:
				m = `<span class="cell also" title="failed on a clean run"></span>`
			default:
				m = `<span class="cell also" title="missed its attack"></span>`
			}
			cells.WriteString(`<td` + gap + `>` + m + `</td>`)
		}
		rows = append(rows, `<tr><td class="scn"><a href="`+escapeHTML(l.Lang)+`/demo.html">`+escapeHTML(l.Name)+`</a></td>`+
			fmt.Sprintf(`<td class="small">%d/%d</td>`, l.ok(), len(l.Results))+cells.String()+`</tr>`)
	}
	var head strings.Builder
	head.WriteString(`<th class="scn">Language</th><th>OK</th>`)
	for i, c := range CheckIDs {
		head.WriteString(`<th class="check` + gapFor(i) + `">` + c + `</th>`)
	}
	body = append(body, `<section><h2>Every check in every language</h2>`+
		`<div class="legend"><span><span class="cell good"></span>caught its attack, clean runs pass</span>`+
		`<span><span class="cell also"></span>missed, or failed a clean run</span></div>`+
		`<div class="table-wrap"><table class="matrix"><thead><tr>`+head.String()+`</tr></thead>`+
		`<tbody>`+strings.Join(rows, "")+`</tbody></table></div></section>`)

	var mech []string
	for _, l := range langs {
		for _, c := range l.Mechanisms.Keys() {
			if !contains(mech, c) {
				mech = append(mech, c)
			}
		}
	}
	idx := func(c string) int {
		for i, x := range CheckIDs {
			if x == c {
				return i
			}
		}
		return -1
	}
	sort.SliceStable(mech, func(i, j int) bool { return idx(mech[i]) < idx(mech[j]) })
	if len(mech) > 0 {
		var hdr strings.Builder
		hdr.WriteString("<th>Check</th>")
		for _, l := range langs {
			hdr.WriteString("<th>" + escapeHTML(l.Name) + "</th>")
		}
		var mrows []string
		for _, c := range mech {
			var tds strings.Builder
			for _, l := range langs {
				txt := "—"
				if l.Mechanisms.Has(c) {
					txt = l.Mechanisms.Str(c)
				}
				tds.WriteString(`<td class="small">` + escapeHTML(txt) + `</td>`)
			}
			mrows = append(mrows, `<tr><td class="id">`+c+`<br><span class="small muted" style="font-family:var(--font-body);`+
				`font-weight:400">`+escapeHTML(Checks[c])+`</span></td>`+tds.String()+`</tr>`)
		}
		body = append(body, `<section><h2>How each language does it</h2><p class="small muted">Only the checks that `+
			`depend on the stack. Every other check works the same way in every language: it reads the `+
			`spec, the contract and git history.</p>`+
			`<div class="table-wrap"><table><thead><tr>`+hdr.String()+`</tr></thead><tbody>`+strings.Join(mrows, "")+
			`</tbody></table></div></section>`)
	}

	var cards strings.Builder
	for _, l := range langs {
		tone := "bad"
		if l.ok() == len(l.Results) {
			tone = "ok"
		}
		cards.WriteString(`<div class="req ok"><div class="top"><span class="id">` + escapeHTML(l.Name) + `</span>` +
			chip(fmt.Sprintf("%d/%d", l.ok(), len(l.Results)), tone) +
			`</div><p>` + escapeHTML(l.Stack) + `</p><a class="small" href="` + escapeHTML(l.Lang) +
			`/demo.html">Scenario details</a></div>`)
	}
	body = append(body, `<section><h2>Languages</h2><div class="reqs">`+cards.String()+`</div></section>`)
	body = append(body, `<footer>Generated by <code>`+escapeHTML(command)+` --lang all</code>.</footer>`)
	return pageHTML("Agent Quality Across Languages", strings.Join(body, "\n"), "", nav, current)
}

// ---------------------------------------------------------------- RESULTS.md

// ResultsMarkdown renders <lang>/RESULTS.md.
func ResultsMarkdown(l *Lang, command string) string {
	var clean []*OMap
	for _, r := range l.Results {
		if len(strList(r.Get("expect"))) == 0 && !r.Has("error") {
			clean = append(clean, r)
		}
	}
	lines := []string{"# Demo results: " + l.Name, "", "Stack: " + l.Stack + ".", "",
		"Generated by `" + command + "`. Each attack runs in its own copy of the baseline repo and " +
			"is checked like a pull request against `main`.", "",
		"## Every check, clean and attacked", "",
		"| Check | What it checks | Clean runs | Caught by |", "|---|---|---|---|"}
	for _, chk := range CheckIDs {
		set := map[string]bool{}
		for _, r := range clean {
			set[r.Map("checks").Str(chk)] = true
		}
		var catchers, missed []string
		for _, r := range l.Results {
			if contains(strList(r.Get("expect")), chk) {
				if rowOK(r) {
					catchers = append(catchers, "`"+r.Str("name")+"`")
				} else {
					missed = append(missed, "`"+r.Str("name")+"`")
				}
			}
		}
		cell := strings.Join(catchers, ", ")
		if cell == "" {
			cell = "—"
		}
		if len(missed) > 0 {
			cell += " · missed: " + strings.Join(missed, ", ")
		}
		lines = append(lines, fmt.Sprintf("| %s | %s | %s | %s |", chk, Checks[chk], strings.Join(sortedKeys(set), " / "), cell))
	}
	lines = append(lines, "", "## Scenarios", "",
		"| Scenario | What happens | Expected | Failing checks | Statuses that changed | Result |",
		"|---|---|---|---|---|---|")
	for _, r := range l.Results {
		if r.Has("error") {
			lines = append(lines, fmt.Sprintf("| `%s` | %s | %s | script error | | ❌ |", r.Str("name"), r.Str("title"),
				strings.Join(strList(r.Get("expect")), ", ")))
			continue
		}
		var changed []string
		st := r.Map("statuses")
		for _, k := range st.Keys() {
			if v := st.Str(k); v != "Sync" {
				changed = append(changed, k+": "+v)
			}
		}
		ch := strings.Join(changed, ", ")
		if ch == "" {
			ch = "all Sync"
		}
		exp := strings.Join(strList(r.Get("expect")), ", ")
		if exp == "" {
			exp = "all pass"
		}
		fail := strings.Join(strList(r.Get("failing")), ", ")
		if fail == "" {
			fail = "none"
		}
		mark := "❌"
		if rowOK(r) {
			mark = "✅"
		}
		lines = append(lines, fmt.Sprintf("| `%s` | %s | %s | %s | %s | %s |", r.Str("name"), r.Str("title"), exp, fail, ch, mark))
	}
	return strings.Join(lines, "\n") + "\n"
}
