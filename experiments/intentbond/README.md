# IntentBond on the verifier's scenarios

HTML version: [docs/compare/intentbond.html](../../docs/compare/intentbond.html).

**IntentBond keeps a change reviewable and its evidence verifiable. This verifier makes the
evidence the review.**

[IntentBond](https://github.com/kbak/intentbond) links requirements to code and tests with
OpenFastTrace tags, runs the tests against a git baseline, keeps evidence tied to the exact
source it checked, and sends every specification or test change to a person. This verifier
turns the questions that review would ask into checks. We ran IntentBond on the same 26
attacks the verifier is tested against, plus three variants that isolate single questions,
with its documented settings and with its strictest options.

## Two goals

> "IntentBond connects intent and specifications to code, tests, and verification evidence.
> Follow explicit links to find what a change affects and keep the related artifacts
> consistent as software changes." … "Review determines whether the linked code and checks
> satisfy the requirement." (IntentBond README)

| | IntentBond | This verifier |
|---|---|---|
| Question | Did this change keep requirements, code and tests linked and passing, and what must a person review? | Which requirements are proven, by checks alone, so review doesn't have to find the problems? |
| Links | OpenFastTrace tags, checked on base and candidate | Conventions: `Refs:` trailers, test names, OpenAPI `x-requirements` |
| Tests | Runs the suite; named tests can be required to pass | Runs each requirement's tests, measures what they execute, mutates the code |
| Judgement | Every spec or test change goes to review (`review.patch`); passing checks don't approve it | Turned into checks (T3, T6, T7, T8); people read findings instead of code |
| Evidence | Saved with source hashes; `ib verify` matches a later commit to it | Recomputed on every run; nothing saved yet |
| Also | Optional Alloy and Z3 checks | API contract (A1–A7) and git history (H1–H9) |

Both read their rules from the base, not from the change being checked.

**What this verifier is for:** letting a person judge an agent's work without reading its
code. For every requirement it answers three questions with checks that give the same
answer for the same commit every time: do the tests prove it (T1–T8), does the API match its
contract (A1–A7), and can the history be trusted (H1–H9)? Where a check can't see, it says
"not covered", never "pass". It deliberately doesn't manage requirement documents, approve
what a requirement should say, store audit evidence (yet) or prove behaviour formally.

## The same scenarios, by the question they ask

"Review" (exit 4) is IntentBond's deliberate answer for any change to specifications or
tests: the clean pull request gets it too. It hands the question to a person rather than
answering it.

| Question the scenario asks | Runs | This verifier | IntentBond default | IntentBond strict |
|---|---|---|---|---|
| Is every requirement linked to code and tests, at its current revision? (T1, T2, T4, T8) | 4 | 4 of 4 | 4 rejected | 4 rejected |
| Do the linked tests run and pass? (T5 ×2, H4) | 3 | 3 of 3 | 3 rejected | 3 rejected |
| Is the linked evidence real: code that exists, tests that run it and would catch it breaking? (T3, T6, T7, X1, X3) | 5 | 5 of 5 | 1 rejected, 4 to review | 2 rejected, 3 to review |
| Is a reworded requirement noticed when nobody marks it as changed? (X2) | 1 | 1 of 1 | to review | rejected |
| Does the API match its OpenAPI contract? (A1–A7) | 8 | 8 of 8 | not its goal (3 to review) | same |
| Does the history follow the conventions? (H1–H3, H5–H9) | 8 | 8 of 8 | not its goal | same |
| **All scenarios and variants** | **29** | **29 of 29** | **8 of 29** by a check, 5 to a person | **10 of 29** by a check, 3 to a person |

## How it was run

1. IntentBond `5a1200a` (2026-09-29) with its pinned OpenFastTrace 4.9.0.
2. The Python demo baseline gets IntentBond's notation the way an agent following its skill
   would write it: an OFT item per requirement, implementation tags, a named `utest` tag and
   `@pytest.mark.oft_id` marker per test, the pytest hook from IntentBond's example, and
   `scope.json` (`../oft_layer.py`).
3. Each scenario script runs unchanged; what it added is tagged the same way. A reworded
   requirement gets revision 2; variant X2 leaves it at 1.
4. `ib check --base <main before the scenario> --candidate HEAD` with two scopes:
   - **default**: the documented example (links required, JUnit execution links);
   - **strict**: also a required revision increase for changed content, no skipped tests,
     and every baseline test pinned in `required_artifacts`.
5. Exit 1 is **rejected**, 4 is **review** (checks passed, a person must review), 0 is
   **passed**.

```bash
python3 -m venv ibvenv && ibvenv/bin/pip install <intentbond checkout> && ibvenv/bin/ib install-oft
python3 experiments/intentbond/run.py --work <dir> --gnupg <short dir> --ib ibvenv/bin/ib --python-bin .venv/bin
.venv/bin/python experiments/ours.py --work <dir> --gnupg <short dir> --out experiments/ours-variants.json
python3 experiments/report.py
```

## Every scenario

| Scenario | This verifier | Default | Strict | What IntentBond saw |
|---|---|---|---|---|
| baseline | passes | passed | passed | Coverage complete; 15 linked tests pass |
| 00 clean pull request | passes | review | review | Any spec or test change goes to a person, by design |
| T1 reused ID | T1 | rejected | rejected | Two active items for `req~auth-006` |
| T2 never implemented | T2 | rejected | rejected | No implementation or test links |
| T3 commit only adds a comment | T3 | rejected | rejected | The missing test link; the comment counts as the implementation link (see X1) |
| T4 no tests | T4 | rejected | rejected | No test link |
| T5 failing test | T5 | rejected | rejected | The suite failed; the linked lockout test failed |
| T5 suite won't load | T5 | rejected | rejected | Collection error; no linked test observed |
| T6 `assert True` test | T6 | review | review | The test passes and is linked; the reviewer decides, with the diff in `review.patch` |
| T7 weakened tests | T7 | review | rejected | Strict: the pinned test names are gone |
| T8 spec changed after the code | T8 | rejected | rejected | Revision 2 leaves the links on revision 1 outdated |
| A1 no contract operation | A1 | review | review | New requirement and test go to review; the contract isn't an input |
| A2, A3, A5, A6 leaked field, A7 | A2–A7 | passed | passed | API contracts are outside its scope |
| A4 breaking change | A4 | review | review | A test was edited, so it goes to review |
| A6 undocumented status | A6 | review | review | A test was edited, so it goes to review |
| H4 "refactor" changes behaviour | H4 | rejected | rejected | A lockout test failed: the tests caught it |
| H1–H3, H5–H9 (8 runs) | H1–H9 | passed | passed | Git conventions are outside its scope |
| X1 comment as code, `assert True` as test | T3 | review | review | Both links exist and the test passes; the reviewer decides |
| X2 rewording, no revision bump | T8 | review | rejected | Strict: changed content without a higher revision |
| X3 weakened tests, same names | T7 | review | review | Same pinned names, still passing; the reviewer sees the weaker assertions |

## What IntentBond does that this verifier doesn't

- **Evidence you can check later.** Each check saves its results with hashes of the source.
  `ib verify` on the checked commit returned `status: matched, review: not_needed`; after a
  later code edit it returned `error: Candidate contents differ from tested evidence; rerun
  checks`.
- **Pinned tests.** Named tests in the trusted scope must run and pass. In T7 (strict) that
  rejected the rewrite because the pinned tests disappeared, even though other tagged tests
  remained.
- **A review step built in.** Every spec or test change is collected into `review.patch`
  with a summary of changed items, so the reviewer sees exactly what moved.
- **More ways to prove things.** An explicit revision policy (rejected X2 in strict mode),
  tags read with Python's tokenizer so strings don't count, and optional Alloy and Z3
  checks (not exercised here).

## What the runs show

- **On links and test runs they agree.** Reused ID, missing implementation, missing tests,
  a failing test, a broken suite, a stale revision and a "refactor" that broke a test: both
  reject all seven.
- **Both distrust the change being checked.** IntentBond reads its scope from the base, as
  this verifier reads its config from the base branch.
- **Where the answer needs judgement, IntentBond asks a person.** Code that is only a
  comment, an `assert True` test and weakened tests (T6, X1, X3) pass its checks and go to
  review, as designed. This verifier answers those with T3, T6 and T7, so the reviewer
  reads a finding instead of hunting for it.
- **Revisions are a policy.** Strict mode rejects reworded content without a higher revision
  (X2); the default sends it to review. This verifier reads the change from git.
- **The API contract and git history** are outside IntentBond's scope.

## Using them together

1. **This verifier's findings in IntentBond's review.** IntentBond decides what a person must
   review; this verifier tells them what's wrong before they start.
2. **IntentBond's evidence for this verifier's results.** Saving results tied to source
   hashes is this verifier's open gap; IntentBond's bundle and `verify` are a model for it.
3. **Pinned tests as a T4 option.** "These named tests must exist and pass" is a stronger
   rule than "at least one tagged test" and would suit critical requirements.

Pick IntentBond when people review every change and you want that review focused and its
evidence kept, this verifier when you need to know what's wrong without reading the code,
and both when you want both.

## Limits of this comparison

- Python only. The tags were written by a script acting as a careful agent, not by a real
  agent.
- The scenarios were written to test this verifier, so most of them ask its questions. The
  probes ask IntentBond's.
- Exit 4 counts as "review", not as a detection or a miss: a careful reviewer may well catch
  T6, X1 and X3 in `review.patch`.
- When `JAVA_TOOL_OPTIONS` is set (as in some CI and proxy setups), Java prints a notice that
  IntentBond counts as an OpenFastTrace import diagnostic, so every check errors. The runner
  removes that variable for `ib`; OpenFastTrace needs no network.

Results: `results/intentbond.json` (both scopes, every scenario), `results/probes.json`, and
`../ours-variants.json` for this verifier on the variants. This verifier's results for the
26 attacks are in `demo/results/python/`.
