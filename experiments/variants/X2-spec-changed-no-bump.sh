# title: Isolates T8: the spec wording changes and nobody bumps the OFT revision
# expect: T8
source "$DEMO/lib.sh"
branch docs/AC-auth-002-raise-threshold
replace specs/auth.md "lock after 3 consecutive" "lock after 5 consecutive"
human_commit "docs(spec): raise the lockout threshold to 5 attempts"
