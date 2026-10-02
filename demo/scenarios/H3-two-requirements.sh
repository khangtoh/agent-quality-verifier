# title: One code commit claims two requirements
# expect: H3
source "$DEMO/lib.sh"
branch fix/AC-auth-001-docstrings
e_doc_comment
agent_commit "docs(auth): document sign-in and lockout" "AC-auth-001, AC-auth-002"
