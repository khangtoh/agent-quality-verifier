# title: The agent changes code without saying which requirement it serves
# expect: H2
source "$DEMO/lib.sh"
branch fix/AC-auth-001-docstring
replace src/app/auth.py "    def sign_in(self, email, password):
" "    def sign_in(self, email, password):
        \"\"\"Return a session token, or 'denied' / 'locked'.\"\"\"
"
agent_commit "docs(auth): document sign_in" ""
