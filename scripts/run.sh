#!/usr/bin/env bash
# One-command smoke / daily run for Atlas.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export PATH="${HOME}/.local/bin:/Applications/Ollama.app/Contents/Resources:${PATH}"

PRIMARY_MODEL="${OLLAMA_MODEL:-qwen3.5:9b}"

if [[ ! -x .venv/bin/python ]]; then
  echo "Missing .venv — run ./scripts/bootstrap.sh first." >&2
  exit 1
fi

if ! curl --fail --silent --max-time 2 http://127.0.0.1:11434/api/version >/dev/null; then
  echo "Starting Ollama..."
  if [[ -d /Applications/Ollama.app ]]; then
    open /Applications/Ollama.app || true
  fi
  if ! curl --fail --silent --max-time 2 http://127.0.0.1:11434/api/version >/dev/null; then
    nohup ollama serve >/tmp/atlas-ollama-serve.log 2>&1 &
  fi
  for _ in $(seq 1 45); do
    curl --fail --silent --max-time 2 http://127.0.0.1:11434/api/version >/dev/null && break
    sleep 1
  done
fi

if ! curl --fail --silent --max-time 2 http://127.0.0.1:11434/api/version >/dev/null; then
  echo "Ollama API is not reachable on 127.0.0.1:11434" >&2
  exit 1
fi

if ! ollama list 2>/dev/null | grep -q "$PRIMARY_MODEL"; then
  echo "Missing model $PRIMARY_MODEL — run: ollama pull $PRIMARY_MODEL" >&2
  exit 1
fi

CTX="${OLLAMA_NUM_CTX:-8192}"
# Keep the primary model warm with the same context the agent will use.
curl --fail --silent --max-time 180 http://127.0.0.1:11434/api/chat \
  -d "{\"model\":\"${PRIMARY_MODEL}\",\"messages\":[{\"role\":\"user\",\"content\":\"OK\"}],\"stream\":false,\"think\":false,\"keep_alive\":\"60m\",\"options\":{\"num_ctx\":${CTX},\"num_predict\":1}}" \
  >/dev/null || true

exec uv run python main.py "$@"
