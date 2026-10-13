package aqv

// aqv init: checks that a project has a goal and a plan, then writes what the verifier and Claude
// Code need to work in it. Nothing that exists is overwritten unless Force is set.

import (
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"

	"github.com/khangtoh/agent-quality-verifier/adapters"
)

type InitOptions struct {
	Repo  string
	Goal  string // relative to Repo
	Plan  string // relative to Repo
	Lang  string // "" picks it from the project's files
	Human string // "" uses git's user.email; "none" lists nobody
	Force bool
}

type InitResult struct {
	Lang     string
	Wrote    []string
	Kept     []string
	Warnings []string
}

const (
	sectionStart = "<!-- aqv:start -->"
	sectionEnd   = "<!-- aqv:end -->"
	outIgnore    = ".aqv-out/"
)

// Stacks init recognises by a file at the project root. Only Go has a profile here; the other
// languages' runner profiles are in demo/langs/<language>/stages.py.
var stackMarkers = []struct{ file, lang string }{
	{"go.mod", "go"}, {"package.json", "javascript"}, {"Cargo.toml", "rust"},
	{"pyproject.toml", "python"}, {"build.gradle.kts", "kotlin"},
}

// initFiles maps each file init writes to its source in the adapters folder.
var initFiles = map[string][][2]string{
	"go": {
		{".aqv.yml", "init/aqv.go.yml"},
		{".spectral.yaml", "init/spectral.yaml"},
		{"tools/aqvcapture/capture.go", "go/aqvcapture/capture.go"},
		{".claude/workflows/aqv-specs.js", "claude/workflows/aqv-specs.js"},
		{".claude/workflows/aqv-build.js", "claude/workflows/aqv-build.js"},
	},
}

var initSections = map[string]string{"go": "init/claude.go.md"}

func detectStack(repo string) (lang, marker string) {
	for _, m := range stackMarkers {
		if exists(filepath.Join(repo, m.file)) {
			return m.lang, m.file
		}
	}
	return "go", ""
}

func hasText(path string) bool {
	data, err := os.ReadFile(path)
	return err == nil && strip(string(data)) != ""
}

// withSection adds the aqv section to CLAUDE.md text, or replaces the one already there.
func withSection(old, section string, force bool) (string, bool) {
	i := strings.Index(old, sectionStart)
	if i < 0 {
		if strip(old) == "" {
			return section, true
		}
		return strings.TrimRight(old, "\n") + "\n\n" + section, true
	}
	j := strings.Index(old, sectionEnd)
	if !force || j < i {
		return old, false
	}
	rest := strings.TrimPrefix(old[j+len(sectionEnd):], "\n")
	return old[:i] + section + rest, true
}

func ignoresOut(text string) bool {
	for _, line := range splitlines(text) {
		if l := strip(line); l == outIgnore || l == strings.TrimSuffix(outIgnore, "/") {
			return true
		}
	}
	return false
}

