# OpenFastTrace on the verifier's scenarios

HTML version: [docs/compare/openfasttrace.html](../../docs/compare/openfasttrace.html).

**OpenFastTrace traces what you planned. This verifier tests what the agent delivered.**

Both start from requirements with stable IDs. [OpenFastTrace](https://github.com/itsallcode/openfasttrace)
(OFT) checks that every planned requirement is linked through the levels of a specification
to code and tests. This verifier checks that the evidence behind each requirement holds up
when you run it. We ran OFT 4.10.0 on the same 26 attacks the verifier is tested against,
plus three variants that isolate single questions, to show where the two overlap and where
they answer different questions.

## Two goals

> "Requirement tracing keeps track of whether you actually implemented everything you
> planned to in your specifications. It also identifies obsolete parts of your product and
> helps you to get rid of them." (OpenFastTrace README)

| | OpenFastTrace | This verifier |
|---|---|---|
| Question | Is everything we specified covered, at every level, at its current revision? | Does the evidence behind each requirement hold up, so nobody has to read the code? |
| Links | Tags in code and tests (`[impl->req~x~1]`), items with `Needs:` and `Covers:` | Conventions: `Refs:` trailers, test names, OpenAPI `x-requirements` |
| Levels | Feature → requirement → design → code and tests | Requirement → code and tests |
| Changes | Revisions in the spec (`~1` → `~2`) mark changed meaning | Read from git history |
| Beyond links | — | Runs the tests, measures what they execute, mutates the code, checks the API contract and git history |

**What this verifier is for:** letting a person judge an agent's work without reading its
code. For every requirement it answers three questions with checks that give the same
answer for the same commit every time: do the tests prove it (T1–T8), does the API match its
contract (A1–A7), and can the history be trusted (H1–H9)? Where a check can't see, it says
"not covered", never "pass". It deliberately doesn't manage requirement documents or a
hierarchy, approve what a requirement should say, store audit evidence (yet) or prove
behaviour formally.

## The same scenarios, by the question they ask

"Not its goal" means OFT isn't designed to answer that question, so a clean trace there
says nothing against OFT.

| Question the scenario asks | Runs | This verifier | OpenFastTrace |
|---|---|---|---|
| Is every requirement linked to code and tests, at its current revision? (T1, T2, T4, T8) | 4 | 4 of 4 | 4 of 4 |
| Do the linked tests run and pass? (T5 ×2, H4) | 3 | 3 of 3 | not its goal |
| Is the linked evidence real: code that exists, tests that run it and would catch it breaking? (T3, T6, T7, X1, X3) | 5 | 5 of 5 | 1 of 5 (T3, for its missing test) |
| Is a reworded requirement noticed when nobody marks it as changed? (X2) | 1 | 1 of 1 | relies on the revision rule |
| Does the API match its OpenAPI contract? (A1–A7) | 8 | 8 of 8 | not its goal |
| Does the history follow the conventions? (H1–H3, H5–H9) | 8 | 8 of 8 | not its goal |
| **All scenarios and variants** | **29** | **29 of 29** | **5 of 29** answered by a check; 20 outside its goals |

## How it was run

1. The Python demo baseline gets OFT notation the way an agent following OFT's skill would
   write it: an item per requirement with `Needs: impl, utest`, ten `[impl->req~…]` tags
   beside the code, and a named `utest` tag on each test (`../oft_layer.py`).
2. Each scenario script from `demo/scenarios/` runs unchanged. Whatever it added then gets
   tagged the same way: new requirement items, new tests, and code for a requirement that
   had no tag yet. A reworded requirement gets revision 2, as OFT asks of whoever edits it;
   variant X2 leaves it at 1.
3. `oft trace specs src tests` on the result. Exit 1 means OFT reported a defect.

```bash
python3 experiments/openfasttrace/run.py --work <dir> --gnupg <short dir> --oft-jar openfasttrace-4.10.0.jar
.venv/bin/python experiments/ours.py --work <dir> --gnupg <short dir> --out experiments/ours-variants.json
python3 experiments/report.py
```

## Every scenario

How to read the results:

- **This verifier** names the check that caught the attack (for example T3).
- **reported**: OFT found a trace defect (a missing, duplicate or outdated link), so it
  caught the attack.
- **clean trace**: every link OFT knows about is in place. On an attack this means it
  wasn't flagged, which is expected on rows about running tests, the API or git history;
  on the two clean runs it's the correct result.

| Scenario | This verifier | OpenFastTrace | What OFT saw |
|---|---|---|---|
| baseline | passes | clean trace | Every requirement has its implementation and test links |
| 00 clean pull request | passes | clean trace | The new requirement is linked to its code and tests |
| T1 reused ID | T1 | reported | The reused ID appears as a second item without links; an exact duplicate is reported as a duplicate too |
| T2 never implemented | T2 | reported | No implementation or test links |
| T3 commit only adds a comment | T3 | reported | The missing test link; the implementation tag on a comment counts (see X1) |
| T4 no tests | T4 | reported | No test link |
| T5 failing test | T5 | clean trace | Tracing reads tags; running tests is left to the build |
| T5 suite won't load | T5 | clean trace | Same |
| T6 `assert True` test | T6 | clean trace | The test is tagged, so the link exists |
| T7 weakened tests | T7 | clean trace | The rewritten tests still carry their links |
| T8 spec changed after the code | T8 | reported | Revision 2 leaves the links on revision 1 outdated |
| A1–A7 (8 runs) | A1–A7 | clean trace | The API contract isn't part of the trace |
| H1–H3, H5–H9 (8 runs) | H1–H9 | clean trace | Git history isn't part of the trace |
| H4 "refactor" changes behaviour | H4 | clean trace | A behaviour change only shows when tests run |
| X1 comment as code, `assert True` as test | T3 | clean trace | Both links are declared |
| X2 rewording, no revision bump | T8 | clean trace | Without a new revision the change isn't visible to tracing |
| X3 weakened tests, same names | T7 | clean trace | Same tests, same links |

## What OFT does that this verifier doesn't

- **Traces a hierarchy.** In the probe a feature needs a requirement, the requirement needs
  a design, the design needs code and a test. With the design's test missing OFT reports
  `dsn~password-check~1 (impl, -utest)`; with it added the trace is clean (5 items). This
  verifier has one level.
- **Makes revisions explicit.** Every item carries a revision and links name the revision
  they cover, so a reviewed change in meaning is visible in the spec itself.
- **Reads tags from almost anything.** One syntax in `.py .js .ts .go .rs .kt .kts .java
  .yaml .json .toml .sh .feature` out of the box; `.tsx` needs a workaround.
- **Fits documentation-heavy work.** Version 4.10, Maven and Gradle plugins, an IntelliJ
  plugin, HTML reports, and agent skills for writing traced specs. It suits teams that must
  show coverage of a written specification, such as safety or regulated work.

## What the runs show

- **On links they agree.** Missing implementation, missing tests, a reused ID and a
  requirement whose revision moved on: OFT reports all four, as does this verifier.
- **A tag is a declaration; this verifier's links are tested claims.** OFT accepts a tag on a
  comment or on an `assert True` test (X1), because whether the tagged code works is a
  question for the build, not for tracing. That question is this verifier's main job: T3,
  T6 and T7.
- **Running tests is left to the build.** Failing tests, a broken suite and a behaviour
  change (T5, H4) aren't part of a trace.
- **Revisions are a process, not a detection.** OFT notices a reworded requirement when its
  revision is raised (T8) and not otherwise (X2). This verifier reads the change from git.
- **The API contract and git history** aren't part of OFT's model.

## Using them together

1. **OFT as the specification format.** Teams that already write OFT items keep them,
   including the feature and design levels this verifier doesn't model.
2. **OFT tags as this verifier's claims.** An `[impl->req~…]` tag says the same thing as a
   `Refs:` trailer. Reading OFT tags would let the verifier test those claims with T3–T8
   without re-tagging. Not built yet.
3. **Each where it's strongest.** OFT shows the specification is fully covered; this
   verifier shows the coverage is real.

Pick OFT when you must demonstrate coverage of a written, multi-level specification, this
verifier when you need to judge an agent's output without reading it, and both when you
need both.

## Limits of this comparison

- Python only, OFT 4.10.0. The tags were written by a script acting as a careful agent, not
  by a real agent.
- The scenarios were written to test this verifier, so most of them ask its questions. The
  probes ask OFT's.
- OFT's HTML report and IDE plugin weren't evaluated.

Results: `results/openfasttrace.json`, `results/probes.json`, and `../ours-variants.json`
for this verifier on the variants. This verifier's results for the 26 attacks are in
`demo/results/python/`.
