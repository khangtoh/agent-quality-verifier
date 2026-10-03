# title: Isolates T3: the implementation is a comment and the tagged test is assert True
# expect: T3
source "$DEMO/lib.sh"
branch feat/AC-auth-007-password-length
add_requirement "$REQ_007"
e_comment_007
e_test_007_assert_true
agent_commit "feat(auth): enforce minimum password length" AC-auth-007
