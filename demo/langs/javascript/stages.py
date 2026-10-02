"""JavaScript demo: Express 4 service, Jest + supertest tests, Istanbul LCOV coverage."""
import json
import os
import subprocess

from ..common import aqv_config, d

NAME = "JavaScript"
STACK = "Node 22 · Express 4 · Jest · supertest"

AQV_CONFIG = aqv_config(["src/"], ["tests/"], d("""
    # Runner profile: how to run the tests and where the reports go.
    runner:
      test: "JEST_JUNIT_OUTPUT_FILE={junit} npx jest --ci --reporters=default --reporters=jest-junit {extra} {filter}"
      coverage: "npx jest --ci --coverage --coverageReporters=lcov --coverageDirectory={cov_data} {filter}"
      coverage_out: "{cov_data}/lcov.info"
      filter: "-t '{id}'"
      select_nothing: "-t aqv_selects_no_tests"
      comment_prefix: ["//", "/*", "*"]
      worktree_links: ["node_modules"]

    api:
      routes_from_code: "node {aqv}/adapters/node/express-routes.cjs src/app.js createApp"
      serve: "PORT={port} node src/server.js"
      capture: true
      capture_extra: "--setupFilesAfterEnv {aqv}/adapters/node/capture.cjs"

    mutation:
      family: c
      build: "node --check {file}"
      min_kill_ratio: 0.6
      max_mutants: 20
"""), size_exclude=("package-lock.json",))

PACKAGE = json.dumps({
    "name": "auth-service",
    "version": "0.1.0",
    "private": True,
    "scripts": {"test": "jest", "start": "node src/server.js"},
    "dependencies": {"express": "^4.21.2"},
    "devDependencies": {"jest": "^29.7.0", "jest-junit": "^16.0.0", "supertest": "^7.0.0"},
    "jest": {"testEnvironment": "node", "testMatch": ["**/tests/**/*.test.js"]},
}, indent=2) + "\n"

# ---------------------------------------------------------------------------
# Code, one version per requirement
# ---------------------------------------------------------------------------

AUTH_1 = d('''
    const crypto = require("crypto");

    class AccountStore {
      constructor() {
        this.accounts = new Map();
      }

      static withDemoAccounts() {
        const store = new AccountStore();
        store.addAccount("ada@example.com", "correct horse");
        return store;
      }

      addAccount(email, password) {
        this.accounts.set(email, password);
      }

      signIn(email, password) {
        if (this.accounts.get(email) === password) {
          return crypto.randomBytes(16).toString("hex");
        }
        return "denied";
      }
    }

    module.exports = { AccountStore };
''')

AUTH_2 = d('''
    const crypto = require("crypto");

    const MAX_FAILED_ATTEMPTS = 3;

    class AccountStore {
      constructor() {
        this.accounts = new Map();
        this.failed = new Map();
        this.locked = new Set();
      }

      static withDemoAccounts() {
        const store = new AccountStore();
        store.addAccount("ada@example.com", "correct horse");
        return store;
      }

      addAccount(email, password) {
        this.accounts.set(email, password);
      }

      signIn(email, password) {
        if (this.locked.has(email)) {
          return "locked";
        }
        if (this.accounts.get(email) === password) {
          this.failed.set(email, 0);
          return crypto.randomBytes(16).toString("hex");
        }
        this.failed.set(email, (this.failed.get(email) || 0) + 1);
        if (this.failed.get(email) >= MAX_FAILED_ATTEMPTS) {
          this.locked.add(email);
        }
        return "denied";
      }
    }

    module.exports = { AccountStore };
''')

AUTH_3 = AUTH_2.replace(
    "const MAX_FAILED_ATTEMPTS = 3;\n",
    "const MAX_FAILED_ATTEMPTS = 3;\nconst SESSION_TTL_SECONDS = 30 * 60;\n\n"
    "function isExpired(lastSeen, now) {\n  return now - lastSeen > SESSION_TTL_SECONDS;\n}\n",
).replace("module.exports = { AccountStore };", "module.exports = { AccountStore, isExpired };")

