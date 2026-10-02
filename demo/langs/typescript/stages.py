"""TypeScript demo: Fastify 5 service with @fastify/swagger, Vitest tests using app.inject, V8 coverage."""
import json
import os
import subprocess

from ..common import aqv_config, d

NAME = "TypeScript"
STACK = "Node 22 · Fastify 5 · Vitest · tsx"

AQV_CONFIG = aqv_config(["src/"], ["tests/"], d("""
    # Runner profile: how to run the tests and where the reports go.
    runner:
      test: "{extra} npx vitest run --reporter=default --reporter=junit --outputFile.junit={junit} {filter}"
      coverage: "npx vitest run --coverage.enabled --coverage.reportOnFailure=true --coverage.provider=v8 --coverage.reporter=lcov --coverage.reportsDirectory={cov_data} --coverage.include='src/**' {filter}"
      coverage_out: "{cov_data}/lcov.info"
      filter: "-t '{id}'"
      select_nothing: "-t aqv_selects_no_tests --passWithNoTests"
      comment_prefix: ["//", "/*", "*"]
      worktree_links: ["node_modules"]

    api:
      openapi_from_code: "npx tsx {aqv}/adapters/node/fastify-openapi.mjs src/app.ts createApp"
      serve: "PORT={port} npx tsx src/server.ts"
      capture: true
      capture_extra: "AQV_SETUP={aqv}/adapters/node/capture.cjs"

    mutation:
      family: c
      build: "npx tsc --noEmit -p ."
      min_kill_ratio: 0.6
      max_mutants: 20
"""), size_exclude=("package-lock.json",))

PACKAGE = json.dumps({
    "name": "auth-service",
    "version": "0.1.0",
    "private": True,
    "type": "module",
    "scripts": {"test": "vitest run", "start": "tsx src/server.ts"},
    "dependencies": {"fastify": "^5.2.0", "@fastify/swagger": "^9.4.0"},
    "devDependencies": {"typescript": "^5.7.0", "vitest": "^3.0.0", "@vitest/coverage-v8": "^3.0.0",
                        "tsx": "^4.19.0", "@types/node": "^22.10.0"},
}, indent=2) + "\n"

TSCONFIG = json.dumps({
    "compilerOptions": {
        "target": "ES2022", "module": "ESNext", "moduleResolution": "Bundler", "strict": True,
        "noEmit": True, "esModuleInterop": True, "skipLibCheck": True, "types": ["node"],
    },
    "include": ["src", "tests"],
}, indent=2) + "\n"

# Human-owned: the verifier's A6 adapter is added as a setup file when AQV_SETUP is set.
VITEST_CONFIG = d('''
    import { defineConfig } from "vitest/config";

    export default defineConfig({
      test: {
        include: ["tests/**/*.test.ts"],
        setupFiles: process.env.AQV_SETUP ? [process.env.AQV_SETUP] : [],
      },
    });
''')

# ---------------------------------------------------------------------------
# Code, one version per requirement
# ---------------------------------------------------------------------------

AUTH_1 = d('''
    import { randomBytes } from "node:crypto";

    export class AccountStore {
      accounts = new Map<string, string>();

      static withDemoAccounts(): AccountStore {
        const store = new AccountStore();
        store.addAccount("ada@example.com", "correct horse");
        return store;
      }

      addAccount(email: string, password: string): void {
        this.accounts.set(email, password);
      }

      signIn(email: string, password: string): string {
        if (this.accounts.get(email) === password) {
          return randomBytes(16).toString("hex");
        }
        return "denied";
      }
    }
''')

AUTH_2 = d('''
    import { randomBytes } from "node:crypto";

    const MAX_FAILED_ATTEMPTS = 3;

    export class AccountStore {
      accounts = new Map<string, string>();
      failed = new Map<string, number>();
      locked = new Set<string>();

      static withDemoAccounts(): AccountStore {
        const store = new AccountStore();
        store.addAccount("ada@example.com", "correct horse");
        return store;
      }

      addAccount(email: string, password: string): void {
        this.accounts.set(email, password);
      }

      signIn(email: string, password: string): string {
        if (this.locked.has(email)) {
          return "locked";
        }
        if (this.accounts.get(email) === password) {
          this.failed.set(email, 0);
          return randomBytes(16).toString("hex");
        }
        const failures = (this.failed.get(email) ?? 0) + 1;
        this.failed.set(email, failures);
        if (failures >= MAX_FAILED_ATTEMPTS) {
          this.locked.add(email);
        }
        return "denied";
      }
    }
''')

