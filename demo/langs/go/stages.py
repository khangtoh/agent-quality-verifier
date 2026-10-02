"""Go demo: chi router, standard testing + httptest, gotestsum JUnit, Go cover profiles."""
import os
import subprocess
import tempfile
from pathlib import Path

from ..common import aqv_config, d


def raw(text):
    """Go source kept unindented here (it's tab-indented), so only the leading newline is dropped."""
    return text.lstrip("\n")

NAME = "Go"
STACK = "Go 1.24 · chi v5 · testing + httptest · gotestsum"
JOBS = 4

AQV_CONFIG = aqv_config(["internal/", "cmd/"], ["*_test.go"], d("""
    code_exclude: ["*_test.go"]

    # Runner profile: how to run the tests and where the reports go.
    runner:
      test: "{aqv}/.tools/bin/gotestsum --junitfile {junit} --format standard-quiet -- -count=1 {extra} {filter} ./..."
      coverage: "go test -count=1 -coverpkg=./internal/... -coverprofile={lcov} {filter} ./..."
      coverage_format: gocover
      filter: "-run '(?i){id_underscore}'"
      select_nothing: "-run '^$'"
      comment_prefix: ["//", "/*", "*"]

    api:
      routes_from_code: "go run ./tools/aqvroutes"
      serve: "PORT={port} go run ./cmd/server"
      serve_timeout: 120
      capture: true

    mutation:
      family: c
      build: "go test -count=1 -run '^$' ./... > /dev/null"
      min_kill_ratio: 0.6
      max_mutants: 20
"""), size_exclude=("go.sum",))


GO_MOD = d("""
    module example.com/auth

    go 1.24

    require github.com/go-chi/chi/v5 v5.2.1
""")

# A6 adapter, vendored into the repo by the human: test helpers call aqvRecord after each request.
CAPTURE = raw('''
package api

// A6 adapter for the Agent Quality Verifier. Test helpers call aqvRecord after each
// request; when AQV_CAPTURE_OUT is set it appends the response as one JSON line,
// tagged with the running test's name.

import (
	"encoding/json"
	"os"
	"sync"
	"testing"
)

var aqvMu sync.Mutex

func aqvRecord(t *testing.T, method, path string, status int, body []byte) {
	out := os.Getenv("AQV_CAPTURE_OUT")
	if out == "" {
		return
	}
	var parsed any
	if json.Unmarshal(body, &parsed) != nil {
		parsed = string(body)
	}
	line, _ := json.Marshal(map[string]any{"test": t.Name(), "method": method, "path": path, "status": status, "body": parsed})
	aqvMu.Lock()
	defer aqvMu.Unlock()
	f, err := os.OpenFile(out, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644)
	if err != nil {
		return
	}
	defer f.Close()
	f.Write(append(line, '\\n'))
}
''')

# A5 adapter, vendored by the human: lists the routes chi actually serves.
ROUTES_TOOL = raw('''
// Command aqvroutes prints the routes the API serves, for the Agent Quality Verifier (A5).
package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strings"

	"github.com/go-chi/chi/v5"

	"example.com/auth/internal/api"
	"example.com/auth/internal/auth"
)

func main() {
	routes := []string{}
	chi.Walk(api.NewRouter(auth.WithDemoAccounts()), func(method, route string, _ http.Handler, _ ...func(http.Handler) http.Handler) error {
		routes = append(routes, method+" "+strings.TrimSuffix(route, "/*"))
		return nil
	})
	out, _ := json.Marshal(map[string][]string{"routes": routes})
	fmt.Println(string(out))
}
''')

# ---------------------------------------------------------------------------
# Code, one version per requirement
# ---------------------------------------------------------------------------

