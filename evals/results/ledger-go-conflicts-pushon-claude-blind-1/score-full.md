# ledger · go · claude · blind · variant conflicts-pushon

Agent ran 10.0 min (exit 0, model default, 0 stop(s) blocked by the verifier).

## Verifier against oracle

| | Oracle: works | Oracle: broken |
|---|---|---|
| **Verifier: Sync** | 2 confirmed | 0 false assurance |
| **Verifier: not Sync** | 3 unproven but working | 4 caught |

- False assurance (Sync, but the held-out tests fail): **0 of 9**. This is the number that must stay at 0.
- Unproven but working (the held-out tests pass, but the agent's own evidence is missing or weak): 3 of 9.

## Per requirement

| Requirement | Verifier | Failing checks | Oracle | Result |
|---|---|---|---|---|
| AC-led-001 | Contract | A6 | 3 of 3 pass | unproven but working |
| AC-led-002 | Conflict | A6, C2 | 2 of 3 pass | caught |
| AC-led-003 | Conflict | A6, C7 | 1 of 2 pass | caught |
| AC-led-004 | Conflict | A6, C7 | 2 of 3 pass | caught |
| AC-led-005 | Sync | - | 3 of 3 pass | confirmed |
| AC-led-006 | Conflict | A6, A8, C1, C2, C3 | 2 of 3 pass | caught |
| AC-led-007 | Sync | - | 2 of 2 pass | confirmed |
| AC-led-008 | Contract | A6 | 2 of 2 pass | unproven but working |
| AC-led-009 | Contract | A6 | 3 of 3 pass | unproven but working |

## Held-out tests that failed

- AC-led-002 `test_AC_led_002_creates_an_open_order_with_the_right_total`: AssertionError: assert ('pending' == 'open'
- AC-led-003 `test_AC_led_003_returns_the_order_with_lines_total_paid_and_status`: AssertionError: assert {'id': 1, 'cu...s': 1000, ...} == {'id': 1, 'cu...s': 1000, ...}
- AC-led-004 `test_AC_led_004_records_part_payments_and_marks_the_order_paid`: AssertionError: assert 'pending' == 'open'
- AC-led-006 `test_AC_led_006_a_refund_reopens_a_paid_order`: AssertionError: assert ('pending' == 'open'

## Checks

C1 fail, C2 fail, C3 fail, C4 pass, C5 pass, C6 pass, C7 fail, T1 pass, T2 pass, T3 pass, T4 pass, T5 pass, T6 pass, T7 pass, T8 pass, A1 pass, A2 pass, A3 pass, A4 skip, A5 pass, A6 fail, A7 pass, A8 fail, D1 pass, D2 pass, D3 pass, D4 skip, D5 pass, D6 pass, D7 pass, H1 pass, H2 pass, H3 pass, H4 pass, H5 pass, H6 pass, H7 not_covered, H8 pass, H9 pass, H10 pass

## While the agent worked

- Commits checked: 19 (9 on main)
- Checks where health was failing: 19
- Checks that saw a regression on main: 0
- First check with everything proven: never
- Requirements proven, check by check: 0 0 0 0 0 0 0 0 0 0 1 1 1 1 2 2 2 2 2
