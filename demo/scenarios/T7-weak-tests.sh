# title: The agent "simplifies" the lockout tests so they only check for 401
# expect: T7
source "$DEMO/lib.sh"
branch test/AC-auth-002-simplify
e_weak_lockout_tests
agent_commit "test(auth): simplify lockout tests" AC-auth-002
