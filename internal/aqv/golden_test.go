package aqv

// Compares the Go helpers with the Python verifier's answers recorded by
// scripts/gen_golden.py.

import (
	"encoding/json"
	"os"
	"reflect"
	"testing"
)

type golden struct {
	Mutants []struct {
		Family  string     `json:"family"`
		Line    string     `json:"line"`
		Mutants [][]string `json:"mutants"`
	} `json:"mutants"`
	Mentions []struct {
		Name   string `json:"name"`
		ID     string `json:"id"`
		Result bool   `json:"result"`
	} `json:"mentions"`
	IDToken []struct {
		ID     string `json:"id"`
		Result string `json:"result"`
	} `json:"id_token"`
	WordDiff []struct {
		Old      string `json:"old"`
		New      string `json:"new"`
		Diff     string `json:"diff"`
		Segments []struct {
			T string `json:"t"`
			M bool   `json:"m"`
		} `json:"segments"`
	} `json:"word_diff"`
	Routes []struct {
		Route  string `json:"route"`
		Result string `json:"result"`
	} `json:"routes"`
	Fnmatch []struct {
		Name   string `json:"name"`
		Pat    string `json:"pat"`
		Result bool   `json:"result"`
	} `json:"fnmatch"`
	JUnit []struct {
		Files  []string   `json:"files"`
		Errors []string   `json:"errors"`
		Cases  [][]string `json:"cases"`
	} `json:"junit"`
	Under []struct {
		Path     string   `json:"path"`
		Prefixes []string `json:"prefixes"`
		Result   bool     `json:"result"`
	} `json:"under"`
}

func loadGolden(t *testing.T) golden {
	data, err := os.ReadFile("testdata/golden.json")
	if err != nil {
		t.Fatal(err)
	}
	var g golden
	if err := json.Unmarshal(data, &g); err != nil {
		t.Fatal(err)
	}
	return g
}

func TestMutantsMatchPython(t *testing.T) {
	g := loadGolden(t)
	bad := 0
	for _, c := range g.Mutants {
		var got [][]string
		for _, m := range mutants(c.Line, c.Family) {
			got = append(got, []string{m.Desc, m.Line})
		}
		want := c.Mutants
		if len(want) == 0 {
			want = nil
		}
		if !reflect.DeepEqual(got, want) {
			bad++
			if bad <= 10 {
				t.Errorf("%s line %q:\n got  %q\n want %q", c.Family, c.Line, got, want)
			}
		}
	}
	if bad > 0 {
		t.Errorf("%d of %d lines differ", bad, len(g.Mutants))
	}
}

func TestSpecHelpersMatchPython(t *testing.T) {
	g := loadGolden(t)
	for _, c := range g.Mentions {
		if got := mentions(c.Name, c.ID); got != c.Result {
			t.Errorf("mentions(%q, %q) = %v, want %v", c.Name, c.ID, got, c.Result)
		}
	}
	for _, c := range g.IDToken {
		if got := idToken(c.ID); got != c.Result {
			t.Errorf("idToken(%q) = %q, want %q", c.ID, got, c.Result)
		}
	}
	for _, c := range g.WordDiff {
		if got := wordDiff(c.Old, c.New); got != c.Diff {
			t.Errorf("wordDiff(%q, %q) = %q, want %q", c.Old, c.New, got, c.Diff)
		}
		segs := wordSegments(c.Old, c.New)
		if len(segs) != len(c.Segments) {
			t.Errorf("wordSegments(%q, %q) = %v, want %v", c.Old, c.New, segs, c.Segments)
			continue
		}
		for i, s := range segs {
			if s.T != c.Segments[i].T || s.M != c.Segments[i].M {
				t.Errorf("wordSegments(%q, %q)[%d] = %v, want %v", c.Old, c.New, i, s, c.Segments[i])
			}
		}
	}
	for _, c := range g.Routes {
		if got := normalizeRoute(c.Route); got != c.Result {
			t.Errorf("normalizeRoute(%q) = %q, want %q", c.Route, got, c.Result)
		}
	}
	for _, c := range g.Fnmatch {
		if got := fnmatch(c.Name, c.Pat); got != c.Result {
			t.Errorf("fnmatch(%q, %q) = %v, want %v", c.Name, c.Pat, got, c.Result)
		}
	}
	for _, c := range g.Under {
		if got := under(c.Path, c.Prefixes); got != c.Result {
			t.Errorf("under(%q, %v) = %v, want %v", c.Path, c.Prefixes, got, c.Result)
		}
	}
}

func TestJUnitMatchesPython(t *testing.T) {
	g := loadGolden(t)
	if len(g.JUnit) == 0 {
		t.Fatal("no JUnit reports in testdata")
	}
	for _, c := range g.JUnit {
		cases, errs := parseJUnit(c.Files)
		var got [][]string
		for _, tc := range cases {
			got = append(got, []string{tc.Name, tc.Classname, tc.Outcome, tc.Message})
		}
		want := c.Cases
		if len(want) == 0 {
			want = nil
		}
		if !reflect.DeepEqual(got, want) {
			t.Errorf("%v: %d cases, want %d", c.Files, len(got), len(want))
			for i := range got {
				if i < len(want) && !reflect.DeepEqual(got[i], want[i]) {
					t.Errorf("  case %d:\n got  %q\n want %q", i, got[i], want[i])
					break
				}
			}
		}
		if len(errs) == 0 {
			errs = nil
		}
		wantErrs := c.Errors
		if len(wantErrs) == 0 {
			wantErrs = nil
		}
		if !reflect.DeepEqual(errs, wantErrs) {
			t.Errorf("%v: suite errors %q, want %q", c.Files, errs, wantErrs)
		}
	}
}

func TestPythonFormatting(t *testing.T) {
	a, b := 0.1, 0.2 // runtime values: constant arithmetic would be exact
	cases := map[string]string{pyFloat(1): "1.0", pyFloat(0.67): "0.67", pyFloat(1e16): "1e+16", pyFloat(1e-5): "1e-05",
		pyFloat(a + b): "0.30000000000000004", percent(4.0 / 9): "44%", percent(0.6): "60%",
		reprString("it's"): `"it's"`, reprString(`a"b'c`): `'a"b\'c'`, reprString("x\ny"): `'x\ny'`,
		escapeHTML(`<a href="x">'&'</a>`): "&lt;a href=&quot;x&quot;&gt;&#x27;&amp;&#x27;&lt;/a&gt;",
		dumpJSON(om("a", []any{}, "b", NewOMap(), "c", "→", "d", nil)): "{\n  \"a\": [],\n  \"b\": {},\n  \"c\": \"\\u2192\",\n  \"d\": null\n}",
	}
	for got, want := range cases {
		if got != want {
			t.Errorf("got %q, want %q", got, want)
		}
	}
	if pyFormat("{python} -k {id_underscore} {{x}}", map[string]string{"python": "py", "id_underscore": "ac_a_001"}) !=
		"py -k ac_a_001 {x}" {
		t.Error("pyFormat")
	}
	if got := splitlines("a\r\nb\rc\n\nd"); !reflect.DeepEqual(got, []string{"a", "b", "c", "", "d"}) {
		t.Errorf("splitlines = %q", got)
	}
}