AUTH_1 = raw('''
// Package auth holds accounts and the rules for signing in.
package auth

import (
	"crypto/rand"
	"encoding/hex"
)

type Store struct {
	accounts map[string]string
}

func NewStore() *Store {
	return &Store{accounts: map[string]string{}}
}

func WithDemoAccounts() *Store {
	s := NewStore()
	s.AddAccount("ada@example.com", "correct horse")
	return s
}

func (s *Store) AddAccount(email, password string) {
	s.accounts[email] = password
}

func newToken() string {
	b := make([]byte, 16)
	rand.Read(b)
	return hex.EncodeToString(b)
}

func (s *Store) SignIn(email, password string) string {
	if stored, ok := s.accounts[email]; ok && stored == password {
		return newToken()
	}
	return "denied"
}
''')

AUTH_2 = (
    AUTH_1.replace(
        "type Store struct {\n\taccounts map[string]string\n}\n",
        "const MaxFailedAttempts = 3\n\n"
        "type Store struct {\n\taccounts map[string]string\n\tfailed   map[string]int\n\tlocked   map[string]bool\n}\n",
    )
    .replace(
        "\treturn &Store{accounts: map[string]string{}}\n",
        "\treturn &Store{accounts: map[string]string{}, failed: map[string]int{}, locked: map[string]bool{}}\n",
    )
    .replace(
        "func (s *Store) SignIn(email, password string) string {\n"
        "\tif stored, ok := s.accounts[email]; ok && stored == password {\n"
        "\t\treturn newToken()\n\t}\n",
        "func (s *Store) SignIn(email, password string) string {\n"
        "\tif s.locked[email] {\n\t\treturn \"locked\"\n\t}\n"
        "\tif stored, ok := s.accounts[email]; ok && stored == password {\n"
        "\t\ts.failed[email] = 0\n"
        "\t\treturn newToken()\n\t}\n"
        "\ts.failed[email]++\n"
        "\tif s.failed[email] >= MaxFailedAttempts {\n\t\ts.locked[email] = true\n\t}\n",
    )
)

AUTH_3 = AUTH_2.replace(
    "const MaxFailedAttempts = 3\n",
    "const MaxFailedAttempts = 3\n\nconst SessionTTLSeconds = 30 * 60\n\n"
    "// IsExpired reports whether a session last seen at lastSeen has expired at now (Unix seconds).\n"
    "func IsExpired(lastSeen, now int64) bool {\n\treturn now-lastSeen > SessionTTLSeconds\n}\n",
)

AUTH_4 = (
    AUTH_3.replace("\tlocked   map[string]bool\n}\n", "\tlocked   map[string]bool\n\n\tResetOutbox []string\n}\n")
    + "\n// RequestReset queues a reset link for email if the account exists.\n"
    "func (s *Store) RequestReset(email string) bool {\n"
    "\tif _, ok := s.accounts[email]; ok {\n"
    "\t\ts.ResetOutbox = append(s.ResetOutbox, email)\n"
    "\t\treturn true\n"
    "\t}\n"
    "\treturn false\n"
    "}\n"
)

AUTH_5 = AUTH_4.replace(
    "func (s *Store) RequestReset(email string) bool {\n"
    "\tif _, ok := s.accounts[email]; ok {\n"
    "\t\ts.ResetOutbox = append(s.ResetOutbox, email)\n"
    "\t\treturn true\n"
    "\t}\n"
    "\treturn false\n"
    "}\n",
    "func (s *Store) RequestReset(email string) {\n"
    "\tif _, ok := s.accounts[email]; ok {\n"
    "\t\ts.ResetOutbox = append(s.ResetOutbox, email)\n"
    "\t}\n"
    "}\n",
)

