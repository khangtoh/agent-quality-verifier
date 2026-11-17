#!/usr/bin/env bash
# Builds the verifier (bin/aqv) and installs the tools its checks use: Python packages in
# .venv (Schemathesis, and the Python reference implementation), Spectral (Node), oasdiff and
# gotestsum (Go) in .tools. Needs Go 1.24+, Python 3.11+, Node 18+ and gpg.
#
# Each demo language also needs its own toolchain:
#   JavaScript, TypeScript  Node 18+ (npm installs the rest)
#   Go                      Go 1.22+
#   Rust                    cargo-nextest, cargo-llvm-cov, and llvm-cov + llvm-profdata: rustup's
#                           llvm-tools-preview, or the LLVM a packaged Rust was built with
#                           (evals/run.py finds Homebrew's; otherwise set LLVM_COV and LLVM_PROFDATA)
#   Kotlin                  JDK 21 and Gradle 8
set -euo pipefail
cd "$(dirname "$0")/.."
GOTOOLCHAIN=local go build -o bin/aqv ./cmd/aqv
python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
mkdir -p .tools
npm install --silent --prefix .tools @stoplight/spectral-cli@6
GOBIN="$PWD/.tools/bin" go install github.com/oasdiff/oasdiff@v1.33.0
GOBIN="$PWD/.tools/bin" go install gotest.tools/gotestsum@v1.12.3
if [ "${WITH_RUST:-0}" = 1 ]; then
  if rustup show active-toolchain >/dev/null 2>&1; then rustup component add llvm-tools-preview; fi
  cargo install --locked cargo-nextest cargo-llvm-cov
fi
echo "Ready. Check a repo: bin/aqv check --repo PATH --base main"
echo "Run the demo:  .venv/bin/python demo/run_demo.py --lang all --impl go"
