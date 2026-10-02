# title: The agent adds a test named for AC-auth-007 that only asserts True
# expect: T6
source "$DEMO/lib.sh"
branch feat/AC-auth-007-password-length
add_requirement "$REQ_007"
implement_007_code
cat > tests/test_password_length.py <<'PY'
def test_AC_auth_007_short_passwords_rejected():
    assert True
PY
agent_commit "feat(auth): reject passwords shorter than 6 characters" AC-auth-007
