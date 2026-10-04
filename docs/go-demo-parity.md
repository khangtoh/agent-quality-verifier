# Two verifiers, two demos: keeping Go and Python in step

The verifier exists twice: the Python package in `aqv/` (the reference) and the Go binary
`bin/aqv` (`cmd/aqv`, `internal/aqv`). Both run for now. Each has its own demo pages:

| | Python | Go |
|---|---|---|
| Verifier | `python -m aqv check` | `bin/aqv check` |
| Demo run | `run_demo.py --lang all` → `demo/.work/` | `run_demo.py --lang all --impl go --work demo/.work-go` |
| Pages | [`demo/results/`](../demo/results/index.html) | [`demo/results-go/`](../demo/results-go/index.html) |
| Pages written by | Python (`aqv/html.py`, `demo/run_demo.py`) | Go (`aqv pages`, `internal/aqv/pages.go`) |

The pages are meant to say the same thing. The Go ones carry a "Go verifier" label in their
headings, their footers name the Go command, and the navigation has a "Results (Go)" link.
Everything else should be identical.

## Where parity stands

Parity has four layers. Each has a check, and each check runs on its own.

| Layer | What must match | Check | Result |
|---|---|---|---|
| **1. Helpers** | Mutants, JUnit parsing, test-name matching, word diffs, routes, globs, number and string formatting | `go test ./internal/...` replays answers recorded from Python (`scripts/gen_golden.py`) | Pass: 1,091 code lines (797 mutants), 16 real JUnit reports, and the rest |
| **2. Verifier** | `results.json`, `report.txt`, `report.html` for the same repo | `scripts/parity.py`: Go on the 168 demo repos against Python's results | **168 of 168** |
| **3. Page writers** | Every demo page, from the same data | `scripts/pages_parity.py`: Go and Python render the Go demo run to temporary folders and compare byte for byte | **217 of 217** identical |
| **4. Published pages** | `demo/results` against `demo/results-go`, from two independent demo runs | `scripts/demo_parity.py`: compares them after removing what always differs | **215 of 217**; 2 differ for a known reason, 0 unexplained |

Layer 4 removes text that differs between any two runs, whichever verifier made them: object
addresses, random tokens and test-case IDs, ports, durations, timestamps, commit hashes (each run
rebuilds the repo with fresh signed commits), and the Go pages' label and footer. It also
sorts runs of test results, because the Python pages were published before tests were sorted
(see step 3).

`scripts/parity_all.sh` runs layers 1, 3 and 4 in a minute or two, and layer 2 too with `--engine`.

## What parity doesn't cover

- **The demo harness is Python for both.** `build_baseline.py`, the per-language `stages.py` and
  `edits.sh`, the scenario scripts and `run_demo.py` build the repos and run the scenarios. `--impl go`
  swaps only the verifier. A "Go demo" is Go checking the same repos.
- **The site home, comparison pages and framework page** are still written by Python
  (`aqv/html.py` `site_index`, `experiments/report.py`). They list both sets of demo pages.
- **The Python-only pytest plugin** (`aqv/pytest_capture.py`) stays Python: it runs inside the
  project's own pytest. Go uses the same file.

## The plan

Steps 1 and 2 are done. The rest are in order, each with a check that says it's finished.

1. **Page writers in Go, with their own page set.** *Done.* `aqv pages` writes `demo/results-go/`
   (per-language `demo.html` and `RESULTS.md`, every scenario page, the examples, the all-languages
   index). `run_demo.py --impl go` calls it, and the site home lists the pages.
   Done when: `scripts/pages_parity.py` reports every page identical. *217 of 217.*

2. **Guards that keep the two in step.** *Done.* `scripts/parity_all.sh`; `scripts/export_langs.py`
   writes `demo/langs.json` so Go reads the language names and stacks from the one place they live.
   Done when: all layers pass from one command.

3. **Fix the truncation difference in both verifiers.** *Next.* A failure message
   that contains the checkout path is cut at a fixed length (200 or 300 characters), so how long the work
   folder's name is changes where the cut falls. The result depends on where the repo is checked out,
   which breaks "the same commit gives the same answer". Fix: replace the repo path with `<repo>`
   before cutting, in `engine.py` and `engine.go`.
   Done when: `RESIDUAL` in `scripts/demo_parity.py` is empty and layer 4 reports 217 of 217.

4. **Publish both page sets from the same code.** After step 3, rerun the Python demo
   (`run_demo.py --lang all`, about two hours) so `demo/results` comes from the current verifier, which
   lists tests in a fixed order, and rerun the Go demo. Then drop the test-sorting normalisation from
   `scripts/demo_parity.py`.
   Done when: layer 4 passes with only run-specific text removed (hashes, tokens, ports, times,
   timestamps), and the published Python pages list tests in the same order as the Go ones.

5. **Run the gates on every change.** Any change to a check, a renderer or a runner profile lands in both
   implementations in the same commit, followed by:
   - `scripts/gen_golden.py` (when a helper changed), then `scripts/parity_all.sh`;
   - `scripts/parity_all.sh --engine` before a release, or whenever a check's behaviour changed.

   Done when: this is the written rule (it is, here) and a CI job runs `parity_all.sh`. *No CI workflow
   exists yet.*

6. **Decide how far to take Go.** Two optional ports, each worth it only for a stated reason:
   - *Site home and comparison pages in Go.* Only if you want the whole site built without Python.
     `site_index` is a small function; `experiments/report.py` is larger. Check: `pages_parity.py`
     extended to cover them.
   - *The harness in Go* (`build_baseline`, scenarios, `run_demo`). The per-language `stages.py` files are
     data written as Python, and the scenarios are bash, so this is a rewrite for a single toolchain and
     little else. Not recommended while Python is needed for the pytest plugin and the Schemathesis A7 check.

7. **Retire the Python verifier, if and when.** Not now. Criteria: layers 1 to 4 are clean for three
   releases in a row; the pytest plugin is shipped separately from the verifier; the golden data is
   regenerated from the last Python release and then frozen; and step 4's Python pages stay published
   as the reference. After that the Go verifier is the only implementation, and the guards compare it
   with the frozen reference instead of live Python.

## Differences that are on purpose

| Where | Python | Go |
|---|---|---|
| Page headings | "… · Python (FastAPI …)" | "… · Python (FastAPI …) · Go verifier" |
| Footers and `RESULTS.md` | "Generated by `python demo/run_demo.py`" | "Generated by `python demo/run_demo.py --impl go`" |
| Which nav link is highlighted on the all-languages index | Results | Results (Go) |
| Work folder | `demo/.work` | `demo/.work-go` |

Anything else that differs is a bug in one of them.
