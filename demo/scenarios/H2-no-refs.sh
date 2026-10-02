# title: The agent changes code without saying which requirement it serves
# expect: H2
source "$DEMO/lib.sh"
branch fix/AC-auth-001-docstring
e_doc_comment
agent_commit "docs(auth): document sign_in" ""
