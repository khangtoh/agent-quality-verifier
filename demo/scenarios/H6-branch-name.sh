# title: The agent works on a branch called quick-fix
# expect: H6
source "$DEMO/lib.sh"
branch quick-fix
printf '\nRun the tests with `pytest`.\n' >> README.md
agent_commit "docs: explain how to run the tests" AC-auth-001
