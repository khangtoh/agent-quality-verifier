# title: The agent adds a requirement that reuses the ID AC-auth-006
# expect: T1
source "$DEMO/lib.sh"
branch docs/AC-auth-006-password-length
printf '%s\n' "- **AC-auth-006**: Passwords are at least 6 characters long." >> specs/auth.md
agent_commit "docs(spec): add password length rule" AC-auth-006
