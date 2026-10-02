# title: Lockout switches to HTTP 423 and the test is updated to match; the contract isn't
# expect: A6
source "$DEMO/lib.sh"
branch fix/AC-auth-002-use-423
replace src/app/main.py '            return JSONResponse({"error": result}, status_code=401)' '            return JSONResponse({"error": result}, status_code=423 if result == "locked" else 401)'
replace tests/test_lockout.py '    assert r.status_code == 401
    assert r.json() == {"error": "locked"}' '    assert r.status_code == 423
    assert r.json() == {"error": "locked"}'
agent_commit "fix(auth): use 423 for locked accounts" AC-auth-002
