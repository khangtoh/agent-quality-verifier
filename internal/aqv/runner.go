package aqv

// Runs the project's own tools through the runner profile in .aqv.yml (runner.py). The
// verifier never imports the project's test framework: it fills command templates and
// reads standard outputs (JUnit XML, LCOV, Go cover profiles, JaCoCo XML).

import (
	"bytes"
	"context"
	"encoding/xml"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"syscall"
	"time"
)

// Home is the directory holding adapters/, .tools/ and the aqv Python package
// (for the pytest capture plugin): $AQV_HOME, else the binary's parent's parent.
func Home() string {
	if h := os.Getenv("AQV_HOME"); h != "" {
		return absPath(h)
	}
	exe, err := os.Executable()
	if err == nil {
		if real, err := filepath.EvalSymlinks(exe); err == nil {
			exe = real
		}
		return filepath.Dir(filepath.Dir(exe))
	}
	return absPath(".")
}

// pythonExe is the interpreter for {python} placeholders and Python syntax checks.
func pythonExe() string {
	if p := os.Getenv("AQV_PYTHON"); p != "" {
		return p
	}
	return "python3"
}

var safeShell = regexp.MustCompile(`^[\w@%+=:,./-]+$`)

func shQuote(s string) string {
	if s == "" {
		return "''"
	}
	if safeShell.MatchString(s) {
		return s
	}
	return "'" + strings.ReplaceAll(s, "'", `'"'"'`) + "'"
}

func placeholders(reqID string) map[string]string {
	v := map[string]string{"python": shQuote(pythonExe()), "aqv": shQuote(Home()), "extra": "", "filter": ""}
	if reqID != "" {
		v["id"] = reqID
		v["id_underscore"] = idToken(reqID)
		v["id_underscore_raw"] = strings.ReplaceAll(reqID, "-", "_")
	}
	return v
}

// pyFormat is str.format for {name} fields, with {{ and }} escapes.
func pyFormat(tmpl string, values map[string]string) string {
	var b strings.Builder
	for i := 0; i < len(tmpl); i++ {
		c := tmpl[i]
		if c == '{' {
			if i+1 < len(tmpl) && tmpl[i+1] == '{' {
				b.WriteByte('{')
				i++
				continue
			}
			j := strings.IndexByte(tmpl[i:], '}')
			if j < 0 {
				panic(fmt.Errorf("Single '{' encountered in format string: %s", tmpl))
			}
			name := tmpl[i+1 : i+j]
			v, ok := values[name]
			if !ok {
				panic(fmt.Errorf("KeyError: %s in %q", reprString(name), tmpl))
			}
			b.WriteString(v)
			i += j
			continue
		}
		if c == '}' {
			if i+1 < len(tmpl) && tmpl[i+1] == '}' {
				b.WriteByte('}')
				i++
				continue
			}
			panic(fmt.Errorf("Single '}' encountered in format string: %s", tmpl))
		}
		b.WriteByte(c)
	}
	return b.String()
}

func fill(tmpl string, kv ...string) string {
	v := placeholders("")
	for i := 0; i+1 < len(kv); i += 2 {
		v[kv[i]] = kv[i+1]
	}
	return pyFormat(tmpl, v)
}

func fillMap(tmpl string, values map[string]string) string {
	v := placeholders("")
	for k, x := range values {
		v[k] = x
	}
	return pyFormat(tmpl, v)
}