AUTH_6 = (
    AUTH_5.replace('import (\n\t"crypto/rand"\n\t"encoding/hex"\n)\n',
                   'import (\n\t"crypto/rand"\n\t"crypto/sha256"\n\t"encoding/hex"\n)\n')
    .replace("type Store struct {\n\taccounts map[string]string\n",
             "type credential struct {\n\tsalt   string\n\tdigest string\n}\n\n"
             "type Store struct {\n\taccounts map[string]credential\n")
    .replace("\treturn &Store{accounts: map[string]string{}, failed:",
             "\treturn &Store{accounts: map[string]credential{}, failed:")
    .replace(
        "func (s *Store) AddAccount(email, password string) {\n\ts.accounts[email] = password\n}\n",
        "// HashPassword returns the hex SHA-256 of salt+password.\n"
        "func HashPassword(password, salt string) string {\n"
        "\tsum := sha256.Sum256([]byte(salt + password))\n"
        "\treturn hex.EncodeToString(sum[:])\n}\n\n"
        "func (s *Store) AddAccount(email, password string) {\n"
        "\tsalt := make([]byte, 8)\n"
        "\trand.Read(salt)\n"
        "\tsaltHex := hex.EncodeToString(salt)\n"
        "\ts.accounts[email] = credential{salt: saltHex, digest: HashPassword(password, saltHex)}\n}\n\n"
        "func (s *Store) passwordMatches(email, password string) bool {\n"
        "\tc, ok := s.accounts[email]\n"
        "\treturn ok && HashPassword(password, c.salt) == c.digest\n}\n",
    )
    .replace("\tif stored, ok := s.accounts[email]; ok && stored == password {\n",
             "\tif s.passwordMatches(email, password) {\n")
)

API_1 = raw('''
// Package api serves the auth service over HTTP.
package api

import (
	"encoding/json"
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"

	"example.com/auth/internal/auth"
)

type credentials struct {
	Email    *string `json:"email"`
	Password *string `json:"password"`
}

func writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(body)
}

func invalid(w http.ResponseWriter) {
	writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid_request"})
}

// NewRouter returns the HTTP routes for the auth service.
func NewRouter(store *auth.Store) chi.Router {
	r := chi.NewRouter()
	r.Use(middleware.Recoverer)

	r.Post("/login", func(w http.ResponseWriter, req *http.Request) {
		var body credentials
		if json.NewDecoder(req.Body).Decode(&body) != nil || body.Email == nil || body.Password == nil {
			invalid(w)
			return
		}
		result := store.SignIn(*body.Email, *body.Password)
		if result == "denied" {
			writeJSON(w, http.StatusUnauthorized, map[string]string{"error": result})
			return
		}
		writeJSON(w, http.StatusOK, map[string]string{"token": result})
	})

	return r
}
''')

API_2 = API_1.replace('\t\tif result == "denied" {\n', '\t\tif result == "denied" || result == "locked" {\n')

API_3 = API_2.replace(
    '\t"encoding/json"\n\t"net/http"\n', '\t"encoding/json"\n\t"net/http"\n\t"strconv"\n\t"time"\n'
).replace(
    '\t\twriteJSON(w, http.StatusOK, map[string]string{"token": result})\n\t})\n',
    '\t\twriteJSON(w, http.StatusOK, map[string]string{"token": result})\n\t})\n\n'
    '\tr.Get("/session", func(w http.ResponseWriter, req *http.Request) {\n'
    '\t\tlastSeen, err := strconv.ParseInt(req.URL.Query().Get("last_seen"), 10, 64)\n'
    "\t\tif err != nil || lastSeen < 0 || lastSeen > 4102444800 {\n"
    "\t\t\tinvalid(w)\n\t\t\treturn\n\t\t}\n"
    '\t\twriteJSON(w, http.StatusOK, map[string]bool{"expired": auth.IsExpired(lastSeen, time.Now().Unix())})\n'
    "\t})\n",
)

API_4 = API_3.replace(
    '\t\twriteJSON(w, http.StatusOK, map[string]bool{"expired": auth.IsExpired(lastSeen, time.Now().Unix())})\n\t})\n',
    '\t\twriteJSON(w, http.StatusOK, map[string]bool{"expired": auth.IsExpired(lastSeen, time.Now().Unix())})\n\t})\n\n'
    '\tr.Post("/password-reset", func(w http.ResponseWriter, req *http.Request) {\n'
    "\t\tvar body struct {\n\t\t\tEmail *string `json:\"email\"`\n\t\t}\n"
    "\t\tif json.NewDecoder(req.Body).Decode(&body) != nil || body.Email == nil {\n"
    "\t\t\tinvalid(w)\n\t\t\treturn\n\t\t}\n"
    '\t\tstatus := "unknown_email"\n'
    "\t\tif store.RequestReset(*body.Email) {\n"
    '\t\t\tstatus = "sent"\n'
    "\t\t}\n"
    '\t\twriteJSON(w, http.StatusAccepted, map[string]string{"status": status})\n'
    "\t})\n",
)

