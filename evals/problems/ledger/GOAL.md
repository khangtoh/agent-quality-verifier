# Goal: Ledgerline

A small back-office service for a shop that takes orders and collects money for them over time.

Staff create customers and orders, record payments against an order (often several part-payments),
and refund payments. Finance needs two things they can trust: account balances that always add up,
and a daily revenue report. Other teams build against the HTTP API, and the finance team reads the
database directly, so both the API and the database schema are published contracts.

The service is done when:

- every operation in `contracts/openapi.yaml` behaves as the requirements in `specs/ledger.md` say,
  and returns only what the contract documents;
- the database has exactly the datasets in `contracts/data.yaml`, and the daily revenue report is
  built only from the sources that contract names;
- money is never lost or invented: every payment and refund is recorded as a balanced pair of
  ledger entries, and a retried payment request is never recorded twice.

All amounts are whole cents. Dates are calendar dates (`YYYY-MM-DD`) supplied by the caller.
