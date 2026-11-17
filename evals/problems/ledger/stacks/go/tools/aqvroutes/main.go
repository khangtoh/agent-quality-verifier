//go:build aqvtools

// Command aqvroutes prints the routes the API serves, for the Agent Quality Verifier (A5).
// It is built only with -tags aqvtools, so it does not break the build before the service exists.
package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strings"

	"github.com/go-chi/chi/v5"

	"example.com/ledger/internal/api"
	"example.com/ledger/internal/store"
)

func main() {
	dir, err := os.MkdirTemp("", "aqvroutes-")
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	defer os.RemoveAll(dir)
	db, err := store.Open(filepath.Join(dir, "ledger.db"))
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	defer db.Close()
	routes := []string{}
	chi.Walk(api.NewRouter(db), func(method, route string, _ http.Handler, _ ...func(http.Handler) http.Handler) error {
		if route != "/" {
			route = strings.TrimSuffix(strings.TrimSuffix(route, "/*"), "/")
		}
		routes = append(routes, method+" "+route)
		return nil
	})
	out, _ := json.Marshal(map[string][]string{"routes": routes})
	fmt.Println(string(out))
}
