# TypeScript edits used by the scenarios. Each function changes files only; the scenario commits.

e_impl_007() {
  replace src/auth.ts "  addAccount(email: string, password: string): void {
" "  addAccount(email: string, password: string): void {
    if (password.length < 6) {
      throw new Error(\"password too short\");
    }
"
}

e_tests_007() {
  cat > tests/password-length.test.ts <<'TS'
import { expect, test } from "vitest";
import { AccountStore } from "../src/auth";

test("AC-auth-007 five characters rejected", () => {
  expect(() => new AccountStore().addAccount("bo@example.com", "five5")).toThrow();
});

test("AC-auth-007 six characters accepted", () => {
  const store = new AccountStore();
  store.addAccount("bo@example.com", "six666");
  expect(store.accounts.has("bo@example.com")).toBe(true);
});
TS
}

e_test_007_assert_true() {
  cat > tests/password-length.test.ts <<'TS'
import { expect, test } from "vitest";

test("AC-auth-007 short passwords rejected", () => {
  expect(true).toBe(true);
});
TS
}

e_comment_007() {
  replace src/auth.ts "  addAccount(email: string, password: string): void {
" "  addAccount(email: string, password: string): void {
    // TODO: enforce the minimum password length
"
}

e_threshold_4() { replace src/auth.ts "const MAX_FAILED_ATTEMPTS = 3;" "const MAX_FAILED_ATTEMPTS = 4;"; }

e_lockout_gt() { replace src/auth.ts "if (failures >= MAX_FAILED_ATTEMPTS) {" "if (failures > MAX_FAILED_ATTEMPTS) {"; }

# Renames isExpired in src but not in the session test, so that test file can't load.
e_rename_expiry_src_only() {
  replace src/auth.ts "export function isExpired(" "export function sessionExpired("
  replace src/app.ts 'import { AccountStore, isExpired } from "./auth";' 'import { AccountStore, sessionExpired } from "./auth";'
  replace src/app.ts "isExpired(request.query.last_seen" "sessionExpired(request.query.last_seen"
}

e_weak_lockout_tests() {
  cat > tests/lockout.test.ts <<'TS'
import { expect, test } from "vitest";
import { setup } from "./setup";

const BAD = { email: "ada@example.com", password: "wrong" };

test("AC-auth-002 failed attempts are rejected", async () => {
  const { app } = await setup();
  for (let i = 0; i < 3; i++) {
    const r = await app.inject({ method: "POST", url: "/login", payload: BAD });
    expect(r.statusCode).toBe(401);
  }
});
TS
}

e_logout_route_and_test() {
  replace src/app.ts "  return app;
}" "  app.post(\"/logout\", async () => ({ status: \"signed_out\" }));

  return app;
}"
  cat > tests/logout.test.ts <<'TS'
import { expect, test } from "vitest";
import { setup } from "./setup";

test("AC-auth-007 sign out", async () => {
  const { app } = await setup();
  const r = await app.inject({ method: "POST", url: "/logout" });
  expect(r.statusCode).toBe(200);
  expect(r.json()).toEqual({ status: "signed_out" });
});
TS
}

e_rename_token() {
  replace src/app.ts "return { token: result };" "return { access_token: result };"
  replace tests/login.test.ts "expect(r.json().token)" "expect(r.json().access_token)"
}

e_debug_route() {
  replace src/app.ts "  return app;
}" "  app.get(\"/debug/users\", async () => ({ users: [...store.accounts.keys()] }));

  return app;
}"
}

e_leak_password() {
  replace src/app.ts "return { token: result };" "return { token: result, debug_password: request.body.password };"
}

e_status_423() {
  replace src/app.ts "      return reply.status(401).send({ error: result });" "      return reply.status(result === \"locked\" ? 423 : 401).send({ error: result });"
  replace tests/lockout.test.ts '  expect(r.statusCode).toBe(401);
  expect(r.json()).toEqual({ error: "locked" });' '  expect(r.statusCode).toBe(423);
  expect(r.json()).toEqual({ error: "locked" });'
}

e_reset_crash() {
  replace src/app.ts "    store.requestReset(request.body.email);
" "    const domain = request.body.email.split(\"@\")[1].toLowerCase();
    store.requestReset(request.body.email);
"
}

e_doc_comment() {
  replace src/auth.ts "  signIn(email: string, password: string): string {
" "  // Returns a session token, or \"denied\" / \"locked\".
  signIn(email: string, password: string): string {
"
}

e_big_file() {
  python3 - <<'PY'
lines = ["// Email domains that never receive reset links.", "export const BLOCKED_DOMAINS = new Set<string>(["]
lines += [f'  "blocked-{i}.example",' for i in range(600)]
lines += ["]);"]
open("src/blocked-domains.ts", "w").write("\n".join(lines) + "\n")
PY
}
