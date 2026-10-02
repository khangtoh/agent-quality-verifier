"""Builds the baseline demo repo: an auth service written the way the verifier expects.

A human writes the requirements, then an agent implements one requirement per
branch: first the OpenAPI contract, then code and tests. Every commit follows
Conventional Commits, carries a `Refs:` trailer and names the agent, and every
commit is signed. Branches merge into main with merge commits.

    python demo/build_baseline.py <target-dir> --gnupg <gnupg-home>
"""
import argparse
import os
import shutil
import subprocess
import textwrap
from pathlib import Path

HUMAN = ("Pat Product", "pat@example.com")
AGENT = ("dev-agent", "agent@example.com")
AGENT_TRAILER = "Co-Authored-By: Claude <noreply@anthropic.com>"


def d(text):
    return textwrap.dedent(text).lstrip("\n")


# ---------------------------------------------------------------------------
# Human-owned files
# ---------------------------------------------------------------------------

SPEC = d("""
    # Auth service requirements

    - **AC-auth-001** (api: POST /login): Users sign in with email and password.
    - **AC-auth-002** (api: POST /login): Accounts lock after 3 consecutive failed sign-in attempts.
    - **AC-auth-003** (api: GET /session): Sessions expire after 30 minutes of inactivity.
    - **AC-auth-004** (api: POST /password-reset): Users can request a password reset link by email.
    - **AC-auth-005** (api: POST /password-reset): The reset response is identical whether or not the email exists.
    - **AC-auth-006**: Passwords are stored hashed, never in plain text.
""")

IDS = "".join(f"AC-auth-00{i}\n" for i in range(1, 7))

AQV_CONFIG = d("""
    # Agent Quality Verifier config. Owned by humans; agents must not change it.
    specs: ["specs/*.md"]
    ids_registry: specs/.ids
    contract: contracts/openapi.yaml
    code_paths: ["src/"]
    test_paths: ["tests/"]
    protected_paths: ["specs/", ".aqv.yml", ".spectral.yaml"]

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

    git:
      humans: ["pat@example.com"]
      agent_trailer: "Co-Authored-By"
      branch_pattern: "^(feat|fix|refactor|test|docs|chore)/AC-[a-z0-9]+-[0-9]{3}(-[a-z0-9-]+)?$"
      max_commit_lines: 400
      size_exclude: ["*.lock"]
      verified_ref: refs/aqv/verified

    mutation:
      min_kill_ratio: 0.6
      max_mutants: 20
""")

SPECTRAL = d("""
    extends: ["spectral:oas"]
    rules:
      aqv-response-has-schema:
        description: Every response except 204 documents a JSON body schema.
        severity: error
        given: "$.paths[*][*].responses[?(@property != '204')]"
        then:
          field: "content.application/json.schema"
          function: truthy
      aqv-closed-objects:
        description: Object schemas set additionalProperties to false so extra fields are caught.
        severity: error
        given: "$.components.schemas[?(@.type == 'object')]"
        then:
          field: additionalProperties
          function: falsy
      aqv-objects-declare-additional-properties:
        description: Object schemas must declare additionalProperties explicitly.
        severity: error
        given: "$.components.schemas[?(@.type == 'object')]"
        then:
          field: additionalProperties
          function: defined
""")

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

README = d("""
    # Auth service (verifier demo)

    Requirements live in `specs/auth.md`, the API contract in `contracts/openapi.yaml`.
    An agent implements each requirement on its own branch.
""")

GITIGNORE = "__pycache__/\n.coverage*\n.pytest_cache/\n"

# ---------------------------------------------------------------------------
# Contract, one version per requirement branch
# ---------------------------------------------------------------------------

CONTRACT_HEAD = d("""
    openapi: 3.1.0
    info:
      title: Auth service
      version: 1.0.0
      description: Sign-in, lockout, session expiry and password reset.
      contact:
        name: Auth team
        email: auth@example.com
    servers:
      - url: http://localhost:8000
    tags:
      - name: auth
        description: Authentication
    paths:
""")

LOGIN_OP = d("""
      /login:
        post:
          operationId: login
          summary: Sign in
          description: Exchange email and password for a session token.
          tags: [auth]
          x-requirements: [AC-auth-001, AC-auth-002]
          requestBody:
            required: true
            content:
              application/json:
                schema: {$ref: "#/components/schemas/Credentials"}
          responses:
            "200":
              description: Signed in
              content:
                application/json:
                  schema: {$ref: "#/components/schemas/Token"}
            "400":
              description: Malformed request
              content:
                application/json:
                  schema: {$ref: "#/components/schemas/Error"}
            "401":
              description: Wrong credentials or locked account
              content:
                application/json:
                  schema: {$ref: "#/components/schemas/Error"}
""")

