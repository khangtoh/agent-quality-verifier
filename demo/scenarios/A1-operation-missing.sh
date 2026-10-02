# title: A sign-out requirement is implemented without adding it to the contract
# expect: A1
source "$DEMO/lib.sh"
branch feat/AC-auth-007-sign-out
add_requirement "- **AC-auth-007** (api: POST /logout): Users can sign out."
e_logout_route_and_test
agent_commit "feat(auth): add sign-out" AC-auth-007
