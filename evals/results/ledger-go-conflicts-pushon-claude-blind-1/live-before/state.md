# Verifier state at d523613 on main

State: 2 of 9 requirements proven (Sync).
Health: failing. 7 problem(s) need attention.

## Requirements

AC-led-001   Contract     A6
AC-led-002   Contract     A6
AC-led-003   Contract     A6
AC-led-004   Contract     A6
AC-led-005   Sync
AC-led-006   Contract     A6
AC-led-007   Sync
AC-led-008   Contract     A6
AC-led-009   Contract     A6

## Needs attention

- A6 AC-led-001: TestAC_led_001_DatabaseFailureReturns500: POST /customers returned 500, which the contract doesn't document; TestAC_led_001_UnknownRouteAndMethodReturnJSONErrors called DELETE /customers, which the contract doesn't have; TestAC_led_001_UnknownRouteAndMethodReturnJSONErrors called GET /nothing-here, which the contract doesn't have
- A6 AC-led-002: TestAC_led_002_DatabaseFailureReturns500: POST /orders returned 500, which the contract doesn't document
- A6 AC-led-003: TestAC_led_003_DatabaseFailureReturns500: GET /orders/{order_id} returned 500, which the contract doesn't document
- A6 AC-led-004: TestAC_led_004_DatabaseFailureReturns500: POST /orders/{order_id}/payments returned 500, which the contract doesn't document
- A6 AC-led-006: TestAC_led_006_DatabaseFailureReturns500: POST /payments/{payment_id}/refunds returned 500, which the contract doesn't document
- A6 AC-led-008: TestAC_led_008_DatabaseFailureReturns500: GET /accounts/{account}/balance returned 500, which the contract doesn't document
- A6 AC-led-009: TestAC_led_009_DatabaseFailureReturns500: GET /reports/daily-revenue returned 500, which the contract doesn't document

Not run on this commit (they run in the final check): C1, C2, C3, C4, C5, C6, T7, A7, A8.
