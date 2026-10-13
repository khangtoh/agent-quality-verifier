package aqvcapture

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
)

func TestDoRecordsTheResponse(t *testing.T) {
	out := filepath.Join(t.TempDir(), "capture.jsonl")
	t.Setenv("AQV_CAPTURE_OUT", out)
	h := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusCreated)
		w.Write([]byte(`{"id":7}`))
	})
	rec := Do(t, h, httptest.NewRequest("POST", "/todos?dry=1", nil))
	if rec.Code != http.StatusCreated {
		t.Fatalf("got %d", rec.Code)
	}
	data, err := os.ReadFile(out)
	if err != nil {
		t.Fatal(err)
	}
	var got struct {
		Test, Method, Path string
		Status             int
		Body               map[string]any
	}
	if err := json.Unmarshal(data, &got); err != nil {
		t.Fatalf("%v in %q", err, data)
	}
	if got.Test != t.Name() || got.Method != "POST" || got.Path != "/todos" || got.Status != 201 || got.Body["id"] != float64(7) {
		t.Fatalf("got %+v", got)
	}
}

func TestRecordWritesNothingOutsideTheVerifier(t *testing.T) {
	t.Setenv("AQV_CAPTURE_OUT", "")
	Record(t, "GET", "/todos", 200, nil)
}
