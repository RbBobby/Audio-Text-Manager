#!/usr/bin/env bash
# Start Ollama on macOS (Apple Silicon) when the default Metal path crashes the
# llama runner (HTTP 500: "llama runner process has terminated").
#
# Usage:
#   1. Quit Ollama from the menu bar, or: killall Ollama
#   2. ./scripts/ollama-serve-macos-metal-safe.sh
#
# See: https://github.com/ollama/ollama/issues/14432
set -euo pipefail
export GGML_METAL_TENSOR_DISABLE=1
exec ollama serve
