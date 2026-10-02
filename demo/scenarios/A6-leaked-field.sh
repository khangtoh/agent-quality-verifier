# title: The login response leaks a debug_password field; tests still pass
# expect: A6
source "$DEMO/lib.sh"
branch feat/AC-auth-001-debug-info
replace src/app/main.py 'return {"token": result}' 'return {"token": result, "debug_password": body.password}'
agent_commit "feat(auth): add debug info to sign-in" AC-auth-001
