//go:build aqvtools

// Command aqvschema builds a fresh database at the given path the way the service does (every
// migration, in order), for the Agent Quality Verifier (D5, D6). The verifier then reads the
// schema back from that file.
package main

import (
	"fmt"
	"os"

	"example.com/ledger/internal/store"
)

func main() {
	if len(os.Args) != 2 {
		fmt.Fprintln(os.Stderr, "usage: aqvschema DATABASE")
		os.Exit(2)
	}
	db, err := store.Open(os.Args[1])
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	if err := db.Close(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
