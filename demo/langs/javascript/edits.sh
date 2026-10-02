# JavaScript edits used by the scenarios. Each function changes files only; the scenario commits.

e_impl_007() {
  replace src/auth.js "  addAccount(email, password) {
" "  addAccount(email, password) {
    if (password.length < 6) {
      throw new Error(\"password too short\");
    }
"
}

e_tests_007() {
  cat > tests/password-length.test.js <<'JS'
const { AccountStore } = require("../src/auth");

test("AC-auth-007 five characters rejected", () => {
  expect(() => new AccountStore().addAccount("bo@example.com", "five5")).toThrow();
});

test("AC-auth-007 six characters accepted", () => {
  const store = new AccountStore();
  store.addAccount("bo@example.com", "six666");
  expect(store.accounts.has("bo@example.com")).toBe(true);
});
JS
}

e_test_007_assert_true() {
  cat > tests/password-length.test.js <<'JS'
test("AC-auth-007 short passwords rejected", () => {
  expect(true).toBe(true);
});
JS
}

e_comment_007() {
  replace src/auth.js "  addAccount(email, password) {
" "  addAccount(email, password) {
    // TODO: enforce the minimum password length
"
}

e_threshold_4() { replace src/auth.js "const MAX_FAILED_ATTEMPTS = 3;" "const MAX_FAILED_ATTEMPTS = 4;"; }

e_lockout_gt() {
  replace src/auth.js "if (this.failed.get(email) >= MAX_FAILED_ATTEMPTS) {" "if (this.failed.get(email) > MAX_FAILED_ATTEMPTS) {"
}

# Moves auth.js but leaves the tests importing the old path, so the suite can't load.
e_rename_expiry_src_only() {
  git mv src/auth.js src/accounts.js
  replace src/app.js 'require("./auth")' 'require("./accounts")'
}

e_weak_lockout_tests() {
  cat > tests/lockout.test.js <<'JS'
const request = require("supertest");
const { setup } = require("./setup");

const BAD = { email: "ada@example.com", password: "wrong" };

test("AC-auth-002 failed attempts are rejected", async () => {
  const { app } = setup();
  for (let i = 0; i < 3; i++) {
    const r = await request(app).post("/login").send(BAD);
    expect(r.status).toBe(401);
  }
});
JS
}

e_logout_route_and_test() {
  replace src/app.js "  app.use((err, req, res, next) => {
" "  app.post(\"/logout\", (req, res) => res.json({ status: \"signed_out\" }));

  app.use((err, req, res, next) => {
"
  cat > tests/logout.test.js <<'JS'
const request = require("supertest");
const { setup } = require("./setup");

test("AC-auth-007 sign out", async () => {
  const { app } = setup();
  const r = await request(app).post("/logout");
  expect(r.status).toBe(200);
  expect(r.body).toEqual({ status: "signed_out" });
});
JS
}

e_rename_token() {
  replace src/app.js "return res.json({ token: result });" "return res.json({ access_token: result });"
  replace tests/login.test.js "expect(r.body.token)" "expect(r.body.access_token)"
}

e_debug_route() {
  replace src/app.js "  app.use((err, req, res, next) => {
" "  app.get(\"/debug/users\", (req, res) => res.json({ users: [...store.accounts.keys()] }));

  app.use((err, req, res, next) => {
"
}

e_leak_password() {
  replace src/app.js "return res.json({ token: result });" "return res.json({ token: result, debug_password: password });"
}

e_status_423() {
  replace src/app.js "      return res.status(401).json({ error: result });" "      return res.status(result === \"locked\" ? 423 : 401).json({ error: result });"
  replace tests/lockout.test.js '  expect(r.status).toBe(401);
  expect(r.body).toEqual({ error: "locked" });' '  expect(r.status).toBe(423);
  expect(r.body).toEqual({ error: "locked" });'
}

e_reset_crash() {
  replace src/app.js "    store.requestReset(email);
" "    const domain = email.split(\"@\")[1].toLowerCase();
    store.requestReset(email);
"
}

e_doc_comment() {
  replace src/auth.js "  signIn(email, password) {
" "  // Returns a session token, or \"denied\" / \"locked\".
  signIn(email, password) {
"
}

e_big_file() {
  python3 - <<'PY'
lines = ["// Email domains that never receive reset links.", "const BLOCKED_DOMAINS = new Set(["]
lines += [f'  "blocked-{i}.example",' for i in range(600)]
lines += ["]);", "", "module.exports = { BLOCKED_DOMAINS };"]
open("src/blocked-domains.js", "w").write("\n".join(lines) + "\n")
PY
}
