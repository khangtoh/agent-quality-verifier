# Helpers sourced by every scenario. Each scenario runs inside its own copy of the
# baseline repo, starting on main, and leaves the branch it built checked out.
set -euo pipefail

AGENT_TRAILER="Co-Authored-By: Claude <noreply@anthropic.com>"

as_agent() {
  export GIT_AUTHOR_NAME=dev-agent GIT_AUTHOR_EMAIL=agent@example.com
  export GIT_COMMITTER_NAME=dev-agent GIT_COMMITTER_EMAIL=agent@example.com
}

as_human() {
  export GIT_AUTHOR_NAME="Pat Product" GIT_AUTHOR_EMAIL=pat@example.com
  export GIT_COMMITTER_NAME="Pat Product" GIT_COMMITTER_EMAIL=pat@example.com
}

branch() { git checkout -q -b "$1"; }

# agent_commit "subject" "AC-x-nnn"   (pass "" for no Refs trailer)
agent_commit() {
  as_agent
  git add -A
  local args=(-q -m "$1")
  if [ -n "${2:-}" ]; then args+=(--trailer "Refs: $2"); fi
  args+=(--trailer "$AGENT_TRAILER")
  git commit "${args[@]}"
}

human_commit() {
  as_human
  git add -A
  git commit -q -m "$1"
}

# replace FILE OLD NEW: exact, single replacement; fails loudly if OLD is missing.
replace() {
  python3 - "$1" "$2" "$3" <<'PY'
import sys
path, old, new = sys.argv[1:]
text = open(path).read()
assert old in text, f"{path}: text to replace not found: {old!r}"
open(path, "w").write(text.replace(old, new, 1))
PY
}

# add_requirement LINE: a human adds a requirement line and registers its ID.
add_requirement() {
  local line="$1" id
  id=$(python3 -c 'import re,sys; print(re.search(r"\*\*([^*]+)\*\*", sys.argv[1]).group(1))' "$line")
  printf '%s\n' "$line" >> specs/auth.md
  printf '%s\n' "$id" >> specs/.ids
  human_commit "docs(spec): add $id"
}

REQ_007="- **AC-auth-007**: Accounts cannot be created with a password shorter than 6 characters."

# Language-specific edits: e_impl_007, e_threshold_4, e_debug_route and the rest.
source "$DEMO/langs/${AQV_LANG:-python}/edits.sh"
