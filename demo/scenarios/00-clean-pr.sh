# title: Clean PR: a human adds AC-auth-007, the agent implements it properly
# expect: none
source "$DEMO/lib.sh"
branch feat/AC-auth-007-password-length
add_requirement "$REQ_007"
implement_007_code
implement_007_tests
agent_commit "feat(auth): reject passwords shorter than 6 characters" AC-auth-007
