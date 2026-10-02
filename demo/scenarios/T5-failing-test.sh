# title: The agent changes the lockout threshold to 4; the lockout tests now fail
# expect: T5
source "$DEMO/lib.sh"
branch fix/AC-auth-002-lockout-threshold
e_threshold_4
agent_commit "fix(auth): allow one more sign-in attempt" AC-auth-002
