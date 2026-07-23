#!/usr/bin/env bash
# Install resources another machine may not have yet.
# Safe to re-run (idempotent where possible).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PRIMARY_MODEL="${OLLAMA_MODEL:-qwen3.5:9b}"
FALLBACK_MODEL="${OLLAMA_FALLBACK_MODEL:-llama3.1:8b}"
SKIP_MODELS="${SKIP_MODELS:-0}"
SKIP_BROWSER="${SKIP_BROWSER:-0}"

log() { printf '\n==> %s\n' "$*"; }
need_cmd() { command -v "$1" >/dev/null 2>&1; }

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This bootstrap currently targets macOS (Ollama app + Apple Silicon path)." >&2
  echo "You can still install uv/Python deps manually on other OSes." >&2
fi

log "1/7 Homebrew"
if ! need_cmd brew; then
  echo "Homebrew is required for the guided macOS install." >&2
  echo "Install from https://brew.sh then re-run this script." >&2
  exit 1
fi
echo "Using $(brew --prefix)"

log "2/7 uv"
if ! need_cmd uv; then
  brew install uv
else
  echo "uv already installed: $(uv --version | head -1)"
fi

log "3/7 Ollama"
if ! need_cmd ollama; then
  brew install --cask ollama
  echo "Opening Ollama once so the local API can start..."
  open -a Ollama || true
  sleep 5
else
  echo "ollama already installed: $(command -v ollama)"
  # Ensure the app/API is up
  if ! curl --fail --silent --max-time 2 http://127.0.0.1:11434/api/version >/dev/null; then
    echo "Starting Ollama app..."
    open -a Ollama || true
  fi
fi

log "4/7 Wait for Ollama API"
for i in $(seq 1 60); do
  if curl --fail --silent --max-time 2 http://127.0.0.1:11434/api/version >/dev/null; then
    curl --fail --silent --max-time 2 http://127.0.0.1:11434/api/version
    echo
    break
  fi
  if (( i == 60 )); then
    echo "Ollama API did not become ready. Open the Ollama app and re-run." >&2
    exit 1
  fi
  sleep 1
done

log "5/7 Python venv + project deps"
if [[ ! -d .venv ]]; then
  uv venv --python 3.12
fi
# shellcheck disable=SC1091
source .venv/bin/activate
uv pip install -e .

if [[ "$SKIP_BROWSER" != "1" ]]; then
  log "6/7 Browser Use Chromium"
  uvx browser-use install
else
  log "6/7 Browser Use Chromium (skipped via SKIP_BROWSER=1)"
fi

if [[ "$SKIP_MODELS" != "1" ]]; then
  log "7/7 Pull Ollama models (large download)"
  ollama pull "$PRIMARY_MODEL"
  ollama pull "$FALLBACK_MODEL"
else
  log "7/7 Model pulls skipped via SKIP_MODELS=1"
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example"
else
  echo ".env already exists (left unchanged)"
fi

echo
log "Bootstrap finished"
./scripts/doctor.sh || true

cat <<EOF

Next:
  source .venv/bin/activate
  uv run python main.py

Optional Ollama memory tuning (then quit/reopen Ollama):
  launchctl setenv OLLAMA_FLASH_ATTENTION 1
  launchctl setenv OLLAMA_KV_CACHE_TYPE q8_0
  launchctl setenv OLLAMA_MAX_LOADED_MODELS 1
  launchctl setenv OLLAMA_NUM_PARALLEL 1
  launchctl setenv OLLAMA_CONTEXT_LENGTH 8192
EOF
