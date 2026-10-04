// Command aqv checks an agent's work against the spec.
//
//	aqv check [--repo .] [--base main] [--out out/] [--skip T7,A7] [--only H1,H2] [--record]
//	aqv pages --work demo/.work-go --meta demo/langs.json --out demo/results-go
//	aqv site  --root . --meta demo/langs.json --py-work demo/.work --go-work demo/.work-go
package main

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/khangtoh/agent-quality-verifier/internal/aqv"
)

func split(s string) []string {
	var out []string
	for _, x := range strings.Split(s, ",") {
		if x != "" {
			out = append(out, x)
		}
	}
	return out
}

func pages(args []string) {
	fs := flag.NewFlagSet("pages", flag.ExitOnError)
	work := fs.String("work", "demo/.work-go", "demo run folder (<work>/<lang>/demo-results.json)")
	meta := fs.String("meta", "demo/langs.json", "language metadata written by scripts/export_langs.py")
	out := fs.String("out", "demo/results-go", "folder to write the pages to")
	variant := fs.String("variant", "Go verifier", "label shown in the page headers")
	command := fs.String("command", "python demo/run_demo.py --impl go", "what regenerates the pages, shown in the footers")
	fs.Parse(args)
	if err := aqv.WritePages(aqv.PagesOptions{Work: *work, Meta: *meta, Out: *out, Variant: *variant, Command: *command}); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	fmt.Println("Wrote", *out)
}

func site(args []string) {
	fs := flag.NewFlagSet("site", flag.ExitOnError)
	root := fs.String("root", ".", "repository root: index.html and docs/compare/*.html are written here")
	meta := fs.String("meta", "demo/langs.json", "language metadata written by scripts/export_langs.py")
	pyWork := fs.String("py-work", "demo/.work", "the Python demo run")
	goWork := fs.String("go-work", "demo/.work-go", "the Go demo run")
	fs.Parse(args)
	if err := aqv.WriteSite(aqv.SiteOptions{Root: *root, Meta: *meta, PyWork: *pyWork, GoWork: *goWork}); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	fmt.Println("Wrote", filepath.Join(*root, "index.html"), "and docs/compare/")
}

func main() {
	if len(os.Args) >= 2 && os.Args[1] == "pages" {
		pages(os.Args[2:])
		return
	}
	if len(os.Args) >= 2 && os.Args[1] == "site" {
		site(os.Args[2:])
		return
	}
	if len(os.Args) < 2 || os.Args[1] != "check" {
		fmt.Fprintln(os.Stderr, "usage: aqv check [--repo .] [--base REF] [--out DIR] [--skip T7,A7] [--only H1,H2] [--record]\n"+
			"       aqv pages [--work DIR] [--meta FILE] [--out DIR]\n"+
			"       aqv site  [--root DIR] [--meta FILE] [--py-work DIR] [--go-work DIR]")
		os.Exit(2)
	}
	fs := flag.NewFlagSet("check", flag.ExitOnError)
	repo := fs.String("repo", ".", "repository to check")
	base := fs.String("base", "", "base ref; checks the range base..HEAD like a pull request")
	out := fs.String("out", "", "directory for results.json, report.txt and report.html")
	skip := fs.String("skip", "", "comma-separated checks to skip")
	only := fs.String("only", "", "comma-separated checks to run")
	record := fs.Bool("record", false, "when every check passes, record HEAD as the last verified commit (refs/aqv/verified)")
	fs.Parse(os.Args[2:])

	dir := *out
	if dir == "" {
		dir = filepath.Join(*repo, ".aqv-out")
	}
	if err := os.MkdirAll(dir, 0o755); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	eng, err := aqv.NewEngine(*repo, aqv.Options{Base: *base, Skip: split(*skip), Only: split(*only),
		Workdir: filepath.Join(dir, "work")})
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	rep := eng.Run()
	txt, err := aqv.WriteOutputs(dir, rep)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	fmt.Println(txt)
	failed := false
	checks := rep.Map("checks")
	for _, k := range checks.Keys() {
		if v := checks.Str(k); v == "fail" || v == "error" {
			failed = true
		}
	}
	if *record && !failed {
		eng.RecordVerified()
	}
	if failed {
		os.Exit(1)
	}
}
