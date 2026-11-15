package aqv

// aqv watch: follows a repository while an agent works in it. Every time the checked-out branch
// moves to a new commit, the commit is checked in a separate worktree (so the agent's uncommitted
// files are never touched or tested) and four files are rewritten:
//
//	timeline.jsonl  one line per checked commit: every requirement's status and every check's verdict
//	state.json      the latest line
//	state.md        the same as short text, for the agent or a person to read
//	live.html       state and health now, and how they moved commit by commit (reloads itself)
//
// State is where each requirement stands. Health is whether the guardrails hold for what has been
// built so far: a requirement nobody has started is not a health problem, a broken one is.

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
)

type WatchOptions struct {
	Repo     string
	Main     string        // the branch requirements merge into
	Out      string        // where the four files and per-commit reports go
	Skip     []string      // checks left out of each run (the slow ones by default)
	Interval time.Duration // how often to look for a new commit
	Once     bool          // check the current commit and return
	Feedback string        // a second place to write state.md, for example inside the repo
	Replay   string        // a timeline.jsonl from an earlier watch: check the same commits again and return
	Log      func(string)
}

func rank(status string) int {
	for i, s := range statusOrder {
		if s == status {
			return i
		}
	}
	return -1
}

// Snapshot summarises one checked commit from its report.
func Snapshot(rep *OMap, seq int, branch, subject string, bestOnMain map[string]string) *OMap {
	reqs := maps(rep.Get("requirements"))
	statuses, counts := NewOMap(), NewOMap()
	proven, built := 0, 0
	for _, r := range reqs {
		st := r.Str("status")
		statuses.Set(r.Str("id"), st)
		n, _ := counts.Get(st).(int)
		counts.Set(st, n+1)
		if st == "Sync" {
			proven++
		}
		if st != "Missing" {
			built++
		}
	}
	// A failure belongs to "attention" unless it only says that work hasn't started.
	noCode := map[string]bool{}
	for _, r := range maps(rep.Get("results")) {
		if r.Str("check") == "T2" && r.Str("verdict") == "fail" {
			noCode[r.Str("subject")] = true
		}
	}
	built = len(reqs) - len(noCode)
	attention, pending := []any{}, 0
	for _, r := range maps(rep.Get("results")) {
		v := r.Str("verdict")
		if v != "fail" && v != "error" {
			continue
		}
		// A requirement with no code yet is not started, whatever else fails on it; a conflict in
		// its wording is still worth a person's attention before anyone builds it.
		notStarted := r.Str("scope") == "requirement" && noCode[r.Str("subject")] && !personChecks[r.Str("check")]
		cantRunYet := v == "error" && built == 0
		if notStarted || cantRunYet {
			pending++
			continue
		}
		who := "agent"
		if personChecks[r.Str("check")] {
			who = "person"
		}
		attention = append(attention, om("check", r.Str("check"), "subject", r.Str("subject"), "verdict", v,
			"summary", r.Str("summary"), "who", who))
	}
	regressed := []string{}
	for _, id := range statuses.Keys() {
		if best, ok := bestOnMain[id]; ok && rank(statuses.Str(id)) < rank(best) {
			regressed = append(regressed, fmt.Sprintf("%s was %s on main, now %s", id, best, statuses.Str(id)))
		}
	}
	health := "healthy"
	for _, a := range attention {
		if a.(*OMap).Str("verdict") == "fail" {
			health = "failing"
		} else if health == "healthy" {
			health = "blocked"
		}
	}
	if len(regressed) > 0 {
		health = "failing"
	}
	families := NewOMap()
	checks := rep.Map("checks")
	for _, fam := range []string{"C", "T", "A", "D", "H"} {
		pass, fail, other := 0, 0, 0
		for _, c := range checks.Keys() {
			if !strings.HasPrefix(c, fam) {
				continue
			}
			switch checks.Str(c) {
			case "pass":
				pass++
			case "fail", "error":
				fail++
			default:
				other++
			}
		}
		if pass+fail+other > 0 {
			families.Set(fam, om("pass", pass, "fail", fail, "other", other))
		}
	}
	return om("seq", seq, "time", time.Now().UTC().Format(time.RFC3339), "sha", rep.Str("head"), "branch", branch,
		"subject", subject, "requirements", len(reqs), "proven", proven, "built", built, "health", health,
		"statuses", statuses, "counts", counts, "checks", checks, "families", families,
		"attention", attention, "pending", pending, "regressed", regressed)
}