// Init sets a project up for the verifier. It returns an error, and writes nothing, when the
// project is not ready: no git repository, no goal, no plan, or a stack init has no profile for.
func Init(o InitOptions) (*InitResult, error) {
	repo := absPath(o.Repo)
	var problems []string
	if !gitOK(repo, "rev-parse", "--git-dir") {
		problems = append(problems, repo+" is not a git repository: run `git init -b main` there first")
	}
	for _, f := range [][2]string{{"goal", o.Goal}, {"plan", o.Plan}} {
		if !hasText(filepath.Join(repo, f[1])) {
			problems = append(problems, fmt.Sprintf("no %s: %s is missing or empty", f[0], f[1]))
		}
	}
	lang, marker := o.Lang, ""
	if lang == "" {
		lang, marker = detectStack(repo)
	}
	if initFiles[lang] == nil {
		why := "--lang " + lang
		if marker != "" {
			why = "found " + marker
		}
		problems = append(problems, fmt.Sprintf("init only sets up Go projects so far (%s): pass --lang go, or write "+
			".aqv.yml from the %s runner profile in demo/langs/%s/stages.py", why, lang, lang))
	}
	if len(problems) > 0 {
		return nil, errors.New(strings.Join(problems, "\n"))
	}

	res := &InitResult{Lang: lang}
	human := o.Human
	if human == "" {
		human = strip(gitQuiet(repo, "config", "--get", "user.email"))
		if human == "" {
			res.Warnings = append(res.Warnings, "git has no user.email, so git.humans in .aqv.yml is empty: every commit will need an agent trailer (H8)")
		}
	}
	humans := ""
	if human != "" && human != "none" {
		humans = strconv.Quote(human)
	}

	write := func(rel, content string, always bool) error {
		path := filepath.Join(repo, rel)
		if exists(path) && !o.Force && !always {
			res.Kept = append(res.Kept, rel)
			return nil
		}
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			return err
		}
		if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
			return err
		}
		res.Wrote = append(res.Wrote, rel)
		return nil
	}
	read := func(rel string) string {
		data, _ := os.ReadFile(filepath.Join(repo, rel))
		return string(data)
	}

	for _, f := range initFiles[lang] {
		data, err := adapters.Files.ReadFile(f[1])
		if err != nil {
			return nil, err
		}
		if err := write(f[0], strings.ReplaceAll(string(data), "__HUMANS__", humans), false); err != nil {
			return nil, err
		}
	}
	cfg, err := LoadConfig(read(".aqv.yml"))
	if err != nil {
		return nil, fmt.Errorf("the .aqv.yml already here can't be read: %w", err)
	}
	// The registry starts empty; an existing one is never touched, since its IDs must not be reissued.
	if registry := cfg.Str("ids_registry"); !exists(filepath.Join(repo, registry)) {
		if err := write(registry, "", false); err != nil {
			return nil, err
		}
	} else {
		res.Kept = append(res.Kept, registry)
	}
	if ignore := read(".gitignore"); ignoresOut(ignore) {
		res.Kept = append(res.Kept, ".gitignore")
	} else {
		if ignore != "" && !strings.HasSuffix(ignore, "\n") {
			ignore += "\n"
		}
		if err := write(".gitignore", ignore+outIgnore+"\n", true); err != nil {
			return nil, err
		}
	}
	section, err := adapters.Files.ReadFile(initSections[lang])
	if err != nil {
		return nil, err
	}
	if text, changed := withSection(read("CLAUDE.md"), string(section), o.Force); changed {
		if err := write("CLAUDE.md", text, true); err != nil {
			return nil, err
		}
	} else {
		res.Kept = append(res.Kept, "CLAUDE.md")
	}

	warn := func(format string, args ...any) { res.Warnings = append(res.Warnings, fmt.Sprintf(format, args...)) }
	if lang == "go" && !exists(filepath.Join(repo, "go.mod")) {
		warn("no go.mod yet: run `go mod init <module>` before the first requirement is built")
	}
	if p := filepath.Join(Home(), ".tools", "bin", "gotestsum"); !exists(p) {
		warn("gotestsum is not at %s: the test checks (T4 to T7) can't run until scripts/setup.sh has installed it", p)
	}
	for _, t := range [][3]string{{"spectral", "node_modules/.bin/spectral", "A3"}, {"oasdiff", "bin/oasdiff", "A4"},
		{"schemathesis", "../.venv/bin/schemathesis", "A7"}} {
		if tool(t[0], t[1]) == "" {
			warn("%s is not installed: %s will report \"not covered\"", t[0], t[2])
		}
	}
	if strip(gitQuiet(repo, "config", "--get", "commit.gpgsign")) != "true" {
		warn("commit signing is off (git config commit.gpgsign): H9 fails on unsigned commits")
	}
	if _, err := exec.LookPath("aqv"); err != nil {
		if exe, err := os.Executable(); err == nil {
			warn("aqv is not on PATH: add %s to it, or pass aqv: %q to the workflows", filepath.Dir(exe), exe)
		}
	}
	return res, nil
}
