# title: The agent loosens the session response schema
# expect: A3
source "$DEMO/lib.sh"
branch feat/AC-auth-003-relax-schema
python3 - <<'PY'
p = "contracts/openapi.yaml"
s = open(p).read()
old = "    SessionState:\n      type: object\n      required: [expired]\n      additionalProperties: false\n"
assert old in s
open(p, "w").write(s.replace(old, "    SessionState:\n      type: object\n      required: [expired]\n"))
PY
agent_commit "feat(contract): relax the session response schema" AC-auth-003
