# Plan: Ledgerline

The API contract (`contracts/openapi.yaml`), the data contract (`contracts/data.yaml`) and the
requirements (`specs/ledger.md`) are already written and reviewed. They are the reference: build the
service to match them, and do not change them.

## Shape

One HTTP service in front of one SQLite database file.

- **API.** JSON over HTTP, exactly the operations in the API contract. Errors are
  `{"error": "<message>"}` with the status the contract documents: 404 for something that doesn't
  exist (including an ID that isn't a positive integer), 409 for a request that conflicts with
  what is already recorded, 422 for a body that is missing, malformed or outside the limits in the
  contract.
- **Database.** Tables and views exactly as the data contract declares: same names, columns, types,
  nullability, primary keys and foreign keys, and nothing else. Foreign keys are enforced.
- **Migrations.** The schema is built by numbered SQL files applied in order, each exactly once.
  A migration that has been merged is never edited; a correction is a new migration.
- **Derived data.** `daily_revenue` is a SQL view. It reads only the columns the data contract lists
  under `from:`.
- **Ledger.** A payment and its two ledger entries are written in one transaction, and so are a
  refund and its two entries.

## Order of work

Build the requirements in the order they appear in `specs/ledger.md`; each one builds on the ones
before it.

## Fixed points

The stack, the layout and a few entry points are fixed so that the checks can run. They are listed
in `AGENTS.md`. Everything else is yours to design.
