"""Ledgerline with conflicts planted in what the people wrote, before the agent starts.

Each edit is a slip a person plausibly makes: one document is changed and the others are not. The
held-out tests keep judging by what was meant (the unedited problem), so an agent that follows the
wrong side builds something the oracle rejects while its own tests agree with its own code.

    expect   the checks that should fail on the seed, before any code exists
             ([] for a probe: the conflict is in the meaning of two sentences, and no check reads meaning)
"""


def edit(path, old, new):
    text = path.read_text()
    assert old in text, f"{path}: {old!r} not found"
    path.write_text(text.replace(old, new, 1))


def status_in_spec(repo):
    edit(repo / "specs/ledger.md", "after its earlier refunds is rejected with 409", "after its earlier refunds is rejected with 400")


def status_in_contract(repo):
    edit(repo / "contracts/openapi.yaml",
         '        "409":\n          description: The payment is larger than the order\'s unpaid balance.',
         '        "400":\n          description: The payment is larger than the order\'s unpaid balance.')


def value_in_contract(repo):
    edit(repo / "contracts/openapi.yaml", "enum: [open, paid]", "enum: [pending, paid]")


def value_in_spec(repo):
    edit(repo / "specs/ledger.md", 'The balance of the "cash" or "revenue" account', 'The balance of the "cash" or "income" account')


def type_across_contracts(repo):
    edit(repo / "contracts/data.yaml",
         "      payment_id:   {type: integer, nullable: false}\n      amount_cents: {type: integer, nullable: false}\n      refunded_on:",
         "      payment_id:   {type: integer, nullable: false}\n      amount_cents: {type: real,    nullable: false}\n      refunded_on:")


def status_in_plan(repo):
    edit(repo / "PLAN.md", "409 for a request that conflicts", "400 for a request that conflicts")


def operation_in_plan(repo):
    edit(repo / "PLAN.md", "## Order of work",
         "- **Cancelling.** An order with no payments is removed with `DELETE /orders/{order_id}`.\n\n## Order of work")


def meaning_between_requirements(repo):
    edit(repo / "specs/ledger.md", "the amount paid so far (payments minus refunds)", "the amount paid so far (its payments, ignoring refunds)")


def meaning_in_goal(repo):
    edit(repo / "GOAL.md", "All amounts are whole cents.", "All amounts are decimal dollars with two places.")


CONFLICTS = [
    {"name": "status-in-spec", "apply": status_in_spec, "expect": ["C1"], "between": "requirement ↔ API contract",
     "what": "AC-led-006 says an over-refund is rejected with 400; the contract documents 409."},
    {"name": "status-in-contract", "apply": status_in_contract, "expect": ["C1"], "between": "requirement ↔ API contract",
     "what": "The contract documents 400 for an over-payment; AC-led-004 says 409."},
    {"name": "value-in-contract", "apply": value_in_contract, "expect": ["C2"], "between": "requirement ↔ API contract",
     "what": 'The contract allows order status "pending" or "paid"; AC-led-002 says a new order is "open".'},
    {"name": "value-in-spec", "apply": value_in_spec, "expect": ["C2"], "between": "requirement ↔ API contract",
     "what": 'AC-led-008 names the account "income"; the contract allows "cash" or "revenue".'},
    {"name": "type-across-contracts", "apply": type_across_contracts, "expect": ["C3"], "between": "API contract ↔ data contract",
     "what": "refunds.amount_cents is real in the data contract and integer in the API contract."},
    {"name": "status-in-plan", "apply": status_in_plan, "expect": ["C4"], "between": "design ↔ API contract",
     "what": "The plan says conflicts return 400; no operation documents 400."},
    {"name": "operation-in-plan", "apply": operation_in_plan, "expect": ["C4"], "between": "design ↔ API contract",
     "what": "The plan describes DELETE /orders/{order_id}; the contract has no such operation."},
    {"name": "meaning-between-requirements", "apply": meaning_between_requirements, "expect": [],
     "between": "requirement ↔ requirement",
     "what": "Probe: AC-led-003 now says amount paid ignores refunds; AC-led-006 still says a refund lowers it."},
    {"name": "meaning-in-goal", "apply": meaning_in_goal, "expect": [], "between": "design ↔ contracts",
     "what": "Probe: the goal says amounts are decimal dollars; both contracts use integer cents."},
]

# What the agent run with `--variant conflicts` starts from: one of each kind an agent can act on.
AGENT_RUN = ["status-in-spec", "value-in-contract", "type-across-contracts", "meaning-between-requirements"]


def apply(repo):
    for c in CONFLICTS:
        if c["name"] in AGENT_RUN:
            c["apply"](repo)


# ---------------------------------------------------------------- drift: a person changes a document after the build

def contract_limit(repo):
    edit(repo / "contracts/openapi.yaml", "minItems: 1\n          maxItems: 100", "minItems: 1\n          maxItems: 50")


def data_nullability(repo):
    edit(repo / "contracts/data.yaml", "idempotency_key: {type: text,    nullable: true}", "idempotency_key: {type: text,    nullable: false}")


def design_changed(repo):
    edit(repo / "PLAN.md", "A payment and its two ledger entries are written in one transaction",
         "A payment is written first and its two ledger entries are written by a nightly job")


def design_typo(repo):
    edit(repo / "PLAN.md", "One HTTP service in front of one SQLite database file.",
         "One HTTP service in front of a single SQLite database file.")


def requirement_reworded(repo):
    edit(repo / "specs/ledger.md", "and is 0 before anything is recorded", "and is null before anything is recorded")


DRIFTS = [
    {"name": "contract-limit-tightened", "apply": contract_limit, "expect": ["C5"], "message": "docs(contract): allow at most 50 lines per order",
     "what": "A person lowers the most lines an order may have from 100 to 50 in the API contract. The build still accepts 100."},
    {"name": "data-contract-tightened", "apply": data_nullability, "expect": ["D5"], "message": "docs(contract): require an idempotency key",
     "what": "Reference: a person makes payments.idempotency_key not nullable in the data contract. The existing D5 check already catches this."},
    {"name": "design-changed", "apply": design_changed, "expect": ["C6"], "message": "docs(plan): write ledger entries in a nightly job",
     "what": "A person changes the plan (ledger entries move to a nightly job) and no requirement or contract follows."},
    {"name": "design-typo-acknowledged", "apply": design_typo, "expect": None, "trailer": "Spec-Impact: none",
     "message": "docs(plan): tidy the wording",
     "what": "Control: a person rewords the plan and marks the commit Spec-Impact: none. Nothing should fail."},
    {"name": "requirement-reworded", "apply": requirement_reworded, "expect": ["T8"], "message": "docs(spec): an empty balance is null",
     "what": "Reference: a person rewords a requirement. The existing T8 check already catches this."},
]
