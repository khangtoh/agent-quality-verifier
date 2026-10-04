package aqv

// Helpers that keep the Go verifier's text identical to the Python reference
// implementation: string slicing by code point, str.split()/splitlines(), fnmatch,
// glob, repr(), %-style percentages and html.escape.

import (
	"fmt"
	"math"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"unicode"
	"unicode/utf8"
)

// head returns the first n code points of s (Python s[:n]).
func head(s string, n int) string {
	if n <= 0 {
		return ""
	}
	if utf8.RuneCountInString(s) <= n {
		return s
	}
	r := []rune(s)
	return string(r[:n])
}

// tail returns the last n code points of s (Python s[-n:]).
func tail(s string, n int) string {
	r := []rune(s)
	if len(r) <= n {
		return s
	}
	return string(r[len(r)-n:])
}

// fields is Python's str.split() with no arguments.
func fields(s string) []string {
	return strings.FieldsFunc(s, isPySpace)
}

func isPySpace(r rune) bool {
	return unicode.IsSpace(r) || (r >= 0x1c && r <= 0x1f)
}

// strip is Python's str.strip() with no arguments.
func strip(s string) string {
	return strings.TrimFunc(s, isPySpace)
}

// splitlines is Python's str.splitlines() (without keepends).
func splitlines(s string) []string {
	var out []string
	r := []rune(s)
	start := 0
	for i := 0; i < len(r); i++ {
		switch r[i] {
		case '\n', '\v', '\f', '\x1c', '\x1d', '\x1e', '\x85', ' ', ' ':
			out = append(out, string(r[start:i]))
			start = i + 1
		case '\r':
			out = append(out, string(r[start:i]))
			if i+1 < len(r) && r[i+1] == '\n' {
				i++
			}
			start = i + 1
		}
	}
	if start < len(r) {
		out = append(out, string(r[start:]))
	}
	return out
}

// splitlinesKeep is str.splitlines(True) for '\n'-terminated source files.
func splitlinesKeep(s string) []string {
	var out []string
	for len(s) > 0 {
		i := strings.IndexAny(s, "\n")
		if i < 0 {
			out = append(out, s)
			break
		}
		out = append(out, s[:i+1])
		s = s[i+1:]
	}
	return out
}

// ---------------------------------------------------------------- fnmatch and glob

var fnCache = map[string]*regexp.Regexp{}

