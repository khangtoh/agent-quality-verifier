package aqv

import (
	"strings"
	"testing"
)

const conSpec = `# Spec
- **AC-shop-001** (api: POST /orders; data: orders): An order starts with status "open" and returns 201; an order for an unknown customer is rejected with 404.
- **AC-shop-002** (api: GET /orders/{id}): An order that does not exist returns 404.
- **AC-shop-003** (data: orders): At most 200 orders are kept per customer.
`

const conAPI = `openapi: 3.0.3
info: {title: Shop, version: 1.0.0}
paths:
  /orders:
    post:
      x-requirements: [AC-shop-001]
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                lines: {type: array, maxItems: 100, items: {type: string}}
      responses:
        "201":
          description: Created.
          content:
            application/json:
              schema: {$ref: "#/components/schemas/Order"}
        "404": {description: No such customer.}
  /orders/{id}:
    get:
      x-requirements: [AC-shop-002]
      responses:
        "200":
          description: The order.
          content:
            application/json:
              schema: {$ref: "#/components/schemas/Order"}
        "404": {description: No such order.}
components:
  schemas:
    Order:
      type: object
      properties:
        id: {type: integer}
        status: {type: string, enum: [open, paid]}
        total_cents: {type: integer}
`

const conData = `datasets:
  orders:
    kind: source
    x-requirements: [AC-shop-001, AC-shop-003]
    primary_key: [id]
    columns:
      id:          {type: integer, nullable: false}
      status:      {type: text,    nullable: false, values: [open, paid]}
      total_cents: {type: integer, nullable: false}
`

const conPlan = "# Plan\n\nOne service. Orders are created with `POST /orders` and read back with `GET /orders/{id}`.\n" +
	"Something that doesn't exist is 404. The contract is `contracts/openapi.yaml`; AC-shop-001 comes first.\n"

const conConfig = `specs: ["specs/*.md"]
code_paths: ["src/"]
contract: contracts/openapi.yaml
data:
  contract: contracts/data.yaml
consistency:
  design: ["PLAN.md"]
git:
  humans: ["pat@example.com"]
`

func conRepo(t *testing.T, edits map[string][2]string) string {
	t.Helper()
	files := map[string]string{"specs/shop.md": conSpec, "contracts/openapi.yaml": conAPI, "contracts/data.yaml": conData,
		"PLAN.md": conPlan, ".aqv.yml": conConfig}
	for path, e := range edits {
		if !strings.Contains(files[path], e[0]) {
			t.Fatalf("%s has no %q", path, e[0])
		}
		files[path] = strings.Replace(files[path], e[0], e[1], 1)
	}
	dir := initRepo(t, files)
	gitIn(t, dir, "config", "user.name", "Pat")
	commitAll(t, dir, "chore: start", "pat@example.com")
	return dir
}

func runCon(t *testing.T, dir string) (map[string]string, map[string]string, string) {
	t.Helper()
	eng, err := NewEngine(dir, Options{Only: append([]string{"T2"}, ConsistencyCheckIDs...), Workdir: t.TempDir()})
	if err != nil {
		t.Fatal(err)
	}
	rep := eng.Run()
	verdicts, statuses := map[string]string{}, map[string]string{}
	for _, k := range rep.Map("checks").Keys() {
		verdicts[k] = rep.Map("checks").Str(k)
	}
	for _, r := range maps(rep.Get("requirements")) {
		statuses[r.Str("id")] = r.Str("status")
	}
	var lines []string
	for _, r := range maps(rep.Get("results")) {
		if v := r.Str("verdict"); v == "fail" || v == "error" {
			lines = append(lines, r.Str("check")+" "+r.Str("subject")+": "+r.Str("summary"))
		}
	}
	return verdicts, statuses, strings.Join(lines, "\n")
}

func TestConsistencyPassesWhenTheDocumentsAgree(t *testing.T) {
	got, _, problems := runCon(t, conRepo(t, nil))
	wantVerdicts(t, got, problems, map[string]string{"C1": "pass", "C2": "pass", "C3": "pass", "C4": "pass", "C6": "pass", "C7": "pass"})
	for _, line := range strings.Split(problems, "\n") {
		if strings.HasPrefix(line, "C") {
			t.Errorf("documents that agree report: %s", line)
		}
	}
}

