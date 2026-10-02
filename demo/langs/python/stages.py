"""Python demo: FastAPI service, pytest tests, coverage.py, the pytest TestClient adapter."""
from ..common import aqv_config, d

NAME = "Python"
STACK = "FastAPI · pytest · coverage.py"


AQV_CONFIG = aqv_config(["src/"], ["tests/"], d("""
    # Runner profile: how to run the tests and where the reports go.
    runner:
      test: "{python} -m pytest -q -p no:cacheprovider {extra} {filter} --junitxml={junit}"
      coverage: "{python} -m coverage run --data-file={cov_data} --source=src -m pytest -q -p no:cacheprovider {filter}"
      coverage_report: "{python} -m coverage lcov --data-file={cov_data} -o {lcov}"
      filter: "-k {id_underscore}"
      select_nothing: "-k aqv_selects_no_tests"
      broken_exit_codes: [2, 3, 4]
      comment_prefix: "#"

    api:
      openapi_from_code: "{python} -c \\"import json,sys; sys.path.insert(0,'src'); from app.main import create_app; print(json.dumps(create_app().openapi()))\\""
      serve: "{python} -m uvicorn --factory app.main:create_app --app-dir src --port {port} --log-level warning"
      capture: pytest-testclient

    mutation:
      min_kill_ratio: 0.6
      max_mutants: 20
"""))

PYPROJECT = d("""
    [project]
    name = "auth-service"
    version = "0.1.0"
    requires-python = ">=3.11"
    dependencies = ["fastapi", "uvicorn", "httpx"]

    [tool.pytest.ini_options]
    pythonpath = ["src"]
    testpaths = ["tests"]
""")

# ---------------------------------------------------------------------------
# Code, one version per requirement branch
# ---------------------------------------------------------------------------

AUTH_1 = d('''
    """Accounts: sign-in, lockout, session expiry and password reset."""
    import secrets


    class AccountStore:
        def __init__(self):
            self.accounts = {}

        @classmethod
        def with_demo_accounts(cls):
            store = cls()
            store.add_account("ada@example.com", "correct horse")
            return store

        def add_account(self, email, password):
            self.accounts[email] = password

        def sign_in(self, email, password):
            if self.accounts.get(email) == password:
                return secrets.token_hex(16)
            return "denied"
''')

AUTH_2 = d('''
    """Accounts: sign-in, lockout, session expiry and password reset."""
    import secrets

    MAX_FAILED_ATTEMPTS = 3


    class AccountStore:
        def __init__(self):
            self.accounts = {}
            self.failed = {}
            self.locked = set()

        @classmethod
        def with_demo_accounts(cls):
            store = cls()
            store.add_account("ada@example.com", "correct horse")
            return store

        def add_account(self, email, password):
            self.accounts[email] = password

        def sign_in(self, email, password):
            if email in self.locked:
                return "locked"
            if self.accounts.get(email) == password:
                self.failed[email] = 0
                return secrets.token_hex(16)
            self.failed[email] = self.failed.get(email, 0) + 1
            if self.failed[email] >= MAX_FAILED_ATTEMPTS:
                self.locked.add(email)
            return "denied"
''')

AUTH_3 = AUTH_2.replace(
    "MAX_FAILED_ATTEMPTS = 3\n",
    "MAX_FAILED_ATTEMPTS = 3\nSESSION_TTL_SECONDS = 30 * 60\n\n\n"
    "def is_expired(last_seen, now):\n    return now - last_seen > SESSION_TTL_SECONDS\n",
)

# request_reset must be a method: indent it into the class body.
AUTH_4 = AUTH_3.replace(
    "        self.locked = set()\n",
    "        self.locked = set()\n        self.reset_outbox = []\n",
) + (
    "\n"
    "    def request_reset(self, email):\n"
    "        if email in self.accounts:\n"
    "            self.reset_outbox.append(email)\n"
    "            return True\n"
    "        return False\n"
)

# AC-auth-005 stops using request_reset's return value, so the agent drops it.
AUTH_5 = AUTH_4.replace(
    "            self.reset_outbox.append(email)\n            return True\n        return False\n",
    "            self.reset_outbox.append(email)\n",
)

AUTH_6 = (
    AUTH_5.replace("import secrets\n", "import hashlib\nimport secrets\n")
    .replace(
        "\n\ndef is_expired",
        "\n\ndef hash_password(password, salt):\n"
        "    return hashlib.sha256((salt + password).encode()).hexdigest()\n\n\ndef is_expired",
    )
    .replace(
        "    def add_account(self, email, password):\n        self.accounts[email] = password\n",
        "    def add_account(self, email, password):\n"
        "        salt = secrets.token_hex(8)\n"
        "        self.accounts[email] = (salt, hash_password(password, salt))\n\n"
        "    def password_matches(self, email, password):\n"
        "        salt, digest = self.accounts[email]\n"
        "        return hash_password(password, salt) == digest\n",
    )
    .replace(
        "        if self.accounts.get(email) == password:\n",
        "        if email in self.accounts and self.password_matches(email, password):\n",
    )
)

