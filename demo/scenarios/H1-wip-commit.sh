# title: The agent commits with the subject "wip"
# expect: H1
source "$DEMO/lib.sh"
branch docs/AC-auth-001-readme
printf '\nRun the tests with `pytest`.\n' >> README.md
agent_commit "wip" AC-auth-001
