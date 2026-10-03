# Agent Quality Verifier

Check an agent's work against the spec without reading its code.

The verifier runs 24 checks on a repo and shows every requirement with four vital
signs (spec, code, api, tests), the commits behind it in order, and a plain sentence
saying what's wrong. Each check is repeatable: the same commit and config always give
the same answer, and anyone can rerun it locally. There are no LLM judges and no
opinion-based scores.

The demo builds the same small auth service in six languages, each the way an agent
usually would, then runs 26 attacks where the agent gets something wrong. Every
attack must be caught by the check written for it, and the clean runs must pass
everything.

**Result: 168 of 168 scenarios behave as expected across 6 languages.** Open
[demo/results/index.html](demo/results/index.html) for every language against every
check, and `demo/results/<language>/demo.html` for each scenario.

**New here?** Read [docs/framework.md](docs/framework.md) (or
[the HTML version](docs/framework.html)): why the checks come in three families
(T, A, H), what each one guards against, and what the demo simulates.

| Language | Stack | Scenarios as expected |
|---|---|---|
| [Python](demo/results/python/RESULTS.md) | FastAPI · pytest · coverage.py | 28 of 28 |
| [JavaScript](demo/results/javascript/RESULTS.md) | Node 22 · Express 4 · Jest · supertest | 28 of 28 |
| [TypeScript](demo/results/typescript/RESULTS.md) | Node 22 · Fastify 5 · Vitest · tsx | 28 of 28 |
| [Go](demo/results/go/RESULTS.md) | Go 1.24 · chi v5 · testing + httptest · gotestsum | 28 of 28 |
| [Rust](demo/results/rust/RESULTS.md) | Rust 1.97 · axum 0.8 · tokio · cargo-nextest · cargo-llvm-cov | 28 of 28 |
| [Kotlin](demo/results/kotlin/RESULTS.md) | Kotlin 2.0 · Spring Boot 3.4 · JUnit 5 + MockMvc · Gradle · JaCoCo · springdoc | 28 of 28 |

## Quick start

```bash
scripts/setup.sh                                   # verifier dependencies
.venv/bin/python demo/run_demo.py --lang python    # one language
.venv/bin/python demo/run_demo.py --lang all       # all six (about two hours)
.venv/bin/python demo/run_demo.py --html-only      # rebuild the pages from the last runs
```

Each language needs its own toolchain; `scripts/setup.sh` lists them.

To check your own repo, add a `.aqv.yml` (each language's is in
`demo/langs/<language>/stages.py`) and run:

```bash
.venv/bin/python -m aqv check --repo path/to/repo               # all history
.venv/bin/python -m aqv check --repo path/to/repo --base main   # like a pull request
```

It writes `report.html` (the requirement view), `report.txt` and `results.json`, and
exits non-zero when a check fails.

## What "quality" means here

1. **Tests prove the spec.** Every requirement has tests tagged to it, the tests run
   its code, and they fail when that code is broken.
2. **The API matches its OpenAPI contract.** The spec marks API requirements, the
   agent documents them in the contract, and the running service must match it.
3. **Git follows standard conventions.** Every change traces to a requirement and to
   the agent that made it.

## Reading the report

Each requirement shows:

- **Vital signs** on the rail and as dots: spec, code, api, tests. Green is proven,
  amber needs attention, red is missing or failing, grey doesn't apply.
- **One sentence** saying what's wrong, for example "The spec changed after the code
  that implements it."
- **Its history in order:** when the spec line was added or changed (changed words
  are underlined), each commit that cites it and how many of its lines are still in
  the code, then what's true now: tagged tests, how much of its code they run,
  how many broken versions of the code they catch, and every API call checked
  against the contract.

Below that: **Outside the spec** (routes and operations no requirement accounts
for), **Git practices** (the nine git rules), and all 24 checks.

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

## The checks

Reach says what a check needs: **G** any git repo, **C** the conventions below,
**S** standard tool output, **E** a per-language tool, **F** a per-framework adapter.

