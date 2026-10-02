# title: The agent renames something the tests depend on but doesn't update the tests, so the suite can't load
# expect: T5
source "$DEMO/lib.sh"
branch fix/AC-auth-003-rename-expiry-check
e_rename_expiry_src_only
agent_commit "fix(auth): clearer name for the session expiry check" AC-auth-003