// StateText is state.md: what an agent needs to decide what to do next.
func StateText(s *OMap, rep *OMap) string {
	var out []string
	out = append(out, fmt.Sprintf("# Verifier state at %s on %s", head(s.Str("sha"), 7), s.Str("branch")), "")
	out = append(out, fmt.Sprintf("State: %s of %s requirements proven (Sync).", pyStr(s.Get("proven")), pyStr(s.Get("requirements"))))
	att := maps(s.Get("attention"))
	decisions := 0
	for _, a := range att {
		if attWho(a) == "person" {
			decisions++
		}
	}
	switch {
	case decisions > 0:
		out = append(out, fmt.Sprintf("Health: needs a person. %d of %d problem(s) can only be settled by a person.", decisions, len(att)))
	case s.Str("health") == "healthy":
		out = append(out, "Health: healthy. Nothing built so far breaks a check.")
	case s.Str("health") == "blocked":
		out = append(out, fmt.Sprintf("Health: blocked. %d check(s) could not run.", len(att)))
	default:
		out = append(out, fmt.Sprintf("Health: failing. %d problem(s) need attention.", len(att)))
	}
	out = append(out, "", "## Requirements", "")
	for _, r := range maps(rep.Get("requirements")) {
		fc := strings.Join(strList(r.Get("failing_checks")), ", ")
		line := pad(r.Str("id"), 13) + pad(r.Str("status"), 13) + fc
		out = append(out, strings.TrimRight(line, " "))
	}
	if reg := strList(s.Get("regressed")); len(reg) > 0 {
		out = append(out, "", "## Regressions", "")
		for _, r := range reg {
			out = append(out, "- "+r)
		}
	}
	var person, agent []*OMap
	for _, a := range att {
		if attWho(a) == "person" {
			person = append(person, a)
		} else {
			agent = append(agent, a)
		}
	}
	if len(person) > 0 {
		out = append(out, "", "## Needs a person", "",
			"These are disagreements between documents you may not edit, or changes only a person may make.",
			"Do not pick a side and do not build the requirements they name. Finish what is unaffected, then stop and report them.", "")
		for _, a := range person {
			out = append(out, fmt.Sprintf("- %s %s: %s", a.Str("check"), a.Str("subject"), a.Str("summary")))
		}
	}
	if len(agent) > 0 {
		out = append(out, "", "## Needs attention", "")
		for _, a := range agent {
			out = append(out, fmt.Sprintf("- %s %s: %s", a.Str("check"), a.Str("subject"), a.Str("summary")))
		}
	}
	if skipped := notRun(s.Map("checks")); len(skipped) > 0 {
		out = append(out, "", "Not run on this commit (they run in the final check): "+strings.Join(skipped, ", ")+".")
	}
	return strings.Join(out, "\n") + "\n"
}

func notRun(checks *OMap) []string {
	var out []string
	for _, c := range checks.Keys() {
		if checks.Str(c) == "not_run" {
			out = append(out, c)
		}
	}
	return out
}

