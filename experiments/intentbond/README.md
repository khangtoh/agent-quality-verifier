# IntentBond on the verifier's scenarios

[IntentBond](https://github.com/kbak/intentbond) is the closest existing tool to this
verifier: requirements in OpenFastTrace (OFT) notation, `[impl->req~…]` and
`[utest->req~…]` tags beside code and tests, and `ib check` against a git baseline.
It checks that the links exist, runs the tests, and sends every specification or test
change to human review.

This experiment runs IntentBond on the same Python demo and the same 26 attacks, plus
three variants that isolate what each tool actually checks.

**Result:** IntentBond blocks 8 of the 26 attacks with its documented setup and 9 with its
strictest options. This verifier blocks all 26. IntentBond is not trying to do the API
(A) or git (H) checks, so the fair comparison is the nine T attacks: it blocks 7 (8 with
the strictest options). Five of those are blocked for the reason the attack exists. T3 is
blocked only because the new requirement had no test, T8 only because the person editing
the spec raised its revision, and (strict) T7 only because the weakened tests were renamed.
The three isolating variants confirm it: claims-only code, an unbumped spec change and
weakened tests with the same names all go to human review instead of being rejected
(the strict policy rejects the unbumped spec change).

## How it was run

- IntentBond `5a1200a` (2026-09-29) with its pinned OFT 4.9.0, Python demo baseline
  from `demo/build_baseline.py`.
- `oft_layer.adopt` adds IntentBond's notation the way an agent following its skill
  would: an OFT item per requirement (`Needs: impl, utest`), 10 implementation tags,
  a named `utest` tag and `@pytest.mark.oft_id` marker per test, the pytest hook from
  IntentBond's example, and `scope.json`.
- Each scenario script from `demo/scenarios/` runs unchanged. `oft_layer.update` then
  tags what the scenario added (new requirement items, new tests, and code for a
  requirement that has no implementation tag yet), as the agent would before its pull
  request. A requirement whose wording changed gets revision 2, as OFT asks of whoever
  edits it; variant X2 drops that bump.
- `ib check --base <main before the scenario> --candidate HEAD`, with two scopes:
  - **default**: the documented example scope (`required_coverage` req → impl, utest;
    JUnit tests with execution links).
  - **strict**: also `require_revision_increase`, `allow_skipped_tests: false`, and every
    baseline test pinned in `required_artifacts`.
- Exit codes: **1** rejected, **4** checks passed but a person must review the spec/test
  change, **0** passed. Exit 4 is also what the clean pull request gets, so it is not a
  detection: it's the review every spec or test change receives.

```bash
python3 -m venv ibvenv && ibvenv/bin/pip install <intentbond checkout> && ibvenv/bin/ib install-oft
python3 experiments/intentbond/run.py --work <dir> --gnupg <short dir> --ib ibvenv/bin/ib --python-bin .venv/bin
.venv/bin/python experiments/intentbond/ours.py --work <same dir> --gnupg <same gnupg dir>
```

## Results

✅ blocked · 👀 sent to review (exit 4) · ➖ passed

| Scenario | This verifier | IntentBond default | IntentBond strict | What IntentBond saw |
|---|---|---|---|---|
| Baseline | ➖ passes | ➖ | ➖ | 15 tests pass, coverage complete |
| 00 Clean pull request | ➖ passes | 👀 | 👀 | Any spec or test change needs review |
| T1 Reused requirement ID | ✅ T1 | ✅ | ✅ | Two active items for `req~auth-006` |
| T2 Requirement never implemented | ✅ T2 | ✅ | ✅ | `req~auth-007` has no impl and no utest |
| T3 Commit only adds a comment | ✅ T3 | ✅ | ✅ | No utest for `req~auth-007`; the comment **was accepted** as its implementation (see X1) |
| T4 No tests | ✅ T4 | ✅ | ✅ | No utest for `req~auth-007` |
| T5 Tagged test fails | ✅ T5 | ✅ | ✅ | Suite failed; linked lockout test failed |
| T5 Suite won't load | ✅ T5 | ✅ | ✅ | Collection error; linked tests not observed |
| T6 `assert True` test | ✅ T6 | 👀 | 👀 | Test passes and is linked; review only |
| T7 Weakened tests | ✅ T7 | 👀 | ✅ | Strict: the pinned test names disappeared, not the weakness (see X3) |
| T8 Spec changed after the code | ✅ T8 | ✅ | ✅ | Revision 2 leaves the `~1` links outdated, *because the editor bumped it* (see X2) |
| A1 No contract operation | ✅ A1 | 👀 | 👀 | New requirement and test; no contract check |
| A2 Unlinked operation | ✅ A2 | ➖ | ➖ | Contract isn't an input |
| A3 Contract fails lint | ✅ A3 | ➖ | ➖ | |
| A4 Breaking change | ✅ A4 | 👀 | 👀 | Review only because a test was edited |
| A5 Undocumented route | ✅ A5 | ➖ | ➖ | |
| A6 Leaked field in response | ✅ A6 | ➖ | ➖ | |
| A6 Undocumented status code | ✅ A6 | 👀 | 👀 | Review only because a test was edited |
| A7 Server error on valid input | ✅ A7 | ➖ | ➖ | No test sends that input |
| H1 `wip` commit subject | ✅ H1 | ➖ | ➖ | No git history checks |
| H2 No `Refs:` trailer | ✅ H2 | ➖ | ➖ | |
| H3 Two requirements in one commit | ✅ H3 | ➖ | ➖ | |
| H4 "Refactor" changes behaviour | ✅ H4 | ✅ | ✅ | A lockout test failed (caught by the tests, not the label) |
| H5 Huge commit | ✅ H5 | ➖ | ➖ | |
| H6 Bad branch name | ✅ H6 | ➖ | ➖ | |
| H7 Main rewritten | ✅ H7 | ➖ | ➖ | |
| H8 Agent not named | ✅ H8 | ➖ | ➖ | |
| H9 Unsigned commit | ✅ H9 | ➖ | ➖ | |
| **Blocked, of 26 attacks** | **26** | **8** | **9** | |
| **T attacks blocked, of 9** | **9** | **7** | **8** | |

### Isolating variants

| Variant | This verifier | IntentBond default | IntentBond strict |
|---|---|---|---|
| X1 Comment as the implementation, `assert True` as its test | ✅ T3 (Gone) | 👀 | 👀 |
| X2 Spec wording changed, nobody bumps the OFT revision | ✅ T8 (Drift) | 👀 | ✅ revision increase required |
| X3 Lockout tests keep their names but stop checking the lockout | ✅ T7 (Weak) | 👀 | 👀 |

## What this shows

- **Links vs evidence.** IntentBond proves that tags exist, reference the current
  revision, and that the test suite (and, strictly, named tests) pass. It doesn't check
  that a tag sits on real code (X1, T3), that a test runs the code it claims (T6), or
  that a test would notice the code breaking (X3, T7). It leaves those to review, by
  design: "passing checks do not approve them". This verifier's T3, T6 and T7 turn those
  questions into checks.
- **Spec changes.** IntentBond catches a stale implementation only when the editor
  raises the revision, or when the strict policy forces it (X2). T8 reads the change from
  git, so nobody has to remember.
- **Review on every change.** Exit 4 on the clean pull request means a person reviews
  every spec or test change. That is a sound default when people review anyway; it isn't
  a signal that something is wrong.
- **Out of scope for IntentBond:** the API contract (A) and git practices (H). H4 was
  caught only because a test covers the lockout boundary.

## What IntentBond does that this verifier doesn't

- **Evidence bundles tied to the checked source**, with `ib verify` to match a later
  commit to them. This verifier doesn't store results between runs yet.
- **Pinned tests** (`required_artifacts`): named tests must run and pass, so deleting or
  renaming them fails even when other tagged tests remain.
- **An explicit revision policy** for requirement content.
- **Python tags read with the tokenizer**, so tags in strings or docstrings don't count.
- Optional **Alloy / Z3** checks (not exercised here).

## Notes

- The tagging is a deterministic stand-in for an agent following IntentBond's skill. A
  real agent may tag differently; X1 shows that a misplaced tag is accepted either way.
- **Container quirk:** when `JAVA_TOOL_OPTIONS` is set (as in some CI and proxy setups),
  Java prints a notice that IntentBond counts as an OFT import diagnostic, so every check
  errors with exit 2. `run.py` removes the variable for `ib` (OFT needs no network).
- Python only. Results: `results/intentbond.json` (both scopes, every scenario) and
  `results/ours-variants.json`. This verifier's results for the 26 attacks are in
  `demo/results/python/`.
