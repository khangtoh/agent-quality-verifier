package aqv

// Runs every check against one repo state and returns results plus requirement statuses
// (engine.py). The report is built as an ordered tree so results.json, report.txt and
// report.html match the Python implementation.

import (
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"syscall"
	"time"

	"github.com/dlclark/regexp2"
)

var CheckIDs = []string{"T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8",
	"A1", "A2", "A3", "A4", "A5", "A6", "A7",
	"H1", "H2", "H3", "H4", "H5", "H6", "H7", "H8", "H9"}

var Checks = map[string]string{
	"T1": "Requirement IDs are valid and never reused",
	"T2": "A code commit references the requirement",
	"T3": "The code from those commits still exists",
	"T4": "Tests are tagged to the requirement",
	"T5": "The tagged tests pass",
	"T6": "The tagged tests run the requirement's code",
	"T7": "The tagged tests fail when the code is broken",
	"T8": "Results reset when the requirement changes",
	"A1": "Every API requirement has an operation",
	"A2": "Every operation references a requirement",
	"A3": "The contract passes the lint rules",
	"A4": "No breaking change unless the spec changed",
	"A5": "The service serves exactly the documented routes",
	"A6": "Responses in the tagged tests match the contract",
	"A7": "The running service conforms to the contract",
	"H1": "Subjects follow Conventional Commits",
	"H2": "Code commits carry a Refs: trailer",
	"H3": "One requirement per code commit",
	"H4": "refactor and chore commits change no status",
	"H5": "Commit size under the limit",
	"H6": "Branch names follow the pattern",
	"H7": "Main is never rewritten",
	"H8": "The agent is named on its commits",
	"H9": "Commits are signed",
}

var lightChecks = map[string]bool{"T2": true, "T3": true, "T4": true, "T5": true, "T6": true, "A1": true,
	"A5": true, "A6": true}

// Status order: the first problem found decides what a requirement shows.
var statusOrder = []string{"Missing", "Gone", "Untested", "Failing", "Unexercised", "Weak", "Contract", "Drift", "Sync"}
var statusByCheck = map[string]string{"T2": "Missing", "T3": "Gone", "T4": "Untested", "T5": "Failing",
	"T6": "Unexercised", "T7": "Weak", "A1": "Contract", "A5": "Contract", "A6": "Contract", "A7": "Contract",
	"T8": "Drift"}

var notes = map[string]string{
	"Missing":     "Exists only in the spec. No commit references it.",
	"Gone":        "A commit claims it, but none of its code exists now.",
	"Untested":    "The code exists, but no test is tagged to it.",
	"Failing":     "Its tests are failing, or the test suite didn't load.",
	"Unexercised": "A tagged test passes, but it never runs this requirement's code.",
	"Weak":        "Its tests run the code but don't catch broken versions of it.",
	"Contract":    "The API doesn't honor its OpenAPI contract for this requirement.",
	"Drift":       "The spec changed after the code that implements it.",
	"Sync":        "Implemented, tested, and matching the contract.",
}

type Result struct {
	Check, Scope, Subject, Verdict, Summary string
	Details                                 *OMap
}

type pathLines struct {
	Path  string
	Lines []int
}

type Options struct {
	Head       string
	Base       string
	Skip, Only []string
	Light      bool
	Workdir    string
	HeadBranch string
	Cfg        *OMap
}

type Engine struct {
	Repo, Head, BaseRef, Base, MergeBase string
	light                                bool
	wanted                               map[string]bool
	Workdir, HeadBranch                  string
	Cfg                                  *OMap
	Results                              []*Result

	reqs        []*Requirement
	activeIDs   []string
	active      map[string]*Requirement
	contract    any
	ops         []*Operation
	history     []*Commit
	rng         []*Commit
	codePaths   []string
	testPaths   []string
	codeExclude []string
	linkedCode  map[string][]*Commit
	linkedAny   map[string][]*Commit
	suite       *SuiteRun
	importOnly  LineSet
	capturePath string
	lines       map[string][]pathLines
	surviving   map[string]map[string]int
	ownersCache map[string]map[string][]int
	tagged      map[string][]*TestCase
	hist        []SpecVersion
	histLoaded  bool
	svcState    int // 0 not started, 1 running, -1 failed or none
	svcCmd      *exec.Cmd
	svcPort     int
	svcLog      *os.File
	svcExited   chan struct{}
}

func NewEngine(repo string, o Options) (*Engine, error) {
	if o.Head == "" {
		o.Head = "HEAD"
	}
	e := &Engine{Repo: absPath(repo), light: o.Light}
	if real, err := filepath.EvalSymlinks(e.Repo); err == nil {
		e.Repo = real
	}
	e.Head = rev(e.Repo, o.Head)
	if e.Head != rev(e.Repo, "HEAD") {
		return nil, fmt.Errorf("check out the head commit first: tests run against the working tree")
	}
	e.BaseRef = o.Base
	if o.Base != "" {
		e.Base = rev(e.Repo, o.Base)
		e.MergeBase = strip(git(e.Repo, "merge-base", e.Base, e.Head))
	}
	e.wanted = map[string]bool{}
	if len(o.Only) > 0 {
		for _, c := range o.Only {
			e.wanted[c] = true
		}
	} else {
		for _, c := range CheckIDs {
			e.wanted[c] = true
		}
	}
	if o.Light {
		for c := range e.wanted {
			if !lightChecks[c] {
				delete(e.wanted, c)
			}
		}
	}
	for _, c := range o.Skip {
		delete(e.wanted, c)
	}
	if o.Workdir == "" {
		d, err := os.MkdirTemp("", "aqv-")
		if err != nil {
			return nil, err
		}
		o.Workdir = d
	}
	e.Workdir = absPath(o.Workdir)
	if err := os.MkdirAll(e.Workdir, 0o755); err != nil {
		return nil, err
	}
	e.HeadBranch = o.HeadBranch
	if e.HeadBranch == "" {
		e.HeadBranch = strip(git(e.Repo, "rev-parse", "--abbrev-ref", "HEAD"))
	}
	// Config comes from the base when there is one, so a PR can't loosen its own checks.
	if o.Cfg != nil {
		e.Cfg = o.Cfg
	} else {
		src := e.Base
		if src == "" {
			src = e.Head
		}
		text, _ := show(e.Repo, src, ".aqv.yml")
		cfg, err := LoadConfig(text)
		if err != nil {
			return nil, fmt.Errorf("can't read .aqv.yml: %w", err)
		}
		e.Cfg = cfg
	}
	return e, nil
}

// ------------------------------------------------------------------ helpers

func (e *Engine) add(check, scope, subject, verdict, summary string, details *OMap) {
	if !e.wanted[check] {
		return
	}
	if details == nil {
		details = NewOMap()
	}
	e.Results = append(e.Results, &Result{check, scope, subject, verdict, summary, details})
}

func (e *Engine) want(checks ...string) bool {
	for _, c := range checks {
		if e.wanted[c] {
			return true
		}
	}
	return false
}

func (e *Engine) rangeArgs() []string {
	if e.Base != "" {
		return []string{e.Base + ".." + e.Head}
	}
	return []string{e.Head}
}

func (e *Engine) commentPrefixes() []string {
	r := e.Cfg.Map("runner")
	if !r.Has("comment_prefix") {
		return []string{"#"}
	}
	return strList(r.Get("comment_prefix"))
}

func (e *Engine) isCode(path string) bool {
	return under(path, e.codePaths) && !under(path, e.codeExclude)
}

func (e *Engine) touchesCode(c *Commit) bool {
	for _, f := range c.Files {
		if e.isCode(f) {
			return true
		}
	}
	return false
}

func (e *Engine) touchesCodeOrTests(c *Commit) bool {
	for _, f := range c.Files {
		if e.isCode(f) || under(f, e.testPaths) {
			return true
		}
	}
	return false
}

func (e *Engine) gitCfg() *OMap { return e.Cfg.Map("git") }

// ------------------------------------------------------------------ load

func (e *Engine) load() {
	c := e.Cfg
	specs := strList(c.Get("specs"))
	e.reqs = specAt(e.Repo, e.Head, specs)
	e.active = map[string]*Requirement{}
	for _, r := range e.reqs {
		if _, ok := e.active[r.ID]; !r.Retired() && !ok {
			e.active[r.ID] = r
			e.activeIDs = append(e.activeIDs, r.ID)
		}
	}
	text, ok := show(e.Repo, e.Head, c.Str("contract"))
	e.contract = nil
	if ok && text != "" {
		doc, err := loadYAML(text)
		if err != nil {
			panic(fmt.Errorf("can't parse the contract: %w", err))
		}
		e.contract = doc
	}
	e.ops = operations(e.contract)
	trailer := e.gitCfg().Str("agent_trailer")
	e.history = commits(e.Repo, []string{e.Head}, trailer)
	e.rng = commits(e.Repo, e.rangeArgs(), trailer)
	e.codePaths, e.testPaths = strList(c.Get("code_paths")), strList(c.Get("test_paths"))
	e.codeExclude = strList(c.Get("code_exclude"))
	e.linkedCode, e.linkedAny = map[string][]*Commit{}, map[string][]*Commit{}
	for _, cm := range e.history {
		if cm.IsMerge() {
			continue
		}
		for _, rid := range cm.Refs {
			if e.touchesCode(cm) {
				e.linkedCode[rid] = append(e.linkedCode[rid], cm)
			}
			if e.touchesCodeOrTests(cm) {
				e.linkedAny[rid] = append(e.linkedAny[rid], cm)
			}
		}
	}
}

