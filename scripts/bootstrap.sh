#!/usr/bin/env bash
# Install resources another machine may not have yet.
# Safe to re-run (idempotent where possible).
# Homebrew is preferred on macOS but not required if uv + ollama are already present.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PRIMARY_MODEL="${OLLAMA_MODEL:-qwen3.5:9b}"
FALLBACK_MODEL="${OLLAMA_FALLBACK_MODEL:-llama3.1:8b}"
SKIP_MODELS="${SKIP_MODELS:-0}"
SKIP_BROWSER="${SKIP_BROWSER:-0}"

log() { printf '\n==> %s\n' "$*"; }
need_cmd() { command -v "$1" >/dev/null 2>&1; }

ensure_path() {
  # Common non-Homebrew install locations used on this machine.
  export PATH="${HOME}/.local/bin:/Applications/Ollama.app/Contents/Resources:${PATH}"
}

ensure_path

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This bootstrap currently targets macOS (Ollama app + Apple Silicon path)." >&2
  echo "You can still install uv/Python deps manually on other OSes." >&2
fi

log "1/7 Homebrew (optional)"
if need_cmd brew; then
  echo "Using $(brew --prefix)"
else
  echo "Homebrew not found — continuing if uv/ollama can be installed another way."
fi

log "2/7 uv"
if ! need_cmd uv; then
  if need_cmd brew; then
    brew install uv
  else
    echo "Installing uv via https://astral.sh/uv ..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ensure_path
  fi
fi
if ! need_cmd uv; then
  echo "uv is still not on PATH after install." >&2
  exit 1
fi
echo "uv already available: $(uv --version | head -1)"

log "3/7 Ollama"
if ! need_cmd ollama; then
  if [[ -x "/Applications/Ollama.app/Contents/Resources/ollama" ]]; then
    mkdir -p "${HOME}/.local/bin"
    ln -sf "/Applications/Ollama.app/Contents/Resources/ollama" "${HOME}/.local/bin/ollama"
    ensure_path
  elif need_cmd brew; then
    brew install --cask ollama
  else
    echo "Ollama CLI not found. Install from https://ollama.com/download then re-run." >&2
    exit 1
  fi
fi
echo "ollama: $(command -v ollama)"

if ! curl --fail --silent --max-time 2 http://127.0.0.1:11434/api/version >/dev/null; then
  echo "Starting Ollama..."
  if [[ -d "/Applications/Ollama.app" ]]; then
    open "/Applications/Ollama.app" || true
  fi
  if ! curl --fail --silent --max-time 2 http://127.0.0.1:11434/api/version >/dev/null; then
    nohup ollama serve >/tmp/atlas-ollama-serve.log 2>&1 &
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
  uvx --from "browser-use==0.13.6" browser-use install
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
