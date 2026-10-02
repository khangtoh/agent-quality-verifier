# title: The agent adds DELETE /session to the contract without naming a requirement
# expect: A2
source "$DEMO/lib.sh"
branch feat/AC-auth-003-end-session
replace contracts/openapi.yaml "  /password-reset:
" "    delete:
      operationId: endSession
      summary: End a session
      description: End the current session.
      tags: [auth]
      responses:
        \"204\":
          description: Session ended
  /password-reset:
"
agent_commit "feat(contract): document ending a session" ""