// runShell runs cmd with /bin/sh in its own session; output is stdout then stderr.
func runShell(cmd, cwd string, env map[string]string, timeout time.Duration) (int, string) {
	e := os.Environ()
	set := map[string]string{"PYTHONPATH": Home() + string(os.PathListSeparator) + os.Getenv("PYTHONPATH")}
	for k, v := range env {
		set[k] = v
	}
	e = mergeEnv(e, set)
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()
	c := exec.Command("/bin/sh", "-c", cmd)
	c.Dir, c.Env = cwd, e
	c.SysProcAttr = &syscall.SysProcAttr{Setsid: true}
	var out, errb bytes.Buffer
	c.Stdout, c.Stderr = &out, &errb
	if err := c.Start(); err != nil {
		return 127, err.Error()
	}
	done := make(chan error, 1)
	go func() { done <- c.Wait() }()
	select {
	case err := <-done:
		text := univNL(out.String() + errb.String())
		if err == nil {
			return 0, text
		}
		var ee *exec.ExitError
		if errors.As(err, &ee) {
			if ws, ok := ee.Sys().(syscall.WaitStatus); ok && ws.Signaled() {
				return -int(ws.Signal()), text
			}
			return ee.ExitCode(), text
		}
		return 1, text
	case <-ctx.Done():
		_ = syscall.Kill(-c.Process.Pid, syscall.SIGKILL)
		<-done
		return 124, fmt.Sprintf("timed out after %ds", int(timeout.Seconds()))
	}
}

func mergeEnv(base []string, set map[string]string) []string {
	var out []string
	for _, kv := range base {
		k, _, _ := strings.Cut(kv, "=")
		if _, ok := set[k]; ok {
			continue
		}
		out = append(out, kv)
	}
	keys := make([]string, 0, len(set))
	for k := range set {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	for _, k := range keys {
		out = append(out, k+"="+set[k])
	}
	return out
}

const defaultTimeout = 900 * time.Second

func profileEnv(cfg *OMap, repo string) map[string]string {
	out := map[string]string{}
	env := cfg.Map("runner").Map("env")
	for _, k := range env.Keys() {
		out[k] = pyFormat(pyStr(env.Get(k)), map[string]string{"repo": repo})
	}
	return out
}

// ---------------------------------------------------------------- JUnit

type TestCase struct {
	Name, Classname, Outcome, Message string
}

func (t *TestCase) FullName() string {
	if t.Classname != "" {
		return t.Classname + "::" + t.Name
	}
	return t.Name
}

type SuiteRun struct {
	ExitCode     int
	Output       string
	Cases        []*TestCase
	Broken       bool
	BrokenReason string
}

// xmlElem is a minimal ElementTree: tag, attributes, text before the first child, children.
type xmlElem struct {
	Tag      string
	Attr     map[string]string
	Text     string
	textDone bool
	Children []*xmlElem
}

func (e *xmlElem) iter(tag string, fn func(*xmlElem)) {
	if e.Tag == tag {
		fn(e)
	}
	for _, c := range e.Children {
		c.iter(tag, fn)
	}
}

func (e *xmlElem) find(tag string) *xmlElem {
	for _, c := range e.Children {
		if c.Tag == tag {
			return c
		}
	}
	return nil
}

// normalizeAttrWhitespace turns literal tabs and newlines inside attribute values into
// spaces, as an XML parser like expat does (character references are left alone).
func normalizeAttrWhitespace(data []byte) []byte {
	out := make([]byte, len(data))
	copy(out, data)
	inTag, quote := false, byte(0)
	for i := 0; i < len(out); i++ {
		c := out[i]
		switch {
		case quote != 0:
			if c == quote {
				quote = 0
			} else if c == '\n' || c == '\t' || c == '\r' {
				out[i] = ' '
			}
		case inTag:
			if c == '"' || c == '\'' {
				quote = c
			} else if c == '>' {
				inTag = false
			}
		case c == '<':
			rest := out[i:]
			switch {
			case bytes.HasPrefix(rest, []byte("<!--")):
				if j := bytes.Index(rest, []byte("-->")); j >= 0 {
					i += j + 2
				}
			case bytes.HasPrefix(rest, []byte("<![CDATA[")):
				if j := bytes.Index(rest, []byte("]]>")); j >= 0 {
					i += j + 2
				}
			case bytes.HasPrefix(rest, []byte("<?")), bytes.HasPrefix(rest, []byte("<!")):
				if j := bytes.IndexByte(rest, '>'); j >= 0 {
					i += j
				}
			default:
				inTag = true
			}
		}
	}
	return out
}

func parseXML(path string) (*xmlElem, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	dec := xml.NewDecoder(bytes.NewReader(normalizeAttrWhitespace(data)))
	dec.Strict = true
	var stack []*xmlElem
	var root *xmlElem
	for {
		tok, err := dec.Token()
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, err
		}
		switch t := tok.(type) {
		case xml.StartElement:
			e := &xmlElem{Tag: t.Name.Local, Attr: map[string]string{}}
			for _, a := range t.Attr {
				e.Attr[a.Name.Local] = a.Value
			}
			if len(stack) > 0 {
				p := stack[len(stack)-1]
				p.textDone = true
				p.Children = append(p.Children, e)
			} else {
				root = e
			}
			stack = append(stack, e)
		case xml.EndElement:
			if len(stack) > 0 {
				stack = stack[:len(stack)-1]
			}
		case xml.CharData:
			if len(stack) > 0 {
				p := stack[len(stack)-1]
				if !p.textDone {
					p.Text += string(t)
				}
			}
		}
	}
	if root == nil {
		return nil, fmt.Errorf("no element found")
	}
	return root, nil
}