// ------------------------------------------------------------------ run

func (e *Engine) Run() *OMap {
	e.load()
	if e.want("T1") {
		e.checkT1()
	}
	if e.want("T4", "T5", "T6", "T7", "A6") {
		e.runSuite()
	}
	e.lines, e.surviving, e.ownersCache = map[string][]pathLines{}, map[string]map[string]int{},
		map[string]map[string][]int{}
	for _, rid := range e.activeIDs {
		e.checkRequirement(rid, e.active[rid])
	}
	if e.want("T8") {
		e.checkT8()
	}
	func() {
		defer e.stopService(nil)
		e.checkContract()
	}()
	e.checkHistory()
	return e.report()
}

func (e *Engine) captureEnabled() bool { return e.Cfg.Map("api").Truthy("capture") }

func (e *Engine) runSuite() {
	extra, env := "", map[string]string{}
	e.capturePath = filepath.Join(e.Workdir, "capture.jsonl")
	os.Remove(e.capturePath)
	if e.captureEnabled() {
		api := e.Cfg.Map("api")
		extra = fill(api.Str("capture_extra"))
		if api.Str("capture") == "pytest-testclient" {
			extra = "-p aqv.pytest_capture"
		}
		env["AQV_CAPTURE_OUT"] = e.capturePath
	}
	e.suite = fullSuite(e.Cfg, e.Repo, e.Workdir, extra, env)
	e.importOnly = nil
}

func (e *Engine) importLines() LineSet {
	if e.importOnly == nil {
		e.importOnly, _ = coveredLines(e.Cfg, e.Repo, e.Cfg.Map("runner").Str("select_nothing"), e.Workdir, "import-only")
	}
	return e.importOnly
}

// ------------------------------------------------------------------ T1

func (e *Engine) checkT1() {
	c := e.Cfg
	var problems []string
	regText, _ := show(e.Repo, e.Head, c.Str("ids_registry"))
	registry := map[string]bool{}
	for _, id := range fields(regText) {
		registry[id] = true
	}
	seen := map[string]string{}
	for _, r := range e.reqs {
		if !idFormat.MatchString(r.ID) {
			problems = append(problems, r.ID+": ID doesn't match AC-<area>-<nnn>")
		}
		if where, ok := seen[r.ID]; ok {
			problems = append(problems, fmt.Sprintf("%s: used twice (%s and %s:%d)", r.ID, where, r.Spec, r.Line))
		} else {
			seen[r.ID] = fmt.Sprintf("%s:%d", r.Spec, r.Line)
		}
		if !registry[r.ID] {
			problems = append(problems, fmt.Sprintf("%s: not in the ID registry %s", r.ID, c.Str("ids_registry")))
		}
		for _, te := range r.TagErrors {
			problems = append(problems, r.ID+": "+te)
		}
	}
	log := git(e.Repo, "log", "-p", "--format=", e.Head, "--", c.Str("ids_registry"))
	for _, line := range splitlines(log) {
		if strings.HasPrefix(line, "-") && !strings.HasPrefix(line, "---") && strip(line[1:]) != "" {
			problems = append(problems, strip(line[1:])+": removed from the ID registry (IDs are never removed)")
		}
	}
	ever := map[string]*Requirement{}
	var everOrder []string
	for _, v := range specHistory(e.Repo, e.Head, strList(c.Get("specs"))) {
		ids := make([]string, 0, len(v.Reqs))
		for id := range v.Reqs {
			ids = append(ids, id)
		}
		for _, rid := range ids {
			r := v.Reqs[rid]
			if prev, ok := ever[rid]; ok && prev.Retired() && !r.Retired() {
				problems = append(problems, rid+": reused after it was retired")
			}
			if _, ok := ever[rid]; !ok {
				everOrder = append(everOrder, rid)
			}
			ever[rid] = r
		}
	}
	current := map[string]bool{}
	for _, r := range e.reqs {
		current[r.ID] = true
	}
	for _, rid := range everOrder {
		if !current[rid] {
			problems = append(problems, rid+": deleted from the spec instead of marked (retired)")
		}
	}
	problems = uniqSorted(problems)
	if len(problems) > 0 {
		shown := problems
		if len(shown) > 4 {
			shown = shown[:4]
		}
		e.add("T1", "project", "spec", "fail", fmt.Sprintf("%d ID problem(s): %s", len(problems), strings.Join(shown, "; ")),
			om("problems", problems))
	} else {
		e.add("T1", "project", "spec", "pass", fmt.Sprintf("%d requirement IDs valid and registered", len(e.reqs)), nil)
	}
}

// ------------------------------------------------------------------ T2–T7, per requirement

func shortList(cs []*Commit) string {
	s := make([]string, len(cs))
	for i, c := range cs {
		s[i] = c.Short()
	}
	return strings.Join(s, ", ")
}

func linesTree(ls []pathLines) *OMap {
	o := NewOMap()
	for _, pl := range ls {
		o.Set(pl.Path, pl.Lines)
	}
	return o
}

func (e *Engine) checkRequirement(rid string, req *Requirement) {
	codeCommits := e.linkedCode[rid]
	if len(codeCommits) > 0 {
		e.add("T2", "requirement", rid, "pass", fmt.Sprintf("%d commit(s) reference it: %s", len(codeCommits),
			shortList(codeCommits)), nil)
	} else {
		e.add("T2", "requirement", rid, "fail", "No commit that changes code references it", nil)
	}

	var linked []pathLines
	if len(codeCommits) > 0 {
		shas := map[string]bool{}
		for _, cm := range codeCommits {
			shas[cm.SHA] = true
		}
		surviving := map[string]int{}
		for sha := range shas {
			surviving[sha] = 0
		}
		for _, path := range filesAt(e.Repo, e.Head) {
			if path == "" || !e.isCode(path) {
				continue
			}
			owners, ok := e.ownersCache[path]
			if !ok {
				owners, _ = blameOwners(e.Repo, path, e.Head, e.commentPrefixes())
				e.ownersCache[path] = owners
			}
			for sha := range shas {
				surviving[sha] += len(owners[sha])
			}
			var ls []int
			for sha, l := range owners {
				if shas[sha] {
					ls = append(ls, l...)
				}
			}
			sort.Ints(ls)
			if len(ls) > 0 {
				linked = append(linked, pathLines{path, ls})
			}
		}
		e.surviving[rid] = surviving
		n := 0
		for _, pl := range linked {
			n += len(pl.Lines)
		}
		if n > 0 {
			e.add("T3", "requirement", rid, "pass", fmt.Sprintf("%d line(s) from its commits still exist", n),
				om("lines", linesTree(linked)))
		} else {
			e.add("T3", "requirement", rid, "fail", "Its commits are referenced, but none of their code lines exist now", nil)
		}
	} else {
		e.add("T3", "requirement", rid, "skip", "No linked commits", nil)
	}
	e.lines[rid] = linked

	if e.suite == nil {
		return
	}
	if e.tagged == nil {
		e.tagged = map[string][]*TestCase{}
	}
	var tagged []*TestCase
	for _, tc := range e.suite.Cases {
		if mentions(tc.Name, rid) {
			tagged = append(tagged, tc)
		}
	}
	if e.suite.Broken {
		msg := "The test suite failed to load: " + e.suite.BrokenReason
		e.add("T4", "requirement", rid, "error", msg, nil)
		e.add("T5", "requirement", rid, "error", msg, nil)
		for _, chk := range []string{"T6", "T7"} {
			e.add(chk, "requirement", rid, "skip", "Test suite failed to load", nil)
		}
		e.tagged[rid] = nil
		return
	}
	e.tagged[rid] = tagged
	if len(tagged) == 0 {
		e.add("T4", "requirement", rid, "fail", "No test name mentions it", nil)
		for _, chk := range []string{"T5", "T6", "T7"} {
			e.add(chk, "requirement", rid, "skip", "No tagged tests", nil)
		}
		return
	}
	names := make([]string, len(tagged))
	for i, tc := range tagged {
		names[i] = tc.FullName()
	}
	e.add("T4", "requirement", rid, "pass", fmt.Sprintf("%d tagged test(s)", len(tagged)), om("tests", names))
	var bad []*TestCase
	for _, tc := range tagged {
		if tc.Outcome != "pass" {
			bad = append(bad, tc)
		}
	}
	if len(bad) > 0 {
		var shown []string
		var failing []any
		for i, tc := range bad {
			if i < 3 {
				shown = append(shown, tc.Name)
			}
			failing = append(failing, om("test", tc.FullName(), "outcome", tc.Outcome, "message", head(tc.Message, 300)))
		}
		e.add("T5", "requirement", rid, "fail", fmt.Sprintf("%d of %d tagged test(s) don't pass: %s", len(bad), len(tagged),
			strings.Join(shown, ", ")), om("failing", failing))
	} else {
		e.add("T5", "requirement", rid, "pass", fmt.Sprintf("All %d tagged test(s) pass", len(tagged)), nil)
	}

	if !e.want("T6", "T7") {
		return
	}
	nLinked := 0
	for _, pl := range linked {
		nLinked += len(pl.Lines)
	}
	if nLinked == 0 {
		e.add("T6", "requirement", rid, "skip", "No linked code lines", nil)
		e.add("T7", "requirement", rid, "skip", "No linked code lines", nil)
		return
	}
	hits, _ := coveredLines(e.Cfg, e.Repo, filterFor(e.Cfg, rid), e.Workdir, idToken(rid))
	baseHits := e.importLines()
	var executed []pathLines
	for _, pl := range linked {
		var ex []int
		for _, l := range uniqInts(pl.Lines) {
			if hits[pl.Path][l] && !baseHits[pl.Path][l] {
				ex = append(ex, l)
			}
		}
		if len(ex) > 0 {
			executed = append(executed, pathLines{pl.Path, ex})
		}
	}
	nEx := 0
	for _, pl := range executed {
		nEx += len(pl.Lines)
	}
	if nEx > 0 {
		e.add("T6", "requirement", rid, "pass", fmt.Sprintf("Its tests run %d of its %d code line(s)", nEx, nLinked),
			om("executed", linesTree(executed)))
	} else {
		e.add("T6", "requirement", rid, "fail",
			fmt.Sprintf("Its tests run none of its %d code line(s) (import-time lines don't count)", nLinked), nil)
	}
	if e.want("T7") && nEx > 0 && e.inMutationScope(rid) {
		e.checkT7(rid, executed)
	} else if e.want("T7") {
		msg := "No executed lines to mutate"
		if nEx > 0 {
			msg = "Not changed in this range"
		}
		e.add("T7", "requirement", rid, "skip", msg, nil)
	}
}

