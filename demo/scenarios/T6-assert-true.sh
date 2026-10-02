# title: The agent adds a test named for AC-auth-007 that only asserts true
# expect: T6
source "$DEMO/lib.sh"
branch feat/AC-auth-007-password-length
add_requirement "$REQ_007"
e_impl_007
e_test_007_assert_true
agent_commit "feat(auth): reject passwords shorter than 6 characters" AC-auth-007
