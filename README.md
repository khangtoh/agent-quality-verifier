# Agent Quality Verifier

Check an agent's work against the spec without reading its code.

The verifier runs 24 checks on a repo and gives every requirement a status. Each
check is repeatable: the same commit and config always give the same answer, and
anyone can rerun it locally. There are no LLM judges and no opinion-based scores.

This repo holds the verifier and a demo. The demo builds a small auth service the
right way, then runs 26 scenarios where an agent gets something wrong. Each one
must be caught by the check designed for it.

**Result: 28 of 28 scenarios behave as expected.** The clean baseline and a clean
pull request pass every check, and each of the 26 attacks is caught by its check.
See [demo/RESULTS.md](demo/RESULTS.md) for the full table. Open
[demo/examples/demo.html](demo/examples/demo.html) for the same results as a page: which
check caught each attack, a scenario-by-check grid, and every failing result.
[demo/examples/](demo/examples/) also has single-run reports (`baseline`, `T7-weak-tests`,
`A6-leaked-field`) as HTML and text.

## Quick start

Needs Python 3.11+, Node 18+, Go 1.22+ and gpg.

```bash
scripts/setup.sh                        # Python packages, Spectral, oasdiff
.venv/bin/python demo/run_demo.py       # build the demo repo, run every scenario
```

To check your own repo, add a `.aqv.yml` (see the demo's, in
[demo/build_baseline.py](demo/build_baseline.py)) and run:

```bash
.venv/bin/python -m aqv check --repo path/to/repo               # all history
.venv/bin/python -m aqv check --repo path/to/repo --base main   # like a pull request
```

It prints a report, writes `results.json`, `report.txt` and `report.html`, and exits non-zero when a check fails.

## What "quality" means here

1. **Tests prove the spec.** Every requirement has tests tagged to it, the tests
   run its code, and they pass.
2. **The API matches its OpenAPI contract.** The spec marks API requirements, the
   agent documents them in the contract, and the running service must match it.
3. **Git follows standard conventions.** Every change traces to a requirement and
   to the agent that made it.

## The checks

Reach says what a check needs: **G** any git repo, **C** the conventions below,
**S** standard tool output, **E** a per-language tool, **F** a per-framework adapter.

### Tests prove the spec

| ID | Check | How the demo does it | Reach |
|---|---|---|---|
| T1 | Requirement IDs are valid and never reused | Parse spec lines; compare with the ID registry and spec history | C |
| T2 | A code commit references the requirement | `Refs:` trailers on commits that change `src/` | C |
| T3 | The code from those commits still exists | `git blame -w -M -C`, ignoring blank and comment lines | G |
| T4 | Tests are tagged to the requirement | Test names from the JUnit report mention the ID | C |
| T5 | The tagged tests pass | JUnit results; a suite that won't load is an error | S |
| T6 | The tagged tests run the requirement's code | Run only that requirement's tests under coverage (LCOV), minus lines that run on import | S |
| T7 | The tagged tests fail when the code is broken | Mutate the requirement's lines one at a time and rerun its tests | E |
| T8 | Results reset when the requirement changes | Requirement wording changed after its last code or test commit | G + C |

### The API matches its OpenAPI contract

| ID | Check | How the demo does it | Reach |
|---|---|---|---|
| A1 | Every API requirement has an operation | `(api: POST /login)` in the spec vs `x-requirements` in the contract | C |
| A2 | Every operation references a requirement | `x-requirements` on every operation | C |
| A3 | The contract passes the lint rules | Spectral with the repo's ruleset | S |
| A4 | No breaking change unless the spec changed | oasdiff against the base branch | S |
| A5 | The service serves exactly the documented routes | OpenAPI generated from the code vs the contract | S |
| A6 | Responses in the tagged tests match the contract | pytest plugin records TestClient traffic per test | F |
| A7 | The running service conforms to the contract | Schemathesis against the running app, fixed seed | S |

### Git follows the conventions

