package aqv

// Thin git helpers (gitx.py). Everything the verifier knows about history comes through here.

import (
	"fmt"
	"os/exec"
	"strconv"
	"strings"
)

const sepField = "\x1f"
const sepRecord = "\x1e"

// univNL applies Python text-mode newline translation to command output.
func univNL(s string) string {
	s = strings.ReplaceAll(s, "\r\n", "\n")
	return strings.ReplaceAll(s, "\r", "\n")
}

func gitRun(repo string, args ...string) (string, string, int) {
	cmd := exec.Command("git", append([]string{"-C", repo}, args...)...)
	var out, errb strings.Builder
	cmd.Stdout, cmd.Stderr = &out, &errb
	err := cmd.Run()
	code := 0
	if err != nil {
		code = 1
		if ee, ok := err.(*exec.ExitError); ok {
			code = ee.ExitCode()
		}
	}
	return univNL(out.String()), univNL(errb.String()), code
}

// git runs a git command and fails loudly, like gitx.git(check=True).
func git(repo string, args ...string) string {
	out, errs, code := gitRun(repo, args...)
	if code != 0 {
		panic(fmt.Errorf("git %s failed: %s", strings.Join(args, " "), strip(errs)))
	}
	return out
}

func gitQuiet(repo string, args ...string) string {
	out, _, _ := gitRun(repo, args...)
	return out
}

func gitOK(repo string, args ...string) bool {
	_, _, code := gitRun(repo, args...)
	return code == 0
}

func rev(repo, ref string) string {
	return strip(git(repo, "rev-parse", "--verify", ref+"^{commit}"))
}

func isAncestor(repo, a, b string) bool {
	return gitOK(repo, "merge-base", "--is-ancestor", a, b)
}

// show returns a file's content at a commit; ok is false when it doesn't exist.
func show(repo, sha, path string) (string, bool) {
	out, _, code := gitRun(repo, "show", sha+":"+path)
	return out, code == 0
}

func filesAt(repo, sha string) []string {
	return strings.Split(git(repo, "ls-tree", "-r", "--name-only", sha), "\n")
}

func matching(paths, patterns []string) []string {
	var out []string
	for _, p := range paths {
		if p == "" {
			continue
		}
		for _, pat := range patterns {
			if fnmatch(p, pat) {
				out = append(out, p)
				break
			}
		}
	}
	return out
}

// under: path starts with one of prefixes, or matches one that is a glob (*_test.go).
func under(path string, prefixes []string) bool {
	for _, p := range prefixes {
		if strings.ContainsAny(p, "*?") {
			base := path
			if i := strings.LastIndex(path, "/"); i >= 0 {
				base = path[i+1:]
			}
			if fnmatch(path, p) || fnmatch(base, p) {
				return true
			}
		} else if strings.HasPrefix(path, p) {
			return true
		}
	}
	return false
}

type Numstat struct {
	Path           string
	Added, Deleted int
}

type Commit struct {
	SHA         string
	Parents     []string
	AuthorEmail string
	Subject     string
	Signature   string
	Refs        []string
	Coauthors   []string
	Files       []string
	Added       int
	Deleted     int
	Numstat     []Numstat
}

func (c *Commit) IsMerge() bool { return len(c.Parents) > 1 }
func (c *Commit) Short() string { return head(c.SHA, 7) }

func splitTrailer(v string) []string {
	var out []string
	for _, part := range strings.Split(strings.ReplaceAll(v, "\n", ","), ",") {
		part = strip(part)
		if part != "" {
			out = append(out, part)
		}
	}
	return out
}

// commits lists the commits in revRange, oldest first, with trailers, signature and numstat.
func commits(repo string, revRange []string, agentTrailer string) []*Commit {
	format := strings.Join([]string{
		"%H", "%P", "%ae", "%s", "%G?",
		"%(trailers:key=Refs,valueonly,separator=%x2C)",
		"%(trailers:key=" + agentTrailer + ",valueonly,separator=%x2C)",
	}, sepField) + sepRecord
	out := git(repo, append([]string{"log", "--reverse", "--format=" + format}, revRange...)...)
	var result []*Commit
	for _, rec := range strings.Split(out, sepRecord) {
		rec = strings.Trim(rec, "\n")
		if rec == "" {
			continue
		}
		f := strings.Split(rec, sepField)
		if len(f) != 7 {
			panic(fmt.Errorf("unexpected git log record: %q", rec))
		}
		c := &Commit{SHA: f[0], Parents: fields(f[1]), AuthorEmail: f[2], Subject: f[3], Signature: f[4],
			Refs: splitTrailer(f[5]), Coauthors: splitTrailer(f[6])}
		if !c.IsMerge() {
			for _, line := range splitlines(git(repo, "show", "--numstat", "--format=", "-M", c.SHA)) {
				parts := strings.Split(line, "\t")
				if len(parts) != 3 {
					continue
				}
				path := parts[2]
				if strings.Contains(path, " => ") {
					ps := strings.Split(path, " => ")
					path = strings.ReplaceAll(strings.ReplaceAll(ps[len(ps)-1], "}", ""), "{", "")
				}
				a, d := 0, 0
				if parts[0] != "-" {
					a, _ = strconv.Atoi(parts[0])
				}
				if parts[1] != "-" {
					d, _ = strconv.Atoi(parts[1])
				}
				c.Numstat = append(c.Numstat, Numstat{path, a, d})
				c.Files = append(c.Files, path)
				c.Added += a
				c.Deleted += d
			}
		}
		result = append(result, c)
	}
	return result
}

// blameOwners maps commit -> line numbers for non-blank, non-comment lines of path at ref.
// -w ignores whitespace-only changes; -M and -C keep credit with the commit that wrote a
// line when it is moved or copied.
func blameOwners(repo, path, ref string, commentPrefixes []string) (map[string][]int, []string) {
	owners := map[string][]int{}
	var order []string
	out := gitQuiet(repo, "blame", "-w", "-M", "-C", "--line-porcelain", ref, "--", path)
	sha, lineno := "", 0
	for _, ln := range splitlines(out) {
		if len(ln) >= 41 && ln[40] == ' ' && isHex40(ln[:40]) {
			parts := fields(ln)
			sha = parts[0]
			lineno, _ = strconv.Atoi(parts[2])
		} else if strings.HasPrefix(ln, "\t") && sha != "" {
			text := strip(ln[1:])
			if text != "" && !hasAnyPrefix(text, commentPrefixes) {
				if _, ok := owners[sha]; !ok {
					order = append(order, sha)
				}
				owners[sha] = append(owners[sha], lineno)
			}
		}
	}
	return owners, order
}

func isHex40(s string) bool {
	for _, c := range s {
		if !strings.ContainsRune("0123456789abcdef", c) {
			return false
		}
	}
	return true
}

func hasAnyPrefix(s string, prefixes []string) bool {
	for _, p := range prefixes {
		if strings.HasPrefix(s, p) {
			return true
		}
	}
	return false
}
