# title: The agent changes the lockout threshold to 4; the lockout tests now fail
# expect: T5
source "$DEMO/lib.sh"
branch fix/AC-auth-002-lockout-threshold
replace src/app/auth.py "MAX_FAILED_ATTEMPTS = 3" "MAX_FAILED_ATTEMPTS = 4"
agent_commit "fix(auth): allow one more sign-in attempt" AC-auth-002
