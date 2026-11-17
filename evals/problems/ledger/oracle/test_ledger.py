

def error_of(r):
    body = r.json()
    assert set(body) == {"error"} and isinstance(body["error"], str) and body["error"], body
    return body["error"]


# ---------------------------------------------------------------- AC-led-001

def test_AC_led_001_creates_a_customer_with_a_new_id(svc):
    a = svc.customer("ada@example.com", "Ada")
    b = svc.customer("bob@example.com", "Bob")
    assert a == {"id": a["id"], "name": "Ada", "email": "ada@example.com"}
    assert isinstance(a["id"], int) and a["id"] >= 1 and b["id"] != a["id"]
    assert svc.rows("SELECT name, email FROM customers ORDER BY id") == [("Ada", "ada@example.com"), ("Bob", "bob@example.com")]


def test_AC_led_001_rejects_a_duplicate_email_and_stores_nothing(svc):
    svc.customer("ada@example.com")
    r = svc.http.post("/customers", json={"name": "Other", "email": "ada@example.com"})
    assert r.status_code == 409
    error_of(r)
    assert svc.rows("SELECT COUNT(*) FROM customers") == [(1,)]


def test_AC_led_001_rejects_a_malformed_body(svc):
    for body in ({"name": "Ada"}, {"name": "", "email": "a@b"}, {"name": "Ada", "email": "no-at-sign"},
                 {"name": "Ada", "email": "a@b", "extra": 1}):
        r = svc.http.post("/customers", json=body)
        assert r.status_code == 422, body
        error_of(r)
    assert svc.rows("SELECT COUNT(*) FROM customers") == [(0,)]


# ---------------------------------------------------------------- AC-led-002

def test_AC_led_002_creates_an_open_order_with_the_right_total(svc):
    c = svc.customer()
    lines = [{"sku": "A", "quantity": 3, "unit_price_cents": 250}, {"sku": "B", "quantity": 1, "unit_price_cents": 999},
             {"sku": "FREE", "quantity": 5, "unit_price_cents": 0}]
    o = svc.order(c["id"], lines)
    assert o["status"] == "open" and o["total_cents"] == 1749 and o["paid_cents"] == 0
    assert o["customer_id"] == c["id"] and o["lines"] == lines
    assert set(o) == {"id", "customer_id", "status", "total_cents", "paid_cents", "lines"}
    assert svc.rows("SELECT customer_id, status, total_cents FROM orders") == [(c["id"], "open", 1749)]
    assert svc.rows("SELECT sku, quantity, unit_price_cents FROM order_lines ORDER BY position") == [
        ("A", 3, 250), ("B", 1, 999), ("FREE", 5, 0)]


def test_AC_led_002_rejects_an_unknown_customer(svc):
    r = svc.http.post("/orders", json={"customer_id": 4242, "lines": [{"sku": "A", "quantity": 1, "unit_price_cents": 1}]})
    assert r.status_code == 404
    error_of(r)
    assert svc.rows("SELECT COUNT(*) FROM orders") == [(0,)]


def test_AC_led_002_rejects_bad_lines(svc):
    c = svc.customer()
    for lines in ([], [{"sku": "A", "quantity": 0, "unit_price_cents": 1}], [{"sku": "A", "quantity": 1, "unit_price_cents": -1}],
                  [{"sku": "", "quantity": 1, "unit_price_cents": 1}], [{"sku": "A", "quantity": 1}]):
        r = svc.http.post("/orders", json={"customer_id": c["id"], "lines": lines})
        assert r.status_code == 422, lines
    assert svc.rows("SELECT COUNT(*) FROM orders") == [(0,)]
    assert svc.rows("SELECT COUNT(*) FROM order_lines") == [(0,)]


# ---------------------------------------------------------------- AC-led-003

def test_AC_led_003_returns_the_order_with_lines_total_paid_and_status(svc):
    c = svc.customer()
    lines = [{"sku": "Z", "quantity": 1, "unit_price_cents": 700}, {"sku": "A", "quantity": 2, "unit_price_cents": 150}]
    o = svc.order(c["id"], lines)
    p = svc.pay(o["id"], 400).json()
    svc.refund(p["id"], 100)
    got = svc.http.get(f"/orders/{o['id']}")
    assert got.status_code == 200
    assert got.json() == {"id": o["id"], "customer_id": c["id"], "status": "open", "total_cents": 1000,
                          "paid_cents": 300, "lines": lines}


def test_AC_led_003_unknown_order_is_404(svc):
    for path in ("/orders/999", "/orders/abc", "/orders/0"):
        r = svc.http.get(path)
        assert r.status_code == 404, path
        error_of(r)


# ---------------------------------------------------------------- AC-led-004

