# Seeded faults: ledger · rust

- Faults with a check written for them: **9 of 9 caught**
- Probes (behaviour changes only the agent's own tests can notice): **2 of 2 caught**
- Caught by the verifier while the held-out black-box tests still pass: 8

| Fault | What the agent did | Expected | Newly failing | Statuses | Held-out tests | Result |
|---|---|---|---|---|---|---|
| shadow-column | A migration adds a column the data contract doesn't have. | D5 | D5 | AC-led-001 Sync → Data | passes | **caught** |
| shadow-table | A migration adds a table the data contract doesn't have. | D5 | D5 | - | passes | **caught** |
| lineage-swap | The report view gives the same numbers but reads ledger_entries, which its lineage doesn't declare. | D6 | D6, H4, T5, T6 | AC-led-009 Sync → Failing | passes | **caught** |
| dropped-foreign-key | A table is rebuilt without its foreign key. | D5 | A6, A8, D5, T5, T6 | AC-led-003 Sync → Failing; AC-led-004 Sync → Failing; AC-led-005 Sync → Failing; AC-led-006 Sync → Failing; AC-led-007 Sync → Failing; AC-led-008 Sync → Failing; AC-led-009 Sync → Failing | fails | **caught** |
| edited-migration | A migration already merged to main is edited. | D7 | D7 | - | passes | **caught** |
| contract-follows-database | The agent adds a column and edits the data contract to match, so the schema check passes. | H10 | H10 | - | passes | **caught** |
| loosened-api-contract | The agent loosens a response schema in the API contract. | A3, H10 | A3, C5, H10 | AC-led-001 Sync → Drift | passes | **caught** |
| shadow-route | An endpoint ships that the API contract doesn't have. | A5 | A5 | - | passes | **caught** |
| untagged-tests | A requirement's tests are renamed and no longer name it. | T4 | A6, T4 | AC-led-008 Sync → Untested | passes | **caught** |
| wrong-net | Probe: net becomes gross plus refunds. Only the agent's own tests can notice. | probe | T5, T6 | AC-led-009 Sync → Failing | fails | **caught** |
| refund-only-days-dropped | Probe: days with a refund and no payment vanish from the report. Only the agent's own tests can notice. | probe | T5, T6 | AC-led-009 Sync → Failing | fails | **caught** |
