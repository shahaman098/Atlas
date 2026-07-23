#!/usr/bin/env bash
# Report whether this machine has what Atlas needs to run.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ok=0
warn=0
fail=0

pass() { echo "OK   $*"; ok=$((ok + 1)); }
note() { echo "WARN $*"; warn=$((warn + 1)); }
miss() { echo "MISS $*"; fail=$((fail + 1)); }

echo "Atlas doctor — checking prerequisites"
echo "Repo: $ROOT"
echo

# OS / arch
uname_s="$(uname -s)"
uname_m="$(uname -m)"
if [[ "$uname_s" == "Darwin" ]]; then
  pass "macOS detected ($uname_m)"
  if [[ "$uname_m" != "arm64" ]]; then
    note "Apple Silicon (arm64) is the tested target; this machine is $uname_m"
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

# Homebrew
if command -v brew >/dev/null 2>&1; then
  pass "Homebrew: $(brew --prefix)"
else
  miss "Homebrew not found (needed for easy uv/ollama install on macOS)"
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
  if "$ROOT/.venv/bin/python" -c "import browser_use" >/dev/null 2>&1; then
    pass "browser-use importable in .venv"
  else
    miss "browser-use not installed in .venv (run scripts/bootstrap.sh)"
  fi
else
  miss "Project venv missing (.venv)"
fi

# Chromium for browser-use / playwright
if [[ -d "$HOME/Library/Caches/ms-playwright" ]] || [[ -d "$HOME/.cache/ms-playwright" ]]; then
  pass "Playwright/Chromium cache present"
else
  miss "Browser binary cache not found (run: uvx browser-use install)"
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
  miss "Ollama API not reachable on 127.0.0.1:11434 (open the Ollama app)"
fi

# Models
if command -v ollama >/dev/null 2>&1 && curl --fail --silent --max-time 2 http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
  models="$(ollama list 2>/dev/null || true)"
  if echo "$models" | grep -q 'qwen3.5:9b'; then
    pass "Model present: qwen3.5:9b"
  else
    miss "Model missing: qwen3.5:9b (ollama pull qwen3.5:9b)"
  fi
  if echo "$models" | grep -q 'llama3.1:8b'; then
    pass "Model present: llama3.1:8b"
  else
    note "Fallback model missing: llama3.1:8b (optional but recommended)"
  fi
else
  note "Skipping model checks until Ollama API is up"
fi

# Env file
if [[ -f "$ROOT/.env" ]]; then
  pass ".env present"
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
