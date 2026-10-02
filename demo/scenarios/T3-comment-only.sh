# title: The agent cites AC-auth-007 but its commit only adds a comment
# expect: T3
source "$DEMO/lib.sh"
branch feat/AC-auth-007-password-length
add_requirement "$REQ_007"
replace src/app/auth.py "    def add_account(self, email, password):
" "    def add_account(self, email, password):
        # TODO: enforce the minimum password length
"
agent_commit "feat(auth): enforce minimum password length" AC-auth-007