AUTH_3 = AUTH_2.replace(
    "const MAX_FAILED_ATTEMPTS = 3;\n",
    "const MAX_FAILED_ATTEMPTS = 3;\nconst SESSION_TTL_SECONDS = 30 * 60;\n\n"
    "export function isExpired(lastSeen: number, now: number): boolean {\n"
    "  return now - lastSeen > SESSION_TTL_SECONDS;\n}\n",
)

AUTH_4 = AUTH_3.replace(
    "  locked = new Set<string>();\n",
    "  locked = new Set<string>();\n  resetOutbox: string[] = [];\n",
).replace(
    '    return "denied";\n  }\n}\n',
    '    return "denied";\n  }\n\n'
    "  requestReset(email: string): boolean {\n"
    "    if (this.accounts.has(email)) {\n"
    "      this.resetOutbox.push(email);\n"
    "      return true;\n"
    "    }\n"
    "    return false;\n"
    "  }\n}\n",
)

AUTH_5 = AUTH_4.replace(
    "  requestReset(email: string): boolean {\n",
    "  requestReset(email: string): void {\n",
).replace(
    "      this.resetOutbox.push(email);\n      return true;\n    }\n    return false;\n  }\n",
    "      this.resetOutbox.push(email);\n    }\n  }\n",
)

AUTH_6 = (
    AUTH_5.replace('import { randomBytes } from "node:crypto";\n',
                   'import { createHash, randomBytes } from "node:crypto";\n')
    .replace(
        "\nexport function isExpired",
        "\nexport function hashPassword(password: string, salt: string): string {\n"
        '  return createHash("sha256").update(salt + password).digest("hex");\n'
        "}\n\nexport function isExpired",
    )
    .replace("  accounts = new Map<string, string>();\n",
             "  accounts = new Map<string, { salt: string; digest: string }>();\n")
    .replace(
        "  addAccount(email: string, password: string): void {\n    this.accounts.set(email, password);\n  }\n",
        "  addAccount(email: string, password: string): void {\n"
        '    const salt = randomBytes(8).toString("hex");\n'
        "    this.accounts.set(email, { salt, digest: hashPassword(password, salt) });\n"
        "  }\n\n"
        "  passwordMatches(email: string, password: string): boolean {\n"
        "    const { salt, digest } = this.accounts.get(email)!;\n"
        "    return hashPassword(password, salt) === digest;\n"
        "  }\n",
    )
    .replace(
        "    if (this.accounts.get(email) === password) {\n",
        "    if (this.accounts.has(email) && this.passwordMatches(email, password)) {\n",
    )
)

APP_1 = d('''
    import Fastify, { FastifyError, FastifyInstance } from "fastify";
    import swagger from "@fastify/swagger";
    import { AccountStore } from "./auth";

    const credentials = {
      type: "object",
      required: ["email", "password"],
      properties: { email: { type: "string" }, password: { type: "string" } },
    } as const;

    export async function createApp(store: AccountStore = AccountStore.withDemoAccounts()): Promise<FastifyInstance> {
      const app = Fastify();
      await app.register(swagger, { openapi: { info: { title: "Auth service", version: "1.0.0" } } });

      app.setErrorHandler<FastifyError>((error, request, reply) => {
        if (error.validation) {
          return reply.status(400).send({ error: "invalid_request" });
        }
        return reply.send(error);
      });

      app.post<{ Body: { email: string; password: string } }>("/login", { schema: { body: credentials } }, async (request, reply) => {
        const result = store.signIn(request.body.email, request.body.password);
        if (result === "denied") {
          return reply.status(401).send({ error: result });
        }
        return { token: result };
      });

      return app;
    }
''')

APP_2 = APP_1.replace('    if (result === "denied") {\n', '    if (result === "denied" || result === "locked") {\n')

APP_3 = APP_2.replace(
    'import { AccountStore } from "./auth";\n', 'import { AccountStore, isExpired } from "./auth";\n'
).replace(
    "} as const;\n\nexport async function",
    "} as const;\n\n"
    "const sessionQuery = {\n"
    '  type: "object",\n'
    '  required: ["last_seen"],\n'
    '  properties: { last_seen: { type: "integer", minimum: 0, maximum: 4102444800 } },\n'
    "} as const;\n\nexport async function",
).replace(
    "    return { token: result };\n  });\n",
    "    return { token: result };\n  });\n\n"
    '  app.get<{ Querystring: { last_seen: number } }>("/session", { schema: { querystring: sessionQuery } }, async (request) => {\n'
    "    return { expired: isExpired(request.query.last_seen, Date.now() / 1000) };\n"
    "  });\n",
)

