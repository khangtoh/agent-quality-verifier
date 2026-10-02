# title: A sign-out requirement is implemented without adding it to the contract
# expect: A1
source "$DEMO/lib.sh"
branch feat/AC-auth-007-sign-out
add_requirement "- **AC-auth-007** (api: POST /logout): Users can sign out."
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
agent_commit "feat(auth): add sign-out" AC-auth-007
