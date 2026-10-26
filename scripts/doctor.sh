#!/usr/bin/env bash
# Report whether this machine has what Atlas needs to run.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Match runtime defaults / .env.example
PRIMARY_MODEL="${OLLAMA_MODEL:-qwen3.5:9b}"
FALLBACK_MODEL="${OLLAMA_FALLBACK_MODEL:-llama3.1:8b}"
EXPECTED_CTX="${OLLAMA_NUM_CTX:-8192}"

export PATH="${HOME}/.local/bin:/Applications/Ollama.app/Contents/Resources:${PATH}"

ok=0
warn=0
fail=0

pass() { echo "OK   $*"; ok=$((ok + 1)); }
note() { echo "WARN $*"; warn=$((warn + 1)); }
miss() { echo "MISS $*"; fail=$((fail + 1)); }

echo "Atlas doctor — checking prerequisites"
echo "Repo: $ROOT"
echo "Expected primary model: $PRIMARY_MODEL (ctx=$EXPECTED_CTX)"
echo

# OS / arch
uname_s="$(uname -s)"
uname_m="$(uname -m)"
if [[ "$uname_s" == "Darwin" ]]; then
  pass "macOS detected ($uname_m)"
  if [[ "$uname_m" != "arm64" ]]; then
    note "Apple Silicon (arm64) is the tested target; this machine is $uname_m"
  fi
  mem_bytes="$(sysctl -n hw.memsize 2>/dev/null || echo 0)"
  if [[ "$mem_bytes" =~ ^[0-9]+$ ]] && (( mem_bytes > 0 )); then
    mem_gb=$(( mem_bytes / 1024 / 1024 / 1024 ))
    if (( mem_gb >= 24 )); then
      pass "Unified memory ~${mem_gb} GB (defaults assume 24 GB)"
    elif (( mem_gb >= 16 )); then
      note "Unified memory ~${mem_gb} GB — consider OLLAMA_NUM_CTX=6144 if runs wedge"
    else
      note "Unified memory ~${mem_gb} GB is below the tested 24 GB target"
    fi
  fi
else
  note "Non-macOS host ($uname_s/$uname_m). Scripts assume macOS + Ollama app."
fi

# Disk hint (models are multi-GB)
if command -v df >/dev/null 2>&1; then
  free_gb="$(df -g . 2>/dev/null | awk 'NR==2 {print $4}')"
  if [[ -n "${free_gb:-}" ]]; then
    if (( free_gb < 20 )); then
      note "Low free disk (~${free_gb}G). Models need roughly 12G+ combined."
    else
      pass "Free disk looks adequate (~${free_gb}G available on this volume)"
    fi
  fi
fi

# Homebrew (optional if uv + ollama already installed)
if command -v brew >/dev/null 2>&1; then
  pass "Homebrew: $(brew --prefix)"
else
  note "Homebrew not found (optional if uv and ollama are already installed)"
fi

# uv
if command -v uv >/dev/null 2>&1; then
  pass "uv: $(uv --version 2>/dev/null | head -1)"
else
  miss "uv not found"
fi

# Python 3.12 via uv or system
if command -v uv >/dev/null 2>&1 && uv python find 3.12 >/dev/null 2>&1; then
  pass "Python 3.12 available via uv: $(uv python find 3.12)"
elif command -v python3.12 >/dev/null 2>&1; then
  pass "python3.12: $(python3.12 --version)"
else
  miss "Python 3.12 not found (uv can download it during bootstrap)"
fi

# Project venv / package
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  pass "Project venv exists (.venv)"
  if "$ROOT/.venv/bin/python" -c "import browser_use, dotenv, ollama_runtime" >/dev/null 2>&1; then
    pass "Runtime imports OK (browser_use, dotenv, ollama_runtime)"
  elif "$ROOT/.venv/bin/python" -c "import browser_use" >/dev/null 2>&1; then
    note "browser-use importable, but ollama_runtime import failed from venv cwd"
  else
    miss "browser-use not installed in .venv (run scripts/bootstrap.sh)"
  fi
  model_default="$("$ROOT/.venv/bin/python" -c "import sys; sys.path.insert(0, '.'); from ollama_runtime import DEFAULT_MODEL, DEFAULT_CONTEXT_SIZE; print(DEFAULT_MODEL, DEFAULT_CONTEXT_SIZE)" 2>/dev/null || true)"
  if [[ -n "$model_default" ]]; then
    pass "ollama_runtime defaults: $model_default"
  fi
else
  miss "Project venv missing (.venv)"
fi

# Chromium for browser-use / playwright
if [[ -d "$HOME/Library/Caches/ms-playwright" ]] || [[ -d "$HOME/.cache/ms-playwright" ]]; then
  pass "Playwright/Chromium cache present"
else
  miss "Browser binary cache not found (run: uvx --from browser-use==0.13.6 browser-use install)"
fi

# Ollama CLI + API
if command -v ollama >/dev/null 2>&1; then
  pass "ollama CLI: $(command -v ollama)"
else
  miss "ollama CLI not found (install Ollama app / brew --cask ollama)"
fi

if curl --fail --silent --max-time 3 http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
  ver="$(curl --fail --silent --max-time 3 http://127.0.0.1:11434/api/version || true)"
  pass "Ollama API reachable ($ver)"
else
  miss "Ollama API not reachable on 127.0.0.1:11434 (open the Ollama app or: ollama serve)"
fi

# Models
if command -v ollama >/dev/null 2>&1 && curl --fail --silent --max-time 2 http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
  models="$(ollama list 2>/dev/null || true)"
  if echo "$models" | grep -q "${PRIMARY_MODEL}"; then
    pass "Model present: ${PRIMARY_MODEL}"
  else
    miss "Model missing: ${PRIMARY_MODEL} (ollama pull ${PRIMARY_MODEL})"
  fi
  if echo "$models" | grep -q "${FALLBACK_MODEL}"; then
    pass "Model present: ${FALLBACK_MODEL}"
  else
    note "Fallback model missing: ${FALLBACK_MODEL} (optional but recommended)"
  fi
else
  note "Skipping model checks until Ollama API is up"
fi

# Env file alignment
if [[ -f "$ROOT/.env" ]]; then
  pass ".env present"
  env_model="$(grep -E '^OLLAMA_MODEL=' "$ROOT/.env" | head -1 | cut -d= -f2- || true)"
  env_ctx="$(grep -E '^OLLAMA_NUM_CTX=' "$ROOT/.env" | head -1 | cut -d= -f2- || true)"
  if [[ -n "$env_model" && "$env_model" != "$PRIMARY_MODEL" ]]; then
    note ".env OLLAMA_MODEL=$env_model (doctor expected $PRIMARY_MODEL)"
  fi
  if [[ -n "$env_ctx" && "$env_ctx" != "$EXPECTED_CTX" ]]; then
    note ".env OLLAMA_NUM_CTX=$env_ctx (default docs use $EXPECTED_CTX)"
  fi
  if [[ -z "$env_model" ]]; then
    note ".env missing OLLAMA_MODEL; runtime will use code default $PRIMARY_MODEL"
  fi
else
  note ".env missing (optional; copy from .env.example)"
fi

echo
echo "Summary: $ok ok, $warn warnings, $fail missing"
if (( fail > 0 )); then
  echo "Next step: ./scripts/bootstrap.sh"
  exit 1
fi
echo "Ready to smoke-test: uv run python main.py"
exit 0
