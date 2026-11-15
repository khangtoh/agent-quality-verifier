# Ledgerline requirements

One requirement per line. `(api: ...)` names the operations in `contracts/openapi.yaml` that serve
it; `(data: ...)` names the datasets in `contracts/data.yaml` it owns.

## Customers and orders

- **AC-led-001** (api: POST /customers; data: customers): A customer is created with a name and an email address and gets a new ID; a second customer with an email address already in use is rejected with 409 and is not stored.
- **AC-led-002** (api: POST /orders; data: orders, order_lines): An order is created for an existing customer with one or more lines, starts with status "open", and its total is the sum of quantity times unit price over its lines; an order for a customer that does not exist is rejected with 404.
- **AC-led-003** (api: GET /orders/{order_id}): An order is returned with its lines in the order they were given, its total, the amount paid so far (payments minus refunds) and its status; an order that does not exist returns 404.

## Payments and refunds

- **AC-led-004** (api: POST /orders/{order_id}/payments; data: payments): A payment records an amount and a payment date against an order and returns 201; a payment larger than the order's unpaid balance is rejected with 409 and not recorded; when the amount paid reaches the order's total, its status becomes "paid".
- **AC-led-005** (api: POST /orders/{order_id}/payments): A payment request that repeats an Idempotency-Key already used on the same order returns the original payment with 200 and records nothing new; requests without the header are never treated as repeats.
- **AC-led-006** (api: POST /payments/{payment_id}/refunds; data: refunds): A refund records an amount and a refund date against a payment and returns 201; a refund larger than what is left of the payment after its earlier refunds is rejected with 409 and not recorded; a refund puts the order's status back to "open" when the amount paid falls below its total.

## Ledger and reporting

- **AC-led-007** (data: ledger_entries): Every payment writes two ledger entries for its amount, a debit to "cash" and a credit to "revenue", and every refund writes two for its amount, a debit to "revenue" and a credit to "cash", so total debits always equal total credits.
- **AC-led-008** (api: GET /accounts/{account}/balance): The balance of the "cash" or "revenue" account is the sum of its debits minus the sum of its credits, and is 0 before anything is recorded; any other account name returns 404.
- **AC-led-009** (api: GET /reports/daily-revenue; data: daily_revenue): The daily revenue report lists, for every date that has a payment or a refund, the payments dated that day (gross), the refunds dated that day, and gross minus refunds (net), in date order; it is computed from the payments and refunds datasets only.
