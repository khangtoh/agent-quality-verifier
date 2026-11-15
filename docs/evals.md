# Evaluating the verifier

The demo shows that each check fires on the attack written for it. That tests the checks one at a
time, on scripted mistakes. It does not show that the verifier is *effective*: that when a real
agent builds real software from a spec, the verifier's picture of the work is true.

This document says what "effective" means, lists the evals that measure it, and describes the ones
that are built: a real agent (Claude Code or Codex) builds a spec'd service in Go while the
verifier watches, and the verifier's verdicts are then compared with held-out acceptance tests and
with faults planted on purpose.

Scope: the evals target **Go and Rust** implementations. The Go stack runs end to end. The Rust
stack is not written yet ([what's missing](#what-is-not-built-yet)).

## What "effective" means

The verifier makes one promise per requirement: **Sync means it is built, proven and honours its
contracts.** Five questions test that promise.

| # | Question | Failure it would show | Measured by |
|---|---|---|---|
| 1 | When the verifier says Sync, does the software work? | **False assurance**: Sync, but the behaviour is wrong | Held-out acceptance tests (E1) |
| 2 | When something is wrong, does a check fail? | A miss: a defect ships under a green report | Seeded faults (E2), red-team agent (E5) |
| 3 | When a check fails, is something really wrong? | A false alarm: the agent is sent to fix what isn't broken | Known-good runs (E3), triage of "unproven but working" (E1) |
| 4 | Does hearing from the verifier make the agent's result better? | The guardrail costs time and changes nothing | Guarded against blind runs (E4) |
| 5 | When the documents disagree with each other, or move after the build, does the verifier say so? | The whole build follows the wrong document under a green report | Planted conflicts and drift (E9), an agent on a conflicted spec (E10) |

Question 1 matters most. A verifier that sometimes cries wolf costs time; one that gives false
assurance defeats the reason for having it.

## The evals

| ID | Eval | Ground truth | Needs an agent run | Status |
|---|---|---|---|---|
| E1 | **Verdict against oracle.** An agent builds the problem; each requirement's status is compared with held-out acceptance tests the agent never saw. | Held-out tests, written from the spec and contracts | Yes | Built: `evals/run.py` |
| E2 | **Seeded faults.** Known defects are planted in a finished, verified build, one per copy. Did the expected check newly fail? | Known by construction | No (reuses a finished run) | Built: `evals/faults.py` |
| E3 | **False-alarm rate.** On builds where the oracle passes everything, how many checks fail, and why? | Oracle plus a person's triage of each failure | Yes | Partly: E1 reports "unproven but working"; triage is manual |
| E4 | **Guarded against blind.** The same problem, agent and model, with and without the verifier's feedback. Compare oracle pass rate, false assurance, time and commits. | Oracle | Yes, several per arm | Harness built (`--arm`); needs repeated runs |
| E5 | **Red-team agent.** A second agent is told to plant a described defect and keep every check green. | Oracle, and the defect's description | Yes | Not built |
| E6 | **Spec change mid-run.** A person changes a requirement after it is built. Does its status drop to Drift, and does the agent bring it back to Sync? | The changed requirement's held-out tests | Yes | Not built |
| E7 | **Determinism.** The same commit checked twice, and on two machines, gives the same results.json. | Itself | No | Not built for agent runs (the demo's parity checks cover the scripted repos) |
| E8 | **Cost.** Seconds per check, per commit; how far behind the agent the live view runs. | Clock | Yes | Partly: the watch log has the times |
| E9 | **Conflicting documents.** A person's slip is planted in the spec, a contract or the plan, one per workspace, before any code exists. Does the verifier say so before an agent builds on it? And when a person changes a document after the build, do the affected requirements stop being Sync? | Known by construction | No | Built: `evals/conflicts.py` |
| E10 | **Agent on a conflicted spec.** An agent builds from a spec that disagrees with itself. Compare what the verifier says about the result, with and without the consistency checks, against the oracle (which holds what was meant). | Oracle | Yes | Built: `--variant conflicts`, `--variant conflicts-pushon` |

E1 and E2 answer different things and need each other. E1 uses mistakes a real agent actually made,
but there may be few of them. E2 guarantees a mistake of each kind, but each is one we thought of.

### Reading E1

Each requirement lands in one of four cells:

| | Oracle: works | Oracle: broken |
|---|---|---|
| **Verifier: Sync** | Confirmed | **False assurance** |
| **Verifier: not Sync** | Unproven but working | Caught |

- **False assurance** is the number to drive to zero. Each case is a gap in the checks or in the
  agent's tests, and should end up as a new seeded fault.
- **Unproven but working** is not automatically a false alarm. The verifier asks for proof, not only
  behaviour: code with no tagged test works and is still unproven. Each case needs one look: was the
  evidence really missing (the verifier is right), or did a check misfire (a false alarm)?

The oracle judges the requirement together with the contracts and the plan (for example that a body
outside the contract's limits gets a 422). It is black-box: it drives the built service over HTTP
and reads the database file. It knows nothing of the implementation, so the same oracle judges a Go
build and a Rust build.

### Reading E2

A planted fault is **caught** when every check it names newly fails, compared with the same build
before the fault. Faults come in two kinds:

- **Targeted**: a check exists for it (a column the data contract doesn't have, a contract edited by
  the agent). All of them should be caught.
- **Probes**: a behaviour change with no check of its own. Whether it is caught depends on the
  agent's own tests, so a missed probe measures how much the verifier's promise rests on test
  quality that T6 and T7 could not see.

Each fault also records whether the held-out tests still pass. A fault the verifier catches while
black-box tests pass is something only this kind of checking can find.

## The problem: Ledgerline

`evals/problems/ledger/` is one real-world problem chosen because it leans on both guardrails.

A shop's back office: customers, orders, part-payments with idempotency keys, refunds, a
double-entry ledger, account balances and a daily revenue report. Other teams call the HTTP API and
finance reads the database, so the **OpenAPI contract** and the **data contract** are both
published promises.

| File | What it is | Who owns it |
|---|---|---|
| `GOAL.md`, `PLAN.md` | What to build and the shape of the solution | People |
| `spec/specs/ledger.md` | 9 requirements, each tagged with its API operations and datasets | People |
| `spec/contracts/openapi.yaml` | 7 operations, closed response schemas, documented errors | People |
| `spec/contracts/data.yaml` | 6 source tables and 1 derived view with column-level lineage | People |
| `stacks/go/` | `.aqv.yml`, `AGENTS.md`, and the small helpers the checks call | People |
| `oracle/` | 24 held-out acceptance tests, named after the requirements | Never shown to the agent |
| `faults.py` | 11 seeded faults | Never shown to the agent |

The spec and both contracts are **given** to the agent and protected: the agent builds to them and
may not edit them. That is what lets one oracle judge any implementation. (The other mode, where
the agent writes the contract and a person reviews it, is what `aqv init` sets up; it is not what
this eval measures.)

A requirement line now carries both tags:

```markdown
- **AC-led-004** (api: POST /orders/{order_id}/payments; data: payments): A payment records ...
```

## The data guardrail (D1–D7)

The API checks (A1–A7) had no counterpart for data. These do the same job for the database. They
run only when `.aqv.yml` has a `data:` section, so existing projects and the demo are unchanged.

| ID | Check | How | Mirrors |
|---|---|---|---|
| D1 | Every data requirement has a dataset | `(data: payments)` in the spec against `x-requirements` in the data contract | A1 |
| D2 | Every dataset references a requirement | `x-requirements` on every dataset names a live requirement | A2 |
| D3 | The data contract is complete and consistent | Every column has a type and nullability, source tables have a primary key, every derived column says what it is built from, lineage resolves and doesn't loop | A3 |
| D4 | No breaking data change unless the spec changed | Removed or retyped columns, changed keys or lineage, against the base branch | A4 |
| D5 | The database has exactly the declared schema | Build a fresh database the project's own way, read back tables, columns, types, nullability, keys; anything undeclared or missing fails | A5 |
| D6 | Derived data reads only its declared sources | For a view, SQLite's own authorizer reports each column the view reads; compared with the `from:` lists in both directions | A6 |
| D7 | Merged migrations are never edited | A migration that has reached the base branch is unchanged | H7 |
| H10 | Protected files are changed only by people | No agent commit touches `protected_paths` (on with `git.protect: true`) | |

A requirement whose D1, D5 or D6 fails gets the status **Data**, next to **Contract** for the API.
In the report, data requirements show a fifth vital sign.

How D6 sees lineage: `adapters/sqlite/schema.py` asks SQLite to compile `SELECT * FROM <view>` with
an authorizer callback installed. SQLite calls it for every table and column the view's own
definition reads. No SQL is parsed by the verifier, and a view built on another view reports the
view it reads, not what lies beneath.

Limits:

- **SQLite only.** The reader is a Python script using the standard library; other databases need
  their own reader that prints the same JSON.
- **Lineage is observed for views only.** A derived *table* is filled by application code, which the
  verifier can't follow without an adapter per database driver. D6 reports **not covered** for it.
- **Lineage is per dataset, not per column.** The contract declares sources per column; the check
  compares the union.
- **Schema, not rows.** Nothing checks the values in the tables (ranges, enumerations, balanced
  ledger entries). The agent's tests and T7 carry that.
- **H10 trusts the author address.** An agent that commits under a person's address is not caught
  by H10; signed commits (H9) with separate keys are what would tell them apart.

## The consistency guardrail (C1–C7, A8)

Every check above compares the code with **one** document. That leaves a hole: when two documents
disagree, an agent builds to one of them, writes tests that agree with its own code, and every
check passes on a build that is wrong as a whole. The same hole opens over time, when a person
changes a contract or the plan after the build and nothing notices.

These checks look for the disagreement itself. They run only when `.aqv.yml` has a `consistency:`
section.

```yaml
consistency:
  design: ["PLAN.md", "GOAL.md"]   # the documents the requirements were written from
```

| ID | Check | Between | How |
|---|---|---|---|
| C1 | Status codes a requirement names are in the API contract | requirement ↔ API contract | "rejected with 409" needs a 409 response on one of the requirement's operations |
| C2 | Values a requirement quotes are allowed by the contracts | requirement ↔ both contracts | A word in double quotes is a literal value: it must be in an `enum` of the requirement's operations, or in a column's `values:` in the data contract |
| C3 | The API and data contracts agree on shared fields | API contract ↔ data contract | A field with the same name in a requirement's operations and in its datasets must have a matching type and the same allowed values |
| C4 | The design names only what the contracts have | design ↔ contracts | Operations, status codes, requirement IDs and file paths named in the design documents must exist |
| C5 | Results reset when the requirement's contract changes | contract ↔ code, over time | T8 for the contracts: if a requirement's operations or datasets change after its last code or test commit, it is Drift. Descriptions and examples don't count; the changed keys are named |
| C6 | The spec followed the last design change | design ↔ spec, over time | A design document that changes after code exists needs a requirement or contract to change with it, or a person's `Spec-Impact: none` trailer on the commit |
| C7 | The requirement relies on nothing the documents disagree about | one conflict → every requirement it reaches | When C2 or C3 finds a field in dispute, every other requirement that carries it is held up too: its operations return the field, its wording quotes another of the field's values, or it is tagged with the dataset whose column is disputed |
| A8 | The tagged tests saw every status the requirement names | requirement ↔ test evidence | If the requirement says 409, a tagged test must have received a 409 from one of its operations. Passing tests that never saw the named outcome prove something else |

A requirement that fails C1, C2, C3 or C7 gets the status **Conflict**. It outranks every other
status, including Missing: a requirement that contradicts its contract should be settled before
anyone builds it, and nothing built on it can be trusted. Conflicts are **for a person**; the
agent may not edit either side.

C7 exists because a conflict is rarely about one requirement. In the run described under "Results
so far", the spec called a new order "open" and the contract called it "pending". Only two
requirements use the word, but two more return or depend on the same field, and all four failed
the held-out tests. Whichever way a person settles it, what those requirements return may change.

Limits:

- **No check reads meaning.** C1 and C2 rest on two writing conventions: a status code follows
  "with", "returns" or "status", and a literal value is in double quotes. Two sentences that
  contradict each other in plain words ("amount paid ignores refunds" against "a refund lowers the
  amount paid") are not found. E9 keeps two such probes so the miss stays visible.
- **C7 follows a field, not a behaviour.** It names the disputed field from the requirement's own
  wording ("status") or, failing that, from every field its operations restrict. A status-code
  conflict (C1) is not spread to other requirements, and a requirement that depends on the
  disputed field without returning it or quoting one of its values is not reached.
- **C3 matches fields by name.** A field stored under another name, or a date held as text in one
  place and as a number in the other on purpose, is not understood.
- **C4 reads only what is mechanical** in a design document. What the plan *says* about behaviour
  is not checked against the requirements.
- **C6 can't tell a real design change from a reworded sentence.** A person has to say so with the
  trailer; an agent's trailer does not count.
- **A8 covers status codes only**, and only for tests that send their requests through the capture
  helper.

## Reviewing the result: `review.html`

`aqv check` writes `review.html` next to `report.html`. `report.html` shows the spec as a document;
`review.html` is laid out for an engineer deciding whether to accept the work:

1. **The verdict**: ready, not ready, or blocked on a person, with how many checks could not run.
2. **Who must act**: decisions for a person, problems for the agent, not started, proven.
3. **Decisions for a person**: each conflict with both sides next to each other (what the
   requirement says, what the contract says) and what settles it.
4. **For the agent to fix**: each failing requirement with the failing checks' own words.
5. **Requirements**: one row each, with the facts behind the status: commits and surviving lines,
   tagged tests, lines run, broken versions caught, responses checked, datasets. Filter by who must
   act, or by any word.
6. **Evidence**: per requirement, every check that looked at it, its history, and the tests.
7. **All checks**, grouped by what they protect. Not covered is shown as not covered.

`aqv render DIR` rewrites the pages from results that already exist, without checking again.

## The verifier during the run: `aqv watch`

```bash
bin/aqv watch --repo path/to/workspace --out path/to/live [--feedback path/to/workspace/.aqv-live/state.md]
```

The watcher is a separate process the agent doesn't control. Each time the checked-out branch moves
to a new commit, it checks that commit in its own worktree (the agent's uncommitted files are never
tested or touched) and rewrites:

| File | For |
|---|---|
| `live.html` | A person: state and health now, and a grid of every requirement's status commit by commit. Reloads itself. |
| `state.md` | The agent, or a person in a terminal: statuses, regressions, and what needs attention |
| `state.json`, `timeline.jsonl` | Programs: the latest snapshot, and all of them |
| `snap/<n>-<sha>/` | The full report for each checked commit |

- **State** is where each requirement stands: 4 of 9 proven, 1 weak, 4 not started.
- **Health** is whether the guardrails hold for what has been built. A requirement nobody has
  started is not a health problem; a broken one is. Health is `healthy`, `failing` (a check fails
  on built work, or a requirement is worse than it was on main), or `blocked` (a check couldn't run).

`live.html` shows the state bar, what needs someone now (a person's items first), requirements
proven over time, and a grid of every requirement's status at every checked commit. Each square
opens that commit's `review.html` at that requirement.

A conflict changes what the agent is told. `state.md` lists it under **Needs a person**, with the
instruction not to pick a side and not to build the requirements it names.

`aqv watch --replay <timeline.jsonl>` checks the commits of a recorded run again with the current
verifier. That is how a run made with an older verifier is judged by a newer one.

T7 and A7 are left out of each commit's check because they are slow; they run in the final check.

It is hooked into the agent in two ways, both set up by the eval harness:

- **Any agent:** with `--feedback`, `state.md` is also written inside the workspace, and `AGENTS.md`
  tells the agent to read it after each merge.
- **Claude Code:** a `Stop` hook refuses to let the agent finish while the state is not healthy and
  fully proven, and hands it `state.md` as the reason. It gives up after 6 refusals so a stuck agent
  still ends.

## Running it

```bash
scripts/setup.sh                                  # once: bin/aqv, .venv, Spectral, oasdiff, gotestsum
.venv/bin/python evals/run.py run --problem ledger --stack go --agent claude --arm guarded
.venv/bin/python evals/run.py run --problem ledger --stack go --agent codex  --arm blind
.venv/bin/python evals/faults.py --run evals/runs/<name>
.venv/bin/python evals/conflicts.py --run evals/runs/<a finished, clean run>
.venv/bin/python evals/run.py run --variant conflicts-pushon --arm blind     # an agent on a conflicted spec
.venv/bin/python evals/run.py score --run evals/runs/<name> --skip C1,C2,C3,C4,C5,C6,C7,A8 --label before
.venv/bin/python evals/keep.py <name>               # copy the run's results into evals/results/ to commit
```

`run` creates a workspace (the spec committed and signed by a person, then the agent's identity),
starts the watcher, runs the agent headless, runs the full check on `main`, runs the oracle, and
writes `score.md`. Open `evals/runs/<name>/live/live.html` while it runs. `evals/runs/` is not
committed: it holds each run's workspace (a git repository), its signing key and its build output.
`evals/keep.py` copies what is worth keeping to `evals/results/<name>/`: the scores, the final
check's pages and `results.json`, the watcher's timeline and per-commit pages, and the agent's final
message.

The agent runs on your machine with file and shell access inside the workspace, and uses your
agent account. A Ledgerline run takes on the order of an hour.

## Results so far

One run, on 2026-11-15: Claude Code, guarded arm, Go stack (`ledger-go-claude-guarded-1`). One run
shows the harness works end to end; it is not a measurement of the verifier.

**E1, verdict against oracle**

| | Oracle: works | Oracle: broken |
|---|---|---|
| **Verifier: Sync** | 9 confirmed | 0 false assurance |
| **Verifier: not Sync** | 0 unproven but working | 0 caught |

- The agent finished in 38.7 minutes with 14 commits on main and 99 tests of its own.
- All 24 held-out tests pass, and every check passes in the final full check, T7 and A7 included
  (A4 and D4 skip with no base to compare; H7 is not covered).
- The watcher checked 33 commits. Requirements proven went 0 → 9 by the 25th check, with no
  regression on main.
- Health was `failing` on 5 of 33 checks, all on feature branches and none on main:
  - 3 were the requirement in progress, whose route was not yet served (A5, A6). That is true but
    not useful mid-branch.
  - 1 was a real finding: a commit over 400 lines (H5); it was gone by the next check.
  - 1 was the seed's fault: the route helper imports a package the agent had not created yet.
- The Stop hook never fired, because the agent was already fully proven when it stopped. It is
  still untested in practice.

Because the agent made no mistake that survived to main, this run says nothing about false
assurance on real mistakes. The "caught" and "false assurance" cells are empty for lack of
defects, not because the verifier was tested and held.

**E2, seeded faults** on the same build

| | Caught |
|---|---|
| Targeted faults | 9 of 9 |
| Probes | 2 of 2 |
| Caught while the held-out tests still pass | 8 of 11 |

- The 8 faults the black-box oracle cannot see are the data and contract ones: undeclared column
  and table, swapped lineage, edited migration, edited contracts, undeclared route, untagged tests.
- Both probes were caught only because this agent's own tests were thorough (T5 failed). A weaker
  test suite would let them through.
- `dropped-foreign-key` also breaks the held-out tests and the agent's tests, so it is a cruder
  fault than intended: it proves D5 fires but not that D5 alone would have caught it.

Full tables: `evals/results/ledger-go-claude-guarded-1/score.md` and `faults.md`.

**E9, conflicting documents** (`evals/results/_conflicts/conflicts.md`)

"Before" is the same binary with C1–C7 and A8 left out.

| | Before | Now |
|---|---|---|
| Conflicts planted before any code (a check is written for each) | 0 of 7 | 7 of 7 |
| Probes: the conflict is in the meaning of two sentences | 0 of 2 | 0 of 2 |
| False alarms on the unedited problem | 0 | 0 |
| Changes planted on the finished build above | 2 of 4 | 4 of 4 |
| Control (a plan typo a person marked `Spec-Impact: none`) stays clean | yes | yes |
| False alarms from the new checks on the finished build itself | - | 0 |

- The two drift cases caught before are references: a reworded requirement (T8) and a tightened
  data contract (D5). The two new ones are a tightened API limit (C5) and a changed plan (C6).
- These are conflicts we thought of, each written the way the checks expect. The 7 of 7 says the
  checks do what they were written to do, not that they would find the next person's slip.

**E10, an agent on a conflicted spec**

Four conflicts were planted before the agent started: 400 against 409 for an over-refund, "open"
against "pending" for a new order, integer against real for `refunds.amount_cents`, and one in
meaning only (whether the amount paid counts refunds).

*Blind arm, default instructions* (`ledger-go-conflicts-claude-blind-1`, 2.9 minutes). Claude Code
built AC-led-001, then stopped and reported all four conflicts itself, including the one in
meaning that no check sees. The old verifier's view of that workspace was eight requirements
"Missing" with no reason given; the new one lists the three mechanical conflicts as needing a
person. Here the agent did better than the verifier.

*Blind arm, told to choose a side and keep going* (`ledger-go-conflicts-pushon-claude-blind-1`, 10.0
minutes; every scoring below is in `evals/results/ledger-go-conflicts-pushon-claude-blind-1/`, and
`evals/results/conflicts-page/index.html` is the summary page with the review and live pages). The
agent built all nine requirements, followed the contracts each time, wrote its tests to match, and
recorded its choices in a commit message. The held-out tests follow the spec's wording, and four
requirements fail them (AC-led-002, 003, 004, 006).

| Scoring of the same build | Sync and working | Sync but failing (false assurance) | Not Sync, failing (caught) | Not Sync, working |
|---|---|---|---|---|
| As built, new checks off | 2 | 0 | 4 | 3 |
| As built, new checks on | 2 | 0 | 4 | 3 |
| A6 left out, new checks off | 5 | **4** | 0 | 0 |
| A6 left out, C1–C6 and A8 on, C7 off | 5 | 2 | 2 | 0 |
| A6 left out, all new checks on | 5 | **0** | 4 | 0 |

- **As built, the old verifier was right for the wrong reason.** The agent also wrote tests that
  expect a 500 the contract doesn't document, so A6 fails on seven requirements. That is the only
  thing the old verifier said. It said nothing about the documents disagreeing, and an agent that
  removed those tests would have been shown nine of nine proven.
- **"A6 left out" is that case**, scored by skipping A6 rather than by editing the agent's build.
- **C7 was written after seeing this run.** C1–C6 alone left AC-led-003 and AC-led-004 as false
  assurance: neither names the disputed value, but both depend on the field. With C7 the four
  requirements the verifier holds up are exactly the four that fail the held-out tests. That
  match is a fit to one run, not a held-out result.
- The meaning-only conflict was again invisible to the checks. The held-out tests do not exercise
  it either: all four failures are the "open" against "pending" status.
- T7 and A7 pass in the full check of this build with the final verifier (`score-full.md`, same
  statuses as "as built, new checks on"). The five scorings above leave them out to save an hour
  each, which does not change a requirement's status when both pass.
- With the conflicts listed from the first commit, a guarded agent would have been told not to
  build the four requirements. That arm (`--variant conflicts --arm guarded`) has not been run.

## What is not built yet

- **Rust stack.** `evals/problems/ledger/stacks/rust/` needs an `.aqv.yml` (cargo-nextest,
  cargo-llvm-cov), the capture helper and a schema tool, as `stacks/go/` has. The oracle, the
  contracts, the data checks and most seeded faults already apply unchanged.
- **More problems.** One problem is an anecdote. Candidates that stress other things: a job queue
  with retries (no HTTP surface), a multi-tenant API (authorization in the contract), an importer
  with a bronze/silver/gold pipeline (deeper lineage).
- **Spec generation as part of the eval.** Here the spec was written once and frozen so runs are
  comparable. Generating it from `GOAL.md` and `PLAN.md` with the `aqv-specs` workflow, then scoring
  the spec itself (does every oracle test trace to a requirement?), is a separate eval.
- **E4 with numbers.** One run per arm says nothing; it needs at least five per arm per agent.
- **E5, E6, E7** as listed above.
- **E10, guarded arm**, and a second problem to try C7 on a conflict it was not written against.
- **Conflicts in meaning.** Nothing deterministic finds two sentences that contradict each other.
  The honest options are a convention (requirements that define the same term must cite each
  other) or a model-based reader kept outside the pass/fail verdict.
- **The Python reference has no data or consistency checks.** D1–D7, H10, C1–C7, A8, `review.html`
  and `aqv watch` are in the Go binary only.