APP_4 = APP_3.replace(
    "} as const;\n\nexport async function",
    "} as const;\n\n"
    "const resetRequest = {\n"
    '  type: "object",\n'
    '  required: ["email"],\n'
    '  properties: { email: { type: "string" } },\n'
    "} as const;\n\nexport async function",
).replace(
    "    return { expired: isExpired(request.query.last_seen, Date.now() / 1000) };\n  });\n",
    "    return { expired: isExpired(request.query.last_seen, Date.now() / 1000) };\n  });\n\n"
    '  app.post<{ Body: { email: string } }>("/password-reset", { schema: { body: resetRequest } }, async (request, reply) => {\n'
    "    const sent = store.requestReset(request.body.email);\n"
    '    return reply.status(202).send({ status: sent ? "sent" : "unknown_email" });\n'
    "  });\n",
)
APP_5 = APP_4.replace(
    "    const sent = store.requestReset(request.body.email);\n"
    '    return reply.status(202).send({ status: sent ? "sent" : "unknown_email" });\n',
    "    store.requestReset(request.body.email);\n"
    '    return reply.status(202).send({ status: "sent" });\n',
)

SERVER = d('''
    import { createApp } from "./app";

    const app = await createApp();
    await app.listen({ port: Number(process.env.PORT ?? 8000), host: "127.0.0.1" });
''')

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

SETUP = d('''
    import { AccountStore } from "../src/auth";
    import { createApp } from "../src/app";

    export async function setup() {
      const store = AccountStore.withDemoAccounts();
      const app = await createApp(store);
      return { store, app };
    }
''')

TEST_LOGIN = d('''
    import { expect, test } from "vitest";
    import { setup } from "./setup";

    const GOOD = { email: "ada@example.com", password: "correct horse" };

    test("AC-auth-001 sign in returns a token", async () => {
      const { app } = await setup();
      const r = await app.inject({ method: "POST", url: "/login", payload: GOOD });
      expect(r.statusCode).toBe(200);
      expect(r.json().token).toHaveLength(32);
    });

    test("AC-auth-001 wrong password is denied", async () => {
      const { app } = await setup();
      const r = await app.inject({ method: "POST", url: "/login", payload: { ...GOOD, password: "wrong" } });
      expect(r.statusCode).toBe(401);
      expect(r.json()).toEqual({ error: "denied" });
    });

    test("AC-auth-001 malformed request is rejected", async () => {
      const { app } = await setup();
      const r = await app.inject({ method: "POST", url: "/login", payload: { email: "ada@example.com" } });
      expect(r.statusCode).toBe(400);
      expect(r.json()).toEqual({ error: "invalid_request" });
    });
''')

TEST_LOCKOUT = d('''
    import { expect, test } from "vitest";
    import type { FastifyInstance } from "fastify";
    import { setup } from "./setup";

    const BAD = { email: "ada@example.com", password: "wrong" };
    const GOOD = { email: "ada@example.com", password: "correct horse" };

    async function fail(app: FastifyInstance, times: number) {
      for (let i = 0; i < times; i++) {
        await app.inject({ method: "POST", url: "/login", payload: BAD });
      }
    }

    test("AC-auth-002 locks after three failures", async () => {
      const { app } = await setup();
      await fail(app, 3);
      const r = await app.inject({ method: "POST", url: "/login", payload: GOOD });
      expect(r.statusCode).toBe(401);
      expect(r.json()).toEqual({ error: "locked" });
    });

    test("AC-auth-002 two failures do not lock", async () => {
      const { app } = await setup();
      await fail(app, 2);
      const r = await app.inject({ method: "POST", url: "/login", payload: GOOD });
      expect(r.statusCode).toBe(200);
    });

    test("AC-auth-002 success resets the count", async () => {
      const { app } = await setup();
      await fail(app, 2);
      await app.inject({ method: "POST", url: "/login", payload: GOOD });
      await fail(app, 2);
      const r = await app.inject({ method: "POST", url: "/login", payload: GOOD });
      expect(r.statusCode).toBe(200);
    });
''')

TEST_SESSION = d('''
    import { expect, test } from "vitest";
    import { isExpired } from "../src/auth";
    import { setup } from "./setup";

    const now = () => Math.floor(Date.now() / 1000);

    test("AC-auth-003 expired after 30 minutes", async () => {
      const { app } = await setup();
      const r = await app.inject({ method: "GET", url: "/session", query: { last_seen: String(now() - 31 * 60) } });
      expect(r.statusCode).toBe(200);
      expect(r.json()).toEqual({ expired: true });
    });

    test("AC-auth-003 active within 30 minutes", async () => {
      const { app } = await setup();
      const r = await app.inject({ method: "GET", url: "/session", query: { last_seen: String(now() - 29 * 60) } });
      expect(r.json()).toEqual({ expired: false });
    });

    test("AC-auth-003 boundary is exactly 30 minutes", () => {
      expect(isExpired(0, 30 * 60)).toBe(false);
      expect(isExpired(0, 30 * 60 + 1)).toBe(true);
    });
''')

