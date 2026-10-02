# title: The last verified commit on main is amended, rewriting main's history
# expect: H7
source "$DEMO/lib.sh"
as_human
git commit -q --amend -m "Merge branch 'feat/AC-auth-006-hash-passwords' (amended)"
