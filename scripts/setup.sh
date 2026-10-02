#!/usr/bin/env bash
# Installs the verifier's own dependencies: Python packages in .venv, Spectral (Node),
# oasdiff and gotestsum (Go) in .tools. Needs Python 3.11+, Node 18+, Go 1.22+ and gpg.
#
# Each demo language also needs its own toolchain:
#   JavaScript, TypeScript  Node 18+ (npm installs the rest)
#   Go                      Go 1.22+
#   Rust                    rustup, cargo-nextest, cargo-llvm-cov, llvm-tools-preview
#   Kotlin                  JDK 21 and Gradle 8
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
mkdir -p .tools
npm install --silent --prefix .tools @stoplight/spectral-cli@6
GOBIN="$PWD/.tools/bin" go install github.com/oasdiff/oasdiff@v1.33.0
GOBIN="$PWD/.tools/bin" go install gotest.tools/gotestsum@v1.12.3
if [ "${WITH_RUST:-0}" = 1 ]; then
  rustup component add llvm-tools-preview
  cargo install --locked cargo-nextest cargo-llvm-cov
fi
echo "Ready. Run: .venv/bin/python demo/run_demo.py --lang all"
