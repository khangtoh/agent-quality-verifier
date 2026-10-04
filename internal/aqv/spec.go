package aqv

// Requirements: parsing spec lines, hashing their text, and reading their history (spec.py).

import (
	"crypto/sha256"
	"encoding/hex"
	"regexp"
	"strings"

	"github.com/dlclark/regexp2"
	"github.com/pmezard/go-difflib/difflib"
	"golang.org/x/text/unicode/norm"
)

var (
	specLine = regexp.MustCompile(`^- \*\*([^*]+)\*\*(?: \(([^)]*)\))?: (.+?)\s*$`)
	idFormat = regexp.MustCompile(`^AC-[a-z0-9]+(?:-[a-z0-9]+)*-\d{3}$`)
	apiOp    = regexp.MustCompile(`^(GET|PUT|POST|DELETE|PATCH|HEAD|OPTIONS)\s+(/\S*)$`)
	idSep    = regexp.MustCompile(`[-_ ]`)
	camel    = regexp2.MustCompile(`(?<=[a-z0-9])(?=[A-Z])`, regexp2.None)
)

func normalizeText(text string) string {
	return strings.Join(fields(norm.NFC.String(text)), " ")
}

func textHash(text string) string {
	sum := sha256.Sum256([]byte(normalizeText(text)))
	return "sha256:" + hex.EncodeToString(sum[:])
}

// idToken is the form an ID takes inside a test name: lower case, with -, _ and spaces equal.
func idToken(id string) string {
	return strings.ToLower(idSep.ReplaceAllString(id, "_"))
}

var mentionCache = map[string]*regexp2.Regexp{}

// mentions: the test name contains the requirement ID in any of the usual spellings:
// test_AC_auth_002_x, TestAC_auth_002X (Go), ac_auth_002_x (Rust), "AC-auth-002 x" (JS, Kotlin).
func mentions(name, id string) bool {
	name, _ = camel.Replace(name, "_", -1, -1)
	n := strings.ToLower(idSep.ReplaceAllString(name, "_"))
	tok := idToken(id)
	rx, ok := mentionCache[tok]
	if !ok {
		rx = regexp2.MustCompile(`(?<![a-z0-9])`+regexp2.Escape(tok)+`(?![0-9])`, regexp2.None)
		mentionCache[tok] = rx
	}
	m, _ := rx.MatchString(n)
	return m
}

type Requirement struct {
	ID        string
	Spec      string
	Line      int
	Tags      string
	Text      string
	APIOps    [][2]string
	TagErrors []string
}

// Body is everything after the ID: tags and wording. Any change here makes results stale.
func (r *Requirement) Body() string {
	if r.Tags != "" {
		return "(" + r.Tags + ") " + r.Text
	}
	return r.Text
}

func (r *Requirement) Hash() string  { return textHash(r.Body()) }
func (r *Requirement) Retired() bool { return strings.HasPrefix(strings.ToLower(r.Text), "(retired)") }
func (r *Requirement) HasAPI() bool  { return len(r.APIOps) > 0 }
func opKey(op [2]string) string      { return op[0] + " " + op[1] }

func parseSpec(path, content string) []*Requirement {
	var reqs []*Requirement
	for i, raw := range splitlines(content) {
		m := specLine.FindStringSubmatch(raw)
		if m == nil {
			continue
		}
		r := &Requirement{ID: m[1], Spec: path, Line: i + 1, Tags: strip(m[2]), Text: m[3]}
		if r.Tags != "" {
			for _, tag := range strings.Split(r.Tags, ";") {
				key, val, _ := strings.Cut(tag, ":")
				if strip(key) != "api" {
					r.TagErrors = append(r.TagErrors, "unknown tag '"+strip(key)+"'")
					continue
				}
				for _, op := range strings.Split(val, ",") {
					op = strings.Join(fields(op), " ")
					if mo := apiOp.FindStringSubmatch(op); mo != nil {
						r.APIOps = append(r.APIOps, [2]string{mo[1], mo[2]})
					} else {
						r.TagErrors = append(r.TagErrors, "bad api operation '"+op+"'")
					}
				}
			}
		}
		reqs = append(reqs, r)
	}
	return reqs
}

// specAt returns every requirement in spec files matching patterns at commit sha.
func specAt(repo, sha string, patterns []string) []*Requirement {
	var reqs []*Requirement
	for _, path := range matching(filesAt(repo, sha), patterns) {
		text, _ := show(repo, sha, path)
		reqs = append(reqs, parseSpec(path, text)...)
	}
	return reqs
}

type SpecVersion struct {
	SHA  string
	Reqs map[string]*Requirement
}

// specHistory lists every commit that touched a spec file, oldest first.
func specHistory(repo, headSHA string, patterns []string) []SpecVersion {
	shas := fields(git(repo, append([]string{"log", "--reverse", "--format=%H", headSHA, "--"}, patterns...)...))
	var out []SpecVersion
	for _, sha := range shas {
		first := map[string]*Requirement{}
		for _, r := range specAt(repo, sha, patterns) {
			if _, ok := first[r.ID]; !ok {
				first[r.ID] = r // a duplicate ID is T1's problem; keep the original line
			}
		}
		out = append(out, SpecVersion{sha, first})
	}
	return out
}

func wordDiff(old, new string) string {
	a, b := fields(old), fields(new)
	var parts []string
	for _, op := range difflib.NewMatcher(a, b).GetOpCodes() {
		if op.Tag == 'e' {
			continue
		}
		o, n := strings.Join(a[op.I1:op.I2], " "), strings.Join(b[op.J1:op.J2], " ")
		switch {
		case o != "" && n != "":
			parts = append(parts, o+" → "+n)
		case n != "":
			parts = append(parts, "+"+n)
		default:
			parts = append(parts, "−"+o)
		}
	}
	return strings.Join(parts, ", ")
}

type Segment struct {
	T string
	M bool
}

// wordSegments splits new into segments, marking the words that changed against old.
func wordSegments(old, new string) []Segment {
	a, b := fields(old), fields(new)
	var segs []Segment
	for _, op := range difflib.NewMatcher(a, b).GetOpCodes() {
		if op.J2 > op.J1 {
			segs = append(segs, Segment{strings.Join(b[op.J1:op.J2], " "), op.Tag != 'e'})
		}
	}
	return segs
}
