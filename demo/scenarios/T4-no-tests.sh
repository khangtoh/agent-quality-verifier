# title: The agent implements AC-auth-007 without any tests
# expect: T4
source "$DEMO/lib.sh"
branch feat/AC-auth-007-password-length
add_requirement "$REQ_007"
e_impl_007
agent_commit "feat(auth): reject passwords shorter than 6 characters" AC-auth-007
