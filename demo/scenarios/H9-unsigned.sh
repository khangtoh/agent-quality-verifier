# title: The agent makes an unsigned commit
# expect: H9
source "$DEMO/lib.sh"
branch docs/AC-auth-001-readme
printf '\nRun the tests with `pytest`.\n' >> README.md
as_agent
git add -A
git -c commit.gpgsign=false commit -q -m "docs: explain how to run the tests" --trailer "Refs: AC-auth-001" --trailer "$AGENT_TRAILER"