| ID | Check | How | Reach |
|---|---|---|---|
| T1 | Requirement IDs are valid and never reused | Spec lines vs the ID registry and spec history | C |
| T2 | A code commit references the requirement | `Refs:` trailers on commits that change code | C |
| T3 | The code from those commits still exists | `git blame -w -M -C`, ignoring blank and comment lines | G |
| T4 | Tests are tagged to the requirement | Test names in the JUnit report mention the ID | C |
| T5 | The tagged tests pass | JUnit results; a suite that won't load is an error | S |
| T6 | The tagged tests run the requirement's code | Run only that requirement's tests under coverage, minus lines that run on load | S |
| T7 | The tagged tests fail when the code is broken | Mutate the requirement's lines one at a time; uncompilable mutants don't count | E |
| T8 | Results reset when the requirement changes | Wording changed after its last code or test commit | G + C |
| A1 | Every API requirement has an operation | `(api: POST /login)` in the spec vs `x-requirements` in the contract | C |
| A2 | Every operation references a requirement | `x-requirements` on every operation | C |
| A3 | The contract passes the lint rules | Spectral with the repo's ruleset | S |
| A4 | No breaking change unless the spec changed | oasdiff against the base branch | S |
| A5 | The service serves exactly the documented routes | Routes from the framework (or source) vs the contract | S / F |
| A6 | Responses in the tagged tests match the contract | Adapter records each test's HTTP responses | F |
| A7 | The running service conforms to the contract | Schemathesis against the running app, fixed seed | S |
| H1 | Subjects follow Conventional Commits | Regex on every subject | C |
| H2 | Code commits carry a `Refs:` trailer | Trailer names a real requirement (`Refs: none` for refactor/chore) | C |
| H3 | One requirement per code commit | At most one ID in `Refs:` | C |
| H4 | refactor and chore commits change no status | Statuses before and after each such commit | G + S |
| H5 | Commit size under the limit | Lines changed per commit (default 400) | G |
| H6 | Branch names follow the pattern | Head branch and merged branch names | C |
| H7 | Main is never rewritten | `refs/aqv/verified` is still an ancestor of main | G |
| H8 | The agent is named on its commits | Non-human commits carry `Co-Authored-By:` | C |
| H9 | Commits are signed | `git log %G?` is a good signature | G |

## How each language does it

Only these checks depend on the stack. Everything else reads the spec, the contract
and git history the same way in every language.

| Check | Python | JavaScript | TypeScript | Go | Rust | Kotlin |
|---|---|---|---|---|---|---|
| T5 | pytest --junitxml | jest-junit reporter | Vitest junit reporter | gotestsum --junitfile | cargo-nextest JUnit | Gradle JUnit XML (build/test-results) |
| T6 | coverage.py run per requirement, LCOV | Jest coverage per requirement (-t), LCOV | Vitest V8 coverage per requirement (-t), LCOV | go test -run per requirement, Go cover profile | cargo-llvm-cov + nextest filter per requirement, LCOV | Gradle --tests per requirement, JaCoCo XML |
| T7 | Built-in line mutator; Python compile check | Built-in line mutator; node --check | Built-in line mutator; tsc --noEmit | Built-in line mutator; go test compile check | Built-in line mutator; nextest build-failure exit code | Built-in line mutator; compileTestKotlin check |
| A5 | OpenAPI generated by FastAPI | Route list from Express's router (adapter) | OpenAPI generated by @fastify/swagger | chi.Walk route list (vendored command) | Source scan of .route(...) calls (partial) | OpenAPI generated by springdoc on the running app |
| A6 | pytest plugin records TestClient calls (adapter) | Setup file records http.ServerResponse per test (adapter) | Setup file records responses, incl. app.inject (adapter) | Test helper records each httptest response (vendored) | Test helper records each oneshot response (vendored) | Test base class records each MockMvc response (vendored) |
| A7 | uvicorn + Schemathesis | node server + Schemathesis | tsx server + Schemathesis | go run server + Schemathesis | cargo run + Schemathesis | Spring Boot jar + Schemathesis |

