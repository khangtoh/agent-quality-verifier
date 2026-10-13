// Package aqvcapture records the HTTP responses a test sees, for the Agent Quality Verifier (A6).
//
// When AQV_CAPTURE_OUT is set, each response is appended to that file as one JSON line, tagged with
// the running test's name. Otherwise nothing is written, so tests behave the same outside the verifier.
package aqvcapture

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"sync"
	"testing"
)

var mu sync.Mutex

// Do sends req to h, records the response and returns it.
func Do(t testing.TB, h http.Handler, req *http.Request) *httptest.ResponseRecorder {
	t.Helper()
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	Record(t, req.Method, req.URL.Path, rec.Code, rec.Body.Bytes())
	return rec
}

// Record notes one response, for tests that reach the service some other way than Do.
func Record(t testing.TB, method, path string, status int, body []byte) {
	out := os.Getenv("AQV_CAPTURE_OUT")
	if out == "" {
		return
	}
	var parsed any
	if json.Unmarshal(body, &parsed) != nil {
		parsed = string(body)
	}
	line, _ := json.Marshal(map[string]any{"test": t.Name(), "method": method, "path": path, "status": status, "body": parsed})
	mu.Lock()
	defer mu.Unlock()
	f, err := os.OpenFile(out, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644)
	if err != nil {
		return
	}
	defer f.Close()
	f.Write(append(line, '\n'))
}