AUTH_4 = AUTH_3.replace(
    "    this.locked = new Set();\n",
    "    this.locked = new Set();\n    this.resetOutbox = [];\n",
).replace(
    '    return "denied";\n  }\n}\n',
    '    return "denied";\n  }\n\n'
    "  requestReset(email) {\n"
    "    if (this.accounts.has(email)) {\n"
    "      this.resetOutbox.push(email);\n"
    "      return true;\n"
    "    }\n"
    "    return false;\n"
    "  }\n}\n",
)

AUTH_5 = AUTH_4.replace(
    "      this.resetOutbox.push(email);\n      return true;\n    }\n    return false;\n  }\n",
    "      this.resetOutbox.push(email);\n    }\n  }\n",
)

AUTH_6 = (
    AUTH_5.replace(
        "\nfunction isExpired",
        "\nfunction hashPassword(password, salt) {\n"
        '  return crypto.createHash("sha256").update(salt + password).digest("hex");\n'
        "}\n\nfunction isExpired",
    )
    .replace(
        "  addAccount(email, password) {\n    this.accounts.set(email, password);\n  }\n",
        "  addAccount(email, password) {\n"
        '    const salt = crypto.randomBytes(8).toString("hex");\n'
        "    this.accounts.set(email, { salt, digest: hashPassword(password, salt) });\n"
        "  }\n\n"
        "  passwordMatches(email, password) {\n"
        "    const { salt, digest } = this.accounts.get(email);\n"
        "    return hashPassword(password, salt) === digest;\n"
        "  }\n",
    )
    .replace(
        "    if (this.accounts.get(email) === password) {\n",
        "    if (this.accounts.has(email) && this.passwordMatches(email, password)) {\n",
    )
    .replace("module.exports = { AccountStore, isExpired };", "module.exports = { AccountStore, hashPassword, isExpired };")
)

APP_1 = d('''
    const express = require("express");
    const { AccountStore } = require("./auth");

    function invalid(res) {
      return res.status(400).json({ error: "invalid_request" });
    }

    function isString(value) {
      return typeof value === "string";
    }

    function createApp(store = AccountStore.withDemoAccounts()) {
      const app = express();
      app.use(express.json());

      app.post("/login", (req, res) => {
        const { email, password } = req.body || {};
        if (!isString(email) || !isString(password)) return invalid(res);
        const result = store.signIn(email, password);
        if (result === "denied") {
          return res.status(401).json({ error: result });
        }
        return res.json({ token: result });
      });

      app.use((err, req, res, next) => {
        if (err.type === "entity.parse.failed") return invalid(res);
        return next(err);
      });
      return app;
    }

    module.exports = { createApp };
''')

APP_2 = APP_1.replace('    if (result === "denied") {\n', '    if (result === "denied" || result === "locked") {\n')

APP_3 = APP_2.replace(
    'const { AccountStore } = require("./auth");\n', 'const { AccountStore, isExpired } = require("./auth");\n'
).replace(
    "    return res.json({ token: result });\n  });\n",
    "    return res.json({ token: result });\n  });\n\n"
    '  app.get("/session", (req, res) => {\n'
    "    const lastSeen = Number(req.query.last_seen);\n"
    "    if (!Number.isInteger(lastSeen) || lastSeen < 0 || lastSeen > 4102444800) return invalid(res);\n"
    "    return res.json({ expired: isExpired(lastSeen, Date.now() / 1000) });\n"
    "  });\n",
)

APP_4 = APP_3.replace(
    "    return res.json({ expired: isExpired(lastSeen, Date.now() / 1000) });\n  });\n",
    "    return res.json({ expired: isExpired(lastSeen, Date.now() / 1000) });\n  });\n\n"
    '  app.post("/password-reset", (req, res) => {\n'
    "    const { email } = req.body || {};\n"
    "    if (!isString(email)) return invalid(res);\n"
    "    const sent = store.requestReset(email);\n"
    '    return res.status(202).json({ status: sent ? "sent" : "unknown_email" });\n'
    "  });\n",
)

APP_5 = APP_4.replace(
    "    const sent = store.requestReset(email);\n"
    '    return res.status(202).json({ status: sent ? "sent" : "unknown_email" });\n',
    "    store.requestReset(email);\n"
    '    return res.status(202).json({ status: "sent" });\n',
)