func uniqInts(xs []int) []int {
	seen := map[int]bool{}
	var out []int
	for _, x := range xs {
		if !seen[x] {
			seen[x] = true
			out = append(out, x)
		}
	}
	sort.Ints(out)
	return out
}

func (e *Engine) inMutationScope(rid string) bool {
	if e.Base == "" {
		return true
	}
	for _, cm := range e.rng {
		if !cm.IsMerge() && contains(cm.Refs, rid) {
			return true
		}
	}
	return false
}

// checkT7 mutates the requirement's executed lines in place, one at a time, restoring each file.
func (e *Engine) checkT7(rid string, executed []pathLines) {
	m := e.Cfg.Map("mutation")
	family := m.Str("family")
	if family == "" {
		cp := e.commentPrefixes()
		family = "c"
		if len(cp) == 1 && cp[0] == "#" {
			family = "python"
		}
	}
	build := m.Str("build")
	env := profileEnv(e.Cfg, e.Repo)
	flt := filterFor(e.Cfg, rid)
	maxMutants, _ := toFloat(m.Get("max_mutants"))
	invalidCodes := intList(m.Get("invalid_exit_codes"))
	tried, killed, invalid := 0, 0, 0
	survivors := []string{}
	sorted := append([]pathLines(nil), executed...)
	sort.Slice(sorted, func(i, j int) bool { return sorted[i].Path < sorted[j].Path })
	for _, pl := range sorted {
		fpath := filepath.Join(e.Repo, pl.Path)
		data, err := os.ReadFile(fpath)
		if err != nil {
			panic(err)
		}
		original := string(data)
		src := splitlinesKeep(original)
		func() {
			defer os.WriteFile(fpath, data, 0o644)
			for _, ln := range pl.Lines {
				if ln-1 >= len(src) {
					continue
				}
				for _, mu := range mutants(src[ln-1], family) {
					if float64(tried) >= maxMutants {
						break
					}
					newLine := mu.Line
					if !strings.HasSuffix(newLine, "\n") {
						newLine += "\n"
					}
					source := strings.Join(src[:ln-1], "") + newLine + strings.Join(src[ln:], "")
					if family == "python" && build == "" && !compilesPython(source) {
						continue
					}
					if err := os.WriteFile(fpath, []byte(source), 0o644); err != nil {
						panic(err)
					}
					if build != "" {
						if code, _ := runShell(fill(build, "file", pl.Path), e.Repo, env, defaultTimeout); code != 0 {
							invalid++
							continue
						}
					}
					code := runSelected(e.Cfg, e.Repo, flt)
					isInvalid := false
					for _, c := range invalidCodes {
						if c == code {
							isInvalid = true
						}
					}
					if isInvalid {
						invalid++ // the runner says it didn't build: not a real mutant
						continue
					}
					tried++
					if code == 0 {
						survivors = append(survivors, fmt.Sprintf("%s:%d %s", pl.Path, ln, mu.Desc))
					} else {
						killed++
					}
				}
			}
		}()
	}
	if build != "" {
		runShell(fill(build, "file", sorted[0].Path), e.Repo, env, defaultTimeout)
	}
	if tried == 0 {
		e.add("T7", "requirement", rid, "skip", "No mutants could be made from its lines", nil)
		return
	}
	ratio := float64(killed) / float64(tried)
	minRatio, _ := toFloat(m.Get("min_kill_ratio"))
	verdict := "fail"
	if ratio >= minRatio {
		verdict = "pass"
	}
	e.add("T7", "requirement", rid, verdict, fmt.Sprintf("Its tests caught %d of %d broken versions (%s; needs %s)",
		killed, tried, percent(ratio), percent(minRatio)), om("survivors", survivors, "uncompilable", invalid))
}

// ------------------------------------------------------------------ T8

func (e *Engine) specHist() []SpecVersion {
	if !e.histLoaded {
		e.hist = specHistory(e.Repo, e.Head, strList(e.Cfg.Get("specs")))
		e.histLoaded = true
	}
	return e.hist
}

func (e *Engine) checkT8() {
	hist := e.specHist()
	for _, rid := range e.activeIDs {
		req := e.active[rid]
		impl := e.linkedAny[rid]
		if len(impl) == 0 {
			e.add("T8", "requirement", rid, "skip", "Not implemented yet", nil)
			continue
		}
		changedAt, before, prev := "", "", ""
		hasBefore, hasPrev := false, false
		for _, v := range hist {
			r, ok := v.Reqs[rid]
			if ok && (!hasPrev || r.Body() != prev) {
				changedAt, before, hasBefore = v.SHA, prev, hasPrev
			}
			if ok {
				prev, hasPrev = r.Body(), true
			} else {
				prev, hasPrev = "", false
			}
		}
		if changedAt == "" {
			e.add("T8", "requirement", rid, "skip", "Requirement not found in spec history", nil)
			continue
		}
		fresh := false
		for _, cm := range impl {
			if isAncestor(e.Repo, changedAt, cm.SHA) {
				fresh = true
				break
			}
		}
		if fresh {
			e.add("T8", "requirement", rid, "pass",
				fmt.Sprintf("Implemented or re-verified after its last wording change (%s)", head(changedAt, 7)), nil)
		} else {
			diff := "new"
			if hasBefore && before != "" {
				diff = wordDiff(before, req.Body())
			}
			e.add("T8", "requirement", rid, "fail",
				fmt.Sprintf("Wording changed in %s (%s) after its last code or test commit", head(changedAt, 7), diff),
				om("changed_in", changedAt, "change", diff))
		}
	}
}

// ------------------------------------------------------------------ A1–A7

func (e *Engine) apiReqs() []string {
	var out []string
	for _, rid := range e.activeIDs {
		if e.active[rid].HasAPI() {
			out = append(out, rid)
		}
	}
	return out
}