func TestConsistencyIsOffWithoutItsSection(t *testing.T) {
	dir := conRepo(t, map[string][2]string{".aqv.yml": {"consistency:\n  design: [\"PLAN.md\"]\n", ""}})
	eng, err := NewEngine(dir, Options{Workdir: t.TempDir(), Only: []string{"T1"}})
	if err != nil {
		t.Fatal(err)
	}
	if checks := eng.Run().Map("checks"); checks.Has("C1") || checks.Has("A8") {
		t.Errorf("C1 or A8 is in a report for a project with no consistency section")
	}
}

func TestC1FindsAStatusTheContractDoesNotDocument(t *testing.T) {
	for name, edit := range map[string]map[string][2]string{
		"the requirement moved": {"specs/shop.md": {"is rejected with 404", "is rejected with 409"}},
		"the contract moved":    {"contracts/openapi.yaml": {`"404": {description: No such customer.}`, `"400": {description: No such customer.}`}},
	} {
		got, statuses, problems := runCon(t, conRepo(t, edit))
		wantVerdicts(t, got, problems, map[string]string{"C1": "fail"})
		if statuses["AC-shop-001"] != "Conflict" || statuses["AC-shop-002"] == "Conflict" {
			t.Errorf("%s: statuses %v\n%s", name, statuses, problems)
		}
	}
}

func TestC1IgnoresNumbersThatAreNotStatusCodes(t *testing.T) {
	if got := statusCodes("At most 200 orders are kept, 404 items per page, and 500 ms at most.", false); len(got) != 0 {
		t.Errorf("read %v as status codes", got)
	}
	if got := strings.Join(statusCodes("returns 201; rejected with 409 or 422; responds with status 404", false), ","); got != "201,409,422,404" {
		t.Errorf("got %s", got)
	}
	if got := strings.Join(statusCodes("Errors: 404 for something missing, `409` when it conflicts.", true), ","); got != "404,409" {
		t.Errorf("got %s", got)
	}
}

func TestC2FindsAQuotedValueTheContractsDoNotAllow(t *testing.T) {
	for name, edit := range map[string]map[string][2]string{
		"the requirement moved": {"specs/shop.md": {`status "open"`, `status "pending"`}},
		"the contract moved":    {"contracts/openapi.yaml": {"enum: [open, paid]", "enum: [new, paid]"}},
	} {
		got, statuses, problems := runCon(t, conRepo(t, edit))
		// The orders dataset also lists the allowed values, so when only the API contract moves the
		// requirement still agrees with one contract and C3 reports the two contracts disagreeing.
		wantVerdicts(t, got, problems, map[string]string{map[bool]string{true: "C2", false: "C3"}[name == "the requirement moved"]: "fail"})
		if statuses["AC-shop-001"] != "Conflict" {
			t.Errorf("%s: statuses %v\n%s", name, statuses, problems)
		}
	}
}

func TestC3FindsAFieldTheTwoContractsTypeDifferently(t *testing.T) {
	got, statuses, problems := runCon(t, conRepo(t, map[string][2]string{
		"contracts/data.yaml": {"total_cents: {type: integer,", "total_cents: {type: real,"}}))
	wantVerdicts(t, got, problems, map[string]string{"C3": "fail", "C1": "pass"})
	if statuses["AC-shop-001"] != "Conflict" || !strings.Contains(problems, "total_cents is integer in the API contract and real in orders") {
		t.Errorf("statuses %v\n%s", statuses, problems)
	}
	got, _, problems = runCon(t, conRepo(t, map[string][2]string{"contracts/data.yaml": {"values: [open, paid]", "values: [open, closed]"}}))
	wantVerdicts(t, got, problems, map[string]string{"C3": "fail"})
}

