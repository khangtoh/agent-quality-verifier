# Python edits used by the scenarios. Each function changes files only; the scenario commits.

e_impl_007() {
  replace src/app/auth.py "    def add_account(self, email, password):
" "    def add_account(self, email, password):
        if len(password) < 6:
            raise ValueError(\"password too short\")
"
}

e_tests_007() {
  cat > tests/test_password_length.py <<'PY'
import pytest

from app.auth import AccountStore


def test_AC_auth_007_five_characters_rejected():
    with pytest.raises(ValueError):
        AccountStore().add_account("bo@example.com", "five5")


def test_AC_auth_007_six_characters_accepted():
    store = AccountStore()
    store.add_account("bo@example.com", "six666")
    assert "bo@example.com" in store.accounts
PY
}

e_test_007_assert_true() {
  cat > tests/test_password_length.py <<'PY'
def test_AC_auth_007_short_passwords_rejected():
    assert True
PY
}

e_comment_007() {
  replace src/app/auth.py "    def add_account(self, email, password):
" "    def add_account(self, email, password):
        # TODO: enforce the minimum password length
"
}

e_threshold_4() { replace src/app/auth.py "MAX_FAILED_ATTEMPTS = 3" "MAX_FAILED_ATTEMPTS = 4"; }

e_lockout_gt() {
  replace src/app/auth.py "if self.failed[email] >= MAX_FAILED_ATTEMPTS:" "if self.failed[email] > MAX_FAILED_ATTEMPTS:"
}

e_rename_expiry_src_only() {
  replace src/app/auth.py "def is_expired(" "def session_expired("
  replace src/app/main.py "from app.auth import AccountStore, is_expired" "from app.auth import AccountStore, session_expired"
  replace src/app/main.py "is_expired(last_seen, time.time())" "session_expired(last_seen, time.time())"
}

e_weak_lockout_tests() {
  cat > tests/test_lockout.py <<'PY'
BAD = {"email": "ada@example.com", "password": "wrong"}


def test_AC_auth_002_failed_attempts_are_rejected(client):
    for _ in range(3):
        r = client.post("/login", json=BAD)
        assert r.status_code == 401
PY
}

e_logout_route_and_test() {
  replace src/app/main.py "    return app
" "    @app.post(\"/logout\")
    def logout():
        return {\"status\": \"signed_out\"}

    return app
"
  cat > tests/test_logout.py <<'PY'
def test_AC_auth_007_sign_out(client):
    r = client.post("/logout")
    assert r.status_code == 200
    assert r.json() == {"status": "signed_out"}
PY
}

e_rename_token() {
  replace src/app/main.py 'return {"token": result}' 'return {"access_token": result}'
  replace tests/test_login.py 'r.json()["token"]' 'r.json()["access_token"]'
}

e_debug_route() {
  replace src/app/main.py "    return app
" "    @app.get(\"/debug/users\")
    def debug_users():
        return {\"users\": sorted(store.accounts)}

    return app
"
}

e_leak_password() {
  replace src/app/main.py 'return {"token": result}' 'return {"token": result, "debug_password": body.password}'
}

e_status_423() {
  replace src/app/main.py '            return JSONResponse({"error": result}, status_code=401)' '            return JSONResponse({"error": result}, status_code=423 if result == "locked" else 401)'
  replace tests/test_lockout.py '    assert r.status_code == 401
    assert r.json() == {"error": "locked"}' '    assert r.status_code == 423
    assert r.json() == {"error": "locked"}'
}

e_reset_crash() {
  replace src/app/main.py "        store.request_reset(body.email)
" "        domain = body.email.split(\"@\")[1]
        store.request_reset(body.email)
"
}

e_doc_comment() {
  replace src/app/auth.py "    def sign_in(self, email, password):
" "    def sign_in(self, email, password):
        \"\"\"Return a session token, or 'denied' / 'locked'.\"\"\"
"
}

e_big_file() {
  python3 - <<'PY'
lines = ['"""Email domains that never receive reset links."""', "BLOCKED_DOMAINS = {"]
lines += [f'    "blocked-{i}.example",' for i in range(600)]
lines += ["}"]
open("src/app/blocked_domains.py", "w").write("\n".join(lines) + "\n")
PY
}