func (e *Engine) checkContract() {
	apiReqs := e.apiReqs()
	if e.contract == nil {
		for _, rid := range apiReqs {
			e.add("A1", "requirement", rid, "fail", "No contract file", nil)
		}
		return
	}
	byKey := map[string]*Operation{}
	for _, op := range e.ops {
		byKey[op.Key()] = op
	}
	for _, rid := range e.activeIDs {
		r := e.active[rid]
		if !r.HasAPI() {
			e.add("A1", "requirement", rid, "skip", "Not an API requirement", nil)
			continue
		}
		var problems []string
		for _, mp := range r.APIOps {
			op := byKey[opKey(mp)]
			if op == nil {
				problems = append(problems, opKey(mp)+" is not in the contract")
			} else if !contains(op.Requirements, rid) {
				problems = append(problems, fmt.Sprintf("%s doesn't list %s in x-requirements", opKey(mp), rid))
			}
		}
		if len(problems) > 0 {
			e.add("A1", "requirement", rid, "fail", strings.Join(problems, "; "), nil)
		} else {
			keys := make([]string, len(r.APIOps))
			for i, mp := range r.APIOps {
				keys[i] = opKey(mp)
			}
			e.add("A1", "requirement", rid, "pass", "Contract covers "+strings.Join(keys, ", "), nil)
		}
	}
	for _, op := range e.ops {
		var unknown []string
		for _, x := range op.Requirements {
			if _, ok := e.active[x]; !ok {
				unknown = append(unknown, x)
			}
		}
		switch {
		case len(op.Requirements) == 0:
			e.add("A2", "operation", op.Key(), "fail", op.Key()+" references no requirement", nil)
		case len(unknown) > 0:
			e.add("A2", "operation", op.Key(), "fail",
				fmt.Sprintf("%s references unknown or retired requirement(s): %s", op.Key(), strings.Join(unknown, ", ")), nil)
		default:
			e.add("A2", "operation", op.Key(), "pass", op.Key()+" → "+strings.Join(op.Requirements, ", "), nil)
		}
	}
	if e.want("A3") {
		e.checkA3()
	}
	if e.want("A4") {
		e.checkA4()
	}
	if e.want("A5") {
		e.checkA5(apiReqs)
	}
	if e.want("A6") {
		e.checkA6(apiReqs)
	}
	if e.want("A7") {
		e.checkA7(apiReqs)
	}
}

func tool(name, rel string) string {
	if env := os.Getenv("AQV_" + strings.ToUpper(name)); env != "" {
		return env
	}
	p := filepath.Clean(filepath.Join(Home(), ".tools", rel))
	if exists(p) {
		return p
	}
	if w, err := exec.LookPath(name); err == nil {
		return w
	}
	return ""
}

func runArgs(cwd string, timeout time.Duration, args ...string) (int, string, string) {
	c := exec.Command(args[0], args[1:]...)
	c.Dir = cwd
	var out, errb strings.Builder
	c.Stdout, c.Stderr = &out, &errb
	if err := c.Start(); err != nil {
		return 127, "", err.Error()
	}
	done := make(chan error, 1)
	go func() { done <- c.Wait() }()
	var err error
	select {
	case err = <-done:
	case <-time.After(timeout):
		c.Process.Kill()
		<-done
		return 124, univNL(out.String()), "timed out"
	}
	code := 0
	if err != nil {
		code = 1
		if ee, ok := err.(*exec.ExitError); ok {
			code = ee.ExitCode()
		}
	}
	return code, univNL(out.String()), univNL(errb.String())
}

func (e *Engine) checkA3() {
	spectral := tool("spectral", "node_modules/.bin/spectral")
	if spectral == "" {
		e.add("A3", "project", "contract", "not_covered", "Spectral is not installed", nil)
		return
	}
	ruleset := filepath.Join(e.Repo, ".spectral.yaml")
	args := []string{spectral, "lint", e.Cfg.Str("contract"), "-f", "json", "--fail-severity", "error", "--quiet"}
	if exists(ruleset) {
		args = append(args, "--ruleset", ruleset)
	}
	_, stdout, stderr := runArgs(e.Repo, 3600*time.Second, args...)
	text := stdout
	if text == "" {
		text = "[]"
	}
	found, err := loadJSON([]byte(text))
	if err != nil {
		msg := stderr
		if msg == "" {
			msg = stdout
		}
		e.add("A3", "project", "contract", "error", "Spectral failed: "+head(msg, 300), nil)
		return
	}
	var errs []string
	list, _ := found.([]any)
	for _, f := range list {
		fm, _ := f.(*OMap)
		if sev, ok := toNum(fm.Get("severity")); !ok || sev != 0 {
			continue
		}
		var path []string
		for _, p := range asList(fm.Get("path")) {
			path = append(path, pyStr(p))
		}
		errs = append(errs, fmt.Sprintf("%s: %s (%s)", strings.Join(path, "."), pyStr(fm.Get("message")), pyStr(fm.Get("code"))))
	}
	if len(errs) > 0 {
		shown := errs
		if len(shown) > 3 {
			shown = shown[:3]
		}
		e.add("A3", "project", "contract", "fail", fmt.Sprintf("%d lint error(s): %s", len(errs), strings.Join(shown, "; ")),
			om("errors", errs))
	} else {
		e.add("A3", "project", "contract", "pass", "Contract passes the lint rules", nil)
	}
}

func asList(v any) []any {
	l, _ := v.([]any)
	return l
}

func (e *Engine) checkA4() {
	if e.Base == "" {
		e.add("A4", "project", "contract", "skip", "No base to compare against", nil)
		return
	}
	oasdiff := tool("oasdiff", "bin/oasdiff")
	if oasdiff == "" {
		e.add("A4", "project", "contract", "not_covered", "oasdiff is not installed", nil)
		return
	}
	old, ok := show(e.Repo, e.MergeBase, e.Cfg.Str("contract"))
	if !ok {
		e.add("A4", "project", "contract", "skip", "No contract at the base", nil)
		return
	}
	baseFile := filepath.Join(e.Workdir, "contract-base.yaml")
	os.WriteFile(baseFile, []byte(old), 0o644)
	headFile := filepath.Join(e.Repo, e.Cfg.Str("contract"))
	cwd, _ := os.Getwd()
	code, stdout, _ := runArgs(cwd, 3600*time.Second, oasdiff, "breaking", baseFile, headFile, "--fail-on", "ERR",
		"--format", "text")
	if code == 0 {
		e.add("A4", "project", "contract", "pass", "No breaking API change", nil)
		return
	}
	var changes []string
	for _, l := range splitlines(stdout) {
		if strip(l) != "" {
			changes = append(changes, strip(l))
		}
	}
	oldReqs := map[string]string{}
	for _, x := range specAt(e.Repo, e.MergeBase, strList(e.Cfg.Get("specs"))) {
		oldReqs[x.ID] = x.Hash()
	}
	var changed []string
	for _, rid := range e.activeIDs {
		if h, ok := oldReqs[rid]; !ok || h != e.active[rid].Hash() {
			changed = append(changed, rid)
		}
	}
	if len(changed) > 0 {
		e.add("A4", "project", "contract", "pass",
			fmt.Sprintf("Breaking change allowed: requirement(s) %s changed in the same range", strings.Join(changed, ", ")),
			om("changes", changes))
	} else {
		shown := changes
		if len(shown) > 3 {
			shown = shown[:3]
		}
		e.add("A4", "project", "contract", "fail", "Breaking API change with no requirement change: "+strings.Join(shown, "; "),
			om("changes", changes))
	}
}

// The running service, started once and shared by A5 (route listing by URL) and A7.

func (e *Engine) startService() bool {
	if e.svcState != 0 {
		return e.svcState == 1
	}
	api := e.Cfg.Map("api")
	serve := api.Str("serve")
	if serve == "" {
		e.svcState = -1
		return false
	}
	l, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		e.svcState = -1
		return false
	}
	port := l.Addr().(*net.TCPAddr).Port
	l.Close()
	set := map[string]string{"PYTHONPATH": filepath.Join(e.Repo, "src"), "PORT": fmt.Sprint(port)}
	for k, v := range profileEnv(e.Cfg, e.Repo) {
		set[k] = v
	}
	log, _ := os.Create(filepath.Join(e.Workdir, "service.log"))
	e.svcLog = log
	cmd := exec.Command("/bin/sh", "-c", fill(serve, "port", fmt.Sprint(port)))
	cmd.Dir, cmd.Env = e.Repo, mergeEnv(os.Environ(), set)
	cmd.Stdout, cmd.Stderr = log, log
	cmd.SysProcAttr = &syscall.SysProcAttr{Setsid: true}
	if err := cmd.Start(); err != nil {
		e.svcState = -1
		return false
	}
	exited := make(chan struct{})
	go func() { cmd.Wait(); close(exited) }()
	timeout := 60.0
	if f, ok := toFloat(api.Get("serve_timeout")); ok {
		timeout = f
	}
	deadline := time.Now().Add(time.Duration(timeout * float64(time.Second)))
	for time.Now().Before(deadline) {
		select {
		case <-exited:
			e.killService(cmd, exited)
			e.svcState = -1
			return false
		default:
		}
		conn, err := net.DialTimeout("tcp", fmt.Sprintf("127.0.0.1:%d", port), 200*time.Millisecond)
		if err == nil {
			conn.Close()
			e.svcCmd, e.svcPort, e.svcState = cmd, port, 1
			e.svcExited = exited
			return true
		}
		time.Sleep(200 * time.Millisecond)
	}
	e.killService(cmd, exited)
	e.svcState = -1
	return false
}

func (e *Engine) killService(cmd *exec.Cmd, exited chan struct{}) {
	if cmd == nil || cmd.Process == nil {
		return
	}
	_ = syscall.Kill(-cmd.Process.Pid, syscall.SIGTERM)
	select {
	case <-exited:
	case <-time.After(20 * time.Second):
		_ = syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL)
		<-exited
	}
}

func (e *Engine) stopService(_ any) {
	if e.svcState == 1 && e.svcCmd != nil {
		e.killService(e.svcCmd, e.svcExited)
	}
	if e.svcLog != nil {
		e.svcLog.Close()
	}
}

