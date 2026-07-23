#!/usr/bin/env bash
set -euo pipefail

if ! curl --fail --silent --max-time 3 http://127.0.0.1:11434/api/version; then
  echo "Ollama API is not reachable at http://127.0.0.1:11434" >&2
  echo "Open the Ollama app, then retry." >&2
  exit 1
fi
echo
ollama list
ollama ps
