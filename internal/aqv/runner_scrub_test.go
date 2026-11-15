package aqv

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// Messages are cut to a fixed length after the checkout and work folder are replaced. Two checkouts of
// the same tree must keep the same tail, and a work folder inside the checkout must become <work>
// rather than <repo>/.aqv-out (the shorter path is a prefix of the longer one).
func TestScrubBeforeCutIgnoresCheckoutLength(t *testing.T) {
	cut := func(repo string) string {
		work := repo + "/.aqv-out"
		text := strings.Repeat("n", 250) + " " + work + "/service.log: listen failed; " + repo + "/main.go: exit 1"
		return tail(scrubPaths(text, []pathPair{{repo, "<repo>"}, {work, "<work>"}}), 80)
	}
	short := cut("/c")
	long := cut("/very/long/checkout/that/would/shift/the/cut")
	if short != long {
		t.Fatalf("message cut depends on the checkout path:\n short %q\n long  %q", short, long)
	}
	if !strings.Contains(short, "<work>/service.log: listen failed") || strings.Contains(short, "<repo>/.aqv-out") {
		t.Fatalf("nested work dir was not replaced first: %q", short)
	}
}

func TestScrubPathsKeepsTheCheckoutLabelWhenWorkIsTheSameFolder(t *testing.T) {
	dir := absPath(t.TempDir())
	got := scrubPaths(dir+"/main.go", pathPairs(dir, dir))
	if got != "<repo>/main.go" {
		t.Fatalf("got %q", got)
	}
}

func TestPathPairsScrubsLinkAndTarget(t *testing.T) {
	root := t.TempDir()
	real := filepath.Join(root, "real")
	if err := os.Mkdir(real, 0o755); err != nil {
		t.Fatal(err)
	}
	link := filepath.Join(root, "link")
	if err := os.Symlink(real, link); err != nil {
		t.Fatal(err)
	}
	absLink := absPath(link)
	absReal, err := filepath.EvalSymlinks(absLink)
	if err != nil {
		t.Fatal(err)
	}
	if absReal == absLink {
		t.Fatal("symlink did not resolve to a different path")
	}
	if got := scrubPaths(absLink+"/a "+absReal+"/b", pathPairs(link, "")); got != "<repo>/a <repo>/b" {
		t.Fatalf("got %q", got)
	}
	for _, p := range pathPairs(real, "") {
		if p.label == "<work>" {
			t.Fatalf("empty work dir produced %#v", p)
		}
	}
}

func TestParseJUnitScrubsPathsBeforeCutting(t *testing.T) {
	repo := "/var/checkout/" + strings.Repeat("p", 180)
	work := repo + "/.aqv-out"
	build := "collection " + repo + "/" + strings.Repeat("d", 220) + " END"
	fail := "got 500 from " + work + "/service.log and " + repo + "/handler.go"
	xml := "<testsuite>\n" +
		"<testcase classname=\"pkg\" name=\"\"><error>" + build + "</error></testcase>\n" +
		"<testcase classname=\"pkg\" name=\"TestAC_auth_001_SignIn\"><failure>" + fail + "</failure></testcase>\n" +
		"</testsuite>\n"
	dir := t.TempDir()
	path := filepath.Join(dir, "junit.xml")
	if err := os.WriteFile(path, []byte(xml), 0o644); err != nil {
		t.Fatal(err)
	}
	pairs := []pathPair{{repo, "<repo>"}, {work, "<work>"}}
	cases, errs := parseJUnit([]string{path}, pairs)
	wantErr := "pkg: " + head(scrubPaths(build, pairs), 200)
	if len(errs) != 1 || errs[0] != wantErr {
		t.Fatalf("suite errors %q, want %q", errs, wantErr)
	}
	if strings.Contains(errs[0], " END") || strings.Contains(errs[0], repo) || !strings.HasPrefix(errs[0], "pkg: collection <repo>/") {
		t.Fatalf("suite error was cut before the checkout was scrubbed: %q", errs[0])
	}
	if len(cases) != 1 || cases[0].Message != "got 500 from <work>/service.log and <repo>/handler.go" {
		t.Fatalf("cases %#v", cases)
	}
}