| ID | Check | How the demo does it | Reach |
|---|---|---|---|
| H1 | Subjects follow Conventional Commits | Regex on every subject | C |
| H2 | Code commits carry a `Refs:` trailer | Trailer present and names a real requirement (`Refs: none` allowed for refactor/chore) | C |
| H3 | One requirement per code commit | At most one ID in `Refs:` | C |
| H4 | refactor and chore commits change no status | Requirement statuses before and after each such commit | G + S |
| H5 | Commit size under the limit | Lines changed per commit (default 400) | G |
| H6 | Branch names follow the pattern | Head branch and merged branch names | C |
| H7 | Main is never rewritten | `refs/aqv/verified` is still an ancestor of main | G |
| H8 | The agent is named on its commits | Non-human commits carry `Co-Authored-By:` | C |
| H9 | Commits are signed | `git log %G?` is a good signature | G |

## Requirement status

Each requirement shows the first problem found, in this order:

| Status | Means | Check |
|---|---|---|
| Missing | No commit references it | T2 |
| Gone | Its code was never written or was deleted | T3 |
| Untested | No tagged test | T4 |
| Failing | Tagged tests fail, or the suite won't load | T5 |
| Unexercised | Tests pass but don't run its code | T6 |
| Weak | Tests run its code but miss broken versions of it | T7 |
| Contract | The API doesn't match the contract | A1, A5, A6, A7 |
| Drift | Its wording changed since it was last implemented | T8 |
| Sync | Every check passes | |

## How it works

- **Runner profile.** `.aqv.yml` tells the verifier how to run the project's tests
  and where the reports go. The verifier reads JUnit XML and LCOV, so the same
  approach works for other languages. Only A6 (the TestClient adapter) and T7
  (the Python mutator) are Python-specific.
- **Per-requirement test runs.** T6 runs each requirement's tests on their own,
  then subtracts a run that selects no tests. What's left is the code those tests
  actually execute.
- **Config comes from the base.** In `--base` mode the verifier reads `.aqv.yml`
  from the base branch, so a pull request can't loosen its own checks.
- **Output.** `results.json` has one result per check per requirement, operation
  or commit, plus statuses and a small agent scorecard.

## Conventions the demo follows

- Requirements: `- **AC-auth-002** (api: POST /login): Accounts lock after 3 consecutive failed sign-in attempts.`
- Every ID ever issued is in `specs/.ids`.
- Contract operations list `x-requirements: [AC-auth-001]`; object schemas set `additionalProperties: false`.
- Test names contain the ID: `test_AC_auth_002_locks_after_three_failures`.
- Commits: `feat(auth): lock accounts after 3 failed attempts` with trailers
  `Refs: AC-auth-002` and `Co-Authored-By: <agent>`, signed, on a branch like
  `feat/AC-auth-002-lockout`, merged with a merge commit.

## Limits

- Python and FastAPI only so far. Other languages need a runner profile, plus an
  A6 adapter and a mutation tool where one isn't available.
- Pull requests are simulated with local branches. There is no CI workflow yet.
- T8 clears when any later commit that references the requirement changes code
  or tests. It catches untouched drift, not a wrong re-implementation; T5–T7 and
  A6 have to catch that.
- H7 needs `refs/aqv/verified` recorded (`aqv check --record` does it after a clean run).
- The mutation check (T7) uses a small built-in line mutator, not a full mutation tool.
- Results aren't stored between runs yet (no git notes or service).

## Layout

```
aqv/                 the verifier
  engine.py          all checks and statuses
  runner.py          runs the project's tools through the runner profile
  gitx.py spec.py contract.py mutate.py
  pytest_capture.py  A6 adapter for pytest + TestClient
  html.py            report.html and demo.html
demo/
  build_baseline.py  builds the clean demo repo
  scenarios/         one clean PR and one attack per check (T5 and A6 have two)
  run_demo.py        runs everything and writes RESULTS.md
  examples/          demo.html for the whole run, plus sample single-run reports
```

Based on the evidence-gated verification prototype (`trace.py`) and the design
guide in [khangtoh/specloop `docs/agent-quality-verifier.md`](https://github.com/khangtoh/specloop/blob/ccr-bd55ced2-pymvfo/docs/agent-quality-verifier.md).