SERVER = d('''
    const { createApp } = require("./app");

    const port = Number(process.env.PORT || 8000);
    createApp().listen(port, "127.0.0.1");
''')

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

SETUP = d('''
    const { AccountStore } = require("../src/auth");
    const { createApp } = require("../src/app");

    function setup() {
      const store = AccountStore.withDemoAccounts();
      return { store, app: createApp(store) };
    }

    module.exports = { setup };
''')

TEST_LOGIN = d('''
    const request = require("supertest");
    const { setup } = require("./setup");

    const GOOD = { email: "ada@example.com", password: "correct horse" };

    test("AC-auth-001 sign in returns a token", async () => {
      const { app } = setup();
      const r = await request(app).post("/login").send(GOOD);
      expect(r.status).toBe(200);
      expect(r.body.token).toHaveLength(32);
    });

    test("AC-auth-001 wrong password is denied", async () => {
      const { app } = setup();
      const r = await request(app).post("/login").send({ ...GOOD, password: "wrong" });
      expect(r.status).toBe(401);
      expect(r.body).toEqual({ error: "denied" });
    });

    test("AC-auth-001 malformed request is rejected", async () => {
      const { app } = setup();
      const r = await request(app).post("/login").send({ email: "ada@example.com" });
      expect(r.status).toBe(400);
      expect(r.body).toEqual({ error: "invalid_request" });
    });
''')

TEST_LOCKOUT = d('''
    const request = require("supertest");
    const { setup } = require("./setup");

    const BAD = { email: "ada@example.com", password: "wrong" };
    const GOOD = { email: "ada@example.com", password: "correct horse" };

    async function fail(app, times) {
      for (let i = 0; i < times; i++) {
        await request(app).post("/login").send(BAD);
      }
    }

    test("AC-auth-002 locks after three failures", async () => {
      const { app } = setup();
      await fail(app, 3);
      const r = await request(app).post("/login").send(GOOD);
      expect(r.status).toBe(401);
      expect(r.body).toEqual({ error: "locked" });
    });

    test("AC-auth-002 two failures do not lock", async () => {
      const { app } = setup();
      await fail(app, 2);
      const r = await request(app).post("/login").send(GOOD);
      expect(r.status).toBe(200);
    });

    test("AC-auth-002 success resets the count", async () => {
      const { app } = setup();
      await fail(app, 2);
      await request(app).post("/login").send(GOOD);
      await fail(app, 2);
      const r = await request(app).post("/login").send(GOOD);
      expect(r.status).toBe(200);
    });
''')

TEST_SESSION = d('''
    const request = require("supertest");
    const { isExpired } = require("../src/auth");
    const { setup } = require("./setup");

    const now = () => Math.floor(Date.now() / 1000);

    test("AC-auth-003 expired after 30 minutes", async () => {
      const { app } = setup();
      const r = await request(app).get("/session").query({ last_seen: now() - 31 * 60 });
      expect(r.status).toBe(200);
      expect(r.body).toEqual({ expired: true });
    });

    test("AC-auth-003 active within 30 minutes", async () => {
      const { app } = setup();
      const r = await request(app).get("/session").query({ last_seen: now() - 29 * 60 });
      expect(r.body).toEqual({ expired: false });
    });

    test("AC-auth-003 boundary is exactly 30 minutes", () => {
      expect(isExpired(0, 30 * 60)).toBe(false);
      expect(isExpired(0, 30 * 60 + 1)).toBe(true);
    });

    test("AC-auth-003 rejects a bad last_seen and accepts the edges", async () => {
      const { app } = setup();
      for (const bad of ["soon", -1, 4102444801]) {
        const r = await request(app).get("/session").query({ last_seen: bad });
        expect(r.status).toBe(400);
        expect(r.body).toEqual({ error: "invalid_request" });
      }
      for (const edge of [0, 4102444800]) {
        const r = await request(app).get("/session").query({ last_seen: edge });
        expect(r.status).toBe(200);
      }
    });
''')