MAIN_1 = d('''
    """HTTP API for the auth service."""
    from fastapi import FastAPI, Request
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel

    from app.auth import AccountStore


    class Credentials(BaseModel):
        email: str
        password: str


    def create_app(store=None):
        store = store if store is not None else AccountStore.with_demo_accounts()
        app = FastAPI(title="Auth service")

        @app.exception_handler(RequestValidationError)
        async def invalid_request(request: Request, exc: RequestValidationError):
            return JSONResponse({"error": "invalid_request"}, status_code=400)

        @app.post("/login")
        def login(body: Credentials):
            result = store.sign_in(body.email, body.password)
            if result == "denied":
                return JSONResponse({"error": result}, status_code=401)
            return {"token": result}

        return app
''')

MAIN_2 = MAIN_1.replace('        if result == "denied":\n', '        if result in ("denied", "locked"):\n')

MAIN_3 = (
    MAIN_2.replace('"""HTTP API for the auth service."""\n', '"""HTTP API for the auth service."""\nimport time\n\n')
    .replace("from fastapi import FastAPI, Request\n", "from fastapi import FastAPI, Query, Request\n")
    .replace("from app.auth import AccountStore\n", "from app.auth import AccountStore, is_expired\n")
    .replace(
        "        return {\"token\": result}\n\n    return app\n",
        "        return {\"token\": result}\n\n"
        "    @app.get(\"/session\")\n"
        "    def session(last_seen: int = Query(ge=0, le=4102444800)):\n"
        "        return {\"expired\": is_expired(last_seen, time.time())}\n\n"
        "    return app\n",
    )
)

MAIN_4 = (
    MAIN_3.replace(
        "class Credentials(BaseModel):\n    email: str\n    password: str\n",
        "class Credentials(BaseModel):\n    email: str\n    password: str\n\n\n"
        "class ResetRequest(BaseModel):\n    email: str\n",
    )
    .replace(
        "        return {\"expired\": is_expired(last_seen, time.time())}\n\n    return app\n",
        "        return {\"expired\": is_expired(last_seen, time.time())}\n\n"
        "    @app.post(\"/password-reset\", status_code=202)\n"
        "    def password_reset(body: ResetRequest):\n"
        "        sent = store.request_reset(body.email)\n"
        "        return {\"status\": \"sent\" if sent else \"unknown_email\"}\n\n"
        "    return app\n",
    )
)

MAIN_5 = MAIN_4.replace(
    "        sent = store.request_reset(body.email)\n"
    "        return {\"status\": \"sent\" if sent else \"unknown_email\"}\n",
    "        store.request_reset(body.email)\n"
    "        return {\"status\": \"sent\"}\n",
)

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

CONFTEST = d('''
    import pytest
    from fastapi.testclient import TestClient

    from app.auth import AccountStore
    from app.main import create_app


    @pytest.fixture
    def store():
        return AccountStore.with_demo_accounts()


    @pytest.fixture
    def client(store):
        return TestClient(create_app(store))
''')

TEST_LOGIN = d('''
    GOOD = {"email": "ada@example.com", "password": "correct horse"}


    def test_AC_auth_001_sign_in_returns_token(client):
        r = client.post("/login", json=GOOD)
        assert r.status_code == 200
        assert len(r.json()["token"]) == 32


    def test_AC_auth_001_wrong_password_is_denied(client):
        r = client.post("/login", json={**GOOD, "password": "wrong"})
        assert r.status_code == 401
        assert r.json() == {"error": "denied"}


    def test_AC_auth_001_malformed_request_is_rejected(client):
        r = client.post("/login", json={"email": "ada@example.com"})
        assert r.status_code == 400
        assert r.json() == {"error": "invalid_request"}
''')

TEST_LOCKOUT = d('''
    BAD = {"email": "ada@example.com", "password": "wrong"}
    GOOD = {"email": "ada@example.com", "password": "correct horse"}


    def test_AC_auth_002_locks_after_three_failures(client):
        for _ in range(3):
            client.post("/login", json=BAD)
        r = client.post("/login", json=GOOD)
        assert r.status_code == 401
        assert r.json() == {"error": "locked"}


    def test_AC_auth_002_two_failures_do_not_lock(client):
        for _ in range(2):
            client.post("/login", json=BAD)
        assert client.post("/login", json=GOOD).status_code == 200


    def test_AC_auth_002_success_resets_the_count(client):
        for _ in range(2):
            client.post("/login", json=BAD)
        client.post("/login", json=GOOD)
        for _ in range(2):
            client.post("/login", json=BAD)
        assert client.post("/login", json=GOOD).status_code == 200
''')