func joinNonEmpty(xs ...string) string {
	var out []string
	for _, x := range xs {
		if x != "" {
			out = append(out, x)
		}
	}
	return strings.Join(out, " ")
}

// parseJUnit reads test cases from JUnit XML files; cases is nil when no report exists.
func parseJUnit(paths []string) ([]*TestCase, []string) {
	var existing []string
	for _, p := range paths {
		if exists(p) {
			existing = append(existing, p)
		}
	}
	if len(existing) == 0 {
		return nil, []string{"no JUnit report was written"}
	}
	cases := []*TestCase{}
	var suiteErrors []string
	for _, path := range existing {
		root, err := parseXML(path)
		if err != nil {
			suiteErrors = append(suiteErrors, fmt.Sprintf("unreadable JUnit report %s: %s", filepath.Base(path), err))
			continue
		}
		root.iter("testcase", func(tc *xmlElem) {
			name, cls := tc.Attr["name"], tc.Attr["classname"]
			outcome, msg := "pass", ""
			if e := tc.find("error"); e != nil {
				outcome, msg = "error", joinNonEmpty(e.Attr["message"], e.Text)
			} else if f := tc.find("failure"); f != nil {
				outcome, msg = "fail", joinNonEmpty(f.Attr["message"], f.Text)
			} else if s := tc.find("skipped"); s != nil {
				outcome, msg = "skipped", s.Attr["message"]
			}
			// Collection and build failures show up as cases that aren't real tests:
			// pytest "collection" errors, gotestsum's "TestMain ... [build failed]".
			low := strings.ToLower(msg)
			if (outcome == "error" || outcome == "fail") && (name == "" || strings.Contains(low, "collection") ||
				strings.Contains(low, "[build failed]") || strings.Contains(low, "[setup failed]")) {
				who := cls
				if who == "" {
					who = name
				}
				suiteErrors = append(suiteErrors, who+": "+head(msg, 200))
				return
			}
			cases = append(cases, &TestCase{name, cls, outcome, msg})
		})
	}
	// Runners that run tests in parallel (cargo-nextest, Gradle forks) write them in the
	// order they finished; sort so the same commit always gives the same report.
	sort.SliceStable(cases, func(i, j int) bool {
		if cases[i].Classname != cases[j].Classname {
			return cases[i].Classname < cases[j].Classname
		}
		return cases[i].Name < cases[j].Name
	})
	return cases, suiteErrors
}

func junitPaths(cfg *OMap, repo, junit string) []string {
	if jdir := cfg.Map("runner").Str("junit_dir"); jdir != "" {
		ps := glob(filepath.Join(repo, jdir, "**", "*.xml"))
		sort.Strings(ps)
		return ps
	}
	return []string{junit}
}

func clearJUnit(cfg *OMap, repo string) {
	if jdir := cfg.Map("runner").Str("junit_dir"); jdir != "" {
		for _, p := range glob(filepath.Join(repo, jdir, "**", "*.xml")) {
			os.Remove(p)
		}
	}
}

