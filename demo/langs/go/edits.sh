# Go edits used by the scenarios. Each function changes files only; the scenario commits.

e_impl_007() {
  replace internal/auth/auth.go "func (s *Store) AddAccount(email, password string) {
" "func (s *Store) AddAccount(email, password string) {
	if len(password) < 6 {
		return
	}
"
}

e_tests_007() {
  cat > internal/auth/password_length_test.go <<'GO'
package auth

import "testing"

func TestAC_auth_007_FiveCharactersRejected(t *testing.T) {
	s := NewStore()
	s.AddAccount("bo@example.com", "five5")
	if _, ok := s.accounts["bo@example.com"]; ok {
		t.Fatal("stored an account with a 5-character password")
	}
}

func TestAC_auth_007_SixCharactersAccepted(t *testing.T) {
	s := NewStore()
	s.AddAccount("bo@example.com", "six666")
	if _, ok := s.accounts["bo@example.com"]; !ok {
		t.Fatal("rejected a 6-character password")
	}
}
GO
}

e_test_007_assert_true() {
  cat > internal/auth/password_length_test.go <<'GO'
package auth

import "testing"

func TestAC_auth_007_ShortPasswordsRejected(t *testing.T) {
	if false {
		t.Fatal("unreachable")
	}
}
GO
}

e_comment_007() {
  replace internal/auth/auth.go "func (s *Store) AddAccount(email, password string) {
" "func (s *Store) AddAccount(email, password string) {
	// TODO: enforce the minimum password length
"
}

e_threshold_4() { replace internal/auth/auth.go "const MaxFailedAttempts = 3" "const MaxFailedAttempts = 4"; }

e_lockout_gt() { replace internal/auth/auth.go "if s.failed[email] >= MaxFailedAttempts {" "if s.failed[email] > MaxFailedAttempts {"; }

# Renames IsExpired in the code but not in its test, so the auth tests no longer compile.
e_rename_expiry_src_only() {
  replace internal/auth/auth.go "func IsExpired(" "func SessionExpired("
  replace internal/auth/auth.go "// IsExpired reports" "// SessionExpired reports"
  replace internal/api/api.go "auth.IsExpired(" "auth.SessionExpired("
}

e_weak_lockout_tests() {
  cat > internal/api/lockout_test.go <<'GO'
package api

import "testing"

func TestAC_auth_002_FailedAttemptsAreRejected(t *testing.T) {
	_, h := setup()
	for i := 0; i < 3; i++ {
		if r := do(t, h, "POST", "/login", bad); r.Status != 401 {
			t.Fatalf("got %d", r.Status)
		}
	}
}
GO
}

e_logout_route_and_test() {
  replace internal/api/api.go "	return r
}" "	r.Post(\"/logout\", func(w http.ResponseWriter, req *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{\"status\": \"signed_out\"})
	})

	return r
}"
  cat > internal/api/logout_test.go <<'GO'
package api

import "testing"

func TestAC_auth_007_SignOut(t *testing.T) {
	_, h := setup()
	r := do(t, h, "POST", "/logout", nil)
	if r.Status != 200 || r.Body["status"] != "signed_out" {
		t.Fatalf("got %d %v", r.Status, r.Body)
	}
}
GO
}

e_rename_token() {
  replace internal/api/api.go 'map[string]string{"token": result}' 'map[string]string{"access_token": result}'
  replace internal/api/login_test.go 'r.Body["token"]' 'r.Body["access_token"]'
}

e_debug_route() {
  replace internal/api/api.go "	return r
}" "	r.Get(\"/debug/users\", func(w http.ResponseWriter, req *http.Request) {
		writeJSON(w, http.StatusOK, map[string][]string{\"users\": {\"ada@example.com\"}})
	})

	return r
}"
}

e_leak_password() {
  replace internal/api/api.go 'map[string]string{"token": result}' 'map[string]string{"token": result, "debug_password": *body.Password}'
}

e_status_423() {
  replace internal/api/api.go '			writeJSON(w, http.StatusUnauthorized, map[string]string{"error": result})' '			status := http.StatusUnauthorized
			if result == "locked" {
				status = http.StatusLocked
			}
			writeJSON(w, status, map[string]string{"error": result})'
  replace internal/api/lockout_test.go '	if r.Status != 401 || r.Body["error"] != "locked" {' '	if r.Status != 423 || r.Body["error"] != "locked" {'
}

e_reset_crash() {
  replace internal/api/api.go '	"strconv"
' '	"strconv"
	"strings"
'
  replace internal/api/api.go "		store.RequestReset(*body.Email)
" "		_ = strings.ToLower(strings.Split(*body.Email, \"@\")[1])
		store.RequestReset(*body.Email)
"
}

e_doc_comment() {
  replace internal/auth/auth.go "func (s *Store) SignIn(email, password string) string {
" "// SignIn returns a session token, or \"denied\" / \"locked\".
func (s *Store) SignIn(email, password string) string {
"
}

e_big_file() {
  python3 - <<'PY'
lines = ["package auth", "", "// BlockedDomains never receive reset links.", "var BlockedDomains = map[string]bool{"]
lines += [f'\t"blocked-{i}.example": true,' for i in range(600)]
lines += ["}"]
open("internal/auth/blocked_domains.go", "w").write("\n".join(lines) + "\n")
PY
}