def test_AC_led_004_records_part_payments_and_marks_the_order_paid(svc):
    o = svc.order(svc.customer()["id"])  # total 3000
    r1 = svc.pay(o["id"], 1000, "2026-03-01")
    assert r1.status_code == 201
    p1 = r1.json()
    assert p1 == {"id": p1["id"], "order_id": o["id"], "amount_cents": 1000, "paid_on": "2026-03-01", "refunded_cents": 0}
    assert svc.http.get(f"/orders/{o['id']}").json()["status"] == "open"
    assert svc.pay(o["id"], 2000, "2026-03-02").status_code == 201
    after = svc.http.get(f"/orders/{o['id']}").json()
    assert after["status"] == "paid" and after["paid_cents"] == 3000
    assert svc.rows("SELECT order_id, amount_cents, paid_on FROM payments ORDER BY id") == [
        (o["id"], 1000, "2026-03-01"), (o["id"], 2000, "2026-03-02")]


def test_AC_led_004_rejects_a_payment_above_the_unpaid_balance(svc):
    o = svc.order(svc.customer()["id"])  # total 3000
    assert svc.pay(o["id"], 2999).status_code == 201
    r = svc.pay(o["id"], 2)
    assert r.status_code == 409
    error_of(r)
    assert svc.rows("SELECT COUNT(*), SUM(amount_cents) FROM payments") == [(1, 2999)]
    assert svc.pay(o["id"], 1).status_code == 201
    assert svc.http.get(f"/orders/{o['id']}").json()["status"] == "paid"


def test_AC_led_004_unknown_order_and_bad_bodies(svc):
    o = svc.order(svc.customer()["id"])
    assert svc.pay(777, 100).status_code == 404
    for body in ({"amount_cents": 0, "paid_on": "2026-03-01"}, {"amount_cents": 100}, {"amount_cents": 100, "paid_on": "March 1"},
                 {"amount_cents": "100", "paid_on": "2026-03-01"}):
        r = svc.http.post(f"/orders/{o['id']}/payments", json=body)
        assert r.status_code == 422, body
    assert svc.rows("SELECT COUNT(*) FROM payments") == [(0,)]


# ---------------------------------------------------------------- AC-led-005

def test_AC_led_005_a_repeated_key_returns_the_original_and_records_nothing(svc):
    o = svc.order(svc.customer()["id"])  # total 3000
    first = svc.pay(o["id"], 1200, key="retry-1")
    assert first.status_code == 201
    again = svc.pay(o["id"], 1200, key="retry-1")
    assert again.status_code == 200
    assert again.json() == first.json()
    assert svc.rows("SELECT COUNT(*) FROM payments") == [(1,)]
    assert svc.rows("SELECT COUNT(*) FROM ledger_entries") == [(2,)]
    assert svc.http.get(f"/orders/{o['id']}").json()["paid_cents"] == 1200


def test_AC_led_005_keys_are_scoped_to_the_order_and_optional(svc):
    c = svc.customer()
    o1, o2 = svc.order(c["id"]), svc.order(c["id"])
    assert svc.pay(o1["id"], 500, key="k").status_code == 201
    assert svc.pay(o2["id"], 500, key="k").status_code == 201      # same key, other order: a new payment
    assert svc.pay(o1["id"], 500, key="other").status_code == 201  # other key: a new payment
    assert svc.pay(o1["id"], 500).status_code == 201               # no key: never a repeat
    assert svc.pay(o1["id"], 500).status_code == 201
    assert svc.rows("SELECT COUNT(*) FROM payments") == [(5,)]


def test_AC_led_005_a_repeat_is_recognised_even_when_the_order_is_fully_paid(svc):
    o = svc.order(svc.customer()["id"])  # total 3000
    first = svc.pay(o["id"], 3000, key="full")
    again = svc.pay(o["id"], 3000, key="full")
    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json()["id"] == first.json()["id"]


# ---------------------------------------------------------------- AC-led-006

def test_AC_led_006_records_refunds_up_to_what_is_left_of_the_payment(svc):
    o = svc.order(svc.customer()["id"])
    p = svc.pay(o["id"], 1000).json()
    r1 = svc.refund(p["id"], 400, "2026-03-05")
    assert r1.status_code == 201
    body = r1.json()
    assert body == {"id": body["id"], "payment_id": p["id"], "amount_cents": 400, "refunded_on": "2026-03-05"}
    too_much = svc.refund(p["id"], 601)
    assert too_much.status_code == 409
    error_of(too_much)
    assert svc.refund(p["id"], 600).status_code == 201
    assert svc.refund(p["id"], 1).status_code == 409
    assert svc.rows("SELECT payment_id, amount_cents FROM refunds ORDER BY id") == [(p["id"], 400), (p["id"], 600)]


def test_AC_led_006_a_refund_reopens_a_paid_order(svc):
    o = svc.order(svc.customer()["id"])  # total 3000
    p = svc.pay(o["id"], 3000).json()
    assert svc.http.get(f"/orders/{o['id']}").json()["status"] == "paid"
    assert svc.refund(p["id"], 1).status_code == 201
    after = svc.http.get(f"/orders/{o['id']}").json()
    assert after["status"] == "open" and after["paid_cents"] == 2999
    # The refunded amount can be paid again, and no more than that.
    assert svc.pay(o["id"], 2).status_code == 409
    assert svc.pay(o["id"], 1).status_code == 201
    assert svc.http.get(f"/orders/{o['id']}").json()["status"] == "paid"