TEST_RESET_4 = d('''
    const request = require("supertest");
    const { setup } = require("./setup");

    test("AC-auth-004 link sent for a known email", async () => {
      const { app, store } = setup();
      const r = await request(app).post("/password-reset").send({ email: "ada@example.com" });
      expect(r.status).toBe(202);
      expect(store.resetOutbox).toEqual(["ada@example.com"]);
    });

    test("AC-auth-004 no link for an unknown email", async () => {
      const { app, store } = setup();
      await request(app).post("/password-reset").send({ email: "nobody@example.com" });
      expect(store.resetOutbox).toEqual([]);
    });
''')

TEST_RESET_5 = TEST_RESET_4 + d('''

    test("AC-auth-005 same response for an unknown email", async () => {
      const { app } = setup();
      const known = await request(app).post("/password-reset").send({ email: "ada@example.com" });
      const unknown = await request(app).post("/password-reset").send({ email: "nobody@example.com" });
      expect(known.status).toBe(202);
      expect(unknown.status).toBe(202);
      expect(known.body).toEqual({ status: "sent" });
      expect(unknown.body).toEqual(known.body);
    });

    test("AC-auth-005 known email still gets its link", async () => {
      const { app, store } = setup();
      await request(app).post("/password-reset").send({ email: "nobody@example.com" });
      await request(app).post("/password-reset").send({ email: "ada@example.com" });
      expect(store.resetOutbox).toEqual(["ada@example.com"]);
    });
''')

TEST_STORAGE = d('''
    const { AccountStore, hashPassword } = require("../src/auth");

    test("AC-auth-006 password not stored in plain text", () => {
      const store = new AccountStore();
      store.addAccount("bo@example.com", "s3cret");
      const { salt, digest } = store.accounts.get("bo@example.com");
      expect([salt, digest]).not.toContain("s3cret");
      expect(digest).toBe(hashPassword("s3cret", salt));
    });

    test("AC-auth-006 hashed password still signs in", () => {
      const store = new AccountStore();
      store.addAccount("bo@example.com", "s3cret");
      expect(["denied", "locked"]).not.toContain(store.signIn("bo@example.com", "s3cret"));
      expect(store.signIn("bo@example.com", "nope")).toBe("denied");
    });
''')

# ---------------------------------------------------------------------------
# What the builder needs
# ---------------------------------------------------------------------------

GITIGNORE = "node_modules\ncoverage/\njunit.xml\n.aqv-out/\n"

SCAFFOLD = {"package.json": PACKAGE, ".aqv.yml": AQV_CONFIG}

CODE = {
    "AC-auth-001": {"src/auth.js": AUTH_1, "src/app.js": APP_1, "src/server.js": SERVER,
                    "tests/setup.js": SETUP, "tests/login.test.js": TEST_LOGIN},
    "AC-auth-002": {"src/auth.js": AUTH_2, "src/app.js": APP_2, "tests/lockout.test.js": TEST_LOCKOUT},
    "AC-auth-003": {"src/auth.js": AUTH_3, "src/app.js": APP_3, "tests/session.test.js": TEST_SESSION},
    "AC-auth-004": {"src/auth.js": AUTH_4, "src/app.js": APP_4, "tests/reset.test.js": TEST_RESET_4},
    "AC-auth-005": {"src/auth.js": AUTH_5, "src/app.js": APP_5, "tests/reset.test.js": TEST_RESET_5},
    "AC-auth-006": {"src/auth.js": AUTH_6, "tests/storage.test.js": TEST_STORAGE},
}

MECHANISMS = {
    "T5": "jest-junit reporter",
    "T6": "Jest coverage per requirement (-t), LCOV",
    "T7": "Built-in line mutator; node --check",
    "A5": "Route list from Express's router (adapter)",
    "A6": "Setup file records http.ServerResponse per test (adapter)",
    "A7": "node server + Schemathesis",
}


def prepare(repo, shared):
    """Install node_modules once per language and link it into the repo (git ignores the link)."""
    deps = shared / "node"
    if not (deps / "node_modules").exists():
        deps.mkdir(parents=True, exist_ok=True)
        (deps / "package.json").write_text(PACKAGE)
        subprocess.run(["npm", "install", "--silent", "--no-audit", "--no-fund"], cwd=deps, check=True)
    link = repo / "node_modules"
    if not link.exists():
        os.symlink(deps / "node_modules", link)
