# Verifier state at d523613 on main

State: 2 of 9 requirements proven (Sync).
Health: needs a person. 6 of 14 problem(s) can only be settled by a person.

## Requirements

AC-led-001   Contract     A6
AC-led-002   Conflict     A6, C2
AC-led-003   Conflict     A6, C7
AC-led-004   Conflict     A6, C7
AC-led-005   Sync
AC-led-006   Conflict     A6, A8, C1, C2, C3
AC-led-007   Sync
AC-led-008   Contract     A6
AC-led-009   Contract     A6

## Needs a person

These are disagreements between documents you may not edit, or changes only a person may make.
Do not pick a side and do not build the requirements they name. Finish what is unaffected, then stop and report them.

- C2 AC-led-002: The requirement says "open"; POST /orders, orders, order_lines allows status: pending | paid
- C1 AC-led-006: The requirement says 400; POST /payments/{payment_id}/refunds documents 201, 404, 409, 422
- C2 AC-led-006: The requirement says "open"; the contracts allow status: pending | paid
- C3 AC-led-006: amount_cents is integer in the API contract and real in refunds
- C7 AC-led-003: Carries status, which is in dispute (see C2 on AC-led-002, AC-led-006)
- C7 AC-led-004: Quotes "paid", a value of status, which is in dispute (see C2 on AC-led-002, AC-led-006)

## Needs attention

- A6 AC-led-001: TestAC_led_001_DatabaseFailureReturns500: POST /customers returned 500, which the contract doesn't document; TestAC_led_001_UnknownRouteAndMethodReturnJSONErrors called DELETE /customers, which the contract doesn't have; TestAC_led_001_UnknownRouteAndMethodReturnJSONErrors called GET /nothing-here, which the contract doesn't have
- A6 AC-led-002: TestAC_led_002_DatabaseFailureReturns500: POST /orders returned 500, which the contract doesn't document
- A6 AC-led-003: TestAC_led_003_DatabaseFailureReturns500: GET /orders/{order_id} returned 500, which the contract doesn't document
- A6 AC-led-004: TestAC_led_004_DatabaseFailureReturns500: POST /orders/{order_id}/payments returned 500, which the contract doesn't document
- A6 AC-led-006: TestAC_led_006_DatabaseFailureReturns500: POST /payments/{payment_id}/refunds returned 500, which the contract doesn't document
- A6 AC-led-008: TestAC_led_008_DatabaseFailureReturns500: GET /accounts/{account}/balance returned 500, which the contract doesn't document
- A6 AC-led-009: TestAC_led_009_DatabaseFailureReturns500: GET /reports/daily-revenue returned 500, which the contract doesn't document
- A8 AC-led-006: The requirement says 400; its tagged tests saw only 201, 404, 409, 422, 500 from POST /payments/{payment_id}/refunds

Not run on this commit (they run in the final check): T7, A7.
