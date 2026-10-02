# title: The agent adds a 600-line file in one commit
# expect: H5
source "$DEMO/lib.sh"
branch feat/AC-auth-004-blocked-domains
e_big_file
agent_commit "feat(auth): add a blocked domain list" AC-auth-004
