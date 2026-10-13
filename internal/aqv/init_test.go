package aqv

import (
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func initRepo(t *testing.T, files map[string]string) string {
	t.Helper()
	dir := t.TempDir()
	for _, args := range [][]string{{"init", "-q", "-b", "main"}, {"config", "user.email", "pat@example.com"}} {
		if out, err := exec.Command("git", append([]string{"-C", dir}, args...)...).CombinedOutput(); err != nil {
			t.Fatalf("git %v: %v %s", args, err, out)
		}
	}
	for rel, text := range files {
		os.MkdirAll(filepath.Dir(filepath.Join(dir, rel)), 0o755)
		if err := os.WriteFile(filepath.Join(dir, rel), []byte(text), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	return dir
}

func readFile(t *testing.T, dir, rel string) string {
	t.Helper()
	data, err := os.ReadFile(filepath.Join(dir, rel))
	if err != nil {
		t.Fatal(err)
	}
	return string(data)
}

func TestInitNeedsAGoalAndAPlan(t *testing.T) {
	dir := initRepo(t, map[string]string{"GOAL.md": "  \n"})
	_, err := Init(InitOptions{Repo: dir, Goal: "GOAL.md", Plan: "PLAN.md"})
	if err == nil || !strings.Contains(err.Error(), "no goal") || !strings.Contains(err.Error(), "no plan") {
		t.Fatalf("got %v", err)
	}
	if exists(filepath.Join(dir, ".aqv.yml")) || exists(filepath.Join(dir, "CLAUDE.md")) {
		t.Fatal("init wrote files for a project that isn't ready")
	}
}

func TestInitNeedsGitAndAKnownStack(t *testing.T) {
	dir := t.TempDir()
	os.WriteFile(filepath.Join(dir, "GOAL.md"), []byte("goal"), 0o644)
	os.WriteFile(filepath.Join(dir, "PLAN.md"), []byte("plan"), 0o644)
	if _, err := Init(InitOptions{Repo: dir, Goal: "GOAL.md", Plan: "PLAN.md"}); err == nil || !strings.Contains(err.Error(), "not a git repository") {
		t.Fatalf("got %v", err)
	}
	dir = initRepo(t, map[string]string{"GOAL.md": "goal", "PLAN.md": "plan", "package.json": "{}"})
	if _, err := Init(InitOptions{Repo: dir, Goal: "GOAL.md", Plan: "PLAN.md"}); err == nil || !strings.Contains(err.Error(), "found package.json") {
		t.Fatalf("got %v", err)
	}
	if _, err := Init(InitOptions{Repo: dir, Goal: "GOAL.md", Plan: "PLAN.md", Lang: "go"}); err != nil {
		t.Fatalf("--lang go should override the detected stack: %v", err)
	}
}

func TestInitWritesAGoProject(t *testing.T) {
	dir := initRepo(t, map[string]string{
		"docs/goal.md": "A todo service.", "PLAN.md": "1. Add todos.", "go.mod": "module example.com/todo\n\ngo 1.24\n",
		"CLAUDE.md": "# Todo\n\nHouse rules.\n", ".gitignore": "bin/",
	})
	opts := InitOptions{Repo: dir, Goal: "docs/goal.md", Plan: "PLAN.md"}
	res, err := Init(opts)
	if err != nil {
		t.Fatal(err)
	}
	want := []string{".aqv.yml", ".spectral.yaml", "tools/aqvcapture/capture.go", ".claude/workflows/aqv-specs.js",
		".claude/workflows/aqv-build.js", "specs/.ids", ".gitignore", "CLAUDE.md"}
	if res.Lang != "go" || strings.Join(res.Wrote, " ") != strings.Join(want, " ") || len(res.Kept) != 0 {
		t.Fatalf("lang %s wrote %v kept %v", res.Lang, res.Wrote, res.Kept)
	}

	cfg, err := LoadConfig(readFile(t, dir, ".aqv.yml"))
	if err != nil {
		t.Fatal(err)
	}
	if got := strList(cfg.Map("git").Get("humans")); len(got) != 1 || got[0] != "pat@example.com" {
		t.Fatalf("humans: %v", got)
	}
	if !strings.Contains(cfg.Map("runner").Str("test"), "gotestsum") || !cfg.Map("api").Truthy("capture") ||
		cfg.Map("api").Str("routes_from_code") != "" || cfg.Map("mutation").Str("family") != "c" {
		t.Fatalf("unexpected profile: %v", readFile(t, dir, ".aqv.yml"))
	}
	if got := readFile(t, dir, ".gitignore"); got != "bin/\n.aqv-out/\n" {
		t.Fatalf(".gitignore: %q", got)
	}
	claude := readFile(t, dir, "CLAUDE.md")
	if !strings.HasPrefix(claude, "# Todo\n\nHouse rules.\n\n"+sectionStart) || !strings.HasSuffix(claude, sectionEnd+"\n") {
		t.Fatalf("CLAUDE.md: %q", claude)
	}
	if !strings.HasPrefix(readFile(t, dir, "tools/aqvcapture/capture.go"), "// Package aqvcapture") ||
		!strings.Contains(readFile(t, dir, ".claude/workflows/aqv-build.js"), "name: 'aqv-build'") {
		t.Fatal("the capture helper or the workflows were not copied")
	}

	// A second run changes nothing, including edits made since and IDs already issued.
	os.WriteFile(filepath.Join(dir, ".aqv.yml"), []byte("code_paths: [\"pkg/\"]\n"), 0o644)
	os.WriteFile(filepath.Join(dir, "specs/.ids"), []byte("AC-todo-001\n"), 0o644)
	res, err = Init(opts)
	if err != nil {
		t.Fatal(err)
	}
	if len(res.Wrote) != 0 || len(res.Kept) != len(want) {
		t.Fatalf("second run wrote %v kept %v", res.Wrote, res.Kept)
	}
	if readFile(t, dir, ".aqv.yml") != "code_paths: [\"pkg/\"]\n" || readFile(t, dir, "CLAUDE.md") != claude {
		t.Fatal("a second run changed files")
	}

	// --force rewrites init's own files and section, and still leaves the registry and other text alone.
	os.WriteFile(filepath.Join(dir, "CLAUDE.md"), []byte(strings.Replace(claude, "## Agent Quality Verifier", "## Old", 1)+"\nAfter.\n"), 0o644)
	opts.Force, opts.Human = true, "none"
	if _, err = Init(opts); err != nil {
		t.Fatal(err)
	}
	cfg, _ = LoadConfig(readFile(t, dir, ".aqv.yml"))
	if len(strList(cfg.Map("git").Get("humans"))) != 0 || readFile(t, dir, "specs/.ids") != "AC-todo-001\n" {
		t.Fatal("--force: humans or the registry are wrong")
	}
	if got := readFile(t, dir, "CLAUDE.md"); got != claude+"\nAfter.\n" {
		t.Fatalf("--force CLAUDE.md: %q", got)
	}
}
