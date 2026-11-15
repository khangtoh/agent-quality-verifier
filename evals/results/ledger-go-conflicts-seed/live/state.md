# Verifier state at c72d377 on main

State: 0 of 9 requirements proven (Sync).
Health: failing. 4 problem(s) need attention.

## Requirements

AC-led-001   Missing      A6, T2, T4
AC-led-002   Conflict     A6, C2, T2, T4
AC-led-003   Missing      A6, T2, T4
AC-led-004   Missing      A6, T2, T4
AC-led-005   Missing      A6, T2, T4
AC-led-006   Conflict     A6, C1, C2, C3, T2, T4
AC-led-007   Missing      T2, T4
AC-led-008   Missing      A6, T2, T4
AC-led-009   Missing      A6, T2, T4

## Needs a person

These are disagreements between documents you may not edit, or changes only a person may make.
Do not pick a side and do not build the requirements they name. Finish what is unaffected, then stop and report them.

- C2 AC-led-002: The requirement says "open"; POST /orders, orders, order_lines allows status: pending | paid
- C1 AC-led-006: The requirement says 400; POST /payments/{payment_id}/refunds documents 201, 404, 409, 422
- C2 AC-led-006: The requirement says "open"; the contracts allows account: cash | revenue; status: pending | paid
- C3 AC-led-006: amount_cents is integer in the API contract and real in refunds

Not run on this commit (they run in the final check): T7, A7.