The runner profile in `.aqv.yml` is the only per-project setup: command templates
for the tests and coverage, the report formats, and how to start the service. JUnit
XML, LCOV, Go cover profiles and JaCoCo XML are all read directly.

## What the checks found in my own demo code

The first draft of each language's tests was written the way a careful agent would.
T7 still found real gaps, all fixed in the tests rather than by lowering the threshold:

- **Python:** after AC-auth-005 changed the reset endpoint, `request_reset`'s return
  values were dead code, and no AC-auth-005 test checked that a known email still gets
  its link.
- **JavaScript:** the hand-written `/session` input validation had no boundary tests.
  Python and TypeScript declare that validation, so it never appears as testable lines.
- **Go:** salt generation is two lines; deleting `rand.Read(salt)` left all-zero salts
  and no test noticed. Added a "same password gets different salts" test (Rust and
  Kotlin got it from the start).
- **Kotlin:** `passwordMatches` returning `true` for an unknown email went unnoticed;
  no test signed in with an unknown email.

Running six languages also fixed the verifier: build failures that JUnit lists as empty
suites now count as "the suite didn't load", Go's `TestAC_...` names match, H4 compares
under the trusted config and links dependency folders into its temporary worktrees, and
the Rust capture helper writes each record in one call so parallel tests don't interleave.

## Conventions the demo follows

- Requirements: `- **AC-auth-002** (api: POST /login): Accounts lock after 3 consecutive failed sign-in attempts.`
- Every ID ever issued is in `specs/.ids`.
- Contract operations list `x-requirements: [AC-auth-001]`; object schemas set `additionalProperties: false`.
- Test names contain the ID: `test_AC_auth_002_x`, `TestAC_auth_002X`, `ac_auth_002_x`, `"AC-auth-002 x"`.
- Commits: `feat(auth): lock accounts after 3 failed attempts` with trailers
  `Refs: AC-auth-002` and `Co-Authored-By: <agent>`, signed, on a branch like
  `feat/AC-auth-002-lockout`, merged with a merge commit.

## Limits

- **A5 in Rust is partial.** axum can't list its routes, so they're read from the
  source; unusual registrations are missed. A7 still covers the documented routes.
- **A6 needs an adapter per framework.** Node and pytest adapters ship with the
  verifier; Go, Rust and Kotlin use a small test helper vendored into the repo.
- **T7 uses a small built-in line mutator**, not a full mutation tool, and is slow in
  compiled languages (each mutant rebuilds). It runs only on requirements a pull
  request touches.
- **Pull requests are simulated** with local branches; there's no CI workflow yet.
- **T8 clears** when any later commit for the requirement changes code or tests.
- **Results aren't stored between runs** (no git notes or service yet).

## Compared with IntentBond

[experiments/intentbond](experiments/intentbond/README.md) runs
[IntentBond](https://github.com/kbak/intentbond), the closest existing tool (OpenFastTrace
links plus tests against a git baseline), on the same Python scenarios. It blocks 8 of the
26 attacks (9 with its strictest options), including 7 of the 9 T attacks. It sends
claims-only code, `assert True` tests and weakened tests to human review, where this
verifier's T3, T6 and T7 reject them.

## Layout

```
aqv/                    the verifier
  engine.py             all checks, statuses and the requirement view
  runner.py             runs the project's tools through the runner profile
  html.py               report.html, demo pages, cross-language page
  gitx.py spec.py contract.py mutate.py pytest_capture.py
adapters/node/          A5 route listers and the A6 capture setup file for Node
demo/
  build_baseline.py     builds a clean demo repo for one language
  langs/<language>/     stages.py (code, tests, runner profile) and edits.sh (attack edits)
  scenarios/            one clean PR and 26 attacks, shared by every language
  run_demo.py           runs everything and writes demo/results/
  results/              index.html, and per language: RESULTS.md, demo.html, runs/*.html
experiments/intentbond/ IntentBond on the same scenarios
```

Based on the evidence-gated verification prototype (`trace.py`) and the design
guide in [khangtoh/specloop `docs/agent-quality-verifier.md`](https://github.com/khangtoh/specloop/blob/main/docs/agent-quality-verifier.md).
