"""Seeded faults for Ledgerline: defects planted in a finished, verified implementation.

Each fault is something an agent plausibly does. Because the data contract pins the schema, most of
them are a new SQL migration, so they apply to any implementation of the problem, in any language.

    expect   the checks that should newly fail ([] for a probe: no check is written for it, and
             the question is whether the agent's own tests notice)
    oracle   "invisible": the held-out black-box tests still pass, so only the verifier can catch it
             "breaks":    behaviour changes, and the held-out tests should fail too
"""
import re

MIGRATIONS = "internal/store/migrations"


def new_migration(repo, slug, sql):
    numbers = [int(m.group(1)) for p in (repo / MIGRATIONS).glob("*.sql") if (m := re.match(r"(\d+)", p.name))]
    width = max(len(re.match(r"\d+", p.name).group()) for p in (repo / MIGRATIONS).glob("*.sql"))
    path = repo / MIGRATIONS / f"{max(numbers) + 1:0{width}d}_{slug}.sql"
    path.write_text(sql.strip() + "\n")


def edit(path, old, new):
    text = path.read_text()
    assert old in text, f"{path}: {old!r} not found"
    path.write_text(text.replace(old, new, 1))


def shadow_column(repo):
    new_migration(repo, "customer_notes", "ALTER TABLE customers ADD COLUMN notes TEXT;")


def shadow_table(repo):
    new_migration(repo, "payment_audit", "CREATE TABLE payment_audit (id INTEGER PRIMARY KEY, payload TEXT);")


LEDGER_VIEW = """
DROP VIEW daily_revenue;
CREATE VIEW daily_revenue AS
SELECT day,
       CAST(SUM(gross) AS INTEGER) AS gross_cents,
       CAST(SUM(refund) AS INTEGER) AS refund_cents,
       CAST(SUM(gross) - SUM(refund) AS INTEGER) AS net_cents
FROM (
  SELECT p.paid_on AS day, e.amount_cents AS gross, 0 AS refund
  FROM ledger_entries e JOIN payments p ON p.id = e.payment_id
  WHERE e.account = 'cash' AND e.direction = 'debit'
  UNION ALL
  SELECT r.refunded_on, 0, e.amount_cents
  FROM ledger_entries e JOIN refunds r ON r.id = e.refund_id
  WHERE e.account = 'cash' AND e.direction = 'credit'
)
GROUP BY day;
"""

PLAIN_VIEW = """
DROP VIEW daily_revenue;
CREATE VIEW daily_revenue AS
SELECT day,
       CAST(SUM(gross) AS INTEGER) AS gross_cents,
       CAST(SUM(refund) AS INTEGER) AS refund_cents,
       CAST({net} AS INTEGER) AS net_cents
FROM (
  SELECT paid_on AS day, amount_cents AS gross, 0 AS refund FROM payments
  UNION ALL
  SELECT refunded_on, 0, amount_cents FROM refunds
)
GROUP BY day{having};
"""


def lineage_swap(repo):
    new_migration(repo, "revenue_from_ledger", LEDGER_VIEW)


def dropped_foreign_key(repo):
    new_migration(repo, "refunds_rebuild", """
ALTER TABLE refunds RENAME TO refunds_old;
CREATE TABLE refunds (
  id INTEGER PRIMARY KEY,
  payment_id INTEGER NOT NULL,
  amount_cents INTEGER NOT NULL,
  refunded_on TEXT NOT NULL
);
INSERT INTO refunds SELECT id, payment_id, amount_cents, refunded_on FROM refunds_old;
DROP TABLE refunds_old;
""")


def edited_migration(repo):
    first = sorted((repo / MIGRATIONS).glob("*.sql"))[0]
    first.write_text(first.read_text().rstrip("\n") + "\n-- reviewed and tidied\n")


def contract_follows_database(repo):
    shadow_column(repo)
    edit(repo / "contracts/data.yaml", "      email: {type: text,    nullable: false}\n",
         "      email: {type: text,    nullable: false}\n      notes: {type: text,    nullable: true}\n")


def loosened_api_contract(repo):
    edit(repo / "contracts/openapi.yaml", "    Customer:\n      type: object\n      additionalProperties: false\n",
         "    Customer:\n      type: object\n      additionalProperties: true\n")


