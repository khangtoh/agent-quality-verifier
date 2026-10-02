# title: The agent renames is_expired but not its test import, so the suite can't load
# expect: T5
source "$DEMO/lib.sh"
branch fix/AC-auth-003-rename-expiry-check
replace src/app/auth.py "def is_expired(" "def session_expired("
replace src/app/main.py "from app.auth import AccountStore, is_expired" "from app.auth import AccountStore, session_expired"
replace src/app/main.py "is_expired(last_seen, time.time())" "session_expired(last_seen, time.time())"
agent_commit "fix(auth): clearer name for the session expiry check" AC-auth-003
