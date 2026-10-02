#!/usr/bin/env bash
# Installs the verifier's dependencies: Python packages in .venv, Spectral (Node)
# and oasdiff (Go) in .tools. Needs Python 3.11+, Node 18+, Go 1.22+ and gpg.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
mkdir -p .tools
npm install --silent --prefix .tools @stoplight/spectral-cli@6
GOBIN="$PWD/.tools/bin" go install github.com/oasdiff/oasdiff@v1.33.0
echo "Ready. Run: .venv/bin/python demo/run_demo.py"