const liveCSS = `
/* Layout: where the work stands now, what needs someone, then how it got here commit by commit. */
.page { padding-left: max(20px, env(safe-area-inset-left, 0px)); padding-right: max(20px, env(safe-area-inset-right, 0px)); gap: 36px; }
.page > * { min-width: 0; }
.lv-head { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }
.lv-head h1 { font-size: clamp(26px, 4.2vw, 36px); }
.lv-bar { display: flex; height: 8px; border-radius: 4px; overflow: hidden; background: var(--muted-bg); }
.lv-bar i { display: block; height: 100%; }
.lv-legend { display: flex; flex-wrap: wrap; gap: 6px 14px; font-size: 12px; color: var(--muted); }
.lv-legend i { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 5px; }
.lv-fams { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 0; border: 1px solid var(--line); border-radius: 10px; background: var(--surface); overflow: hidden; }
.lv-fam { padding: 12px 14px; border-left: 1px solid var(--line); margin-left: -1px; display: grid; gap: 2px; min-width: 0; }
.lv-fam b { font-family: var(--font-display); font-size: 20px; line-height: 1.1; font-variant-numeric: tabular-nums; }
.lv-fam b.bad { color: var(--bad-fg); }
.lv-fam span { font-size: 12px; color: var(--muted); }
.lv-att { display: grid; background: var(--surface); border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
.lv-att > div { display: grid; grid-template-columns: 128px 150px minmax(0, 1fr); gap: 4px 12px; padding: 9px 14px; border-top: 1px solid var(--line); font-size: 14px; align-items: baseline; overflow-wrap: anywhere; }
.lv-att > div:first-child { border-top: 0; }
.lv-att code { font-size: 12px; }
@media (max-width: 640px) { .lv-att > div { grid-template-columns: minmax(0, 1fr); } }
.lv-scroll { overflow-x: auto; border: 1px solid var(--line); border-radius: 10px; background: var(--surface); padding: 14px; }
.lv-grid { display: grid; gap: 3px; align-items: center; width: max-content; font-size: 12px; }
.lv-grid .lv-rid { font-family: var(--font-mono); padding-right: 12px; white-space: nowrap; position: sticky; left: 0; background: var(--surface); }
.lv-grid .lv-now { padding-left: 10px; white-space: nowrap; }
.lv-grid a.lv-c, .lv-grid span.lv-c { display: block; width: 16px; height: 16px; border-radius: 4px; }
.lv-grid a.lv-c:hover, .lv-grid a.lv-c:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
.lv-grid .lv-n { font-family: var(--font-mono); font-size: 10px; color: var(--muted); text-align: center; width: 16px; }
.lv-grid .lv-n.main { color: var(--fg); font-weight: 600; }
.lv-grid .lv-h { width: 16px; height: 6px; border-radius: 3px; }
.lv-grid .lv-lab { font-size: 11px; color: var(--muted); padding-right: 12px; position: sticky; left: 0; background: var(--surface); }
.lv-chart { display: block; width: 100%; height: auto; max-width: 720px; }
.lv-chart text { font-family: var(--font-mono); font-size: 11px; fill: var(--muted); }
`

var statusColor = map[string]string{"Sync": "var(--ok-fg)", "Drift": "var(--warn-fg)", "Untested": "var(--warn-fg)",
	"Unexercised": "var(--warn-fg)", "Weak": "var(--warn-fg)", "Missing": "var(--muted-bg)", "Gone": "var(--bad-fg)",
	"Failing": "var(--bad-fg)", "Contract": "var(--bad-fg)", "Data": "var(--bad-fg)", "Conflict": "var(--bad-fg)"}

var familyNames = map[string]string{"C": "Spec, contracts and design agree", "T": "Tests prove the spec",
	"A": "API matches its contract", "D": "Database matches its contract", "H": "Git history can be trusted"}

// attWho says who must act on a failure: a person, for the checks only a person can settle.
func attWho(a *OMap) string {
	if a.Str("who") == "person" || personChecks[a.Str("check")] {
		return "person"
	}
	return "agent"
}

// Render rewrites the pages in dir from the results already there: report.html and review.html
// from results.json, and for a watch folder every snapshot's pages and live.html. Nothing is
// checked again, so results from an older run can be read with the current pages.
func Render(dir string) error {
	one := func(d string) error {
		data, err := os.ReadFile(filepath.Join(d, "results.json"))
		if err != nil {
			return err
		}
		v, err := loadJSON(data)
		if err != nil {
			return err
		}
		rep, ok := v.(*OMap)
		if !ok {
			return fmt.Errorf("%s/results.json is not a report", d)
		}
		if err := writeFile(filepath.Join(d, "report.html"), HTMLReport(rep, nil)); err != nil {
			return err
		}
		return writeFile(filepath.Join(d, "review.html"), ReviewHTML(rep))
	}
	found := false
	if exists(filepath.Join(dir, "results.json")) {
		found = true
		if err := one(dir); err != nil {
			return err
		}
	}
	if exists(filepath.Join(dir, "timeline.jsonl")) {
		found = true
		snaps, _ := filepath.Glob(filepath.Join(dir, "snap", "*"))
		for _, d := range snaps {
			if exists(filepath.Join(d, "results.json")) {
				if err := one(d); err != nil {
					return err
				}
			}
		}
		repo := filepath.Base(dir)
		if data, err := os.ReadFile(filepath.Join(dir, "state.json")); err == nil {
			if v, err := loadJSON(data); err == nil {
				if m, ok := v.(*OMap); ok && m.Str("repo") != "" {
					repo = m.Str("repo")
				}
			}
		}
		if err := writeFile(filepath.Join(dir, "live.html"), LiveHTML(readTimeline(filepath.Join(dir, "timeline.jsonl")), repo, false)); err != nil {
			return err
		}
	}
	if !found {
		return fmt.Errorf("%s has no results.json or timeline.jsonl", dir)
	}
	return nil
}

