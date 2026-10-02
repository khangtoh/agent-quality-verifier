# title: The agent renames token to access_token in contract, code and tests; the spec didn't change
# expect: A4
source "$DEMO/lib.sh"
branch feat/AC-auth-001-access-token
python3 - <<'PY'
p = "contracts/openapi.yaml"
s = open(p).read()
s = s.replace("required: [token]", "required: [access_token]").replace("        token: {type: string}", "        access_token: {type: string}")
open(p, "w").write(s)
PY
agent_commit "feat(contract): rename token to access_token" AC-auth-001
e_rename_token
agent_commit "feat(auth): return access_token" AC-auth-001
