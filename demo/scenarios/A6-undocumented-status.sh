# title: Lockout switches to HTTP 423 and the test is updated to match; the contract isn't
# expect: A6
source "$DEMO/lib.sh"
branch fix/AC-auth-002-use-423
e_status_423
agent_commit "fix(auth): use 423 for locked accounts" AC-auth-002
