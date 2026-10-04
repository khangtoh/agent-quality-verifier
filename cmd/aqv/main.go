// Command aqv checks an agent's work against the spec.
//
//	aqv check [--repo .] [--base main] [--out out/] [--skip T7,A7] [--only H1,H2] [--record]
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

func main() {
	if len(os.Args) < 2 || os.Args[1] != "check" {
		fmt.Fprintln(os.Stderr, "usage: aqv check [--repo .] [--base REF] [--out DIR] [--skip T7,A7] [--only H1,H2] [--record]")
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