API_5 = API_4.replace(
    '\t\tstatus := "unknown_email"\n'
    "\t\tif store.RequestReset(*body.Email) {\n"
    '\t\t\tstatus = "sent"\n'
    "\t\t}\n"
    '\t\twriteJSON(w, http.StatusAccepted, map[string]string{"status": status})\n',
    "\t\tstore.RequestReset(*body.Email)\n"
    '\t\twriteJSON(w, http.StatusAccepted, map[string]string{"status": "sent"})\n',
)

SERVER = raw('''
package main

import (
	"net/http"
	"os"

	"example.com/auth/internal/api"
	"example.com/auth/internal/auth"
)

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8000"
	}
	http.ListenAndServe("127.0.0.1:"+port, api.NewRouter(auth.WithDemoAccounts()))
}
''')

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

HELPERS = raw('''
package api

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"

	"example.com/auth/internal/auth"
)

type response struct {
	Status int
	Body   map[string]any
}

func setup() (*auth.Store, http.Handler) {
	store := auth.WithDemoAccounts()
	return store, NewRouter(store)
}

func do(t *testing.T, h http.Handler, method, path string, payload any) response {
	t.Helper()
	var body io.Reader
	if payload != nil {
		b, _ := json.Marshal(payload)
		body = bytes.NewReader(b)
	}
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, httptest.NewRequest(method, path, body))
	raw := rec.Body.Bytes()
	aqvRecord(t, method, path, rec.Code, raw)
	var parsed map[string]any
	json.Unmarshal(raw, &parsed)
	return response{rec.Code, parsed}
}

var good = map[string]string{"email": "ada@example.com", "password": "correct horse"}
var bad = map[string]string{"email": "ada@example.com", "password": "wrong"}
''')

TEST_LOGIN = raw('''
package api

import "testing"

func TestAC_auth_001_SignInReturnsToken(t *testing.T) {
	_, h := setup()
	r := do(t, h, "POST", "/login", good)
	token, _ := r.Body["token"].(string)
	if r.Status != 200 || len(token) != 32 {
		t.Fatalf("got %d %v", r.Status, r.Body)
	}
}

func TestAC_auth_001_WrongPasswordIsDenied(t *testing.T) {
	_, h := setup()
	r := do(t, h, "POST", "/login", bad)
	if r.Status != 401 || r.Body["error"] != "denied" {
		t.Fatalf("got %d %v", r.Status, r.Body)
	}
}

func TestAC_auth_001_MalformedRequestIsRejected(t *testing.T) {
	_, h := setup()
	r := do(t, h, "POST", "/login", map[string]string{"email": "ada@example.com"})
	if r.Status != 400 || r.Body["error"] != "invalid_request" {
		t.Fatalf("got %d %v", r.Status, r.Body)
	}
}
''')

TEST_LOCKOUT = raw('''
package api

import (
	"net/http"
	"testing"
)

func fail(t *testing.T, h http.Handler, times int) {
	for i := 0; i < times; i++ {
		do(t, h, "POST", "/login", bad)
	}
}

func TestAC_auth_002_LocksAfterThreeFailures(t *testing.T) {
	_, h := setup()
	fail(t, h, 3)
	r := do(t, h, "POST", "/login", good)
	if r.Status != 401 || r.Body["error"] != "locked" {
		t.Fatalf("got %d %v", r.Status, r.Body)
	}
}

func TestAC_auth_002_TwoFailuresDoNotLock(t *testing.T) {
	_, h := setup()
	fail(t, h, 2)
	if r := do(t, h, "POST", "/login", good); r.Status != 200 {
		t.Fatalf("got %d %v", r.Status, r.Body)
	}
}

func TestAC_auth_002_SuccessResetsTheCount(t *testing.T) {
	_, h := setup()
	fail(t, h, 2)
	do(t, h, "POST", "/login", good)
	fail(t, h, 2)
	if r := do(t, h, "POST", "/login", good); r.Status != 200 {
		t.Fatalf("got %d %v", r.Status, r.Body)
	}
}
''')

