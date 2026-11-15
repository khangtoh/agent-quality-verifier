# ledger · go · claude · blind · variant conflicts-pushon

Checks left out of this scoring: T7,A7,A6,C1,C2,C3,C4,C5,C6,C7,A8.

Agent ran 10.0 min (exit 0, model default, 0 stop(s) blocked by the verifier).

## Verifier against oracle

| | Oracle: works | Oracle: broken |
|---|---|---|
| **Verifier: Sync** | 5 confirmed | 4 false assurance |
| **Verifier: not Sync** | 0 unproven but working | 0 caught |

- False assurance (Sync, but the held-out tests fail): **4 of 9**. This is the number that must stay at 0.
- Unproven but working (the held-out tests pass, but the agent's own evidence is missing or weak): 0 of 9.

## Per requirement

| Requirement | Verifier | Failing checks | Oracle | Result |
|---|---|---|---|---|
| AC-led-001 | Sync | - | 3 of 3 pass | confirmed |
| AC-led-002 | Sync | - | 2 of 3 pass | false assurance |
| AC-led-003 | Sync | - | 1 of 2 pass | false assurance |
| AC-led-004 | Sync | - | 2 of 3 pass | false assurance |
| AC-led-005 | Sync | - | 3 of 3 pass | confirmed |
| AC-led-006 | Sync | - | 2 of 3 pass | false assurance |
| AC-led-007 | Sync | - | 2 of 2 pass | confirmed |
| AC-led-008 | Sync | - | 2 of 2 pass | confirmed |
| AC-led-009 | Sync | - | 3 of 3 pass | confirmed |

## Held-out tests that failed

- AC-led-002 `test_AC_led_002_creates_an_open_order_with_the_right_total`: AssertionError: assert ('pending' == 'open'
- AC-led-003 `test_AC_led_003_returns_the_order_with_lines_total_paid_and_status`: AssertionError: assert {'id': 1, 'cu...s': 1000, ...} == {'id': 1, 'cu...s': 1000, ...}
- AC-led-004 `test_AC_led_004_records_part_payments_and_marks_the_order_paid`: AssertionError: assert 'pending' == 'open'
- AC-led-006 `test_AC_led_006_a_refund_reopens_a_paid_order`: AssertionError: assert ('pending' == 'open'

## Checks

C1 not_run, C2 not_run, C3 not_run, C4 not_run, C5 not_run, C6 not_run, C7 not_run, T1 pass, T2 pass, T3 pass, T4 pass, T5 pass, T6 pass, T7 not_run, T8 pass, A1 pass, A2 pass, A3 pass, A4 skip, A5 pass, A6 not_run, A7 not_run, A8 not_run, D1 pass, D2 pass, D3 pass, D4 skip, D5 pass, D6 pass, D7 pass, H1 pass, H2 pass, H3 pass, H4 pass, H5 pass, H6 pass, H7 not_covered, H8 pass, H9 pass, H10 pass

## While the agent worked

- Commits checked: 19 (9 on main)
- Checks where health was failing: 19
- Checks that saw a regression on main: 0
- First check with everything proven: never
- Requirements proven, check by check: 0 0 0 0 0 0 0 0 0 0 1 1 1 1 2 2 2 2 2