// servedRoutes lists the routes the service actually serves, or why it can't.
func (e *Engine) servedRoutes() (map[string]bool, string) {
	api := e.Cfg.Map("api")
	if cmd := firstNonEmpty(api.Str("openapi_from_code"), api.Str("routes_from_code")); cmd != "" {
		_, out := runShell(fill(cmd), e.Repo, profileEnv(e.Cfg, e.Repo), defaultTimeout)
		line := ""
		ls := splitlines(strip(out))
		for i := len(ls) - 1; i >= 0; i-- {
			if t := strip(ls[i]); strings.HasPrefix(t, "{") || strings.HasPrefix(t, "[") {
				line = ls[i]
				break
			}
		}
		doc, err := loadJSON([]byte(line))
		if err != nil || line == "" {
			return nil, "couldn't read routes from the code: " + tail(out, 300)
		}
		return parseRoutes(doc), ""
	}
	if url := api.Str("openapi_url"); url != "" {
		if !e.startService() {
			return nil, "the service didn't start"
		}
		client := http.Client{Timeout: 30 * time.Second}
		resp, err := client.Get(fmt.Sprintf("http://127.0.0.1:%d%s", e.svcPort, url))
		if err != nil {
			return nil, fmt.Sprintf("couldn't fetch %s: %v", url, err)
		}
		defer resp.Body.Close()
		data, _ := io.ReadAll(resp.Body)
		if resp.StatusCode >= 400 {
			return nil, fmt.Sprintf("couldn't fetch %s: HTTP Error %d: %s", url, resp.StatusCode,
				http.StatusText(resp.StatusCode))
		}
		doc, err := loadJSON(data)
		if err != nil {
			return nil, fmt.Sprintf("couldn't fetch %s: %v", url, err)
		}
		return parseRoutes(doc), ""
	}
	if conf := api.Map("routes_scan"); conf != nil {
		return scanRoutes(e.Repo, conf), ""
	}
	return nil, "no way to list the service's routes for this stack"
}

func firstNonEmpty(xs ...string) string {
	for _, x := range xs {
		if x != "" {
			return x
		}
	}
	return ""
}

func (e *Engine) checkA5(apiReqs []string) {
	served, why := e.servedRoutes()
	if served == nil {
		verdict := "error"
		if strings.HasPrefix(why, "no way") {
			verdict = "not_covered"
		}
		e.add("A5", "project", "routes", verdict, upperFirst(why), nil)
		return
	}
	documented := map[string]bool{}
	for _, op := range e.ops {
		documented[op.Key()] = true
	}
	servedN := map[string]string{}
	for _, k := range sortedKeys(served) {
		servedN[normalizeRoute(k)] = k
	}
	documentedN := map[string]bool{}
	for k := range documented {
		documentedN[normalizeRoute(k)] = true
	}
	for _, key := range sortedKeys(servedN) {
		if !documentedN[key] {
			e.add("A5", "operation", servedN[key], "fail", servedN[key]+" is served but not in the contract", nil)
		}
	}
	for _, rid := range apiReqs {
		var missing []string
		for _, mp := range e.active[rid].APIOps {
			k := opKey(mp)
			if _, ok := servedN[normalizeRoute(k)]; documented[k] && !ok {
				missing = append(missing, k)
			}
		}
		if len(missing) > 0 {
			e.add("A5", "requirement", rid, "fail", "Documented but not served: "+strings.Join(missing, ", "), nil)
		} else {
			e.add("A5", "requirement", rid, "pass", "Its operations are served", nil)
		}
	}
}

func (e *Engine) readCapture() []*OMap {
	var calls []*OMap
	data, err := os.ReadFile(e.capturePath)
	if err != nil {
		return calls
	}
	text := strip(string(data))
	if strings.HasPrefix(text, "[") {
		v, err := loadJSON([]byte(text))
		if err != nil {
			panic(fmt.Errorf("unreadable capture file: %w", err))
		}
		for _, x := range asList(v) {
			if m, ok := x.(*OMap); ok {
				calls = append(calls, m)
			}
		}
		return calls
	}
	for _, line := range splitlines(text) {
		line = strip(line)
		if line == "" {
			continue
		}
		if v, err := loadJSON([]byte(line)); err == nil {
			if m, ok := v.(*OMap); ok {
				calls = append(calls, m)
			}
		}
	}
	return calls
}

func (e *Engine) checkA6(apiReqs []string) {
	if !e.captureEnabled() {
		for _, rid := range apiReqs {
			e.add("A6", "requirement", rid, "not_covered", "No test-traffic adapter for this framework", nil)
		}
		return
	}
	if e.suite == nil || e.suite.Broken {
		for _, rid := range apiReqs {
			e.add("A6", "requirement", rid, "skip", "Test suite didn't run", nil)
		}
		return
	}
	calls := e.readCapture()
	for _, rid := range apiReqs {
		r := e.active[rid]
		var mine []*OMap
		for _, c := range calls {
			test := ""
			if c.Has("test") {
				test = pyStr(c.Get("test"))
			}
			if mentions(test, rid) {
				mine = append(mine, c)
			}
		}
		ownOps := map[string]bool{}
		for _, mp := range r.APIOps {
			ownOps[opKey(mp)] = true
		}
		var problems []string
		hit := map[string]bool{}
		for _, c := range mine {
			path := strings.SplitN(pyStr(c.Get("path")), "?", 2)[0]
			method := pyStr(c.Get("method"))
			op := findOp(e.ops, method, path)
			if op == nil {
				problems = append(problems, fmt.Sprintf("%s called %s %s, which the contract doesn't have",
					pyStr(c.Get("test")), method, path))
				continue
			}
			hit[op.Key()] = true
			body := c.Get("body")
			if s, ok := body.(string); ok {
				if v, err := loadJSON([]byte(s)); err == nil {
					body = v
				}
			}
			for _, p := range checkResponse(e.contract, op, c.Get("status"), body) {
				problems = append(problems, pyStr(c.Get("test"))+": "+p)
			}
		}
		problems = uniqSorted(problems)
		overlap := false
		for k := range ownOps {
			if hit[k] {
				overlap = true
			}
		}
		switch {
		case len(problems) > 0:
			shown := problems
			if len(shown) > 3 {
				shown = shown[:3]
			}
			e.add("A6", "requirement", rid, "fail", strings.Join(shown, "; "), om("violations", problems))
		case !overlap:
			e.add("A6", "requirement", rid, "fail", "No tagged test calls "+strings.Join(sortedKeys(ownOps), ", "), nil)
		default:
			e.add("A6", "requirement", rid, "pass", fmt.Sprintf("%d call(s) from tagged tests match the contract", len(mine)), nil)
		}
	}
}

func (e *Engine) checkA7(apiReqs []string) {
	st := tool("schemathesis", "../.venv/bin/schemathesis")
	if e.Cfg.Map("api").Str("serve") == "" || st == "" {
		e.add("A7", "project", "service", "not_covered", "No way to start the service or Schemathesis missing", nil)
		return
	}
	if !e.startService() {
		logText, _ := os.ReadFile(filepath.Join(e.Workdir, "service.log"))
		e.add("A7", "project", "service", "error", "The service didn't start: "+tail(string(logText), 300), nil)
		return
	}
	junit := filepath.Join(e.Workdir, "schemathesis.xml")
	code, stdout, stderr := runArgs(e.Workdir, 600*time.Second, st, "run", filepath.Join(e.Repo, e.Cfg.Str("contract")),
		"--url", fmt.Sprintf("http://127.0.0.1:%d", e.svcPort),
		"--mode", "positive", "--seed", "1", "--max-examples", "30", "--workers", "1",
		"--checks", "not_a_server_error,status_code_conformance,response_schema_conformance",
		"--report", "junit", "--report-junit-path", junit, "--no-shrink", "--warnings", "off")
	failed := NewOMap()
	if exists(junit) {
		root, err := parseXML(junit)
		if err != nil {
			panic(fmt.Errorf("unreadable Schemathesis report: %w", err))
		}
		root.iter("testcase", func(tc *xmlElem) {
			f := tc.find("failure")
			if f == nil {
				f = tc.find("error")
			}
			if f != nil {
				failed.Set(tc.Attr["name"], head(strip(f.Attr["message"]+" "+f.Text), 400))
			}
		})
	} else if code != 0 {
		e.add("A7", "project", "service", "error", "Schemathesis didn't run: "+tail(stdout+stderr, 300), nil)
		return
	}
	bad := NewOMap()
	for _, op := range e.ops {
		for _, name := range failed.Keys() {
			if strings.HasPrefix(name, op.Key()) || name == op.Key() {
				bad.Set(op.Key(), failed.Get(name))
			}
		}
	}
	for _, op := range e.ops {
		if bad.Has(op.Key()) {
			msg := bad.Str(op.Key())
			e.add("A7", "operation", op.Key(), "fail", fmt.Sprintf("%s failed generated requests: %s", op.Key(), firstLine(msg)),
				om("output", msg))
		}
	}
	for _, rid := range apiReqs {
		var failing []string
		for _, mp := range e.active[rid].APIOps {
			if bad.Has(opKey(mp)) {
				failing = append(failing, opKey(mp))
			}
		}
		if len(failing) > 0 {
			e.add("A7", "requirement", rid, "fail", "Generated requests failed on "+strings.Join(failing, ", "), nil)
		} else {
			e.add("A7", "requirement", rid, "pass", "Generated requests got documented responses", nil)
		}
	}
}

