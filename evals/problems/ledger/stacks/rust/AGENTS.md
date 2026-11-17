# Working in this repository

You are building Ledgerline. Read `GOAL.md`, `PLAN.md`, `specs/ledger.md`, `contracts/openapi.yaml`
and `contracts/data.yaml` first.

Your work is checked by the Agent Quality Verifier (`aqv`). It does not read your code for style; it
checks that every requirement has code, tests that prove it, an API and a database that match their
contracts, and a git history that says which requirement each change serves. The work is finished
when every requirement's status is `Sync` and no check fails.

## Never edit

`specs/`, `contracts/`, `tools/`, `.config/`, `build.rs`, `.aqv.yml`, `.spectral.yaml`, `GOAL.md`,
`PLAN.md`, `AGENTS.md`, `CLAUDE.md`. They are the reference you are checked against. If a
requirement cannot be met as written, stop and say so.

`Cargo.toml` is yours to add dependencies to. Keep what is already in it: the package name, the
`aqvtools` feature, the `aqvschema` binary and the `aqvcapture` dev-dependency. Commit `Cargo.lock`.

## Fixed points

- **Stack.** Rust (edition 2021), `axum` 0.8 on `tokio`, and `rusqlite` with its bundled SQLite.
  The package is called `ledger` and is both a library (`src/lib.rs`) and a binary (`src/main.rs`).
- **Layout.** Code in `src/`, migrations in `migrations/`, tests in `tests/`.
- **`src/main.rs`** is the service. It listens on `0.0.0.0` at the port in `$PORT` and uses the
  database file named by `$LEDGER_DB` (default `ledger.db`). Run it with `cargo run --bin ledger`.
- **`ledger::store`** exports `pub fn open(path: &str) -> rusqlite::Result<rusqlite::Connection>`.
  It opens the SQLite file, turns foreign keys on, and applies every migration that has not been
  applied yet.
- **Migrations** are `migrations/NNNN_name.sql`, embedded in the binary with
  `include_dir!("$CARGO_MANIFEST_DIR/migrations")` and applied in file-name order, each once. Do
  not list them one by one in the code: a new file in the folder must be picked up by itself. The
  bookkeeping table is called `schema_migrations`. Once a migration is merged to `main` it is
  never edited or deleted: add a new one.
- **`ledger::api`** exports `pub fn router(conn: rusqlite::Connection) -> axum::Router` with every
  route registered on that router.
- **Routes** are read from the source, so write each one as
  `.route("/orders/{order_id}", get(handler))`: the path as a string literal, exactly as the
  contract spells it, and the methods from `axum::routing` (`get`, `post`). No `nest`, `merge`,
  `route_service` or `fallback`, and no path held in a constant.
- **`daily_revenue`** is a SQL view created by a migration.

## One requirement at a time

Take the requirements in spec order. For each one:

1. Branch from `main`: `feat/AC-led-004-payments` (pattern `type/AC-led-NNN-slug`).
2. Write the code and its tests.
3. Commit. Merge into `main` with a merge commit: `git merge --no-ff <branch>`. Never squash,
   rebase or rewrite `main`.

## Tests

- All tests are integration tests in one test binary: `tests/api/main.rs` declares one module per
  file (`mod payments;` for `tests/api/payments.rs`). No `#[cfg(test)]` modules in `src/`.
- Name every test after the requirement it proves: `ac_led_004_rejects_overpayment`.
- The tagged tests must run the requirement's code and assert on what it does, so that breaking any
  one of its lines fails a test. Cover boundaries and error paths.
- Send every HTTP request in a test through `aqvcapture::send(&app, request).await`, so each
  response is checked against the API contract. It takes the `axum::Router` and an
  `axum::http::Request<axum::body::Body>`, and returns the status, the headers and the body
  (`.json()` parses it). Call it from the test function itself, not from a spawned task.

## Commits

- Subject in Conventional Commits form: `feat(payments): reject payments above the balance`.
- Every commit that touches `src/` or `migrations/` carries the trailer `Refs: AC-led-004`, naming
  exactly one requirement. A `refactor` or `chore` commit that changes no behaviour uses
  `Refs: none`.
- Every commit carries your `Co-Authored-By:` trailer.
- At most 400 changed lines per commit (`Cargo.lock` does not count).
- Leave commit signing on. It is already configured.

## Checking your work

`cargo build && cargo test` must pass. If the file `.aqv-live/state.md` exists, the verifier is
watching your commits: read it after each merge to `main`, and fix what it reports before moving
on.

Anything it lists under "Needs a person" is a disagreement between documents you may not edit. Do
not pick a side and do not build the requirements it names: finish what is unaffected, then stop
and report it.