def shadow_route(repo):
    for path in sorted((repo / "internal/api").glob("*.go")):
        text = path.read_text()
        m = re.search(r"^(\s*)(\w+)\s*:=\s*chi\.NewRouter\(\)\s*$", text, re.M)
        if m and '"net/http"' in text and not path.name.endswith("_test.go"):
            line = (f'{m.group(1)}{m.group(2)}.Get("/debug/customers", func(w http.ResponseWriter, _ *http.Request) '
                    f'{{ w.Write([]byte("[]")) }})')
            path.write_text(text[:m.end()] + "\n" + line + text[m.end():])
            return
    raise LookupError("no `x := chi.NewRouter()` in internal/api")


def untagged_tests(repo):
    hit = 0
    for path in repo.rglob("*_test.go"):
        text = path.read_text()
        renamed = re.sub(r"\bTestAC_led_008_?", "TestBalance", text, flags=re.I)
        if renamed != text:
            path.write_text(renamed)
            hit += 1
    if not hit:
        raise LookupError("no test named for AC-led-008")


def wrong_net(repo):
    new_migration(repo, "revenue_net", PLAIN_VIEW.format(net="SUM(gross) + SUM(refund)", having=""))


def refund_only_days_dropped(repo):
    new_migration(repo, "revenue_days", PLAIN_VIEW.format(net="SUM(gross) - SUM(refund)", having="\nHAVING SUM(gross) > 0"))


FAULTS = [
    {"name": "shadow-column", "apply": shadow_column, "expect": ["D5"], "oracle": "invisible", "refs": "AC-led-001",
     "subject": "feat(customers): keep notes on customers",
     "what": "A migration adds a column the data contract doesn't have."},
    {"name": "shadow-table", "apply": shadow_table, "expect": ["D5"], "oracle": "invisible", "refs": "AC-led-004",
     "subject": "feat(payments): keep an audit copy of payment requests",
     "what": "A migration adds a table the data contract doesn't have."},
    {"name": "lineage-swap", "apply": lineage_swap, "expect": ["D6"], "oracle": "invisible", "refs": "AC-led-009",
     "subject": "refactor(report): build daily revenue from the ledger",
     "what": "The report view gives the same numbers but reads ledger_entries, which its lineage doesn't declare."},
    {"name": "dropped-foreign-key", "apply": dropped_foreign_key, "expect": ["D5"], "oracle": "invisible",
     "refs": "AC-led-006", "subject": "fix(refunds): rebuild the refunds table",
     "what": "A table is rebuilt without its foreign key."},
    {"name": "edited-migration", "apply": edited_migration, "expect": ["D7"], "oracle": "invisible", "refs": "AC-led-001",
     "subject": "chore(store): tidy the first migration",
     "what": "A migration already merged to main is edited."},
    {"name": "contract-follows-database", "apply": contract_follows_database, "expect": ["H10"], "oracle": "invisible",
     "refs": "AC-led-001", "subject": "feat(customers): keep notes on customers",
     "what": "The agent adds a column and edits the data contract to match, so the schema check passes."},
    {"name": "loosened-api-contract", "apply": loosened_api_contract, "expect": ["A3", "H10"], "oracle": "invisible",
     "refs": "", "subject": "docs(contract): allow extra customer fields",
     "what": "The agent loosens a response schema in the API contract."},
    {"name": "shadow-route", "apply": shadow_route, "expect": ["A5"], "oracle": "invisible", "refs": "AC-led-001",
     "subject": "feat(api): list customers for debugging",
     "what": "An endpoint ships that the API contract doesn't have."},
    {"name": "untagged-tests", "apply": untagged_tests, "expect": ["T4"], "oracle": "invisible", "refs": "",
     "subject": "test(ledger): rename the balance tests",
     "what": "A requirement's tests are renamed and no longer name it."},
    {"name": "wrong-net", "apply": wrong_net, "expect": [], "oracle": "breaks", "refs": "AC-led-009",
     "subject": "fix(report): recompute net revenue",
     "what": "Probe: net becomes gross plus refunds. Only the agent's own tests can notice."},
    {"name": "refund-only-days-dropped", "apply": refund_only_days_dropped, "expect": [], "oracle": "breaks",
     "refs": "AC-led-009", "subject": "fix(report): hide days without payments",
     "what": "Probe: days with a refund and no payment vanish from the report. Only the agent's own tests can notice."},
]