func snapDir(t *OMap) string {
	seq, _ := toFloat(t.Get("seq"))
	return fmt.Sprintf("snap/%03d-%s", int(seq), head(t.Str("sha"), 7))
}

// provenChart draws requirements proven after each checked commit, to scale.
func provenChart(show []*OMap, total float64) string {
	if len(show) < 2 || total == 0 {
		return ""
	}
	const w, h, left, top, bottom = 720.0, 150.0, 30.0, 10.0, 22.0
	plotW, plotH := w-left-10, h-top-bottom
	x := func(i int) float64 { return left + plotW*float64(i)/float64(len(show)-1) }
	y := func(v float64) float64 { return top + plotH*(1-v/total) }
	var line, area strings.Builder
	fmt.Fprintf(&area, "M%.1f %.1f", x(0), y(0))
	for i, t := range show {
		v, _ := toFloat(t.Get("proven"))
		cmd := "L"
		if i == 0 {
			cmd = "M"
		}
		if i > 0 {
			pv, _ := toFloat(show[i-1].Get("proven"))
			fmt.Fprintf(&line, "L%.1f %.1f", x(i), y(pv))
			fmt.Fprintf(&area, "L%.1f %.1f", x(i), y(pv))
		}
		fmt.Fprintf(&line, "%s%.1f %.1f", cmd, x(i), y(v))
		fmt.Fprintf(&area, "L%.1f %.1f", x(i), y(v))
	}
	fmt.Fprintf(&area, "L%.1f %.1fZ", x(len(show)-1), y(0))
	first, _ := toFloat(show[0].Get("seq"))
	last, _ := toFloat(show[len(show)-1].Get("seq"))
	return fmt.Sprintf(`<svg class="lv-chart" viewBox="0 0 %.0f %.0f" role="img" aria-label="Requirements proven after each checked commit">`+
		`<line x1="%.0f" y1="%.1f" x2="%.0f" y2="%.1f" stroke="var(--line)" stroke-dasharray="3 3"/>`+
		`<line x1="%.0f" y1="%.1f" x2="%.0f" y2="%.1f" stroke="var(--line)"/>`+
		`<path d="%s" fill="var(--ok-bg)" stroke="none"/><path d="%s" fill="none" stroke="var(--ok-fg)" stroke-width="2"/>`+
		`<text x="%.0f" y="%.1f" text-anchor="end">%.0f</text><text x="%.0f" y="%.1f" text-anchor="end">0</text>`+
		`<text x="%.0f" y="%.0f">check %.0f</text><text x="%.0f" y="%.0f" text-anchor="end">check %.0f</text></svg>`,
		w, h, left, y(total), w-10, y(total), left, y(0), w-10, y(0), area.String(), line.String(),
		left-6, y(total)+4, total, left-6, y(0)+4, left, h-5, first, w-10, h-5, last)
}