func fullSuite(cfg *OMap, repo, workdir, extra string, env map[string]string) *SuiteRun {
	r := cfg.Map("runner")
	junit := filepath.Join(workdir, "junit-full.xml")
	os.Remove(junit)
	clearJUnit(cfg, repo)
	e := profileEnv(cfg, repo)
	for k, v := range env {
		e[k] = v
	}
	code, out := runShell(fill(r.Str("test"), "junit", junit, "extra", extra), repo, e, defaultTimeout)
	cases, suiteErrors := parseJUnit(junitPaths(cfg, repo, junit))
	// A non-zero exit that no failing test explains means part of the suite didn't run
	// (for example a Go package that failed to compile, which JUnit lists as 0 tests).
	explained := false
	for _, c := range cases {
		if c.Outcome == "fail" || c.Outcome == "error" {
			explained = true
		}
	}
	unexplained := code != 0 && !explained
	brokenCode := false
	for _, n := range intList(r.Get("broken_exit_codes")) {
		if n == code {
			brokenCode = true
		}
	}
	broken := brokenCode || cases == nil || len(suiteErrors) > 0 || unexplained
	reason := ""
	if len(suiteErrors) > 0 {
		reason = strings.Join(suiteErrors, "; ")
	} else if broken {
		reason = fmt.Sprintf("runner exited %d", code)
		var lines []string
		for _, l := range splitlines(strip(out)) {
			if strip(l) != "" {
				lines = append(lines, l)
			}
		}
		if len(lines) > 3 {
			lines = lines[len(lines)-3:]
		}
		if len(lines) > 0 {
			reason += ": " + head(strings.Join(lines, " | "), 300)
		}
	}
	if cases == nil {
		cases = []*TestCase{}
	}
	return &SuiteRun{code, out, cases, broken, reason}
}

// ---------------------------------------------------------------- coverage

type LineSet map[string]map[int]bool

func (h LineSet) add(file string, line int) {
	if h[file] == nil {
		h[file] = map[int]bool{}
	}
	h[file][line] = true
}

func relTo(path, repo string) string {
	if filepath.IsAbs(path) {
		rp, err1 := filepath.EvalSymlinks(path)
		if err1 != nil {
			rp = filepath.Clean(path)
		}
		rr, err2 := filepath.EvalSymlinks(repo)
		if err2 != nil {
			rr = filepath.Clean(repo)
		}
		if rel, err := filepath.Rel(rr, rp); err == nil {
			return rel
		}
		return path
	}
	return path
}

func readLines(path string) []string {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil
	}
	return strings.SplitAfter(string(data), "\n")
}

func parseLCOV(path, repo string) LineSet {
	hits, current := LineSet{}, ""
	for _, line := range readLines(path) {
		line = strip(line)
		if strings.HasPrefix(line, "SF:") {
			current = relTo(line[3:], repo)
		} else if strings.HasPrefix(line, "DA:") && current != "" {
			parts := strings.Split(line[3:], ",")
			if len(parts) < 2 {
				continue
			}
			count, _ := strconv.ParseFloat(strip(parts[1]), 64)
			ln, _ := strconv.Atoi(strip(parts[0]))
			if int(count) > 0 {
				hits.add(current, ln)
			}
		}
	}
	return hits
}

// parseGoCover reads a Go cover profile: `file.go:startLine.col,endLine.col numStmts count`.
func parseGoCover(path, repo string) LineSet {
	module := ""
	for _, line := range readLines(filepath.Join(repo, "go.mod")) {
		if strings.HasPrefix(line, "module ") {
			module = strip(fields(line)[1])
			break
		}
	}
	hits := LineSet{}
	for _, line := range readLines(path) {
		if strings.HasPrefix(line, "mode:") || strip(line) == "" {
			continue
		}
		i := strings.LastIndex(line, " ")
		j := strings.LastIndex(line[:i], " ")
		loc, count := line[:j], strip(line[i+1:])
		if n, _ := strconv.Atoi(count); n == 0 {
			continue
		}
		k := strings.LastIndex(loc, ":")
		fname, rng := loc[:k], loc[k+1:]
		se := strings.Split(rng, ",")
		start, _ := strconv.Atoi(strings.Split(se[0], ".")[0])
		end, _ := strconv.Atoi(strings.Split(se[1], ".")[0])
		if module != "" && strings.HasPrefix(fname, module+"/") {
			fname = fname[len(module)+1:]
		}
		rel := relTo(fname, repo)
		for l := start; l <= end; l++ {
			hits.add(rel, l)
		}
	}
	return hits
}

