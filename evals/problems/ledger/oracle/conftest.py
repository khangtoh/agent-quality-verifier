"""Held-out acceptance tests for Ledgerline.

The agent never sees this folder. Each test starts the agent's service binary with an empty
database, drives it over HTTP as a client would, and reads the SQLite file the way the finance team
would. Tests are named after the requirement they judge, so the score can compare the oracle's
answer with the verifier's, requirement by requirement.
"""
import os
import socket
import sqlite3
import subprocess
import time

import httpx
import pytest


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Service:
    def __init__(self, client, db_path):
        self.http = client
        self.db_path = db_path

    def rows(self, sql, params=()):
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    # Shortcuts for the steps most tests share.
    def customer(self, email="ada@example.com", name="Ada"):
        r = self.http.post("/customers", json={"name": name, "email": email})
        assert r.status_code == 201, r.text
        return r.json()

    def order(self, customer_id, lines=None):
        lines = lines or [{"sku": "WIDGET", "quantity": 2, "unit_price_cents": 1500}]
        r = self.http.post("/orders", json={"customer_id": customer_id, "lines": lines})
        assert r.status_code == 201, r.text
        return r.json()

    def pay(self, order_id, amount, day="2026-03-01", key=None):
        headers = {"Idempotency-Key": key} if key else {}
        return self.http.post(f"/orders/{order_id}/payments", json={"amount_cents": amount, "paid_on": day},
                              headers=headers)

    def refund(self, payment_id, amount, day="2026-03-02"):
        return self.http.post(f"/payments/{payment_id}/refunds", json={"amount_cents": amount, "refunded_on": day})


@pytest.fixture
def svc(tmp_path):
    binary = os.environ["ORACLE_BIN"]
    port = _free_port()
    db = tmp_path / "ledger.db"
    env = dict(os.environ)
    for pair in os.environ.get("ORACLE_ENV", "").split("\n"):
        if "=" in pair:
            key, value = pair.split("=", 1)
            env[key] = value.replace("{port}", str(port)).replace("{db}", str(db))
    log = open(tmp_path / "service.log", "w")
    proc = subprocess.Popen([binary], env=env, stdout=log, stderr=log, cwd=tmp_path)
    try:
        deadline = time.time() + 20
        while True:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                break
            except OSError:
                if proc.poll() is not None or time.time() > deadline:
                    pytest.fail("the service did not start: " + (tmp_path / "service.log").read_text()[-400:])
                time.sleep(0.05)
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10) as client:
            yield Service(client, db)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()
