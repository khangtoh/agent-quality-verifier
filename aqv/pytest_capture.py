"""A6 adapter for pytest + Starlette/FastAPI TestClient.

Loaded with `-p aqv.pytest_capture`. Records every TestClient call (method, path,
status, JSON body) with the name of the test that made it, and writes them to
$AQV_CAPTURE_OUT when the run ends. This is the only framework-specific piece
of the verifier; other frameworks need their own small adapter.
"""
import json
import os
from urllib.parse import urlsplit

CALLS = []


def pytest_configure(config):
    try:
        from starlette.testclient import TestClient
    except ImportError:
        return
    original = TestClient.request

    def request(self, method, url, *args, **kwargs):
        response = original(self, method, url, *args, **kwargs)
        current = os.environ.get("PYTEST_CURRENT_TEST", "")
        test = current.split(" ")[0]
        try:
            body = response.json()
        except Exception:
            body = None
        CALLS.append({
            "test": test.split("::")[-1],
            "nodeid": test,
            "method": method.upper(),
            "path": urlsplit(str(response.request.url)).path,
            "status": response.status_code,
            "body": body,
        })
        return response

    TestClient.request = request


def pytest_unconfigure(config):
    out = os.environ.get("AQV_CAPTURE_OUT")
    if out:
        with open(out, "w") as f:
            json.dump(CALLS, f)