func parseJaCoCo(path, repo string, roots []string) LineSet {
	hits := LineSet{}
	root, err := parseXML(path)
	if err != nil {
		panic(fmt.Errorf("unreadable JaCoCo report %s: %w", path, err))
	}
	root.iter("package", func(pkg *xmlElem) {
		pname := pkg.Attr["name"]
		pkg.iter("sourcefile", func(sf *xmlElem) {
			rel := ""
			for _, r := range roots {
				cand := filepath.Join(r, pname, sf.Attr["name"])
				if exists(filepath.Join(repo, cand)) {
					rel = cand
					break
				}
			}
			if rel == "" {
				return
			}
			sf.iter("line", func(ln *xmlElem) {
				ci, _ := strconv.Atoi(ln.Attr["ci"])
				if ci > 0 {
					nr, _ := strconv.Atoi(ln.Attr["nr"])
					hits.add(rel, nr)
				}
			})
		})
	})
	return hits
}

func readCoverage(cfg *OMap, repo, path string) LineSet {
	if !exists(path) {
		return LineSet{}
	}
	r := cfg.Map("runner")
	switch r.Str("coverage_format") {
	case "gocover":
		return parseGoCover(path, repo)
	case "jacoco":
		roots := strList(r.Get("coverage_source_roots"))
		if !r.Has("coverage_source_roots") {
			roots = []string{"src/main/kotlin"}
		}
		return parseJaCoCo(path, repo, roots)
	}
	return parseLCOV(path, repo)
}

// coveredLines runs only the tests selected by filterArgs under coverage.
func coveredLines(cfg *OMap, repo, filterArgs, workdir, tag string) (LineSet, int) {
	r := cfg.Map("runner")
	covData := filepath.Join(workdir, ".coverage-"+tag)
	lcov := filepath.Join(workdir, tag+".cov")
	outTmpl := "{lcov}"
	if r.Has("coverage_out") {
		outTmpl = r.Str("coverage_out")
	}
	outPath := fill(outTmpl, "lcov", lcov, "cov_data", covData)
	if !filepath.IsAbs(outPath) {
		outPath = filepath.Join(repo, outPath)
	}
	os.Remove(outPath)
	env := profileEnv(cfg, repo)
	code, _ := runShell(fill(r.Str("coverage"), "filter", filterArgs, "cov_data", covData, "lcov", lcov,
		"junit", filepath.Join(workdir, "junit-"+tag+".xml")), repo, env, defaultTimeout)
	if rep := r.Str("coverage_report"); rep != "" {
		runShell(fill(rep, "cov_data", covData, "lcov", lcov), repo, env, defaultTimeout)
	}
	return readCoverage(cfg, repo, outPath), code
}

func filterFor(cfg *OMap, reqID string) string {
	return fillMap(cfg.Map("runner").Str("filter"), placeholders(reqID))
}

// runSelected returns the exit code of the selected tests. Used by mutation testing.
func runSelected(cfg *OMap, repo, filterArgs string) int {
	tmp, err := os.MkdirTemp("", "aqv-sel-")
	if err != nil {
		panic(err)
	}
	defer os.RemoveAll(tmp)
	code, _ := runShell(fill(cfg.Map("runner").Str("test"), "filter", filterArgs, "junit", filepath.Join(tmp, "j.xml")),
		repo, profileEnv(cfg, repo), defaultTimeout)
	return code
}