// LiveHTML renders live.html from every snapshot so far.
func LiveHTML(timeline []*OMap, repoName string, reload bool) string {
	var body []string
	if len(timeline) == 0 {
		body = append(body, `<header class="top"><span class="eyebrow">`+escapeHTML(repoName)+`</span><h1>Waiting for the first commit.</h1></header>`)
	} else {
		s := timeline[len(timeline)-1]
		tone := map[string]string{"healthy": "ok", "blocked": "warn", "failing": "bad"}[s.Str("health")]
		total, _ := toFloat(s.Get("requirements"))
		att := maps(s.Get("attention"))
		reg := strList(s.Get("regressed"))
		person := 0
		for _, a := range att {
			if attWho(a) == "person" {
				person++
			}
		}
		healthChip := chip(s.Str("health"), tone)
		if person > 0 {
			healthChip = chip("needs a person", "bad")
		}
		body = append(body, `<header class="top"><span class="eyebrow">`+escapeHTML(repoName)+` · `+escapeHTML(s.Str("branch"))+
			` · `+head(s.Str("sha"), 7)+` · check `+pyStr(s.Get("seq"))+`</span><div class="lv-head"><h1>`+
			fmt.Sprintf("%s of %s requirements proven.", pyStr(s.Get("proven")), pyStr(s.Get("requirements")))+`</h1>`+
			healthChip+`</div><p class="lede muted">Last commit checked: `+escapeHTML(s.Str("subject"))+
			`. <a href="`+snapDir(s)+`/review.html">Open its full review</a>.</p></header>`)

		// State: one bar, one segment per status.
		var segs, legend strings.Builder
		counts := s.Map("counts")
		for _, st := range []string{"Sync", "Drift", "Weak", "Unexercised", "Untested", "Data", "Contract", "Failing", "Gone", "Conflict", "Missing"} {
			n, ok := toFloat(counts.Get(st))
			if !ok || n == 0 || total == 0 {
				continue
			}
			fmt.Fprintf(&segs, `<i style="width:%.2f%%;background:%s" title="%s: %d"></i>`, 100*n/total, statusColor[st], st, int(n))
			fmt.Fprintf(&legend, `<span><i style="background:%s"></i>%d %s</span>`, statusColor[st], int(n), st)
		}
		body = append(body, `<section><h2>State</h2><div class="lv-bar">`+segs.String()+`</div><div class="lv-legend">`+
			legend.String()+`</div></section>`)

		// Health: what needs someone now, then one cell per family of checks.
		var tiles strings.Builder
		fams := s.Map("families")
		for _, f := range fams.Keys() {
			m := fams.Map(f)
			fail, _ := toFloat(m.Get("fail"))
			cls := ""
			if fail > 0 {
				cls = ` class="bad"`
			}
			tiles.WriteString(`<div class="lv-fam"><b` + cls + `>` + pyStr(m.Get("pass")) + ` pass · ` + pyStr(m.Get("fail")) + ` fail</b><span>` +
				escapeHTML(f+" · "+familyNames[f]) + `</span></div>`)
		}
		health := `<section><h2>Health</h2>`
		if len(att)+len(reg) == 0 {
			health += `<p class="muted small" style="margin:0">Nothing built so far breaks a check. ` + pyStr(s.Get("pending")) +
				` failure(s) only say that work hasn't started.</p>`
		} else {
			var rows strings.Builder
			for _, r := range reg {
				rows.WriteString(`<div><span>` + chip("regression", "bad") + `</span><code>main</code><span>` + escapeHTML(r) + `</span></div>`)
			}
			for _, who := range []string{"person", "agent"} {
				for _, a := range att {
					if attWho(a) != who {
						continue
					}
					label, t := "for the agent", "warn"
					if who == "person" {
						label, t = "needs a person", "bad"
					}
					rows.WriteString(`<div><span>` + chip(label, t) + `</span><code>` + escapeHTML(a.Str("check")+" "+a.Str("subject")) +
						`</code><span>` + escapeHTML(a.Str("summary")) + `</span></div>`)
				}
			}
			health += `<div class="lv-att">` + rows.String() + `</div>`
		}
		body = append(body, health+`<div class="lv-fams">`+tiles.String()+`</div></section>`)

		// How it moved: requirements down, checked commits across. Each cell opens that commit's review.
		show := timeline
		if len(show) > 60 {
			show = show[len(show)-60:]
		}
		var grid strings.Builder
		fmt.Fprintf(&grid, `<div class="lv-grid" style="grid-template-columns:max-content repeat(%d, 16px) max-content">`, len(show))
		grid.WriteString(`<span class="lv-lab">check</span>`)
		for _, t := range show {
			cls := "lv-n"
			if t.Truthy("on_main") {
				cls += " main"
			}
			grid.WriteString(`<span class="` + cls + `" title="` + escapeHTML(head(t.Str("sha"), 7)+" on "+t.Str("branch")+": "+t.Str("subject")) +
				`">` + pyStr(t.Get("seq")) + `</span>`)
		}
		grid.WriteString(`<span></span><span class="lv-lab">health</span>`)
		for _, t := range show {
			c := map[string]string{"healthy": "var(--ok-fg)", "blocked": "var(--warn-fg)", "failing": "var(--bad-fg)"}[t.Str("health")]
			grid.WriteString(`<span class="lv-h" style="background:` + c + `" title="` + escapeHTML(t.Str("health")) + `"></span>`)
		}
		grid.WriteString(`<span></span>`)
		for _, id := range s.Map("statuses").Keys() {
			grid.WriteString(`<span class="lv-rid">` + escapeHTML(id) + `</span>`)
			for _, t := range show {
				st := t.Map("statuses").Str(id)
				color, ok := statusColor[st]
				if !ok {
					grid.WriteString(`<span class="lv-c"></span>`)
					continue
				}
				grid.WriteString(`<a class="lv-c" href="` + snapDir(t) + `/review.html#` + escapeHTML(id) + `" style="background:` + color +
					`" title="` + escapeHTML(id+" was "+st+" at check "+pyStr(t.Get("seq"))+" ("+head(t.Str("sha"), 7)+")") + `"></a>`)
			}
			grid.WriteString(`<span class="lv-now">` + chip(s.Map("statuses").Str(id), statusToneOf(s.Map("statuses").Str(id))) + `</span>`)
		}
		grid.WriteString(`</div>`)
		body = append(body, `<section><h2>Commit by commit</h2>`+provenChart(show, total)+`<div class="lv-scroll">`+grid.String()+`</div>`+
			`<p class="muted small" style="margin:0">One column per checked commit, oldest first; numbers in bold are commits on main. `+
			`A square opens that commit's review at that requirement.</p></section>`)
	}
	foot := `<footer>Written by <code>aqv watch</code>.`
	if reload {
		foot += ` This page reloads every 5 seconds.<script>setTimeout(function () { location.reload(); }, 5000);</script>`
	}
	body = append(body, foot+`</footer>`)
	return pageHTML("Agent Work Live", strings.Join(body, "\n"), liveCSS, nil, "")
}

