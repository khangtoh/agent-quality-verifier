# title: The agent adds a 600-line file in one commit
# expect: H5
source "$DEMO/lib.sh"
branch feat/AC-auth-004-blocked-domains
python3 - <<'PY'
lines = ['"""Email domains that never receive reset links."""', "BLOCKED_DOMAINS = {"]
lines += [f'    "blocked-{i}.example",' for i in range(600)]
lines += ["}"]
open("src/app/blocked_domains.py", "w").write("\n".join(lines) + "\n")
PY
agent_commit "feat(auth): add a blocked domain list" AC-auth-004