func firstLine(text string) string {
	for _, l := range splitlines(text) {
		if strip(l) != "" {
			return head(strip(l), 200)
		}
	}
	return ""
}

// ------------------------------------------------------------------ H1–H9

var conventionalRx = regexp.MustCompile(conventional)
var mergeBranchRx = regexp.MustCompile(`^Merge branch '([^']+)'`)

func commitType(subject string) string {
	t := strings.SplitN(subject, "(", 2)[0]
	t = strings.SplitN(t, ":", 2)[0]
	return strings.TrimRight(t, "!")
}

func pyMatch(pattern, s string) bool {
	rx, err := regexp2.Compile(`\A(?:`+pattern+`)`, regexp2.None)
	if err != nil {
		panic(fmt.Errorf("bad pattern %q: %w", pattern, err))
	}
	m, _ := rx.MatchString(s)
	return m
}

func (e *Engine) checkHistory() {
	g := e.gitCfg()
	var plain, code []*Commit
	for _, cm := range e.rng {
		if !cm.IsMerge() {
			plain = append(plain, cm)
			if e.touchesCode(cm) {
				code = append(code, cm)
			}
		}
	}
	verdict := func(check string, offenders []string, ok, bad string) {
		if len(offenders) > 0 {
			shown := offenders
			if len(shown) > 4 {
				shown = shown[:4]
			}
			e.add(check, "project", "history", "fail", bad+": "+strings.Join(shown, "; "), om("offenders", offenders))
		} else {
			e.add(check, "project", "history", "pass", ok, nil)
		}
	}
	if e.want("H1") {
		var off []string
		for _, cm := range plain {
			if !conventionalRx.MatchString(cm.Subject) {
				off = append(off, fmt.Sprintf("%s '%s'", cm.Short(), cm.Subject))
			}
		}
		verdict("H1", off, fmt.Sprintf("%d commit subject(s) follow Conventional Commits", len(plain)), "Not Conventional Commits")
	}
	if e.want("H2") {
		var off []string
		for _, cm := range code {
			ctype := commitType(cm.Subject)
			if len(cm.Refs) == 0 {
				off = append(off, cm.Short()+" has no Refs: trailer")
			} else if len(cm.Refs) == 1 && cm.Refs[0] == "none" && contains(noBehaviorTypes, ctype) {
				continue
			} else {
				var bad []string
				for _, x := range cm.Refs {
					if _, ok := e.active[x]; !ok {
						bad = append(bad, x)
					}
				}
				if len(bad) > 0 {
					off = append(off, fmt.Sprintf("%s refers to unknown requirement(s) %s", cm.Short(), strings.Join(bad, ", ")))
				}
			}
		}
		verdict("H2", off, fmt.Sprintf("%d code commit(s) reference a requirement", len(code)), "Missing or bad Refs")
	}
	if e.want("H3") {
		var off []string
		for _, cm := range code {
			if len(cm.Refs) > 1 {
				off = append(off, fmt.Sprintf("%s cites %s", cm.Short(), strings.Join(cm.Refs, ", ")))
			}
		}
		verdict("H3", off, "Each code commit serves one requirement", "Several requirements in one commit")
	}
	if e.want("H4") {
		e.checkH4(plain)
	}
	if e.want("H5") {
		limit, _ := toFloat(g.Get("max_commit_lines"))
		limitS := pyStr(g.Get("max_commit_lines"))
		exclude := strList(g.Get("size_exclude"))
		var off []string
		for _, cm := range plain {
			n := 0
			for _, ns := range cm.Numstat {
				skip := false
				for _, pat := range exclude {
					if fnmatch(ns.Path, pat) {
						skip = true
					}
				}
				if !skip {
					n += ns.Added + ns.Deleted
				}
			}
			if float64(n) > limit {
				off = append(off, fmt.Sprintf("%s changes %d lines", cm.Short(), n))
			}
		}
		verdict("H5", off, "Every commit changes at most "+limitS+" lines", "Commits over "+limitS+" lines")
	}
	if e.want("H6") {
		var names []string
		if e.Base != "" && e.Base != e.Head {
			names = append(names, e.HeadBranch)
		}
		for _, cm := range e.rng {
			if m := mergeBranchRx.FindStringSubmatch(cm.Subject); cm.IsMerge() && m != nil {
				names = append(names, m[1])
			}
		}
		var off []string
		for _, n := range names {
			if !pyMatch(g.Str("branch_pattern"), n) {
				off = append(off, n)
			}
		}
		verdict("H6", off, fmt.Sprintf("%d branch name(s) follow the pattern", len(names)), "Branch names off pattern")
	}
	if e.want("H7") {
		ref := g.Str("verified_ref")
		target := e.Base
		if target == "" {
			target = e.Head
		}
		switch {
		case !gitOK(e.Repo, "rev-parse", "--verify", ref):
			e.add("H7", "project", "history", "not_covered", "No "+ref+" recorded yet", nil)
		case isAncestor(e.Repo, rev(e.Repo, ref), target):
			e.add("H7", "project", "history", "pass", "Last verified commit is still in history", nil)
		default:
			e.add("H7", "project", "history", "fail",
				fmt.Sprintf("Last verified commit %s is no longer in main's history", head(rev(e.Repo, ref), 7)), nil)
		}
	}
	if e.want("H8") {
		humans := strList(g.Get("humans"))
		var off []string
		for _, cm := range plain {
			if !contains(humans, cm.AuthorEmail) && len(cm.Coauthors) == 0 {
				off = append(off, fmt.Sprintf("%s by %s has no %s trailer", cm.Short(), cm.AuthorEmail, g.Str("agent_trailer")))
			}
		}
		verdict("H8", off, "Every agent commit names the agent", "Agent commits without attribution")
	}
	if e.want("H9") {
		var off []string
		for _, cm := range e.rng {
			if cm.Signature != "G" && cm.Signature != "U" {
				off = append(off, fmt.Sprintf("%s signature '%s'", cm.Short(), cm.Signature))
			}
		}
		verdict("H9", off, fmt.Sprintf("%d commit(s) carry good signatures", len(e.rng)), "Unsigned or unverifiable commits")
	}
}

func (e *Engine) checkH4(plain []*Commit) {
	var cands []*Commit
	for _, cm := range plain {
		if contains(noBehaviorTypes, commitType(cm.Subject)) && e.touchesCodeOrTests(cm) {
			cands = append(cands, cm)
		}
	}
	if len(cands) == 0 {
		e.add("H4", "project", "history", "pass", "No refactor or chore commits change code", nil)
		return
	}
	var offenders, broken []string
	links := strList(e.Cfg.Map("runner").Get("worktree_links"))
	for _, cm := range cands {
		before, beforeBroken := lightStatuses(e.Repo, cm.Parents[0], e.Workdir, links, e.Cfg)
		after, _ := lightStatuses(e.Repo, cm.SHA, e.Workdir, links, e.Cfg)
		hadCode := false
		for _, v := range before {
			if v != "Missing" {
				hadCode = true
			}
		}
		if beforeBroken && hadCode {
			broken = append(broken, cm.Short()+": the tests don't load at its parent, so it can't be compared")
			continue
		}
		ids := map[string]bool{}
		for k := range before {
			ids[k] = true
		}
		for k := range after {
			ids[k] = true
		}
		var changed []string
		for _, rid := range sortedKeys(ids) {
			b, bok := before[rid]
			a, aok := after[rid]
			if b != a || bok != aok {
				changed = append(changed, fmt.Sprintf("%s %s → %s", rid, noneOr(b, bok), noneOr(a, aok)))
			}
		}
		if len(changed) > 0 {
			offenders = append(offenders, fmt.Sprintf("%s '%s' changed %s", cm.Short(), cm.Subject, strings.Join(changed, ", ")))
		}
	}
	switch {
	case len(offenders) > 0:
		e.add("H4", "project", "history", "fail", "Behavior changed in no-behavior commits: "+strings.Join(offenders, "; "),
			om("offenders", offenders))
	case len(broken) > 0:
		e.add("H4", "project", "history", "error", strings.Join(broken, "; "), nil)
	default:
		e.add("H4", "project", "history", "pass",
			fmt.Sprintf("%d refactor/chore commit(s) left every status unchanged", len(cands)), nil)
	}
}

func noneOr(s string, ok bool) string {
	if !ok {
		return "None"
	}
	return s
}

// ------------------------------------------------------------------ statuses and report

