# The Agent Quality Verifier framework

How to judge an agent's code without reading it: what the 24 checks are, why they're
grouped into T, A and H, what each one guards against, and what the demo does and
doesn't prove.

## Contents

1. [The problem](#1-the-problem)
2. [The idea in one paragraph](#2-the-idea-in-one-paragraph)
3. [Three things a person can review instead of code](#3-three-things-a-person-can-review-instead-of-code)
4. [The rules every check follows](#4-the-rules-every-check-follows)
5. [T: tests prove the spec (T1–T8)](#5-t-tests-prove-the-spec-t1t8)
6. [A: the API matches its contract (A1–A7)](#6-a-the-api-matches-its-contract-a1a7)
7. [H: git history can be trusted (H1–H9)](#7-h-git-history-can-be-trusted-h1h9)
8. [What the agent is assumed to do wrong](#8-what-the-agent-is-assumed-to-do-wrong)
9. [Requirement status and the report](#9-requirement-status-and-the-report)
10. [How a check reaches across languages](#10-how-a-check-reaches-across-languages)
11. [How the verifier runs](#11-how-the-verifier-runs)
12. [The demo: what is real and what is simulated](#12-the-demo-what-is-real-and-what-is-simulated)
13. [What it doesn't guarantee](#13-what-it-doesnt-guarantee)
14. [Glossary](#14-glossary)

## 1. The problem

Coding agents write more code than people can read. Reviewing every line doesn't
scale, and skimming gives a false sense of safety. Green CI isn't enough either: an
agent that wants a green build can get one by weakening a test, updating a test to
match a bug, or adding a commit that only claims to implement something.

So the question changes from "is this code good?" to "can I prove this code does what
we asked, the way we asked, without reading it?"

## 2. The idea in one paragraph

A person writes **requirements** with stable IDs. The agent implements them and
leaves a trail that follows simple conventions: commits name the requirement they
serve, tests carry the requirement ID in their name, and API operations in the OpenAPI
contract list the requirements they implement. The verifier follows that trail and
runs **24 checks**. Each check is a fixed, repeatable rule that either holds or doesn't.
The result is one **status per requirement**: is it implemented, tested, honest to its
contract, and current with the spec. A person reads the statuses and opens the code
only where a check fails.

## 3. Three things a person can review instead of code

The checks are grouped by what they protect. Each group is a short artifact a person
can actually read and approve:

| Letter | Group | What a person reviews | What the checks make sure of |
|---|---|---|---|
| **T** | Tests prove the spec | The **spec**: a list of requirement sentences | Every requirement is backed by code that exists and by tests that run that code and would fail if it broke |
| **A** | The API matches its contract | The **OpenAPI contract**: the endpoints, statuses and response shapes | The service does exactly what the contract says, no more and no less |
| **H** | Git history can be trusted | The **history**: who changed what, why, and when | The trail that T and A rely on is complete, honest and unaltered |

T and A answer "is it right?". H answers "can we trust the evidence?". The T and A
checks follow links in git history (which commit implemented which requirement, which
lines it wrote), so if history can be faked, they can be fooled. That's why H exists.

There are 8 T checks, 7 A checks and 9 H checks. The counts aren't targets; each check
closes one specific way the evidence could lie. The next three sections list them.

## 4. The rules every check follows

A check is only allowed if all of these hold:

- **Repeatable.** The same commit and config always give the same answer.
- **Defined in advance.** The pass/fail rule is written down before it runs, with any
  threshold in config.
- **Rerunnable by anyone.** A developer gets the same answer on their own machine.
- **Honest about what it can't see.** A check that can't run reports *not covered*,
  never *pass*.

This rules out LLM judges and "code quality" scores. They might help a person, but they
never change a status.

Two more design rules matter:

- **A checked box or a commit message is a claim, not evidence.** Evidence comes from
  running something: blame, the tests, coverage, the service.
- **The rules come from the base branch.** When checking a pull request, the verifier
  reads its config from `main`, so a pull request can't loosen its own checks.

## 5. T: tests prove the spec (T1–T8)

The T checks are a chain. Each link answers the next obvious question about one
requirement, and each one stops a specific shortcut.

| # | Question | Check | Guards against | Example the demo catches |
|---|---|---|---|---|
| T1 | Can we refer to this requirement reliably? | IDs are valid, registered, never reused or deleted | A requirement silently renumbered, duplicated or removed, so old evidence points at the wrong thing | The agent adds a new rule that reuses the ID `AC-auth-006` |
| T2 | Did anyone claim to build it? | A commit that changes code references it in a `Refs:` trailer | Work that can't be traced to any requirement | A requirement is added and nothing implements it |
| T3 | Is the claimed code still there? | `git blame` finds lines written by those commits at the current commit (blank and comment lines don't count) | Commits that only claim, and code deleted later by unrelated changes | The agent "implements" a requirement with a commit that only adds a TODO comment |
| T4 | Is there a test for it? | A test name in the JUnit report contains the ID | Untested features | Code is added with no tests |
| T5 | Do those tests pass? | Every tagged test passes; a suite that won't load is an error | Broken behavior, and test suites that silently stop running | The lockout threshold changes to 4; a renamed function breaks test compilation |
| T6 | Do the tests actually run its code? | Run only that requirement's tests under coverage; they must execute its lines, not counting code that runs just from loading | Tests that pass without touching the code they claim to test | A test named for the requirement that only asserts true |
| T7 | Would the tests notice if the code broke? | Change the requirement's lines one at a time (mutation); its tests must catch at least 60% | Tests that run the code but check nothing meaningful | Lockout tests "simplified" so they only check for a 401 |
| T8 | Is the evidence about the current wording? | The requirement's wording hasn't changed since its last code or test commit | Old results shown as current after the spec changed | Product changes lockout from 3 to 5 attempts; no code changes |

Read top to bottom, the chain moves from claim (T2) to existence (T3) to tested (T4–T5)
to exercised (T6) to meaningful (T7), with T1 and T8 making sure the requirement itself
is stable and current.

## 6. A: the API matches its contract (A1–A7)

The contract is the API's public promise, so it needs checking from both directions:
does it cover the spec, and does the running service keep it?

| # | Question | Check | Guards against | Example the demo catches |
|---|---|---|---|---|
| A1 | Does the contract cover every API requirement? | Each `(api: POST /login)` in the spec has that operation, listing the requirement in `x-requirements` | Endpoints built without updating the contract | A sign-out endpoint is shipped with no contract entry |
| A2 | Is every contract operation explained by the spec? | Every operation lists real requirements | Endpoints nobody asked for, documented to look legitimate | `DELETE /session` added to the contract with no requirement |
| A3 | Is the contract well-formed and strict? | Spectral lint: valid OpenAPI, every response has a schema, objects disallow extra fields | A contract too loose to catch anything | The session response schema loses `additionalProperties: false` |
| A4 | Did the API break its consumers? | oasdiff against the base branch; a breaking change is allowed only if a requirement changed too | Breaking changes slipped in under "cleanup" | `token` renamed to `access_token` in contract, code and tests |
| A5 | Does the service serve exactly the documented routes? | Routes listed from the running code compared with the contract | Hidden or debug endpoints, and documented endpoints that don't exist | `GET /debug/users` ships |
| A6 | Do the responses the tests see match the contract? | An adapter records every response during the tagged tests and validates it | Leaked fields and undocumented status codes, even when tests pass | Login response leaks `debug_password`; lockout switches to HTTP 423 and the test is updated to match |
| A7 | Does the running service hold up to inputs nobody wrote a test for? | Schemathesis sends generated requests (fixed seed) to the running service | Crashes and contract breaks on inputs the agent's own tests never tried | Password reset crashes on an email without `@` |

A6 and A7 complement each other. A6 can say which requirement broke but only sees what
the tests send. A7 is independent of the agent's tests but works per operation.

## 7. H: git history can be trusted (H1–H9)

Each H check protects one property of the trail the other checks follow.

| # | Property | Check | Guards against | Example the demo catches |
|---|---|---|---|---|
| H1 | Readable | Commit subjects follow Conventional Commits (`feat(auth): …`) | Unreadable history, no changelog | A commit titled `wip` |
| H2 | Traceable | Commits that change code carry `Refs: <ID>` (`Refs: none` allowed for refactor/chore) | Code changes nobody can tie to a requirement | Code changed with no `Refs:` |
| H3 | Scoped | At most one requirement per code commit | Shared commits that let one requirement's tests take credit for another's code | One commit cites two requirements |
| H4 | Honest | A `refactor` or `chore` commit leaves every requirement's status unchanged | Behavior changes hidden inside "no behavior change" commits | A "refactor" turns `>=` into `>` in the lockout check |
| H5 | Reviewable | No commit changes more than 400 lines (lockfiles excluded) | Huge commits that hide changes | A 600-line file in one commit |
| H6 | Organized | Branch names follow `type/AC-xxx-nnn-slug` | Work in progress nobody can match to a requirement | Work on a branch called `quick-fix` |
| H7 | Immutable | The last verified commit is still in main's history | Rewritten history that erases or changes evidence | The verified merge on main is amended |
| H8 | Attributed | Commits by non-humans name the agent (`Co-Authored-By:`) | Agent work passed off as human work | An agent commit with no attribution |
| H9 | Authentic | Every commit has a good signature | Commits forged under someone else's name | An unsigned commit |

## 8. What the agent is assumed to do wrong

The checks assume an agent that is capable but unreliable. It doesn't have to be
malicious. It may be careless, overconfident, or simply optimizing for a green build.
The failures it is assumed to make are the ones that look fine on the surface:

| Failure | Looks like | Caught by |
|---|---|---|
| Claiming without doing | A commit that cites a requirement | T3 |
| Testing nothing | A passing test with the right name | T6, T7 |
| Fixing the test instead of the bug | A test updated alongside a behavior change | A6, A4, T7 |
| Quietly widening the API | An extra field or endpoint | A6, A5, A2 |
| Hiding behavior changes | A commit called "refactor" | H4 |
| Ignoring a spec change | Code that still matches the old wording | T8 |
| Making evidence hard to follow | Mixed commits, huge commits, rewritten history | H2, H3, H5, H7 |
| Hiding who did the work | Unattributed or unsigned commits | H8, H9 |

The demo turns each row into at least one concrete attack.

## 9. Requirement status and the report

Every requirement gets exactly one status: the first problem found, in this order.

| Status | Means | Set by |
|---|---|---|
| Missing | No commit references it | T2 |
| Gone | Its code was never written or was deleted | T3 |
| Untested | No tagged test | T4 |
| Failing | Tagged tests fail, or the suite won't load | T5 |
| Unexercised | Tests pass but don't run its code | T6 |
| Weak | Tests run its code but miss broken versions of it | T7 |
| Contract | The API doesn't match the contract | A1, A5, A6, A7 |
| Drift | Its wording changed since it was implemented | T8 |
| Sync | Every check passes | |

The HTML report shows each requirement with:

- **Four vital signs** (spec, code, api, tests) on a colored rail: green proven, amber
  needs attention, red missing or failing, grey not applicable.
- **One sentence** saying what's wrong.
- **Its history in order:** spec added or changed (changed words underlined), each
  commit with how many of its lines are still in the code, then what's true now:
  tests, coverage, mutation results and every API call checked against the contract.

Below that are an **Outside the spec** panel (routes and operations no requirement
accounts for), a **Git practices** panel, and all 24 checks.

## 10. How a check reaches across languages

Some checks only need git; others need something from the project's tools. Each check
has a **reach** label:

| Reach | Needs | Checks |
|---|---|---|
| **G** Any git repo | Nothing but history | T3, T8, H4, H5, H7, H9 |
| **C** Conventions | IDs in the spec, `Refs:` trailers, IDs in test names, `x-requirements` | T1, T2, T4, A1, A2, H1, H2, H3, H6, H8 |
| **S** Standard outputs | JUnit XML, LCOV / Go cover profile / JaCoCo XML, OpenAPI | T5, T6, A3, A4, A7 (and A5 where the framework generates OpenAPI) |
| **E** A per-language tool | A mutation step that can rebuild the code | T7 |
| **F** A per-framework adapter | A small hook that records test traffic or lists routes | A6 (and A5 where the framework can't generate OpenAPI) |

The only per-project setup is a **runner profile** in `.aqv.yml`: command templates for
running the tests and coverage, the report formats, how to start the service, and
which adapter to use.

How each language does the stack-dependent checks in the demo:

| Check | Python | JavaScript | TypeScript | Go | Rust | Kotlin |
|---|---|---|---|---|---|---|
| T5 | pytest JUnit | jest-junit | Vitest JUnit | gotestsum | cargo-nextest | Gradle JUnit |
| T6 | coverage.py, LCOV | Jest, LCOV | Vitest V8, LCOV | Go cover profile | cargo-llvm-cov, LCOV | JaCoCo XML |
| T7 compile check | Python compile | `node --check` | `tsc --noEmit` | `go test` build | nextest build exit code | `compileTestKotlin` |
| A5 | FastAPI OpenAPI | Express router list | @fastify/swagger | `chi.Walk` | source scan (partial) | springdoc on the running app |
| A6 | pytest plugin | Node setup file | Node setup file | test helper | test helper | test base class |
| A7 | uvicorn | node | tsx | `go run` | `cargo run` | Spring Boot jar |

## 11. How the verifier runs

```
.aqv.yml (from the base branch)   spec files   OpenAPI contract   git history
                 \                    |               |               /
                  ------------------- aqv check -----------------------
                                      |
       1. read requirements, contract and every commit's trailers
       2. run the full test suite once (JUnit + traffic capture)        T4 T5 A6
       3. per requirement: blame its commits' lines                     T2 T3
          run only its tests under coverage, minus a no-test run        T6
          mutate its executed lines and rerun its tests                 T7
       4. compare the spec's history with its last code commit          T1 T8
       5. lint and diff the contract; list routes; start the service
          and send generated requests                                  A1–A7
       6. read the commit range: subjects, trailers, size, branches,
          signatures; compare statuses around refactor commits          H1–H9
                                      |
              results.json   report.txt   report.html
```

Two modes:

- **All history** (`aqv check --repo .`): checks everything up to `HEAD`.
- **Pull request** (`aqv check --repo . --base main`): the H checks look only at the
  new commits, T7 mutates only the requirements the pull request touches, and A4
  compares the contract with `main`.

The exit code is non-zero when any check fails, so it can gate a merge.

## 12. The demo: what is real and what is simulated

**The demo does not call an AI agent.** It simulates one. Everything else is real.

| Part | Real or simulated |
|---|---|
| The auth service in six languages | Real code, built and run |
| Tests, coverage, mutation, contract tools, Schemathesis | Real tools, really run |
| Git history | Real commits, really signed, with a human author for the spec and an agent identity (`dev-agent` with a `Co-Authored-By: Claude` trailer) for the implementation |
| **The agent's work** | **Simulated:** the clean history is written by `demo/build_baseline.py`, and each attack is a scripted edit in `demo/langs/<language>/edits.sh` |
| Pull requests and CI | Simulated with local branches; the verifier runs locally |

**Why simulate?** The demo tests the referee, not the player. To know the verifier
works, each mistake has to happen exactly the same way every run, so the result can be
compared: did the right check fire, and did the clean runs stay clean? A live agent
makes different mistakes each time, which is what you want when measuring agents and
what you don't want when testing the verifier.

The attacks aren't invented at random. They come from the failures in section 8, most
of them seen in the original prototype: comment-only commits, `assert True` tests, a
test updated to expect HTTP 423, a leaked debug field, a debug endpoint.

Result: in each of the six languages, the clean baseline and a clean pull request pass
every check, and all 26 attacks are caught by the check written for them. That's
168 of 168 scenarios.

**Using it with real agents** is the next step:

1. Put the conventions in the agent's instructions (for example `CLAUDE.md`): IDs in
   test names, `Refs:` trailers, contract first, one requirement per commit.
2. Give the agent requirements to implement on branches.
3. Run `aqv check --base main` on each pull request, in CI or locally.
4. Track the statuses and the agent scorecard across many runs to compare agents,
   prompts or models on the same spec.

## 13. What it doesn't guarantee

- **Meaning.** The checks prove the code does what its tests and the contract check.
  If the tests and contract both miss part of what a requirement means, so does the
  verifier. T7 narrows this gap; it doesn't close it.
- **Good requirements.** A vague requirement can pass. Writing testable requirements is
  still the person's job.
- **T8 is cleared by any later commit** that references the requirement and changes
  code or tests. It catches untouched drift, not a wrong re-implementation (T5–T7 and A6
  have to catch that).
- **T7 is a small built-in mutator**, not a full mutation tool, with a 60% threshold.
  It's slow in compiled languages because each mutant rebuilds.
- **A5 in Rust is partial:** axum can't list its routes, so they're read from source.
- **A6 needs an adapter per framework.** In Go, Rust and Kotlin it's a small helper
  kept in the repo, which the tests must use.
- **No storage yet:** results aren't kept between runs, and there's no CI workflow or
  hosted board.

Some of these are other tools' goals. [OpenFastTrace](compare/openfasttrace.html) traces a
multi-level specification, and [IntentBond](compare/intentbond.html) keeps verifiable
evidence and a built-in review step. Both comparisons run those tools on the same scenarios
(Markdown: [OpenFastTrace](../experiments/openfasttrace/README.md),
[IntentBond](../experiments/intentbond/README.md)).

## 14. Glossary

| Term | Meaning |
|---|---|
| Requirement | One line in the spec with a stable ID, for example `AC-auth-002` |
| Contract | The OpenAPI file describing the API |
| Claim | Something asserted but not shown: a commit message, a checked box |
| Evidence | Something observed by running a tool: blame, test results, coverage, responses |
| Tagged test | A test whose name contains the requirement ID |
| Mutation | A deliberate small change to code (`>=` to `>`) to see whether tests notice |
| Runner profile | The `.aqv.yml` section telling the verifier how to run a project's tools |
| Adapter | A small, framework-specific helper that lists routes or records test traffic |
| Reach | What a check needs to work: G, C, S, E or F |
| Vital signs | The four per-requirement indicators: spec, code, api, tests |