TEST_RESET_4 = d('''
    import { expect, test } from "vitest";
    import { setup } from "./setup";

    test("AC-auth-004 link sent for a known email", async () => {
      const { app, store } = await setup();
      const r = await app.inject({ method: "POST", url: "/password-reset", payload: { email: "ada@example.com" } });
      expect(r.statusCode).toBe(202);
      expect(store.resetOutbox).toEqual(["ada@example.com"]);
    });

    test("AC-auth-004 no link for an unknown email", async () => {
      const { app, store } = await setup();
      await app.inject({ method: "POST", url: "/password-reset", payload: { email: "nobody@example.com" } });
      expect(store.resetOutbox).toEqual([]);
    });
''')

TEST_RESET_5 = TEST_RESET_4 + d('''

    test("AC-auth-005 same response for an unknown email", async () => {
      const { app } = await setup();
      const known = await app.inject({ method: "POST", url: "/password-reset", payload: { email: "ada@example.com" } });
      const unknown = await app.inject({ method: "POST", url: "/password-reset", payload: { email: "nobody@example.com" } });
      expect(known.statusCode).toBe(202);
      expect(unknown.statusCode).toBe(202);
      expect(known.json()).toEqual({ status: "sent" });
      expect(unknown.json()).toEqual(known.json());
    });

    test("AC-auth-005 known email still gets its link", async () => {
      const { app, store } = await setup();
      await app.inject({ method: "POST", url: "/password-reset", payload: { email: "nobody@example.com" } });
      await app.inject({ method: "POST", url: "/password-reset", payload: { email: "ada@example.com" } });
      expect(store.resetOutbox).toEqual(["ada@example.com"]);
    });
''')

TEST_STORAGE = d('''
    import { expect, test } from "vitest";
    import { AccountStore, hashPassword } from "../src/auth";

    test("AC-auth-006 password not stored in plain text", () => {
      const store = new AccountStore();
      store.addAccount("bo@example.com", "s3cret");
      const { salt, digest } = store.accounts.get("bo@example.com")!;
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

GITIGNORE = "node_modules\ncoverage/\n.aqv-out/\n"

SCAFFOLD = {"package.json": PACKAGE, "tsconfig.json": TSCONFIG, "vitest.config.ts": VITEST_CONFIG,
            ".aqv.yml": AQV_CONFIG}

CODE = {
    "AC-auth-001": {"src/auth.ts": AUTH_1, "src/app.ts": APP_1, "src/server.ts": SERVER,
                    "tests/setup.ts": SETUP, "tests/login.test.ts": TEST_LOGIN},
    "AC-auth-002": {"src/auth.ts": AUTH_2, "src/app.ts": APP_2, "tests/lockout.test.ts": TEST_LOCKOUT},
    "AC-auth-003": {"src/auth.ts": AUTH_3, "src/app.ts": APP_3, "tests/session.test.ts": TEST_SESSION},
    "AC-auth-004": {"src/auth.ts": AUTH_4, "src/app.ts": APP_4, "tests/reset.test.ts": TEST_RESET_4},
    "AC-auth-005": {"src/auth.ts": AUTH_5, "src/app.ts": APP_5, "tests/reset.test.ts": TEST_RESET_5},
    "AC-auth-006": {"src/auth.ts": AUTH_6, "tests/storage.test.ts": TEST_STORAGE},
}

MECHANISMS = {
    "T5": "Vitest junit reporter",
    "T6": "Vitest V8 coverage per requirement (-t), LCOV",
    "T7": "Built-in line mutator; tsc --noEmit",
    "A5": "OpenAPI generated by @fastify/swagger",
    "A6": "Setup file records responses, incl. app.inject (adapter)",
    "A7": "tsx server + Schemathesis",
}


def prepare(repo, shared):
    deps = shared / "node"
    if not (deps / "node_modules").exists():
        deps.mkdir(parents=True, exist_ok=True)
        (deps / "package.json").write_text(PACKAGE)
        subprocess.run(["npm", "install", "--silent", "--no-audit", "--no-fund"], cwd=deps, check=True)
    link = repo / "node_modules"
    if not link.exists():
        os.symlink(deps / "node_modules", link)