func readTimeline(path string) []*OMap {
	var out []*OMap
	data, err := os.ReadFile(path)
	if err != nil {
		return out
	}
	for _, line := range splitlines(string(data)) {
		if v, err := loadJSON([]byte(line)); err == nil {
			if m, ok := v.(*OMap); ok {
				out = append(out, m)
			}
		}
	}
	return out
}

// oneLineJSON re-encodes dumpJSON's indented output on a single line.
func oneLineJSON(v any) string {
	var parts []string
	for _, l := range splitlines(dumpJSON(v)) {
		parts = append(parts, strip(l))
	}
	return strings.Join(parts, " ")
}

type watcher struct {
	o        WatchOptions
	repo     string
	timeline []*OMap
	best     map[string]string // best status each requirement has had on main
	seen     map[string]bool
	mainAt   string // replay only: where main stood when the commit being checked was made
}

func (w *watcher) logf(format string, args ...any) {
	if w.o.Log != nil {
		w.o.Log(fmt.Sprintf(format, args...))
	}
}

// checkCommit checks sha in its own worktree and returns the report, or why it couldn't.
func (w *watcher) checkCommit(branch, sha string) (rep *OMap, err error) {
	tree := filepath.Join(w.o.Out, "tree")
	gitQuiet(w.repo, "worktree", "remove", "--force", tree)
	os.RemoveAll(tree)
	gitQuiet(w.repo, "worktree", "prune")
	if _, msg, code := gitRun(w.repo, "worktree", "add", "--detach", "-f", tree, sha); code != 0 {
		return nil, fmt.Errorf("can't check out %s: %s", head(sha, 7), strip(msg))
	}
	defer func() {
		gitQuiet(w.repo, "worktree", "remove", "--force", tree)
		if r := recover(); r != nil {
			err = fmt.Errorf("%v", r)
		}
	}()
	base := ""
	if branch != w.o.Main && gitOK(w.repo, "rev-parse", "--verify", "-q", w.o.Main) {
		base = w.o.Main
		if w.o.Replay != "" {
			base = w.mainAt // main has moved on since; compare with main as it was
		}
	}
	eng, err := NewEngine(tree, Options{Base: base, Skip: w.o.Skip, HeadBranch: branch,
		Workdir: filepath.Join(w.o.Out, "work")})
	if err != nil {
		return nil, err
	}
	return eng.Run(), nil
}

