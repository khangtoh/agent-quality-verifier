# title: Password reset crashes on emails without "@"; the tagged tests only use valid emails
# expect: A7
source "$DEMO/lib.sh"
branch feat/AC-auth-004-reset-domain
e_reset_crash
agent_commit "feat(auth): read the email domain on reset requests" AC-auth-004
