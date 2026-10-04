#!/usr/bin/env bash
# Runs every Go/Python parity check, cheapest first. See docs/go-demo-parity.md.
#
#   scripts/parity_all.sh             helpers, page writers, published page sets (a minute or two)
#   scripts/parity_all.sh --engine    also reruns the Go verifier on all 168 demo repos (about an hour)
#
# Needs bin/aqv (go build -o bin/aqv ./cmd/aqv), .venv, and demo/.work and demo/.work-go from earlier demo runs.
set -euo pipefail
cd "$(dirname "$0")/.."
step() { printf '\n== %s\n' "$1"; }

step "1. Helpers: Go against the Python answers recorded in internal/aqv/testdata"
GOTOOLCHAIN=local go test ./internal/...

step "2. Page writers: Go and Python render the Go demo run to identical pages"
.venv/bin/python scripts/pages_parity.py

step "3. Published pages: demo/results (Python run) against demo/results-go (Go run)"
.venv/bin/python scripts/demo_parity.py

if [ "${1:-}" = "--engine" ]; then
  step "4. Engine: the Go verifier on the 168 demo repos against the Python results"
  .venv/bin/python scripts/parity.py --lang all
fi
printf '\nAll parity checks passed.\n'