def test_AC_led_006_unknown_payment_and_bad_bodies(svc):
    o = svc.order(svc.customer()["id"])
    p = svc.pay(o["id"], 1000).json()
    assert svc.refund(555, 10).status_code == 404
    for body in ({"amount_cents": 0, "refunded_on": "2026-03-01"}, {"refunded_on": "2026-03-01"},
                 {"amount_cents": 10, "refunded_on": "soon"}):
        r = svc.http.post(f"/payments/{p['id']}/refunds", json=body)
        assert r.status_code == 422, body
    assert svc.rows("SELECT COUNT(*) FROM refunds") == [(0,)]


# ---------------------------------------------------------------- AC-led-007

def test_AC_led_007_payments_and_refunds_write_balanced_entry_pairs(svc):
    o = svc.order(svc.customer()["id"])
    p = svc.pay(o["id"], 1000).json()
    r = svc.refund(p["id"], 300).json()
    assert sorted(svc.rows("SELECT account, direction, amount_cents FROM ledger_entries WHERE payment_id = ?", (p["id"],))) == [
        ("cash", "debit", 1000), ("revenue", "credit", 1000)]
    assert sorted(svc.rows("SELECT account, direction, amount_cents FROM ledger_entries WHERE refund_id = ?", (r["id"],))) == [
        ("cash", "credit", 300), ("revenue", "debit", 300)]
    assert svc.rows("SELECT COUNT(*) FROM ledger_entries") == [(4,)]
    assert svc.rows("SELECT SUM(CASE direction WHEN 'debit' THEN amount_cents ELSE -amount_cents END) FROM ledger_entries") == [(0,)]


def test_AC_led_007_rejected_requests_write_no_entries(svc):
    o = svc.order(svc.customer()["id"])  # total 3000
    p = svc.pay(o["id"], 1000).json()
    assert svc.pay(o["id"], 5000).status_code == 409
    assert svc.refund(p["id"], 2000).status_code == 409
    assert svc.pay(o["id"], 0).status_code == 422
    assert svc.rows("SELECT COUNT(*) FROM ledger_entries") == [(2,)]


# ---------------------------------------------------------------- AC-led-008

def test_AC_led_008_balances_start_at_zero_and_follow_the_ledger(svc):
    for account in ("cash", "revenue"):
        r = svc.http.get(f"/accounts/{account}/balance")
        assert r.status_code == 200 and r.json() == {"account": account, "balance_cents": 0}
    o = svc.order(svc.customer()["id"])
    p = svc.pay(o["id"], 1000).json()
    svc.pay(o["id"], 500)
    svc.refund(p["id"], 300)
    assert svc.http.get("/accounts/cash/balance").json() == {"account": "cash", "balance_cents": 1200}
    assert svc.http.get("/accounts/revenue/balance").json() == {"account": "revenue", "balance_cents": -1200}


def test_AC_led_008_unknown_account_is_404(svc):
    for account in ("bank", "CASH", "revenues"):
        r = svc.http.get(f"/accounts/{account}/balance")
        assert r.status_code == 404, account
        error_of(r)


# ---------------------------------------------------------------- AC-led-009

def test_AC_led_009_report_is_empty_before_anything_is_recorded(svc):
    r = svc.http.get("/reports/daily-revenue")
    assert r.status_code == 200 and r.json() == {"days": []}


def test_AC_led_009_report_lists_gross_refunds_and_net_per_day_in_date_order(svc):
    c = svc.customer()
    o1 = svc.order(c["id"], [{"sku": "A", "quantity": 1, "unit_price_cents": 10000}])
    o2 = svc.order(c["id"], [{"sku": "B", "quantity": 1, "unit_price_cents": 10000}])
    p1 = svc.pay(o1["id"], 4000, "2026-03-03").json()
    svc.pay(o2["id"], 2500, "2026-03-01")
    svc.pay(o1["id"], 1000, "2026-03-03")
    svc.refund(p1["id"], 1500, "2026-03-03")
    svc.refund(p1["id"], 500, "2026-03-07")   # a day with a refund and no payment
    assert svc.http.get("/reports/daily-revenue").json() == {"days": [
        {"day": "2026-03-01", "gross_cents": 2500, "refund_cents": 0, "net_cents": 2500},
        {"day": "2026-03-03", "gross_cents": 5000, "refund_cents": 1500, "net_cents": 3500},
        {"day": "2026-03-07", "gross_cents": 0, "refund_cents": 500, "net_cents": -500},
    ]}


def test_AC_led_009_the_daily_revenue_dataset_agrees_with_the_report(svc):
    o = svc.order(svc.customer()["id"])
    p = svc.pay(o["id"], 2000, "2026-04-10").json()
    svc.refund(p["id"], 250, "2026-04-11")
    assert svc.rows("SELECT day, gross_cents, refund_cents, net_cents FROM daily_revenue ORDER BY day") == [
        ("2026-04-10", 2000, 0, 2000), ("2026-04-11", 0, 250, -250)]
