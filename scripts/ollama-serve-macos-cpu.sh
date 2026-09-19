#!/usr/bin/env bash
# Ollama on macOS without GPU offload: avoids Metal-backed llama crashes on some
# setups. Slower than full Metal but does not use GGML_METAL_TENSOR_DISABLE.
#
# Usage:
#   1. Quit Ollama from the menu bar, or: killall Ollama
#   2. ./scripts/ollama-serve-macos-cpu.sh
set -euo pipefail
export OLLAMA_NUM_GPU=0
exec ollama serve
