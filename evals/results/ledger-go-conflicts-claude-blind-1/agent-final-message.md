# The agent's final message

Copied from the run's agent log, which is not committed.

---

I built and merged AC-led-001, then stopped at AC-led-002: it cannot be met as written, and AGENTS.md says to stop and say so in that case. I know you asked me not to stop early, but every later requirement builds on orders, and the reference files I'm not allowed to edit disagree with each other.

## What is done

AC-led-001 is merged to `main` as a signed merge commit from `feat/AC-led-001-customers`. `go build ./... && go test ./...` passes, and the real server returned 201 then 409 for a repeated email. There was no `.aqv-live/state.md`, so I have no verifier result for it.

- **Store:** `store.Open` turns foreign keys on, and applies each embedded migration once, in order.
- **API:** `POST /customers` returns 201, 409 for an email already in use, and 422 for a bad body.
- **Server:** `cmd/server` listens on `$PORT` and uses `$LEDGER_DB`.

One thing to know: email uniqueness is enforced by a `UNIQUE` constraint on `customers.email`. The data contract doesn't mention one; if the verifier counts it as "something else" in the schema, it would need to move into code.

## What blocks the rest

All four conflicts involve the latest commit, `78b95ce` ("revise the requirements, the contracts and the plan"), which changed one side of each without the other.

1. **Order status, "open" vs "pending" (blocks AC-led-002, 003, 006).** The spec says a new order has status "open". `openapi.yaml` now allows only `pending` or `paid` (it was `open` or `paid` before the revision). Returning "open" fails the contract check; returning "pending" fails the requirement.

2. **Over-refund status, 400 vs 409 (blocks AC-led-006).** The spec now says an over-refund is rejected with 400. The API contract documents only 409 for `createRefund`, and PLAN.md says conflicts are 409.

3. **Amount paid, with or without refunds (AC-led-003 vs 006).** AC-led-003 now says the amount paid ignores refunds. AC-led-006 still says a refund reopens the order "when the amount paid falls below its total", which can never happen if refunds are ignored. The same ambiguity affects "unpaid balance" in AC-led-004, where it decides whether a refunded order can be paid again.

4. **`refunds.amount_cents` is now `real` (AC-led-006, 009).** GOAL.md says all amounts are whole cents, every other amount column is `integer`, and `daily_revenue.refund_cents` is declared `integer` but derived from this column. This one is buildable as written (a REAL column holding whole numbers, cast in the view), but it looks like a mistake in a table finance reads directly.

## Decisions for you

The revision's direction suggests these resolutions, but each one changes a published contract or a money rule, so I did not guess:

1. Status: either put `open` back in the OpenAPI enum, or change the spec to "pending".
2. Over-refund: either put 409 back in AC-led-006, or add a 400 response to the contract.
3. Amount paid: state whether `paid_cents`, the "paid" status and the unpaid balance are net of refunds or gross.
4. Refund amount: confirm `real` is intended, or revert it to `integer`.

Once those files are fixed, I can continue from AC-led-002 on the existing `main`.
