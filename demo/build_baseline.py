"""Builds the baseline demo repo: an auth service written the way the verifier expects.

A human writes the requirements, then an agent implements one requirement per
branch: first the OpenAPI contract, then code and tests. Every commit follows
Conventional Commits, carries a `Refs:` trailer and names the agent, and every
commit is signed. Branches merge into main with merge commits.

    python demo/build_baseline.py <target-dir> --gnupg <gnupg-home> [--lang python]
"""
import argparse
import os
import shutil
import subprocess
import sys
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

README = d("""
    # Auth service (verifier demo, {name})

    Requirements live in `specs/auth.md`, the API contract in `contracts/openapi.yaml`.
    An agent implements each requirement on its own branch. Stack: {stack}.
""")

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
# History: one branch per requirement, contract first, then the language's code and tests
# ---------------------------------------------------------------------------

FEATURES = [
    ("feat/AC-auth-001-sign-in", "AC-auth-001", ("feat(contract): document POST /login", C1),
     "feat(auth): sign in with email and password"),
    ("feat/AC-auth-002-lockout", "AC-auth-002", ("feat(contract): document the locked error", C2),
     "feat(auth): lock accounts after 3 failed attempts"),
    ("feat/AC-auth-003-session-expiry", "AC-auth-003", ("feat(contract): document GET /session", C3),
     "feat(auth): expire sessions after 30 minutes"),
    ("feat/AC-auth-004-password-reset", "AC-auth-004", ("feat(contract): document POST /password-reset", C4),
     "feat(auth): send password reset links"),
    ("feat/AC-auth-005-private-reset", "AC-auth-005", ("feat(contract): drop the unknown_email reset status", C5),
     "feat(auth): answer reset requests the same way for every email"),
    ("feat/AC-auth-006-hash-passwords", "AC-auth-006", None, "feat(auth): store salted password hashes"),
]

LANGS = ["python", "javascript", "typescript", "go", "rust", "kotlin"]


def load_lang(name):
    import importlib
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    return importlib.import_module(f"langs.{name}.stages")


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


def build(target, gnupg, lang="python", shared=None):
    L = load_lang(lang)
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
    scaffold = {".spectral.yaml": SPECTRAL, ".gitignore": L.GITIGNORE,
                "README.md": README.format(name=L.NAME, stack=L.STACK),
                **(L.SCAFFOLD() if callable(L.SCAFFOLD) else L.SCAFFOLD)}
    repo.write(scaffold)
    repo.commit("chore: add project scaffold and verifier config")
    if hasattr(L, "prepare"):
        L.prepare(target, (Path(shared) if shared else target.parent / "shared").resolve())

    for branch, req, contract, message in FEATURES:
        repo.git("checkout", "-q", "-b", branch)
        if contract:
            repo.write({"contracts/openapi.yaml": contract[1]})
            repo.commit(contract[0], author=AGENT, trailers=[f"Refs: {req}", AGENT_TRAILER])
        repo.write(L.CODE[req])
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
    ap.add_argument("--lang", default="python", choices=LANGS)
    ap.add_argument("--shared", help="directory for dependencies shared between copies of the repo")
    a = ap.parse_args()
    print(build(a.target, a.gnupg, a.lang, a.shared))
