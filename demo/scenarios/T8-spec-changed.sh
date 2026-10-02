# title: Product changes the lockout rule from 3 to 5 attempts; no code changes
# expect: T8
source "$DEMO/lib.sh"
branch docs/AC-auth-002-raise-threshold
replace specs/auth.md "lock after 3 consecutive" "lock after 5 consecutive"
human_commit "docs(spec): raise the lockout threshold to 5 attempts"
