#!/usr/bin/env bash
set -euo pipefail

PRIMARY_MODEL="${OLLAMA_MODEL:-qwen3.5:9b}"
FALLBACK_MODEL="${OLLAMA_FALLBACK_MODEL:-llama3.1:8b}"
export PATH="${HOME}/.local/bin:/Applications/Ollama.app/Contents/Resources:${PATH}"

if ! curl --fail --silent --max-time 3 http://127.0.0.1:11434/api/version; then
  echo "Ollama API is not reachable at http://127.0.0.1:11434" >&2
  echo "Open the Ollama app (or run: ollama serve), then retry." >&2
  exit 1
fi
echo
ollama list
echo
ollama ps

models="$(ollama list 2>/dev/null || true)"
missing=0
if ! echo "$models" | grep -q "$PRIMARY_MODEL"; then
  echo "Missing primary model: $PRIMARY_MODEL" >&2
  echo "  ollama pull $PRIMARY_MODEL" >&2
  missing=1
fi
if ! echo "$models" | grep -q "$FALLBACK_MODEL"; then
  echo "Missing fallback model: $FALLBACK_MODEL (optional)" >&2
  echo "  ollama pull $FALLBACK_MODEL" >&2
fi
exit "$missing"