SESSION_OP = d("""
      /session:
        get:
          operationId: getSession
          summary: Check a session
          description: Report whether a session last seen at the given time has expired.
          tags: [auth]
          x-requirements: [AC-auth-003]
          parameters:
            - name: last_seen
              in: query
              required: true
              description: Unix time the session was last active.
              schema: {type: integer, minimum: 0, maximum: 4102444800}
          responses:
            "200":
              description: Session state
              content:
                application/json:
                  schema: {$ref: "#/components/schemas/SessionState"}
            "400":
              description: Malformed request
              content:
                application/json:
                  schema: {$ref: "#/components/schemas/Error"}
""")

RESET_OP = d("""
      /password-reset:
        post:
          operationId: requestPasswordReset
          summary: Request a password reset link
          description: Email a reset link if the account exists.
          tags: [auth]
          x-requirements: [AC-auth-004, AC-auth-005]
          requestBody:
            required: true
            content:
              application/json:
                schema: {$ref: "#/components/schemas/ResetRequest"}
          responses:
            "202":
              description: Request accepted
              content:
                application/json:
                  schema: {$ref: "#/components/schemas/ResetAccepted"}
            "400":
              description: Malformed request
              content:
                application/json:
                  schema: {$ref: "#/components/schemas/Error"}
""")


def indent_block(block, n):
    pad = " " * n
    return "".join(pad + line if line.strip() else line for line in block.splitlines(True))


def components(errors, session=False, reset_statuses=None):
    s = [
        "components:",
        "  schemas:",
        "    Credentials:",
        "      type: object",
        "      required: [email, password]",
        "      additionalProperties: false",
        "      properties:",
        "        email: {type: string}",
        "        password: {type: string}",
        "    Token:",
        "      type: object",
        "      required: [token]",
        "      additionalProperties: false",
        "      properties:",
        "        token: {type: string}",
        "    Error:",
        "      type: object",
        "      required: [error]",
        "      additionalProperties: false",
        "      properties:",
        f"        error: {{enum: [{', '.join(errors)}]}}",
    ]
    if session:
        s += [
            "    SessionState:",
            "      type: object",
            "      required: [expired]",
            "      additionalProperties: false",
            "      properties:",
            "        expired: {type: boolean}",
        ]
    if reset_statuses:
        s += [
            "    ResetRequest:",
            "      type: object",
            "      required: [email]",
            "      additionalProperties: false",
            "      properties:",
            "        email: {type: string}",
            "    ResetAccepted:",
            "      type: object",
            "      required: [status]",
            "      additionalProperties: false",
            "      properties:",
            f"        status: {{enum: [{', '.join(reset_statuses)}]}}",
        ]
    return "\n".join(s) + "\n"


def contract_v(ops, errors, session=False, reset_statuses=None):
    return CONTRACT_HEAD + "".join(indent_block(op, 2) for op in ops) + components(errors, session, reset_statuses)


C1 = contract_v([LOGIN_OP], ["invalid_request", "denied"])
C2 = contract_v([LOGIN_OP], ["invalid_request", "denied", "locked"])
C3 = contract_v([LOGIN_OP, SESSION_OP], ["invalid_request", "denied", "locked"], session=True)
C4 = contract_v([LOGIN_OP, SESSION_OP, RESET_OP], ["invalid_request", "denied", "locked"], session=True,
                reset_statuses=["sent", "unknown_email"])
C5 = contract_v([LOGIN_OP, SESSION_OP, RESET_OP], ["invalid_request", "denied", "locked"], session=True,
                reset_statuses=["sent"])

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
# History
# ---------------------------------------------------------------------------

FEATURES = [
    ("feat/AC-auth-001-sign-in", "AC-auth-001", [
        ("feat(contract): document POST /login", {"contracts/openapi.yaml": C1}),
        ("feat(auth): sign in with email and password", {
            "src/app/__init__.py": "",
            "src/app/auth.py": AUTH_1,
            "src/app/main.py": MAIN_1,
            "tests/conftest.py": CONFTEST,
            "tests/test_login.py": TEST_LOGIN,
        }),
    ]),
    ("feat/AC-auth-002-lockout", "AC-auth-002", [
        ("feat(contract): document the locked error", {"contracts/openapi.yaml": C2}),
        ("feat(auth): lock accounts after 3 failed attempts", {
            "src/app/auth.py": AUTH_2,
            "src/app/main.py": MAIN_2,
            "tests/test_lockout.py": TEST_LOCKOUT,
        }),
    ]),
    ("feat/AC-auth-003-session-expiry", "AC-auth-003", [
        ("feat(contract): document GET /session", {"contracts/openapi.yaml": C3}),
        ("feat(auth): expire sessions after 30 minutes", {
            "src/app/auth.py": AUTH_3,
            "src/app/main.py": MAIN_3,
            "tests/test_session.py": TEST_SESSION,
        }),
    ]),
    ("feat/AC-auth-004-password-reset", "AC-auth-004", [
        ("feat(contract): document POST /password-reset", {"contracts/openapi.yaml": C4}),
        ("feat(auth): send password reset links", {
            "src/app/auth.py": AUTH_4,
            "src/app/main.py": MAIN_4,
            "tests/test_reset.py": TEST_RESET_4,
        }),
    ]),
    ("feat/AC-auth-005-private-reset", "AC-auth-005", [
        ("feat(contract): drop the unknown_email reset status", {"contracts/openapi.yaml": C5}),
        ("feat(auth): answer reset requests the same way for every email", {
            "src/app/auth.py": AUTH_5,
            "src/app/main.py": MAIN_5,
            "tests/test_reset.py": TEST_RESET_5,
        }),
    ]),
    ("feat/AC-auth-006-hash-passwords", "AC-auth-006", [
        ("feat(auth): store salted password hashes", {
            "src/app/auth.py": AUTH_6,
            "tests/test_storage.py": TEST_STORAGE,
        }),
    ]),
]