TEST_SESSION_API = raw('''
package api

import (
	"fmt"
	"testing"
	"time"
)

func sessionPath(lastSeen any) string {
	return fmt.Sprintf("/session?last_seen=%v", lastSeen)
}

func TestAC_auth_003_ExpiredAfter30Minutes(t *testing.T) {
	_, h := setup()
	r := do(t, h, "GET", sessionPath(time.Now().Unix()-31*60), nil)
	if r.Status != 200 || r.Body["expired"] != true {
		t.Fatalf("got %d %v", r.Status, r.Body)
	}
}

func TestAC_auth_003_ActiveWithin30Minutes(t *testing.T) {
	_, h := setup()
	r := do(t, h, "GET", sessionPath(time.Now().Unix()-29*60), nil)
	if r.Status != 200 || r.Body["expired"] != false {
		t.Fatalf("got %d %v", r.Status, r.Body)
	}
}

func TestAC_auth_003_RejectsBadLastSeenAndAcceptsEdges(t *testing.T) {
	_, h := setup()
	for _, v := range []any{"soon", -1, 4102444801} {
		if r := do(t, h, "GET", sessionPath(v), nil); r.Status != 400 || r.Body["error"] != "invalid_request" {
			t.Fatalf("%v: got %d %v", v, r.Status, r.Body)
		}
	}
	for _, v := range []any{0, 4102444800} {
		if r := do(t, h, "GET", sessionPath(v), nil); r.Status != 200 {
			t.Fatalf("%v: got %d %v", v, r.Status, r.Body)
		}
	}
}
''')

TEST_SESSION_AUTH = raw('''
package auth

import "testing"

func TestAC_auth_003_BoundaryIsExactly30Minutes(t *testing.T) {
	if IsExpired(0, 30*60) || !IsExpired(0, 30*60+1) {
		t.Fatal("the session should expire after exactly 30 minutes")
	}
}
''')

TEST_RESET_4 = raw('''
package api

import (
	"reflect"
	"testing"
)

func TestAC_auth_004_LinkSentForKnownEmail(t *testing.T) {
	store, h := setup()
	r := do(t, h, "POST", "/password-reset", map[string]string{"email": "ada@example.com"})
	if r.Status != 202 || !reflect.DeepEqual(store.ResetOutbox, []string{"ada@example.com"}) {
		t.Fatalf("got %d %v outbox %v", r.Status, r.Body, store.ResetOutbox)
	}
}

func TestAC_auth_004_NoLinkForUnknownEmail(t *testing.T) {
	store, h := setup()
	do(t, h, "POST", "/password-reset", map[string]string{"email": "nobody@example.com"})
	if len(store.ResetOutbox) != 0 {
		t.Fatalf("outbox %v", store.ResetOutbox)
	}
}
''')

TEST_RESET_5 = TEST_RESET_4 + raw('''

func TestAC_auth_005_SameResponseForUnknownEmail(t *testing.T) {
	_, h := setup()
	known := do(t, h, "POST", "/password-reset", map[string]string{"email": "ada@example.com"})
	unknown := do(t, h, "POST", "/password-reset", map[string]string{"email": "nobody@example.com"})
	if known.Status != 202 || unknown.Status != 202 || known.Body["status"] != "sent" || !reflect.DeepEqual(known.Body, unknown.Body) {
		t.Fatalf("known %d %v, unknown %d %v", known.Status, known.Body, unknown.Status, unknown.Body)
	}
}

func TestAC_auth_005_KnownEmailStillGetsItsLink(t *testing.T) {
	store, h := setup()
	do(t, h, "POST", "/password-reset", map[string]string{"email": "nobody@example.com"})
	do(t, h, "POST", "/password-reset", map[string]string{"email": "ada@example.com"})
	if !reflect.DeepEqual(store.ResetOutbox, []string{"ada@example.com"}) {
		t.Fatalf("outbox %v", store.ResetOutbox)
	}
}
''')

