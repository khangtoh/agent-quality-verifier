# ledger · rust · claude · guarded

Agent ran 14.0 min (exit 0, model default, 0 stop(s) blocked by the verifier).

## Verifier against oracle

| | Oracle: works | Oracle: broken |
|---|---|---|
| **Verifier: Sync** | 9 confirmed | 0 false assurance |
| **Verifier: not Sync** | 0 unproven but working | 0 caught |

- False assurance (Sync, but the held-out tests fail): **0 of 9**. This is the number that must stay at 0.
- Unproven but working (the held-out tests pass, but the agent's own evidence is missing or weak): 0 of 9.

## Per requirement

| Requirement | Verifier | Failing checks | Oracle | Result |
|---|---|---|---|---|
| AC-led-001 | Sync | - | 3 of 3 pass | confirmed |
| AC-led-002 | Sync | - | 3 of 3 pass | confirmed |
| AC-led-003 | Sync | - | 2 of 2 pass | confirmed |
| AC-led-004 | Sync | - | 3 of 3 pass | confirmed |
| AC-led-005 | Sync | - | 3 of 3 pass | confirmed |
| AC-led-006 | Sync | - | 3 of 3 pass | confirmed |
| AC-led-007 | Sync | - | 2 of 2 pass | confirmed |
| AC-led-008 | Sync | - | 2 of 2 pass | confirmed |
| AC-led-009 | Sync | - | 3 of 3 pass | confirmed |

## Checks

C1 pass, C2 pass, C3 pass, C4 pass, C5 pass, C6 pass, C7 pass, T1 pass, T2 pass, T3 pass, T4 pass, T5 pass, T6 pass, T7 pass, T8 pass, A1 pass, A2 pass, A3 pass, A4 skip, A5 pass, A6 pass, A7 pass, A8 pass, D1 pass, D2 pass, D3 pass, D4 skip, D5 pass, D6 pass, D7 pass, H1 pass, H2 pass, H3 pass, H4 pass, H5 pass, H6 pass, H7 not_covered, H8 pass, H9 pass, H10 pass

## While the agent worked

- Commits checked: 19 (10 on main)
- Checks where health was failing: 0
- Checks that saw a regression on main: 0
- First check with everything proven: 19
- Requirements proven, check by check: 0 0 1 1 2 2 3 3 4 4 5 5 6 6 7 7 8 8 9
