package aqv

// T7: small, deterministic line mutations (mutate.py). Each mutant changes one line written
// for the requirement; mutants that don't compile are discarded, never counted as caught.
// Positions are code points, as in Python.

import (
	"os/exec"
	"strconv"
	"strings"

	"github.com/dlclark/regexp2"
)

type swap struct {
	rx   *regexp2.Regexp
	repl string
}

func swaps(pairs ...string) []swap {
	var out []swap
	for i := 0; i+1 < len(pairs); i += 2 {
		out = append(out, swap{regexp2.MustCompile(pairs[i], regexp2.None), pairs[i+1]})
	}
	return out
}

var pySwaps = swaps(
	`>=`, ">", `<=`, "<", `(?<![<>=!])>(?!=)`, ">=", `(?<![<>=!-])<(?!=)`, "<=",
	`==`, "!=", `!=`, "==",
	`\bnot in\b`, "in", `(?<!not )\bin\b(?=\s)`, "not in",
	`\bTrue\b`, "False", `\bFalse\b`, "True",
	`\band\b`, "or", `\bor\b`, "and",
	`(?<![\w.])\+(?![+=])`, "-", `(?<![\w.eE])-(?![-=>])`, "+",
)

var cSwaps = swaps(
	`===`, "!==", `!==`, "===",
	`(?<![=!<>])>=`, ">", `(?<![=<])<=(?!>)`, "<",
	`(?<![-=<>!])>(?![=>])`, ">=", `(?<![<!])<(?![=<-])`, "<=",
	`(?<![=!<>])==(?!=)`, "!=", `!=(?!=)`, "==",
	`&&`, "||", `\|\|`, "&&",
	`\btrue\b`, "false", `\bfalse\b`, "true",
	`(?<![\w.+])\+(?![+=])`, "-", `(?<![\w.eE-])-(?![-=>])`, "+",
)

var pySkip = []string{"def ", "class ", "if ", "elif ", "else", "for ", "while ", "try", "except", "finally",
	"with ", "@", "async def ", "import ", "from ", "return", `"""`, "'''"}
var cSkip = []string{"import ", "package ", "use ", "mod ", "#[", "@", "func ", "fun ", "fn ", "pub fn ", "class ",
	"interface ", "type ", "struct ", "impl ", "export ", "}", "{", "//", "/*", "*"}

var intRx = regexp2.MustCompile(`(?<![\w.])(\d+)(?![\w.])`, regexp2.None)
var maskRx = regexp2.MustCompile("(\"(?:\\\\.|[^\"\\\\])*\"|`[^`]*`|'(?:\\\\.|[^'\\\\])')", regexp2.None)

// mask blanks out string literals so swaps never edit text inside quotes.
func mask(line string) string {
	out, _ := maskRx.ReplaceFunc(line, func(m regexp2.Match) string {
		return strings.Repeat(" ", len([]rune(m.String())))
	}, -1, -1)
	return out
}

type Mutant struct {
	Desc string
	Line string
}

func hasAnySuffix(s string, suffixes []string) bool {
	for _, x := range suffixes {
		if strings.HasSuffix(s, x) {
			return true
		}
	}
	return false
}

// mutants lists the mutants of one source line, in a fixed order.
func mutants(line, family string) []Mutant {
	var out []Mutant
	stripped := strip(line)
	comment := "//"
	if family == "python" {
		comment = "#"
	}
	if stripped == "" || strings.HasPrefix(stripped, comment) {
		return nil
	}
	if family != "python" && (hasAnyPrefix(stripped, []string{"import ", "package ", "use "}) ||
		strings.Contains(stripped, "require(")) {
		return nil
	}
	lr := []rune(line)
	trimmed := []rune(strings.TrimLeftFunc(line, isPySpace))
	indent := string(lr[:len(lr)-len(trimmed)])
	start := len(lr) - len(trimmed)
	masked := []rune(mask(line))
	rest := string(masked[start:])
	table := cSwaps
	if family == "python" {
		table = pySwaps
	}
	for _, sw := range table {
		m, _ := sw.rx.FindStringMatch(rest)
		if m != nil {
			s, e := m.Index+start, m.Index+m.Length+start
			out = append(out, Mutant{"'" + string(lr[s:e]) + "' → '" + sw.repl + "'",
				string(lr[:s]) + sw.repl + string(lr[e:])})
		}
	}
	if m, _ := intRx.FindStringMatch(rest); m != nil {
		s, e := m.Index+start, m.Index+m.Length+start
		n, err := strconv.Atoi(string(lr[s:e]))
		if err == nil {
			out = append(out, Mutant{strconv.Itoa(n) + " → " + strconv.Itoa(n+1),
				string(lr[:s]) + strconv.Itoa(n+1) + string(lr[e:])})
		}
	}
	if family == "python" {
		if strings.HasPrefix(stripped, "return ") && stripped != "return None" {
			out = append(out, Mutant{"return value → None", indent + "return None\n"})
		}
		if !hasAnyPrefix(stripped, pySkip) && !hasAnySuffix(stripped, []string{":", ",", "(", "[", "{", "\\"}) {
			out = append(out, Mutant{"line removed", indent + "pass\n"})
		}
	} else {
		if !hasAnyPrefix(stripped, cSkip) && !hasAnySuffix(stripped, []string{"{", ",", "(", "[", "=>", "->", "="}) &&
			!hasAnyPrefix(stripped, []string{"return", "let ", "const ", "val ", "var "}) {
			out = append(out, Mutant{"line removed", "\n"})
		}
	}
	return out
}

// compilesPython asks the project's Python whether a mutated source still compiles.
func compilesPython(source string) bool {
	cmd := exec.Command(pythonExe(), "-c", "import sys; compile(sys.stdin.read(), '<mutant>', 'exec')")
	cmd.Stdin = strings.NewReader(source)
	return cmd.Run() == nil
}