func TestC7HoldsUpEveryRequirementThatCarriesADisputedField(t *testing.T) {
	// AC-shop-001 says "pending" where the contracts say open | paid. AC-shop-002 returns the same
	// status field and AC-shop-003 is tagged with the dataset that stores it.
	got, statuses, problems := runCon(t, conRepo(t, map[string][2]string{"specs/shop.md": {`status "open"`, `status "pending"`}}))
	wantVerdicts(t, got, problems, map[string]string{"C2": "fail", "C7": "fail"})
	for _, rid := range []string{"AC-shop-001", "AC-shop-002", "AC-shop-003"} {
		if statuses[rid] != "Conflict" {
			t.Errorf("%s is %s, want Conflict\n%s", rid, statuses[rid], problems)
		}
	}
	if !strings.Contains(problems, "C7 AC-shop-002: Carries status, which is in dispute (see C2 on AC-shop-001)") {
		t.Errorf("C7 doesn't say where the dispute is:\n%s", problems)
	}
	if strings.Contains(problems, "C7 AC-shop-001") {
		t.Errorf("the requirement that shows the disagreement is also held up by it:\n%s", problems)
	}
}

func TestC7ReachesARequirementThatQuotesAnotherValueOfTheField(t *testing.T) {
	// AC-shop-002 no longer returns the order, but its wording relies on the "paid" status.
	got, statuses, problems := runCon(t, conRepo(t, map[string][2]string{
		"specs/shop.md": {`status "open" and returns 201; an order for an unknown customer is rejected with 404.
- **AC-shop-002** (api: GET /orders/{id}): An order that does not exist returns 404.`,
			`status "pending" and returns 201; an order for an unknown customer is rejected with 404.
- **AC-shop-002** (api: GET /orders/{id}): An order that is "paid" returns 200; one that does not exist returns 404.`},
		"contracts/openapi.yaml": {`        "200":
          description: The order.
          content:
            application/json:
              schema: {$ref: "#/components/schemas/Order"}
`, `        "200": {description: The order.}
`}}))
	wantVerdicts(t, got, problems, map[string]string{"C2": "fail", "C7": "fail"})
	if statuses["AC-shop-002"] != "Conflict" || !strings.Contains(problems, `C7 AC-shop-002: Quotes "paid", a value of status`) {
		t.Errorf("statuses %v\n%s", statuses, problems)
	}
}

func TestC7FollowsATypeDisputeOnlyIntoItsDataset(t *testing.T) {
	// total_cents is typed differently in the orders dataset. AC-shop-003 is tagged with orders;
	// AC-shop-002 returns total_cents from the API but stores nothing.
	_, statuses, problems := runCon(t, conRepo(t, map[string][2]string{
		"contracts/data.yaml": {"total_cents: {type: integer,", "total_cents: {type: real,"}}))
	if statuses["AC-shop-003"] != "Conflict" || !strings.Contains(problems, "C7 AC-shop-003: Uses orders, where total_cents is in dispute (see C3 on AC-shop-001)") {
		t.Errorf("statuses %v\n%s", statuses, problems)
	}
	if statuses["AC-shop-002"] == "Conflict" {
		t.Errorf("AC-shop-002 is held up by a dispute about a dataset it doesn't use\n%s", problems)
	}
}

func TestC4FindsDesignThatNamesWhatTheContractLacks(t *testing.T) {
	for want, edit := range map[string][2]string{
		"DELETE /orders/{id}":    {"read back with `GET /orders/{id}`", "removed with `DELETE /orders/{id}`"},
		"status 410":             {"doesn't exist is 404", "doesn't exist is 404, and 410 when it was deleted"},
		"AC-shop-009":            {"AC-shop-001 comes first", "AC-shop-009 comes first"},
		"contracts/openapi.json": {"`contracts/openapi.yaml`", "`contracts/openapi.json`"},
	} {
		got, _, problems := runCon(t, conRepo(t, map[string][2]string{"PLAN.md": edit}))
		wantVerdicts(t, got, problems, map[string]string{"C4": "fail"})
		if !strings.Contains(problems, want) {
			t.Errorf("no mention of %s in:\n%s", want, problems)
		}
	}
}