func (e *Engine) statuses() map[string]string {
	out := map[string]string{}
	for _, rid := range e.activeIDs {
		failing := map[string]bool{}
		suiteError := false
		for _, r := range e.Results {
			if r.Scope == "requirement" && r.Subject == rid && (r.Verdict == "fail" || r.Verdict == "error") {
				failing[r.Check] = true
			}
			if r.Check == "T4" && r.Subject == rid && r.Verdict == "error" {
				suiteError = true
			}
		}
		// A suite that won't load can't list tagged tests; show it as Failing, not Untested.
		if suiteError {
			delete(failing, "T4")
			failing["T5"] = true
		}
		status := "Sync"
	outer:
		for _, name := range statusOrder {
			for chk := range failing {
				if statusByCheck[chk] == name {
					status = name
					break outer
				}
			}
		}
		out[rid] = status
	}
	return out
}

func (e *Engine) report() *OMap {
	statuses := e.statuses()
	summary := NewOMap()
	for _, chk := range CheckIDs {
		var rs []*Result
		for _, r := range e.Results {
			if r.Check == chk {
				rs = append(rs, r)
			}
		}
		has := func(v string) bool {
			for _, r := range rs {
				if r.Verdict == v {
					return true
				}
			}
			return false
		}
		switch {
		case !e.wanted[chk]:
			summary.Set(chk, "not_run")
		case len(rs) == 0:
			summary.Set(chk, "skip")
		case has("fail"):
			summary.Set(chk, "fail")
		case has("error"):
			summary.Set(chk, "error")
		case has("pass"):
			summary.Set(chk, "pass")
		case has("not_covered"):
			summary.Set(chk, "not_covered")
		default:
			summary.Set(chk, "skip")
		}
	}
	notCovered := []string{}
	for _, c := range summary.Keys() {
		if summary.Str(c) == "not_covered" {
			notCovered = append(notCovered, c)
		}
	}
	sort.Strings(notCovered)
	var views map[string]*OMap
	if !e.light {
		views = e.requirementViews(statuses)
	}
	reqs := []any{}
	for _, rid := range e.activeIDs {
		r := e.active[rid]
		api := []string{}
		for _, mp := range r.APIOps {
			api = append(api, opKey(mp))
		}
		var failing []string
		for _, x := range e.Results {
			if x.Subject == rid && (x.Verdict == "fail" || x.Verdict == "error") {
				failing = append(failing, x.Check)
			}
		}
		failing = uniqSorted(failing)
		if failing == nil {
			failing = []string{}
		}
		o := om("id", rid, "text", r.Text, "api", api, "status", statuses[rid], "not_covered", notCovered,
			"failing_checks", failing)
		if v := views[rid]; v != nil {
			for _, k := range v.Keys() {
				o.Set(k, v.Get(k))
			}
		}
		reqs = append(reqs, o)
	}
	outside := []any{}
	if !e.light {
		outside = e.outsideTheSpec()
	}
	results := []any{}
	for _, r := range e.Results {
		results = append(results, om("check", r.Check, "scope", r.Scope, "subject", r.Subject, "verdict", r.Verdict,
			"summary", r.Summary, "details", r.Details))
	}
	var base any
	if e.Base != "" {
		base = e.Base
	}
	return om("repo", e.Repo, "head", e.Head, "base", base, "head_branch", e.HeadBranch, "checks", summary,
		"requirements", reqs, "outside", outside, "results", results, "scorecard", e.scorecard())
}

// ------------------------------------------------------------------ the requirement view

func (e *Engine) res(check, rid string) []*Result {
	var out []*Result
	for _, r := range e.Results {
		if r.Check == check && r.Subject == rid {
			out = append(out, r)
		}
	}
	return out
}

func (e *Engine) verdicts(checks []string, rid string) map[string]bool {
	out := map[string]bool{}
	for _, c := range checks {
		for _, r := range e.res(c, rid) {
			out[r.Verdict] = true
		}
	}
	return out
}

func (e *Engine) vitals(rid string, req *Requirement) *OMap {
	v := NewOMap()
	t1 := false
	for _, r := range e.Results {
		if r.Check == "T1" {
			for _, p := range strList(r.Details.Get("problems")) {
				if strings.HasPrefix(p, rid+":") {
					t1 = true
				}
			}
		}
	}
	switch {
	case t1:
		v.Set("spec", "bad")
	case e.verdicts([]string{"T8"}, rid)["fail"]:
		v.Set("spec", "warn")
	default:
		v.Set("spec", "ok")
	}
	code := e.verdicts([]string{"T2", "T3"}, rid)
	switch {
	case code["fail"]:
		v.Set("code", "bad")
	case code["pass"]:
		v.Set("code", "ok")
	default:
		v.Set("code", "none")
	}
	if req.HasAPI() {
		api := e.verdicts([]string{"A1", "A5", "A6", "A7"}, rid)
		switch {
		case api["fail"] || api["error"]:
			v.Set("api", "bad")
		case api["pass"]:
			v.Set("api", "ok")
		default:
			v.Set("api", "none")
		}
	} else {
		v.Set("api", "none")
	}
	t := e.verdicts([]string{"T4", "T5", "T6", "T7"}, rid)
	switch {
	case t["error"] || e.verdicts([]string{"T5"}, rid)["fail"]:
		v.Set("tests", "bad")
	case t["fail"]:
		v.Set("tests", "warn")
	case t["pass"]:
		v.Set("tests", "ok")
	default:
		v.Set("tests", "none")
	}
	return v
}

type event struct {
	order             int
	sha, label, state string
}

func (e *Engine) requirementViews(statuses map[string]string) map[string]*OMap {
	order := map[string]int{}
	for i, cm := range e.history {
		order[cm.SHA] = i
	}
	gitRules := map[string]map[string]bool{}
	for _, r := range e.Results {
		if strings.HasPrefix(r.Check, "H") && r.Verdict == "fail" {
			for _, off := range strList(r.Details.Get("offenders")) {
				k := strings.TrimRight(strings.SplitN(off, " ", 2)[0], ":")
				if gitRules[k] == nil {
					gitRules[k] = map[string]bool{}
				}
				gitRules[k][r.Check] = true
			}
		}
	}
	hist := e.specHist()
	views := map[string]*OMap{}
	for _, rid := range e.activeIDs {
		req := e.active[rid]
		status := statuses[rid]
		var events []event
		prev, prevText := "", ""
		hasPrev, hasPrevText := false, false
		driftSHA := ""
		for _, r := range e.res("T8", rid) {
			if r.Verdict == "fail" {
				driftSHA = r.Details.Str("changed_in")
				break
			}
		}
		segments := []any{om("t", req.Text, "m", false)}
		for _, v := range hist {
			r, ok := v.Reqs[rid]
			if ok && (!hasPrev || r.Body() != prev) {
				label := "Spec added"
				if hasPrev {
					label = "Spec changed: " + wordDiff(prev, r.Body())
				}
				ord, found := order[v.SHA]
				if !found {
					ord = -1
				}
				state := "neutral"
				if v.SHA == driftSHA {
					state = "warn"
				}
				events = append(events, event{ord, head(v.SHA, 7), label, state})
				if v.SHA == driftSHA && hasPrevText {
					segments = nil
					for _, s := range wordSegments(prevText, req.Text) {
						segments = append(segments, om("t", s.T, "m", s.M))
					}
					if segments == nil {
						segments = []any{}
					}
				}
			}
			if ok {
				prev, hasPrev = r.Body(), true
				prevText, hasPrevText = r.Text, true
			} else {
				prev, hasPrev = "", false
			}
		}
		for _, cm := range e.linkedAny[rid] {
			label, state := "", ""
			n, ok := e.surviving[rid][cm.SHA]
			if _, has := e.surviving[rid]; !has {
				ok = false
			}
			if !ok {
				label, state = cm.Subject+" (tests)", "ok"
			} else {
				s := "s"
				if n == 1 {
					s = ""
				}
				label = fmt.Sprintf("%s (%d line%s still in the code)", cm.Subject, n, s)
				state = "bad"
				if n > 0 {
					state = "ok"
				}
			}
			if broke := gitRules[cm.Short()]; len(broke) > 0 {
				label += " · breaks " + strings.Join(sortedKeys(broke), ", ")
				if state != "bad" {
					state = "warn"
				}
			}
			ord, found := order[cm.SHA]
			if !found {
				ord = -1
			}
			events = append(events, event{ord, cm.Short(), label, state})
		}
		sort.SliceStable(events, func(i, j int) bool { return events[i].order < events[j].order })
		type nowItem struct{ label, state string }
		var now []nowItem
		for _, r := range append(e.res("T5", rid), e.res("T4", rid)...) {
			if r.Verdict == "error" {
				now = append(now, nowItem{r.Summary, "bad"})
				break
			}
		}
		for _, tc := range e.tagged[rid] {
			st := "bad"
			if tc.Outcome == "pass" {
				st = "ok"
			}
			now = append(now, nowItem{tc.Name + ": " + tc.Outcome, st})
		}
		for _, r := range e.res("T4", rid) {
			if r.Verdict == "fail" {
				now = append(now, nowItem{"No tagged test", "warn"})
			}
		}
		for _, chk := range []string{"T6", "T7"} {
			for _, r := range e.res(chk, rid) {
				if r.Verdict == "pass" || r.Verdict == "fail" {
					st := "warn"
					if r.Verdict == "pass" {
						st = "ok"
					}
					now = append(now, nowItem{r.Summary, st})
					sv := strList(r.Details.Get("survivors"))
					if len(sv) > 2 {
						sv = sv[:2]
					}
					for _, s := range sv {
						now = append(now, nowItem{"Not caught: " + s, "warn"})
					}
				}
			}
		}
		for _, mp := range req.APIOps {
			key := opKey(mp)
			for _, chk := range []string{"A1", "A5", "A6", "A7"} {
				for _, r := range e.res(chk, rid) {
					if r.Verdict == "fail" || r.Verdict == "error" {
						lines := strList(r.Details.Get("violations"))
						if len(lines) == 0 {
							lines = []string{r.Summary}
						}
						if len(lines) > 3 {
							lines = lines[:3]
						}
						for _, l := range lines {
							now = append(now, nowItem{chk + ": " + l, "bad"})
						}
					} else if r.Verdict == "pass" && (chk == "A6" || chk == "A7") {
						now = append(now, nowItem{key + ": " + lowerFirst(r.Summary), "ok"})
					}
				}
			}
		}
		// De-duplicate API lines shared by requirements with several operations.
		seen := map[string]bool{}
		nowTree := []any{}
		for _, n := range now {
			if !seen[n.label] {
				seen[n.label] = true
				nowTree = append(nowTree, om("label", n.label, "state", n.state))
			}
		}
		timeline := []any{}
		for _, ev := range events {
			timeline = append(timeline, om("sha", ev.sha, "label", ev.label, "state", ev.state))
		}
		views[rid] = om("vitals", e.vitals(rid, req), "note", notes[status], "segments", segments,
			"timeline", timeline, "now", nowTree)
	}
	return views
}

