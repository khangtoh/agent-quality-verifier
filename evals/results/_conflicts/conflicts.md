# Conflicts and drift: ledger · go

## Conflicts planted before any code exists

- Conflicts a check is written for: **7 of 7 caught** (before: 0 of 7)
- Probes (the conflict is in the meaning of two sentences): **0 of 2 caught**
- False alarms on the unedited problem: 0

| Case | What the people wrote | Expected | Verifier before | Verifier now | What it says now |
|---|---|---|---|---|---|
| status-in-spec | AC-led-006 says an over-refund is rejected with 400; the contract documents 409. | C1 | missed | **caught**: C1 (AC-led-006 Missing → Conflict) | The requirement says 400; POST /payments/{payment_id}/refunds documents 201, 404, 409, 422 |
| status-in-contract | The contract documents 400 for an over-payment; AC-led-004 says 409. | C1 | missed | **caught**: C1 (AC-led-004 Missing → Conflict) | The requirement says 409; POST /orders/{order_id}/payments documents 200, 201, 404, 400, 422 |
| value-in-contract | The contract allows order status "pending" or "paid"; AC-led-002 says a new order is "open". | C2 | missed | **caught**: C2, C7 (AC-led-002 Missing → Conflict; AC-led-003 Missing → Conflict; AC-led-004 Missing → Conflict; AC-led-006 Missing → Conflict) | The requirement says "open"; POST /orders, orders, order_lines allows status: pending | paid |
| value-in-spec | AC-led-008 names the account "income"; the contract allows "cash" or "revenue". | C2 | missed | **caught**: C2, C7 (AC-led-007 Missing → Conflict; AC-led-008 Missing → Conflict) | The requirement says "income"; GET /accounts/{account}/balance allows account: cash | revenue |
| type-across-contracts | refunds.amount_cents is real in the data contract and integer in the API contract. | C3 | missed | **caught**: C3 (AC-led-006 Missing → Conflict) | amount_cents is integer in the API contract and real in refunds |
| status-in-plan | The plan says conflicts return 400; no operation documents 400. | C4 | missed | **caught**: C4 | PLAN.md says status 400, which no operation documents |
| operation-in-plan | The plan describes DELETE /orders/{order_id}; the contract has no such operation. | C4 | missed | **caught**: C4 | PLAN.md describes DELETE /orders/{order_id}, which the contract doesn't have |
| meaning-between-requirements | Probe: AC-led-003 now says amount paid ignores refunds; AC-led-006 still says a refund lowers it. | probe | missed | **missed** | - |
| meaning-in-goal | Probe: the goal says amounts are decimal dollars; both contracts use integer cents. | probe | missed | **missed** | - |

## Drift planted on a finished build (ledger-go-claude-guarded-1)

- Changes a check is written for: **4 of 4 caught** (before: 2 of 4)
- Controls that stayed clean: 1 of 1
- False alarms from the new checks on the finished build itself: 0

| Case | What a person changed after the build | Expected | Verifier before | Verifier now | What it says now |
|---|---|---|---|---|---|
| contract-limit-tightened | A person lowers the most lines an order may have from 100 to 50 in the API contract. The build still accepts 100. | C5 | missed | **caught**: C5 (AC-led-002 Sync → Drift) | Its contract changed in 84a1070 after its last code or test commit: POST /orders › requestBody › content › application/json › schema › properties › lines › maxItems: 100 → 50 |
| data-contract-tightened | Reference: a person makes payments.idempotency_key not nullable in the data contract. The existing D5 check already catches this. | D5 | caught: D5 | **caught**: C5, D5 (AC-led-004 Sync → Data) | payments.idempotency_key is nullable in the database, not null in the contract |
| design-changed | A person changes the plan (ledger entries move to a nightly job) and no requirement or contract follows. | C6 | missed | **caught**: C6 | PLAN.md changed in cc46dca after 9 requirement(s) were built, and no requirement or contract changed with it. Carry the change into the spec, or mark the commit Spec-Impact: none |
| design-typo-acknowledged | Control: a person rewords the plan and marks the commit Spec-Impact: none. Nothing should fail. | nothing (control) | clean | **clean** | - |
| requirement-reworded | Reference: a person rewords a requirement. The existing T8 check already catches this. | T8 | caught: T8 | **caught**: T8 (AC-led-008 Sync → Drift) | Wording changed in c323b7a (0 → null) after its last code or test commit |