// build adds a code commit for AC-shop-001, as an agent would.
func build(t *testing.T, dir string) {
	t.Helper()
	put(t, dir, "src/orders.txt", "create an order\n")
	gitIn(t, dir, "add", "-A")
	gitIn(t, dir, "-c", "commit.gpgsign=false", "-c", "user.email=agent@example.com", "commit", "-q", "-m",
		"feat(orders): create an order", "--trailer", "Refs: AC-shop-001")
}

func TestC5ResetsARequirementWhenItsContractChangesAfterTheBuild(t *testing.T) {
	dir := conRepo(t, nil)
	build(t, dir)
	got, statuses, problems := runCon(t, dir)
	wantVerdicts(t, got, problems, map[string]string{"C5": "pass"})
	text := strings.Replace(conAPI, "maxItems: 100", "maxItems: 50", 1)
	put(t, dir, "contracts/openapi.yaml", text)
	commitAll(t, dir, "docs(contract): fewer lines", "pat@example.com")
	got, statuses, problems = runCon(t, dir)
	wantVerdicts(t, got, problems, map[string]string{"C5": "fail"})
	if statuses["AC-shop-001"] != "Drift" || !strings.Contains(problems, "maxItems: 100 → 50") {
		t.Errorf("statuses %v\n%s", statuses, problems)
	}
	// A description is wording, not a promise: changing it resets nothing.
	put(t, dir, "contracts/openapi.yaml", strings.Replace(conAPI, "description: Created.", "description: The order was created.", 1))
	commitAll(t, dir, "docs(contract): reword", "pat@example.com")
	build2 := func() {
		put(t, dir, "src/orders.txt", "create an order\nwith at most 100 lines\n")
		gitIn(t, dir, "add", "-A")
		gitIn(t, dir, "-c", "commit.gpgsign=false", "-c", "user.email=agent@example.com", "commit", "-q", "-m",
			"fix(orders): limit lines", "--trailer", "Refs: AC-shop-001")
	}
	build2()
	got, _, problems = runCon(t, dir)
	wantVerdicts(t, got, problems, map[string]string{"C5": "pass"})
}

func TestC6FindsADesignChangeTheSpecDidNotFollow(t *testing.T) {
	dir := conRepo(t, nil)
	build(t, dir)
	put(t, dir, "PLAN.md", conPlan+"Orders are archived after a year.\n")
	commitAll(t, dir, "docs(plan): archive old orders", "pat@example.com")
	got, _, problems := runCon(t, dir)
	wantVerdicts(t, got, problems, map[string]string{"C6": "fail"})

	// A person says the change needs nothing from the spec.
	put(t, dir, "PLAN.md", conPlan+"Orders are archived after one year.\n")
	gitIn(t, dir, "add", "-A")
	gitIn(t, dir, "-c", "commit.gpgsign=false", "-c", "user.email=pat@example.com", "commit", "-q", "-m",
		"docs(plan): reword", "--trailer", "Spec-Impact: none")
	got, _, problems = runCon(t, dir)
	wantVerdicts(t, got, problems, map[string]string{"C6": "pass"})

	// An agent can't wave a design change through.
	put(t, dir, "PLAN.md", conPlan+"Orders are deleted after a year.\n")
	gitIn(t, dir, "add", "-A")
	gitIn(t, dir, "-c", "commit.gpgsign=false", "-c", "user.email=agent@example.com", "commit", "-q", "-m",
		"docs(plan): delete instead", "--trailer", "Spec-Impact: none")
	got, _, problems = runCon(t, dir)
	wantVerdicts(t, got, problems, map[string]string{"C6": "fail"})

	// The spec follows.
	put(t, dir, "specs/shop.md", conSpec+"- **AC-shop-004** (data: orders): Orders older than a year are deleted.\n")
	commitAll(t, dir, "docs(spec): delete old orders", "pat@example.com")
	got, _, problems = runCon(t, dir)
	wantVerdicts(t, got, problems, map[string]string{"C6": "pass"})
}
