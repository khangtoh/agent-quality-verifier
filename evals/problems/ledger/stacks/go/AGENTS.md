# Working in this repository

You are building Ledgerline. Read `GOAL.md`, `PLAN.md`, `specs/ledger.md`, `contracts/openapi.yaml`
and `contracts/data.yaml` first.

Your work is checked by the Agent Quality Verifier (`aqv`). It does not read your code for style; it
checks that every requirement has code, tests that prove it, an API and a database that match their
contracts, and a git history that says which requirement each change serves. The work is finished
when every requirement's status is `Sync` and no check fails.

## Never edit

`specs/`, `contracts/`, `tools/`, `.aqv.yml`, `.spectral.yaml`, `GOAL.md`, `PLAN.md`, `AGENTS.md`,
`CLAUDE.md`. They are the reference you are checked against. If a requirement cannot be met as
written, stop and say so.

## Fixed points

- **Stack.** Go, the chi router (`github.com/go-chi/chi/v5`), `database/sql` with the pure-Go
  SQLite driver `modernc.org/sqlite`. Module path `example.com/ledger`. No cgo.
- **Layout.** Code in `internal/` and `cmd/`. Tests in `*_test.go` next to the code.
- **`cmd/server`** is the service. It listens on the port in `$PORT` and uses the database file
  named by `$LEDGER_DB` (default `ledger.db`).
- **`internal/store`** exports `func Open(path string) (*sql.DB, error)`. It opens the SQLite file,
  turns foreign keys on, and applies every migration that has not been applied yet.
- **Migrations** are `internal/store/migrations/NNNN_name.sql`, embedded in the binary and applied
  in order, each once. The bookkeeping table is called `schema_migrations`. Once a migration is
  merged to `main` it is never edited or deleted: add a new one.
- **`internal/api`** exports `func NewRouter(db *sql.DB) chi.Router` with every route registered
  on that router.
- **`daily_revenue`** is a SQL view created by a migration.

## One requirement at a time

Take the requirements in spec order. For each one:

1. Branch from `main`: `feat/AC-led-004-payments` (pattern `type/AC-led-NNN-slug`).
2. Write the code and its tests.
3. Commit. Merge into `main` with a merge commit: `git merge --no-ff <branch>`. Never squash,
   rebase or rewrite `main`.

## Tests

- Name every test after the requirement it proves: `TestAC_led_004_RejectsOverpayment`.
- The tagged tests must run the requirement's code and assert on what it does, so that breaking any
  one of its lines fails a test. Cover boundaries and error paths.
- Send every HTTP request in a test through `aqvcapture.Do(t, handler, req)` from
  `example.com/ledger/tools/aqvcapture`, so each response is checked against the API contract.

## Commits

- Subject in Conventional Commits form: `feat(payments): reject payments above the balance`.
- Every commit that touches `internal/` or `cmd/` carries the trailer `Refs: AC-led-004`, naming
  exactly one requirement. A `refactor` or `chore` commit that changes no behaviour uses
  `Refs: none`.
- Every commit carries your `Co-Authored-By:` trailer.
- At most 400 changed lines per commit (`go.sum` does not count).
- Leave commit signing on. It is already configured.

## Checking your work

`go build ./... && go test ./...` must pass. If the file `.aqv-live/state.md` exists, the verifier
is watching your commits: read it after each merge to `main`, and fix what it reports before moving
on.

Anything it lists under "Needs a person" is a disagreement between documents you may not edit. Do
not pick a side and do not build the requirements it names: finish what is unaffected, then stop
and report it.