class Repo:
    def __init__(self, path, gnupg):
        self.path = Path(path)
        self.env = dict(os.environ, GNUPGHOME=str(Path(gnupg).resolve()))
        self.clock = 1767225600  # 2026-01-01T00:00:00Z, so the build is repeatable

    def git(self, *args, author=HUMAN):
        """Runs git with a fixed author and a clock that advances 10 minutes per call."""
        self.clock += 600
        env = dict(self.env,
                   GIT_AUTHOR_NAME=author[0], GIT_AUTHOR_EMAIL=author[1],
                   GIT_COMMITTER_NAME=author[0], GIT_COMMITTER_EMAIL=author[1],
                   GIT_AUTHOR_DATE=f"{self.clock} +0000", GIT_COMMITTER_DATE=f"{self.clock} +0000")
        r = subprocess.run(["git", "-C", str(self.path), *args], env=env, capture_output=True, text=True)
        if r.returncode:
            raise SystemExit(f"git {' '.join(args)} failed:\n{r.stderr}")
        return r.stdout

    def write(self, files):
        for rel, content in files.items():
            p = self.path / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
        self.git("add", "-A")

    def commit(self, message, author=HUMAN, trailers=()):
        args = ["commit", "-q", "-m", message]
        for t in trailers:
            args += ["--trailer", t]
        self.git(*args, author=author)


def ensure_key(gnupg):
    gnupg = Path(gnupg).resolve()
    gnupg.mkdir(parents=True, exist_ok=True)
    os.chmod(gnupg, 0o700)
    env = dict(os.environ, GNUPGHOME=str(gnupg))
    listing = subprocess.run(["gpg", "--batch", "--list-secret-keys", "--with-colons"], env=env,
                             capture_output=True, text=True).stdout
    if "sec:" not in listing:
        subprocess.run(["gpg", "--batch", "--passphrase", "", "--quick-gen-key",
                        "Demo Signer <signer@example.com>", "ed25519", "sign", "never"],
                       env=env, check=True, capture_output=True)
        listing = subprocess.run(["gpg", "--batch", "--list-secret-keys", "--with-colons"], env=env,
                                 capture_output=True, text=True).stdout
    return next(line.split(":")[9] for line in listing.splitlines() if line.startswith("fpr:"))


def configure(repo, key):
    for k, v in [("user.name", HUMAN[0]), ("user.email", HUMAN[1]),
                 ("gpg.format", "openpgp"), ("gpg.program", "gpg"),
                 ("user.signingkey", key), ("commit.gpgsign", "true"), ("tag.gpgsign", "false"),
                 ("merge.ff", "false"), ("init.defaultBranch", "main")]:
        repo.git("config", k, v)


def build(target, gnupg):
    target = Path(target)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    key = ensure_key(gnupg)
    repo = Repo(target, gnupg)
    repo.git("init", "-q", "-b", "main")
    configure(repo, key)

    repo.write({"specs/auth.md": SPEC, "specs/.ids": IDS})
    repo.commit("docs(spec): add auth service requirements")
    repo.write({"pyproject.toml": PYPROJECT, ".aqv.yml": AQV_CONFIG, ".spectral.yaml": SPECTRAL,
                "README.md": README, ".gitignore": GITIGNORE})
    repo.commit("chore: add project scaffold and verifier config")

    for branch, req, commits in FEATURES:
        repo.git("checkout", "-q", "-b", branch)
        for message, files in commits:
            repo.write(files)
            repo.commit(message, author=AGENT, trailers=[f"Refs: {req}", AGENT_TRAILER])
        repo.git("checkout", "-q", "main")
        repo.git("merge", "-q", "--no-ff", "-m", f"Merge branch '{branch}'", branch)

    head = repo.git("rev-parse", "HEAD").strip()
    repo.git("update-ref", "refs/aqv/verified", head)
    return head


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--gnupg", required=True)
    a = ap.parse_args()
    print(build(a.target, a.gnupg))