TEST_SESSION = d('''
    import time

    from app.auth import is_expired


    def test_AC_auth_003_expired_after_30_minutes(client):
        r = client.get("/session", params={"last_seen": int(time.time()) - 31 * 60})
        assert r.status_code == 200
        assert r.json() == {"expired": True}


    def test_AC_auth_003_active_within_30_minutes(client):
        r = client.get("/session", params={"last_seen": int(time.time()) - 29 * 60})
        assert r.json() == {"expired": False}


    def test_AC_auth_003_boundary_is_exactly_30_minutes():
        assert not is_expired(0, 30 * 60)
        assert is_expired(0, 30 * 60 + 1)
''')

TEST_RESET_4 = d('''
    def test_AC_auth_004_link_sent_for_known_email(client, store):
        r = client.post("/password-reset", json={"email": "ada@example.com"})
        assert r.status_code == 202
        assert store.reset_outbox == ["ada@example.com"]


    def test_AC_auth_004_no_link_for_unknown_email(client, store):
        client.post("/password-reset", json={"email": "nobody@example.com"})
        assert store.reset_outbox == []
''')

TEST_RESET_5 = TEST_RESET_4 + d('''


    def test_AC_auth_005_same_response_for_unknown_email(client):
        known = client.post("/password-reset", json={"email": "ada@example.com"})
        unknown = client.post("/password-reset", json={"email": "nobody@example.com"})
        assert known.status_code == unknown.status_code == 202
        assert known.json() == unknown.json() == {"status": "sent"}


    def test_AC_auth_005_known_email_still_gets_its_link(client, store):
        client.post("/password-reset", json={"email": "nobody@example.com"})
        client.post("/password-reset", json={"email": "ada@example.com"})
        assert store.reset_outbox == ["ada@example.com"]
''')

TEST_STORAGE = d('''
    from app.auth import AccountStore, hash_password


    def test_AC_auth_006_password_not_stored_in_plain_text():
        store = AccountStore()
        store.add_account("bo@example.com", "s3cret")
        salt, digest = store.accounts["bo@example.com"]
        assert "s3cret" not in (salt, digest)
        assert digest == hash_password("s3cret", salt)


    def test_AC_auth_006_hashed_password_still_signs_in():
        store = AccountStore()
        store.add_account("bo@example.com", "s3cret")
        assert store.sign_in("bo@example.com", "s3cret") not in ("denied", "locked")
        assert store.sign_in("bo@example.com", "nope") == "denied"
''')

# ---------------------------------------------------------------------------
# What the builder needs
# ---------------------------------------------------------------------------

GITIGNORE = "__pycache__/\n.coverage*\n.pytest_cache/\n.aqv-out/\n"

# Committed by the human with the verifier config, before any feature work.
SCAFFOLD = {"pyproject.toml": PYPROJECT, ".aqv.yml": AQV_CONFIG}

# The code-and-tests commit for each requirement (its contract commit is shared).
CODE = {
    "AC-auth-001": {
        "src/app/__init__.py": "",
        "src/app/auth.py": AUTH_1,
        "src/app/main.py": MAIN_1,
        "tests/conftest.py": CONFTEST,
        "tests/test_login.py": TEST_LOGIN,
    },
    "AC-auth-002": {"src/app/auth.py": AUTH_2, "src/app/main.py": MAIN_2, "tests/test_lockout.py": TEST_LOCKOUT},
    "AC-auth-003": {"src/app/auth.py": AUTH_3, "src/app/main.py": MAIN_3, "tests/test_session.py": TEST_SESSION},
    "AC-auth-004": {"src/app/auth.py": AUTH_4, "src/app/main.py": MAIN_4, "tests/test_reset.py": TEST_RESET_4},
    "AC-auth-005": {"src/app/auth.py": AUTH_5, "src/app/main.py": MAIN_5, "tests/test_reset.py": TEST_RESET_5},
    "AC-auth-006": {"src/app/auth.py": AUTH_6, "tests/test_storage.py": TEST_STORAGE},
}


def prepare(repo, shared):
    """Nothing to install: the verifier's virtualenv already has the dependencies."""

MECHANISMS = {
    "T5": "pytest --junitxml",
    "T6": "coverage.py run per requirement, LCOV",
    "T7": "Built-in line mutator; Python compile check",
    "A5": "OpenAPI generated by FastAPI",
    "A6": "pytest plugin records TestClient calls (adapter)",
    "A7": "uvicorn + Schemathesis",
}
