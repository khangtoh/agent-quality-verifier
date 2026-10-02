# title: One code commit claims two requirements
# expect: H3
source "$DEMO/lib.sh"
branch fix/AC-auth-001-docstrings
replace src/app/auth.py "    def sign_in(self, email, password):
" "    def sign_in(self, email, password):
        \"\"\"Return a session token, or 'denied' / 'locked'.\"\"\"
"
agent_commit "docs(auth): document sign-in and lockout" "AC-auth-001, AC-auth-002"