// fnmatchTranslate is fnmatch.translate: '*' matches anything, including '/'.
func fnmatchTranslate(pat string) string {
	var b strings.Builder
	r := []rune(pat)
	for i := 0; i < len(r); i++ {
		c := r[i]
		switch c {
		case '*':
			for i+1 < len(r) && r[i+1] == '*' {
				i++
			}
			b.WriteString(".*")
		case '?':
			b.WriteString(".")
		case '[':
			j := i + 1
			if j < len(r) && r[j] == '!' {
				j++
			}
			if j < len(r) && r[j] == ']' {
				j++
			}
			for j < len(r) && r[j] != ']' {
				j++
			}
			if j >= len(r) {
				b.WriteString(`\[`)
				continue
			}
			stuff := string(r[i+1 : j])
			i = j
			stuff = strings.ReplaceAll(stuff, `\`, `\\`)
			if strings.HasPrefix(stuff, "!") {
				stuff = "^" + stuff[1:]
			} else if strings.HasPrefix(stuff, "^") {
				stuff = `\` + stuff
			}
			b.WriteString("[" + stuff + "]")
		default:
			b.WriteString(regexp.QuoteMeta(string(c)))
		}
	}
	return `(?s)\A(?:` + b.String() + `)\z`
}

func fnmatch(name, pat string) bool {
	rx, ok := fnCache[pat]
	if !ok {
		rx = regexp.MustCompile(fnmatchTranslate(pat))
		fnCache[pat] = rx
	}
	return rx.MatchString(name)
}

func hasMagic(s string) bool { return strings.ContainsAny(s, "*?[") }

// glob is glob.glob(pattern, recursive=True) for absolute or relative patterns.
// Wildcards never match names starting with '.', as in Python.
func glob(pattern string) []string {
	parts := strings.Split(pattern, "/")
	root := ""
	if strings.HasPrefix(pattern, "/") {
		root = "/"
		parts = parts[1:]
	}
	var out []string
	var walk func(dir string, parts []string)
	join := func(dir, name string) string {
		if dir == "" {
			return name
		}
		if strings.HasSuffix(dir, "/") {
			return dir + name
		}
		return dir + "/" + name
	}
	list := func(dir string) []os.DirEntry {
		d := dir
		if d == "" {
			d = "."
		}
		es, err := os.ReadDir(d)
		if err != nil {
			return nil
		}
		return es
	}
	walk = func(dir string, parts []string) {
		if len(parts) == 0 {
			return
		}
		p, rest := parts[0], parts[1:]
		if p == "**" {
			// zero or more directories
			var dirs []string
			var rec func(d string)
			rec = func(d string) {
				dirs = append(dirs, d)
				for _, e := range list(d) {
					if strings.HasPrefix(e.Name(), ".") {
						continue
					}
					full := join(d, e.Name())
					if isDir(full) {
						rec(full)
					}
				}
			}
			rec(dir)
			if len(rest) == 0 {
				for _, d := range dirs[1:] {
					out = append(out, d)
				}
				for _, d := range dirs {
					for _, e := range list(d) {
						if !strings.HasPrefix(e.Name(), ".") && !isDir(join(d, e.Name())) {
							out = append(out, join(d, e.Name()))
						}
					}
				}
				return
			}
			for _, d := range dirs {
				walk(d, rest)
			}
			return
		}
		if !hasMagic(p) {
			full := join(dir, p)
			if len(rest) == 0 {
				if _, err := os.Lstat(full); err == nil {
					out = append(out, full)
				}
				return
			}
			if isDir(full) {
				walk(full, rest)
			}
			return
		}
		for _, e := range list(dir) {
			name := e.Name()
			if strings.HasPrefix(name, ".") && !strings.HasPrefix(p, ".") {
				continue
			}
			if !fnmatch(name, p) {
				continue
			}
			full := join(dir, name)
			if len(rest) == 0 {
				out = append(out, full)
			} else if isDir(full) {
				walk(full, rest)
			}
		}
	}
	walk(root, parts)
	seen := map[string]bool{}
	var uniq []string
	for _, p := range out {
		if !seen[p] {
			seen[p] = true
			uniq = append(uniq, p)
		}
	}
	return uniq
}

func isDir(p string) bool {
	st, err := os.Stat(p)
	return err == nil && st.IsDir()
}

func exists(p string) bool {
	_, err := os.Stat(p)
	return err == nil
}

// ---------------------------------------------------------------- repr and numbers

// pyFloat formats a float like Python's repr().
func pyFloat(f float64) string {
	if math.IsInf(f, 1) {
		return "inf"
	}
	if math.IsInf(f, -1) {
		return "-inf"
	}
	if math.IsNaN(f) {
		return "nan"
	}
	if f == 0 {
		if math.Signbit(f) {
			return "-0.0"
		}
		return "0.0"
	}
	e := strconv.FormatFloat(f, 'e', -1, 64) // d.ddde±XX
	mant, expS, _ := strings.Cut(e, "e")
	exp, _ := strconv.Atoi(expS)
	if exp < -4 || exp >= 16 {
		if !strings.Contains(mant, ".") {
			mant += ""
		}
		sign := "+"
		if exp < 0 {
			sign = "-"
			exp = -exp
		}
		return fmt.Sprintf("%se%s%02d", mant, sign, exp)
	}
	s := strconv.FormatFloat(f, 'f', -1, 64)
	if !strings.ContainsAny(s, ".") {
		s += ".0"
	}
	return s
}

// percent is Python's f"{x:.0%}".
func percent(x float64) string {
	return strconv.FormatFloat(x*100, 'f', 0, 64) + "%"
}

// round2 is Python's round(x, 2).
func round2(x float64) float64 {
	v, _ := strconv.ParseFloat(strconv.FormatFloat(x, 'f', 2, 64), 64)
	return v
}

// pyStr is Python's str() for values decoded from JSON or YAML.
func pyStr(v any) string {
	switch x := v.(type) {
	case nil:
		return "None"
	case string:
		return x
	case bool:
		if x {
			return "True"
		}
		return "False"
	case int:
		return strconv.Itoa(x)
	case int64:
		return strconv.FormatInt(x, 10)
	case float64:
		return pyFloat(x)
	default:
		return pyRepr(v)
	}
}

// pyRepr is Python's repr() for values decoded from JSON or YAML.
func pyRepr(v any) string {
	switch x := v.(type) {
	case nil:
		return "None"
	case string:
		return reprString(x)
	case bool, int, int64, float64:
		return pyStr(x)
	case []any:
		parts := make([]string, len(x))
		for i, e := range x {
			parts[i] = pyRepr(e)
		}
		return "[" + strings.Join(parts, ", ") + "]"
	case []string:
		parts := make([]string, len(x))
		for i, e := range x {
			parts[i] = reprString(e)
		}
		return "[" + strings.Join(parts, ", ") + "]"
	case *OMap:
		parts := make([]string, 0, x.Len())
		for _, k := range x.Keys() {
			parts = append(parts, reprString(k)+": "+pyRepr(x.Get(k)))
		}
		return "{" + strings.Join(parts, ", ") + "}"
	default:
		return fmt.Sprint(x)
	}
}

func reprString(s string) string {
	quote := '\''
	if strings.ContainsRune(s, '\'') && !strings.ContainsRune(s, '"') {
		quote = '"'
	}
	var b strings.Builder
	b.WriteRune(quote)
	for _, r := range s {
		switch {
		case r == quote || r == '\\':
			b.WriteRune('\\')
			b.WriteRune(r)
		case r == '\n':
			b.WriteString(`\n`)
		case r == '\r':
			b.WriteString(`\r`)
		case r == '\t':
			b.WriteString(`\t`)
		case r < 0x20 || r == 0x7f:
			fmt.Fprintf(&b, `\x%02x`, r)
		case r > 0x7f && !unicode.IsPrint(r):
			if r <= 0xff {
				fmt.Fprintf(&b, `\x%02x`, r)
			} else if r <= 0xffff {
				fmt.Fprintf(&b, `\u%04x`, r)
			} else {
				fmt.Fprintf(&b, `\U%08x`, r)
			}
		default:
			b.WriteRune(r)
		}
	}
	b.WriteRune(quote)
	return b.String()
}

// ---------------------------------------------------------------- html

// escapeHTML is Python's html.escape(s, quote=True).
func escapeHTML(s string) string {
	return htmlReplacer.Replace(s)
}

var htmlReplacer = strings.NewReplacer("&", "&amp;", "<", "&lt;", ">", "&gt;", `"`, "&quot;", "'", "&#x27;")

// ---------------------------------------------------------------- small collections

func sortedKeys[V any](m map[string]V) []string {
	ks := make([]string, 0, len(m))
	for k := range m {
		ks = append(ks, k)
	}
	sort.Strings(ks)
	return ks
}

func uniqSorted(xs []string) []string {
	seen := map[string]bool{}
	var out []string
	for _, x := range xs {
		if !seen[x] {
			seen[x] = true
			out = append(out, x)
		}
	}
	sort.Strings(out)
	return out
}

func contains(xs []string, x string) bool {
	for _, y := range xs {
		if y == x {
			return true
		}
	}
	return false
}

func absPath(p string) string {
	a, err := filepath.Abs(p)
	if err != nil {
		return p
	}
	return a
}

func upperFirst(s string) string {
	r := []rune(s)
	if len(r) == 0 {
		return s
	}
	return string(unicode.ToUpper(r[0])) + string(r[1:])
}

func lowerFirst(s string) string {
	r := []rune(s)
	if len(r) == 0 {
		return s
	}
	return string(unicode.ToLower(r[0])) + string(r[1:])
}

func writeFile(path, content string) error {
	return os.WriteFile(path, []byte(content), 0o644)
}