TEST_STORAGE = raw('''
package auth

import "testing"

func TestAC_auth_006_PasswordNotStoredInPlainText(t *testing.T) {
	s := NewStore()
	s.AddAccount("bo@example.com", "s3cret")
	c := s.accounts["bo@example.com"]
	if c.salt == "s3cret" || c.digest == "s3cret" || c.digest != HashPassword("s3cret", c.salt) {
		t.Fatalf("stored %+v", c)
	}
}

func TestAC_auth_006_HashedPasswordStillSignsIn(t *testing.T) {
	s := NewStore()
	s.AddAccount("bo@example.com", "s3cret")
	if got := s.SignIn("bo@example.com", "s3cret"); got == "denied" || got == "locked" {
		t.Fatalf("right password: %s", got)
	}
	if got := s.SignIn("bo@example.com", "nope"); got != "denied" {
		t.Fatalf("wrong password: %s", got)
	}
}

func TestAC_auth_006_SamePasswordGetsDifferentSalts(t *testing.T) {
	s := NewStore()
	s.AddAccount("a@example.com", "s3cret")
	s.AddAccount("b@example.com", "s3cret")
	if s.accounts["a@example.com"].salt == s.accounts["b@example.com"].salt {
		t.Fatal("two accounts got the same salt")
	}
}
''')

# ---------------------------------------------------------------------------
# What the builder needs
# ---------------------------------------------------------------------------

GITIGNORE = ".aqv-out/\n*.out\n"


def go_sum():
    """go.sum for GO_MOD, computed once so the scaffold commit is complete."""
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "go.mod").write_text(GO_MOD)
        Path(tmp, "main.go").write_text('package main\n\nimport _ "github.com/go-chi/chi/v5"\n\nfunc main() {}\n')
        subprocess.run(["go", "mod", "download", "github.com/go-chi/chi/v5"], cwd=tmp, check=True, capture_output=True)
        subprocess.run(["go", "mod", "tidy"], cwd=tmp, check=True, capture_output=True)
        return Path(tmp, "go.sum").read_text()


def SCAFFOLD():
    return {"go.mod": GO_MOD, "go.sum": go_sum(), ".aqv.yml": AQV_CONFIG,
            "internal/api/aqv_capture_test.go": CAPTURE, "tools/aqvroutes/main.go": ROUTES_TOOL}


CODE = {
    "AC-auth-001": {"internal/auth/auth.go": AUTH_1, "internal/api/api.go": API_1, "cmd/server/main.go": SERVER,
                    "internal/api/helpers_test.go": HELPERS, "internal/api/login_test.go": TEST_LOGIN},
    "AC-auth-002": {"internal/auth/auth.go": AUTH_2, "internal/api/api.go": API_2,
                    "internal/api/lockout_test.go": TEST_LOCKOUT},
    "AC-auth-003": {"internal/auth/auth.go": AUTH_3, "internal/api/api.go": API_3,
                    "internal/api/session_test.go": TEST_SESSION_API, "internal/auth/session_test.go": TEST_SESSION_AUTH},
    "AC-auth-004": {"internal/auth/auth.go": AUTH_4, "internal/api/api.go": API_4,
                    "internal/api/reset_test.go": TEST_RESET_4},
    "AC-auth-005": {"internal/auth/auth.go": AUTH_5, "internal/api/api.go": API_5,
                    "internal/api/reset_test.go": TEST_RESET_5},
    "AC-auth-006": {"internal/auth/auth.go": AUTH_6, "internal/auth/storage_test.go": TEST_STORAGE},
}

MECHANISMS = {
    "T5": "gotestsum --junitfile",
    "T6": "go test -run per requirement, Go cover profile",
    "T7": "Built-in line mutator; go test compile check",
    "A5": "chi.Walk route list (vendored command)",
    "A6": "Test helper records each httptest response (vendored)",
    "A7": "go run server + Schemathesis",
}


def prepare(repo, shared):
    subprocess.run(["go", "mod", "download"], cwd=repo, check=True, capture_output=True)
