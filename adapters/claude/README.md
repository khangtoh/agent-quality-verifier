# Claude Code workflows

Two saved workflows that take a project from a goal and a plan to verified code, with `aqv` deciding
what counts as done.

| Workflow | When | What it does |
|---|---|---|
| `aqv-specs` | A goal and a plan exist; `.aqv.yml` is committed | Drafts the requirements in the form the verifier reads, validates them with `aqv check --only T1`, and reviews them against the plan. Commits nothing. |
| `aqv-build` | The spec is committed on `main` | Builds each requirement that is not `Sync` on its own branch, runs `aqv check`, sends failures back to be fixed, and merges only what passes. Ends with a check over all history. |

You review and commit the spec between the two. The verifier treats the spec as the reference, so it
should not go in unread.

## Install

In the project you are building, which needs a `GOAL.md` and a `PLAN.md`:

```bash
aqv init
```

That copies both workflows into `.claude/workflows/`, and writes `.aqv.yml`, the `CLAUDE.md` section
and the rest of what the verifier needs (see the main README). Commit what it wrote. `init` sets up
Go projects; for another stack, copy `workflows/*.js` into `.claude/workflows/` yourself and write
`.aqv.yml` from that language's profile in `demo/langs/`.

## Run

Ask Claude Code to run a workflow by name: "run the aqv-specs workflow", then, once the spec is
committed, "run the aqv-build workflow".

| Argument | Workflow | Default | Meaning |
|---|---|---|---|
| `aqv` | both | `aqv` | Path to the verifier |
| `goal`, `plan` | specs | `GOAL.md`, `PLAN.md` | Where the goal and plan are |
| `maxRevisions` | specs | `1` | Redrafts after a failed check or review |
| `main` | build | `main` | The branch requirements merge into |
| `skip` | build | none | Checks to leave out of each requirement's check, e.g. `"T7,A7"` |
| `finalSkip` | build | same as `skip` | Checks to leave out of the final check |
| `only` | build | every unbuilt requirement | IDs to build in this run |
| `maxFix` | build | `2` | Fix rounds per requirement before it is reported as blocked |
| `continueOnBlocked` | build | `false` | Go on to the next requirement after one is blocked |
| `record` | build | `true` | Pass `--record` to the final check |

## How a requirement passes

`aqv check` exits non-zero while any requirement is unbuilt, so the build workflow does not use the
exit code. A requirement passes when its status is `Sync` and the only failures left belong to
requirements that are not built yet. A failure on an earlier requirement, or on a git rule, blocks it.

## Limits

- Requirements are built one at a time, in spec order. Each needs about three agents (build, check,
  merge) and two more for each fix round.
- A blocked requirement stays on its branch, unmerged, and the run stops unless `continueOnBlocked` is set.
- The verifier reads commits. Status changes when a commit lands, not while files are being edited.
- Unsigned commits fail H9. Set up commit signing first, or pass `skip: "H9"` knowingly.
