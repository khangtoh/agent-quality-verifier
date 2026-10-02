# title: Clean PR: a human adds AC-auth-007, the agent implements it properly
# expect: none
source "$DEMO/lib.sh"
branch feat/AC-auth-007-password-length
add_requirement "$REQ_007"
e_impl_007
e_tests_007
agent_commit "feat(auth): reject passwords shorter than 6 characters" AC-auth-007
