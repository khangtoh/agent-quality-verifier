# title: The agent ships GET /debug/users, which isn't in the contract
# expect: A5
source "$DEMO/lib.sh"
branch feat/AC-auth-001-debug-users
e_debug_route
agent_commit "feat(auth): add a debug endpoint" AC-auth-001
