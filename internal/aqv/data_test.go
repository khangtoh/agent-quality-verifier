package aqv

import (
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

const dataSpec = `# Spec
- **AC-shop-001** (data: customers): Customers are stored.
- **AC-shop-002** (api: GET /report; data: payments, daily_revenue): Revenue is reported per day.
`

const dataContract = `datasets:
  customers:
    kind: source
    x-requirements: [AC-shop-001]
    primary_key: [id]
    columns:
      id:    {type: integer, nullable: false}
      email: {type: text,    nullable: false}
  payments:
    kind: source
    x-requirements: [AC-shop-002]
    primary_key: [id]
    columns:
      id:           {type: integer, nullable: false}
      customer_id:  {type: integer, nullable: false}
      amount_cents: {type: integer, nullable: false}
      paid_on:      {type: text,    nullable: false}
    foreign_keys:
      - {columns: [customer_id], references: customers.id}
  daily_revenue:
    kind: derived
    x-requirements: [AC-shop-002]
    columns:
      day:         {type: text,    nullable: false, from: [payments.paid_on]}
      gross_cents: {type: integer, nullable: false, from: [payments.amount_cents]}
`

const dataSchema = `CREATE TABLE customers (id INTEGER PRIMARY KEY, email TEXT NOT NULL);
CREATE TABLE payments (id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES customers(id),
  amount_cents INTEGER NOT NULL, paid_on TEXT NOT NULL);
CREATE TABLE schema_migrations (version TEXT PRIMARY KEY);
`

const dataView = `CREATE VIEW daily_revenue AS
  SELECT paid_on AS day, CAST(SUM(amount_cents) AS INTEGER) AS gross_cents FROM payments GROUP BY paid_on;
`

const dataConfig = `specs: ["specs/*.md"]
code_paths: ["src/"]
protected_paths: ["specs/", "contracts/", ".aqv.yml"]
data:
  contract: contracts/data.yaml
  schema_from_code: "cat migrations/*.sql | sqlite3 {db} && {python} {aqv}/adapters/sqlite/schema.py {db}"
  ignore: ["schema_migrations"]
  migrations: ["migrations/*.sql"]
git:
  humans: ["pat@example.com"]
  protect: true
`

func gitIn(t *testing.T, dir string, args ...string) {
	t.Helper()
	if out, err := exec.Command("git", append([]string{"-C", dir}, args...)...).CombinedOutput(); err != nil {
		t.Fatalf("git %v: %v %s", args, err, out)
	}
}

func put(t *testing.T, dir, rel, text string) {
	t.Helper()
	os.MkdirAll(filepath.Dir(filepath.Join(dir, rel)), 0o755)
	if err := os.WriteFile(filepath.Join(dir, rel), []byte(text), 0o644); err != nil {
		t.Fatal(err)
	}
}

func commitAll(t *testing.T, dir, subject string, as ...string) {
	t.Helper()
	gitIn(t, dir, "add", "-A")
	args := []string{"-c", "commit.gpgsign=false"}
	if len(as) > 0 {
		args = append(args, "-c", "user.email="+as[0])
	}
	gitIn(t, dir, append(args, "commit", "-q", "-m", subject)...)
}

// dataRepo is a project whose database matches its data contract exactly.
func dataRepo(t *testing.T) string {
	t.Helper()
	if _, err := exec.LookPath("sqlite3"); err != nil {
		t.Skip("sqlite3 is not installed")
	}
	root, _ := filepath.Abs("../..")
	t.Setenv("AQV_HOME", root)
	dir := initRepo(t, map[string]string{"specs/shop.md": dataSpec, "contracts/data.yaml": dataContract,
		".aqv.yml": dataConfig, "migrations/0001_tables.sql": dataSchema, "migrations/0002_report.sql": dataView})
	gitIn(t, dir, "config", "user.name", "Pat")
	commitAll(t, dir, "chore: start")
	return dir
}

// runData runs the data checks (and H10) and returns each check's verdict and every failure line.
func runData(t *testing.T, dir, base string) (map[string]string, string) {
	t.Helper()
	eng, err := NewEngine(dir, Options{Base: base, Only: append(append([]string{}, DataCheckIDs...), ProtectCheck),
		Workdir: t.TempDir()})
	if err != nil {
		t.Fatal(err)
	}
	rep := eng.Run()
	verdicts := map[string]string{}
	for _, k := range rep.Map("checks").Keys() {
		verdicts[k] = rep.Map("checks").Str(k)
	}
	var lines []string
	for _, r := range maps(rep.Get("results")) {
		if v := r.Str("verdict"); v == "fail" || v == "error" || v == "not_covered" {
			lines = append(lines, r.Str("check")+" "+r.Str("subject")+": "+r.Str("summary"))
			for _, p := range strList(r.Map("details").Get("problems")) {
				lines = append(lines, "  "+p)
			}
		}
	}
	return verdicts, strings.Join(lines, "\n")
}

func wantVerdicts(t *testing.T, got map[string]string, problems string, want map[string]string) {
	t.Helper()
	for check, v := range want {
		if got[check] != v {
			t.Errorf("%s is %q, want %q\n%s", check, got[check], v, problems)
		}
	}
}

func TestDataChecksPassWhenTheDatabaseMatchesItsContract(t *testing.T) {
	dir := dataRepo(t)
	got, problems := runData(t, dir, "")
	wantVerdicts(t, got, problems, map[string]string{"D1": "pass", "D2": "pass", "D3": "pass", "D4": "skip",
		"D5": "pass", "D6": "pass", "D7": "pass", "H10": "pass"})
	if problems != "" {
		t.Errorf("a clean repo reports problems:\n%s", problems)
	}
}

func TestDataChecksAreOffWithoutADataSection(t *testing.T) {
	dir := initRepo(t, map[string]string{"specs/shop.md": "- **AC-shop-001**: Something.\n", ".aqv.yml": "specs: [\"specs/*.md\"]\n"})
	commitAll(t, dir, "chore: start")
	eng, err := NewEngine(dir, Options{Only: []string{"T1"}, Workdir: t.TempDir()})
	if err != nil {
		t.Fatal(err)
	}
	checks := eng.Run().Map("checks")
	if checks.Len() != len(CheckIDs) || checks.Has("D1") || checks.Has("H10") {
		t.Fatalf("got checks %v", checks.Keys())
	}
}

func TestD5CatchesShadowAndMissingData(t *testing.T) {
	dir := dataRepo(t)
	put(t, dir, "migrations/0003_extra.sql", "ALTER TABLE customers ADD COLUMN notes TEXT;\nCREATE TABLE audit_dump (id INTEGER PRIMARY KEY, body TEXT);\n")
	commitAll(t, dir, "feat: more data")
	got, problems := runData(t, dir, "")
	wantVerdicts(t, got, problems, map[string]string{"D5": "fail", "D6": "pass"})
	for _, want := range []string{"D5 audit_dump: Table audit_dump is in the database but not in the data contract",
		"D5 AC-shop-001: customers.notes is in the database but not in the contract"} {
		if !strings.Contains(problems, want) {
			t.Errorf("missing %q in:\n%s", want, problems)
		}
	}
}

func TestD5ComparesTypesNullabilityAndKeys(t *testing.T) {
	dir := dataRepo(t)
	put(t, dir, "migrations/0001_tables.sql", `CREATE TABLE customers (id INTEGER PRIMARY KEY, email TEXT);
CREATE TABLE payments (id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL, amount_cents REAL NOT NULL);
`)
	commitAll(t, dir, "feat: other tables")
	_, problems := runData(t, dir, "")
	for _, want := range []string{"daily_revenue is broken in the database: no such column: paid_on",
		"customers.email is nullable in the database, not null in the contract",
		"payments.amount_cents is real in the database, integer in the contract",
		"payments.paid_on is declared but missing from the database",
		"payments: foreign key customer_id -> customers.id is declared but not in the database"} {
		if !strings.Contains(problems, want) {
			t.Errorf("missing %q in:\n%s", want, problems)
		}
	}
}

func TestD6CatchesLineageTheContractDoesNotDeclare(t *testing.T) {
	dir := dataRepo(t)
	// Same numbers for any customer who paid, but now the report also depends on customers.
	put(t, dir, "migrations/0003_report.sql", `DROP VIEW daily_revenue;
CREATE VIEW daily_revenue AS
  SELECT p.paid_on AS day, CAST(SUM(p.amount_cents) AS INTEGER) AS gross_cents
  FROM payments p JOIN customers c ON c.id = p.customer_id GROUP BY p.paid_on;
`)
	commitAll(t, dir, "feat: report through customers")
	got, problems := runData(t, dir, "")
	wantVerdicts(t, got, problems, map[string]string{"D5": "pass", "D6": "fail"})
	for _, want := range []string{"daily_revenue reads customers.id, which its lineage doesn't declare",
		"daily_revenue reads payments.customer_id, which its lineage doesn't declare"} {
		if !strings.Contains(problems, want) {
			t.Errorf("missing %q in:\n%s", want, problems)
		}
	}
}

func TestD6CatchesADeclaredSourceThatIsNeverRead(t *testing.T) {
	dir := dataRepo(t)
	put(t, dir, "migrations/0003_report.sql", `DROP VIEW daily_revenue;
CREATE VIEW daily_revenue AS SELECT paid_on AS day, CAST(COUNT(*) AS INTEGER) AS gross_cents FROM payments GROUP BY paid_on;
`)
	commitAll(t, dir, "feat: count instead of sum")
	_, problems := runData(t, dir, "")
	if !strings.Contains(problems, "D6 AC-shop-002: daily_revenue declares payments.amount_cents as a source but never reads it") {
		t.Errorf("got:\n%s", problems)
	}
}

func TestD6DoesNotCoverADerivedTable(t *testing.T) {
	dir := dataRepo(t)
	put(t, dir, "migrations/0002_report.sql", "CREATE TABLE daily_revenue (day TEXT NOT NULL, gross_cents INTEGER NOT NULL);\n")
	commitAll(t, dir, "feat: report as a table")
	got, problems := runData(t, dir, "")
	wantVerdicts(t, got, problems, map[string]string{"D5": "pass", "D6": "not_covered"})
}

func TestD1D2D3ReadTheContract(t *testing.T) {
	dir := dataRepo(t)
	put(t, dir, "contracts/data.yaml", strings.NewReplacer(
		"x-requirements: [AC-shop-001]", "x-requirements: [AC-shop-999]",
		"from: [payments.amount_cents]", "from: [payments.total]",
		"email: {type: text,    nullable: false}", "email: {type: varchar}").Replace(dataContract))
	commitAll(t, dir, "docs: contract", "pat@example.com")
	got, problems := runData(t, dir, "")
	wantVerdicts(t, got, problems, map[string]string{"D1": "fail", "D2": "fail", "D3": "fail"})
	for _, want := range []string{"D1 AC-shop-001: customers doesn't list AC-shop-001 in x-requirements",
		"D2 customers: customers references unknown or retired requirement(s): AC-shop-999",
		"customers.email: nullable must be true or false", "customers.email: type must be one of",
		"daily_revenue.gross_cents: from payments.total is not a declared dataset.column"} {
		if !strings.Contains(problems, want) {
			t.Errorf("missing %q in:\n%s", want, problems)
		}
	}
}

func TestD3CatchesLineageThatLoops(t *testing.T) {
	ds := parseDatasets(mustYAML(t, `datasets:
  a:
    kind: derived
    columns: {x: {type: integer, nullable: false, from: [b.y]}}
  b:
    kind: derived
    columns: {y: {type: integer, nullable: false, from: [a.x]}}
`))
	problems := strings.Join(lintDatasets(ds), "\n")
	if !strings.Contains(problems, "a: its lineage loops back to itself") {
		t.Errorf("got:\n%s", problems)
	}
}

func mustYAML(t *testing.T, text string) any {
	t.Helper()
	doc, err := loadYAML(text)
	if err != nil {
		t.Fatal(err)
	}
	return doc
}

func TestD4AllowsABreakingDataChangeOnlyWithASpecChange(t *testing.T) {
	dir := dataRepo(t)
	gitIn(t, dir, "checkout", "-q", "-b", "feat/AC-shop-001-rename")
	put(t, dir, "contracts/data.yaml", strings.Replace(dataContract, "email: {type: text,    nullable: false}",
		"email: {type: text,    nullable: true}", 1))
	put(t, dir, "migrations/0003_email.sql", "ALTER TABLE customers RENAME TO customers_old;\n"+
		"CREATE TABLE customers (id INTEGER PRIMARY KEY, email TEXT);\nDROP TABLE customers_old;\n")
	commitAll(t, dir, "feat: optional email", "pat@example.com")
	got, problems := runData(t, dir, "main")
	wantVerdicts(t, got, problems, map[string]string{"D4": "fail"})
	if !strings.Contains(problems, "customers.email: changed from not null to nullable") {
		t.Errorf("got:\n%s", problems)
	}
	put(t, dir, "specs/shop.md", strings.Replace(dataSpec, "Customers are stored.", "Customers are stored; email is optional.", 1))
	commitAll(t, dir, "docs(spec): email is optional", "pat@example.com")
	got, problems = runData(t, dir, "main")
	wantVerdicts(t, got, problems, map[string]string{"D4": "pass"})
}

func TestD7CatchesAnEditedMigration(t *testing.T) {
	dir := dataRepo(t)
	// On a branch: a new migration reworked before it merges is fine, an old one edited is not.
	gitIn(t, dir, "checkout", "-q", "-b", "feat/AC-shop-001-more")
	put(t, dir, "migrations/0003_new.sql", "CREATE INDEX payments_day ON payments(paid_on);\n")
	commitAll(t, dir, "feat: index")
	put(t, dir, "migrations/0003_new.sql", "CREATE INDEX payments_by_day ON payments(paid_on);\n")
	commitAll(t, dir, "fix: index name")
	got, problems := runData(t, dir, "main")
	wantVerdicts(t, got, problems, map[string]string{"D7": "pass"})

	put(t, dir, "migrations/0001_tables.sql", dataSchema+"-- tidied\n")
	commitAll(t, dir, "chore: tidy")
	got, problems = runData(t, dir, "main")
	wantVerdicts(t, got, problems, map[string]string{"D7": "fail"})
	if !strings.Contains(problems, "migrations/0001_tables.sql was edited after it reached main") {
		t.Errorf("got:\n%s", problems)
	}

	// Merged: the mainline shows the branch as one step, and still shows the edit.
	gitIn(t, dir, "checkout", "-q", "main")
	gitIn(t, dir, "-c", "commit.gpgsign=false", "merge", "-q", "--no-ff", "feat/AC-shop-001-more", "-m", "Merge branch 'feat/AC-shop-001-more'")
	got, problems = runData(t, dir, "")
	wantVerdicts(t, got, problems, map[string]string{"D7": "fail"})
	if !strings.Contains(problems, "edits migrations/0001_tables.sql") || strings.Contains(problems, "0003_new.sql") {
		t.Errorf("got:\n%s", problems)
	}
}

func TestH10CatchesAnAgentChangingAProtectedFile(t *testing.T) {
	dir := dataRepo(t)
	put(t, dir, "migrations/0003_extra.sql", "ALTER TABLE customers ADD COLUMN notes TEXT;\n")
	put(t, dir, "contracts/data.yaml", strings.Replace(dataContract, "      email: {type: text,    nullable: false}\n",
		"      email: {type: text,    nullable: false}\n      notes: {type: text,    nullable: true}\n", 1))
	commitAll(t, dir, "feat: notes", "agent@example.com")
	got, problems := runData(t, dir, "")
	// The agent made the contract agree with its database, so D5 passes; H10 is what catches it.
	wantVerdicts(t, got, problems, map[string]string{"D5": "pass", "H10": "fail"})
	if !strings.Contains(problems, "by agent@example.com changes contracts/data.yaml") {
		t.Errorf("got:\n%s", problems)
	}
}

func TestSpecDataTag(t *testing.T) {
	reqs := parseSpec("s.md", "- **AC-a-001** (api: GET /x; data: orders, order_lines): Text.\n- **AC-a-002** (data: Bad Name): Text.\n")
	if got := strings.Join(reqs[0].DataSets, ","); got != "orders,order_lines" || len(reqs[0].APIOps) != 1 || len(reqs[0].TagErrors) != 0 {
		t.Errorf("got %q, %v, %v", got, reqs[0].APIOps, reqs[0].TagErrors)
	}
	if len(reqs[1].TagErrors) != 1 {
		t.Errorf("got %v", reqs[1].TagErrors)
	}
}