func (e *Engine) outsideTheSpec() []any {
	out := []any{}
	for _, r := range e.Results {
		if r.Verdict != "fail" && r.Verdict != "error" {
			continue
		}
		if r.Scope == "operation" || r.Check == "A3" || r.Check == "A4" || r.Check == "T1" ||
			(r.Check == "A7" && r.Scope != "requirement") {
			out = append(out, om("check", r.Check, "subject", r.Subject, "summary", r.Summary, "state", "bad"))
		}
	}
	return out
}

func (e *Engine) scorecard() *OMap {
	failingCommits := map[string]bool{}
	for _, r := range e.Results {
		if strings.HasPrefix(r.Check, "H") && r.Verdict == "fail" {
			for _, off := range strList(r.Details.Get("offenders")) {
				failingCommits[strings.SplitN(off, " ", 2)[0]] = true
			}
		}
	}
	humans := strList(e.gitCfg().Get("humans"))
	type agent struct {
		commits, breaking int
		refs              map[string]bool
	}
	agents := map[string]*agent{}
	var order []string
	for _, cm := range e.rng {
		if cm.IsMerge() || contains(humans, cm.AuthorEmail) {
			continue
		}
		who := cm.AuthorEmail
		if len(cm.Coauthors) > 0 {
			who = cm.Coauthors[0]
		}
		a, ok := agents[who]
		if !ok {
			a = &agent{refs: map[string]bool{}}
			agents[who] = a
			order = append(order, who)
		}
		a.commits++
		if failingCommits[cm.Short()] {
			a.breaking++
		}
		for _, r := range cm.Refs {
			a.refs[r] = true
		}
	}
	out := NewOMap()
	for _, who := range order {
		a := agents[who]
		var rate any
		if a.commits > 0 {
			rate = round2(1 - float64(a.breaking)/float64(a.commits))
		}
		refs := sortedKeys(a.refs)
		if refs == nil {
			refs = []string{}
		}
		out.Set(who, om("commits", a.commits, "commits_breaking_git_rules", a.breaking,
			"requirements_referenced", refs, "git_rule_pass_rate", rate))
	}
	return out
}

// ------------------------------------------------------------------ H4 support and routes

type lightResult struct {
	statuses map[string]string
	broken   bool
}

var lightCache = map[string]lightResult{}

// lightStatuses returns requirement statuses at sha using only the fast checks (for H4).
// links names untracked dependency folders (node_modules) to link into the worktree.
func lightStatuses(repo, sha, workdir string, links []string, cfg *OMap) (map[string]string, bool) {
	key := repo + "\x00" + sha
	if r, ok := lightCache[key]; ok {
		return copyStatuses(r.statuses), r.broken
	}
	wt, err := os.MkdirTemp(workdir, "aqv-wt-")
	if err != nil {
		panic(err)
	}
	git(repo, "worktree", "add", "--detach", "-f", wt, sha)
	var result lightResult
	func() {
		defer gitQuiet(repo, "worktree", "remove", "--force", wt)
		for _, name := range links {
			src := filepath.Join(repo, name)
			if exists(src) && !exists(filepath.Join(wt, name)) {
				real, err := filepath.EvalSymlinks(src)
				if err != nil {
					real = src
				}
				os.Symlink(real, filepath.Join(wt, name))
			}
		}
		// Old commits may predate .aqv.yml; compare both sides under the current, trusted config.
		eng, err := NewEngine(wt, Options{Head: sha, Light: true, Workdir: filepath.Join(wt, ".aqv-work"), Cfg: cfg})
		if err != nil {
			panic(err)
		}
		rep := eng.Run()
		result.statuses = map[string]string{}
		for _, r := range asList(rep.Get("requirements")) {
			m := r.(*OMap)
			result.statuses[m.Str("id")] = m.Str("status")
		}
		result.broken = eng.suite != nil && eng.suite.Broken
	}()
	lightCache[key] = result
	return copyStatuses(result.statuses), result.broken
}

func copyStatuses(m map[string]string) map[string]string {
	out := map[string]string{}
	for k, v := range m {
		out[k] = v
	}
	return out
}

// parseRoutes reads routes from an OpenAPI document, or from {"routes": [...]} / [...].
func parseRoutes(doc any) map[string]bool {
	out := map[string]bool{}
	if m, ok := doc.(*OMap); ok && m.Has("paths") {
		for _, op := range operations(m) {
			out[op.Key()] = true
		}
		return out
	}
	var items []any
	if m, ok := doc.(*OMap); ok {
		items = asList(m.Get("routes"))
	} else {
		items = asList(doc)
	}
	for _, x := range items {
		s := pyStr(x)
		f := fields(s)
		if len(f) < 2 {
			panic(fmt.Errorf("IndexError: bad route %q", s))
		}
		method := strings.SplitN(strings.ToUpper(strings.Join(f, " ")), " ", 2)[0]
		out[method+" "+f[1]] = true
	}
	return out
}

var routeParam = regexp.MustCompile(`\{[^/}]+\}|:[A-Za-z_][\w]*|<[^/>]+>`)

// normalizeRoute makes 'GET /users/:id' and 'GET /users/{user_id}' compare equal.
func normalizeRoute(key string) string {
	method, path, _ := strings.Cut(key, " ")
	path = strings.TrimRight(path, "/")
	if path == "" {
		path = "/"
	}
	return strings.ToUpper(method) + " " + routeParam.ReplaceAllString(path, "{}")
}

// scanRoutes finds routes by reading source files: a declared, partial fallback for
// frameworks that can't list their routes (axum). Unusual registrations are missed.
func scanRoutes(repo string, conf *OMap) map[string]bool {
	routeRx := regexp2.MustCompile(conf.Str("route"), regexp2.None)
	methodRx := regexp2.MustCompile(conf.Str("methods"), regexp2.None)
	found := map[string]bool{}
	files := strList(conf.Get("files"))
	if !conf.Has("files") {
		files = []string{"src/**/*"}
	}
	for _, pattern := range files {
		for _, path := range glob(filepath.Join(repo, pattern)) {
			data, err := os.ReadFile(path)
			if err != nil {
				continue
			}
			text := []rune(strings.ToValidUTF8(string(data), "�"))
			s := string(text)
			var ms []*regexp2.Match
			for m, _ := routeRx.FindStringMatch(s); m != nil; m, _ = routeRx.FindNextMatch(m) {
				ms = append(ms, m)
			}
			for i, m := range ms {
				end := len(text)
				if i+1 < len(ms) {
					end = ms[i+1].Index
				}
				seg := string(text[m.Index+m.Length : end])
				if j := strings.Index(seg, ";"); j >= 0 {
					seg = seg[:j]
				}
				for mm, _ := methodRx.FindStringMatch(seg); mm != nil; mm, _ = methodRx.FindNextMatch(mm) {
					found[strings.ToUpper(mm.GroupByNumber(1).String())+" "+m.GroupByNumber(1).String()] = true
				}
			}
		}
	}
	return found
}

// RecordVerified points the verified ref at HEAD (aqv check --record).
func (e *Engine) RecordVerified() {
	git(e.Repo, "update-ref", e.gitCfg().Str("verified_ref"), e.Head)
}