func (w *watcher) record(branch, sha string) {
	subject := strip(gitQuiet(w.repo, "log", "-1", "--format=%s", sha))
	w.logf("checking %s on %s: %s", head(sha, 7), branch, subject)
	rep, err := w.checkCommit(branch, sha)
	if err != nil {
		w.logf("  could not check: %v", err)
		return
	}
	// The worktree's folder name and path are the watcher's, not the project's.
	rep.Set("repo", w.repo)
	seq := len(w.timeline) + 1
	s := Snapshot(rep, seq, branch, subject, w.best)
	s.Set("on_main", branch == w.o.Main)
	if branch == w.o.Main {
		st := s.Map("statuses")
		for _, id := range st.Keys() {
			if cur, ok := w.best[id]; !ok || rank(st.Str(id)) > rank(cur) {
				w.best[id] = st.Str(id)
			}
		}
	}
	w.timeline = append(w.timeline, s)
	snap := filepath.Join(w.o.Out, "snap", fmt.Sprintf("%03d-%s", seq, head(sha, 7)))
	os.MkdirAll(snap, 0o755)
	WriteOutputs(snap, rep)
	f, err := os.OpenFile(filepath.Join(w.o.Out, "timeline.jsonl"), os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644)
	if err == nil {
		f.WriteString(oneLineJSON(s) + "\n")
		f.Close()
	}
	text := StateText(s, rep)
	writeFile(filepath.Join(w.o.Out, "state.json"), dumpJSON(s))
	writeFile(filepath.Join(w.o.Out, "state.md"), text)
	if w.o.Feedback != "" {
		os.MkdirAll(filepath.Dir(w.o.Feedback), 0o755)
		writeFile(w.o.Feedback, text)
	}
	writeFile(filepath.Join(w.o.Out, "live.html"), LiveHTML(w.timeline, filepath.Base(w.repo), !w.o.Once && w.o.Replay == ""))
	w.logf("  %s of %s proven, health %s, %d need attention", pyStr(s.Get("proven")), pyStr(s.Get("requirements")),
		s.Str("health"), len(maps(s.Get("attention"))))
}

// Watch runs until the process is stopped, or once when o.Once is set.
func Watch(o WatchOptions) error {
	repo := absPath(o.Repo)
	if real, err := filepath.EvalSymlinks(repo); err == nil {
		repo = real
	}
	if !gitOK(repo, "rev-parse", "--git-dir") {
		return fmt.Errorf("%s is not a git repository", repo)
	}
	if o.Main == "" {
		o.Main = "main"
	}
	if o.Interval <= 0 {
		o.Interval = 5 * time.Second
	}
	o.Out = absPath(o.Out)
	if err := os.MkdirAll(o.Out, 0o755); err != nil {
		return err
	}
	w := &watcher{o: o, repo: repo, best: map[string]string{}, seen: map[string]bool{}}
	// Pick up where an earlier watch left off.
	w.timeline = readTimeline(filepath.Join(o.Out, "timeline.jsonl"))
	for _, s := range w.timeline {
		w.seen[s.Str("branch")+"@"+s.Str("sha")] = true
		if s.Truthy("on_main") {
			st := s.Map("statuses")
			for _, id := range st.Keys() {
				if cur, ok := w.best[id]; !ok || rank(st.Str(id)) > rank(cur) {
					w.best[id] = st.Str(id)
				}
			}
		}
	}
	writeFile(filepath.Join(o.Out, "live.html"), LiveHTML(w.timeline, filepath.Base(repo), !o.Once && o.Replay == ""))
	if o.Replay != "" {
		// Judge a recorded run again, commit by commit, with this version of the verifier.
		for _, s := range readTimeline(o.Replay) {
			w.record(s.Str("branch"), s.Str("sha"))
			if s.Str("branch") == o.Main {
				w.mainAt = s.Str("sha")
			}
		}
		return nil
	}
	for {
		branch := strip(gitQuiet(repo, "symbolic-ref", "-q", "--short", "HEAD"))
		sha := strip(gitQuiet(repo, "rev-parse", "-q", "--verify", "HEAD"))
		if key := branch + "@" + sha; branch != "" && sha != "" && !w.seen[key] {
			w.seen[key] = true
			w.record(branch, sha)
		}
		if o.Once {
			return nil
		}
		time.Sleep(o.Interval)
	}
}
