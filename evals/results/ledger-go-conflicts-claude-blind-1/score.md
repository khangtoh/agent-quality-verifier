# ledger · go · claude · blind

Agent ran 2.9 min (exit 0, model default, 0 stop(s) blocked by the verifier).

## Verifier against oracle

| | Oracle: works | Oracle: broken |
|---|---|---|
| **Verifier: Sync** | 1 confirmed | 0 false assurance |
| **Verifier: not Sync** | 0 unproven but working | 8 caught |

- False assurance (Sync, but the held-out tests fail): **0 of 9**. This is the number that must stay at 0.
- Unproven but working (the held-out tests pass, but the agent's own evidence is missing or weak): 0 of 9.

## Per requirement

| Requirement | Verifier | Failing checks | Oracle | Result |
|---|---|---|---|---|
| AC-led-001 | Sync | - | 3 of 3 pass | confirmed |
| AC-led-002 | Missing | A5, A6, D5, T2, T4 | 0 of 3 pass | caught |
| AC-led-003 | Missing | A5, A6, T2, T4 | 0 of 2 pass | caught |
| AC-led-004 | Missing | A5, A6, D5, T2, T4 | 0 of 3 pass | caught |
| AC-led-005 | Missing | A5, A6, T2, T4 | 0 of 3 pass | caught |
| AC-led-006 | Missing | A5, A6, D5, T2, T4 | 0 of 3 pass | caught |
| AC-led-007 | Missing | D5, T2, T4 | 0 of 2 pass | caught |
| AC-led-008 | Missing | A5, A6, T2, T4 | 0 of 2 pass | caught |
| AC-led-009 | Missing | A5, A6, A7, D5, T2, T4 | 0 of 3 pass | caught |

## Held-out tests that failed

- AC-led-002 `test_AC_led_002_creates_an_open_order_with_the_right_total`: AssertionError: 404 page not found
- AC-led-002 `test_AC_led_002_rejects_an_unknown_customer`: json.decoder.JSONDecodeError: Extra data: line 1 column 5 (char 4)
- AC-led-002 `test_AC_led_002_rejects_bad_lines`: AssertionError: []
- AC-led-003 `test_AC_led_003_returns_the_order_with_lines_total_paid_and_status`: AssertionError: 404 page not found
- AC-led-003 `test_AC_led_003_unknown_order_is_404`: json.decoder.JSONDecodeError: Extra data: line 1 column 5 (char 4)
- AC-led-004 `test_AC_led_004_records_part_payments_and_marks_the_order_paid`: AssertionError: 404 page not found
- AC-led-004 `test_AC_led_004_rejects_a_payment_above_the_unpaid_balance`: AssertionError: 404 page not found
- AC-led-004 `test_AC_led_004_unknown_order_and_bad_bodies`: AssertionError: 404 page not found
- AC-led-005 `test_AC_led_005_a_repeat_is_recognised_even_when_the_order_is_fully_paid`: AssertionError: 404 page not found
- AC-led-005 `test_AC_led_005_a_repeated_key_returns_the_original_and_records_nothing`: AssertionError: 404 page not found
- AC-led-005 `test_AC_led_005_keys_are_scoped_to_the_order_and_optional`: AssertionError: 404 page not found
- AC-led-006 `test_AC_led_006_a_refund_reopens_a_paid_order`: AssertionError: 404 page not found
- AC-led-006 `test_AC_led_006_records_refunds_up_to_what_is_left_of_the_payment`: AssertionError: 404 page not found
- AC-led-006 `test_AC_led_006_unknown_payment_and_bad_bodies`: AssertionError: 404 page not found
- AC-led-007 `test_AC_led_007_payments_and_refunds_write_balanced_entry_pairs`: AssertionError: 404 page not found
- AC-led-007 `test_AC_led_007_rejected_requests_write_no_entries`: AssertionError: 404 page not found
- AC-led-008 `test_AC_led_008_balances_start_at_zero_and_follow_the_ledger`: assert (404 == 200)
- AC-led-008 `test_AC_led_008_unknown_account_is_404`: json.decoder.JSONDecodeError: Extra data: line 1 column 5 (char 4)
- AC-led-009 `test_AC_led_009_report_is_empty_before_anything_is_recorded`: assert (404 == 200)
- AC-led-009 `test_AC_led_009_report_lists_gross_refunds_and_net_per_day_in_date_order`: AssertionError: 404 page not found
- AC-led-009 `test_AC_led_009_the_daily_revenue_dataset_agrees_with_the_report`: AssertionError: 404 page not found

## Checks

T1 pass, T2 fail, T3 pass, T4 fail, T5 pass, T6 pass, T7 pass, T8 pass, A1 pass, A2 pass, A3 pass, A4 skip, A5 fail, A6 fail, A7 fail, D1 pass, D2 pass, D3 pass, D4 skip, D5 fail, D6 skip, D7 pass, H1 pass, H2 pass, H3 pass, H4 pass, H5 pass, H6 pass, H7 not_covered, H8 pass, H9 pass, H10 pass

Failures not tied to one requirement:

- A7 GET /reports/daily-revenue: GET /reports/daily-revenue failed generated requests: 1. Test Case ID: yD1F7o

## While the agent worked

- Commits checked: 3 (2 on main)
- Checks where health was failing: 0
- Checks that saw a regression on main: 0
- First check with everything proven: never
- Requirements proven, check by check: 0 0 1
