#!/usr/bin/env bash
# Run the main.py smoke task repeatedly and print a pass/fail score.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export PATH="${HOME}/.local/bin:/Applications/Ollama.app/Contents/Resources:${PATH}"

REPEATS="${1:-${SMOKE_REPEATS:-5}}"
MODEL="${OLLAMA_MODEL:-qwen3.5:9b}"
CTX="${OLLAMA_NUM_CTX:-8192}"

if ! [[ "$REPEATS" =~ ^[0-9]+$ ]] || (( REPEATS < 1 )); then
  echo "Usage: ./scripts/smoke_repeat.sh [repeats]" >&2
  exit 1
fi

if ! curl --fail --silent --max-time 2 http://127.0.0.1:11434/api/version >/dev/null; then
  echo "Starting Ollama..."
  open /Applications/Ollama.app 2>/dev/null || true
  nohup ollama serve >/tmp/atlas-ollama-serve.log 2>&1 &
  for _ in $(seq 1 45); do
    curl --fail --silent --max-time 2 http://127.0.0.1:11434/api/version >/dev/null && break
    sleep 1
  done
fi

echo "Warming ${MODEL} (ctx=${CTX})..."
curl --fail --silent --max-time 180 http://127.0.0.1:11434/api/chat \
  -d "{\"model\":\"${MODEL}\",\"messages\":[{\"role\":\"user\",\"content\":\"OK\"}],\"stream\":false,\"think\":false,\"keep_alive\":\"60m\",\"options\":{\"num_ctx\":${CTX},\"num_predict\":1}}" \
  >/dev/null

pass=0
fail=0
run_dir="$(mktemp -d -t atlas-smoke.XXXXXX)"
echo "Smoke loop: model=${MODEL} repeats=${REPEATS}"
echo "Artifacts: ${run_dir}"
echo

for i in $(seq 1 "$REPEATS"); do
  echo "=== smoke ${i}/${REPEATS} ==="
  out="${run_dir}/run-${i}.log"
  set +e
  OLLAMA_MODEL="$MODEL" OLLAMA_NUM_CTX="$CTX" uv run python main.py >"$out" 2>&1
  code=$?
  set -e
  tail -n 12 "$out"
  if (( code == 0 )) \
    && grep -q '^Successful: True$' "$out" \
    && grep -qi 'Example Domain' "$out" \
    && grep -q '^Quality: True$' "$out"; then
    echo "→ PASS"
    pass=$((pass + 1))
  else
    echo "→ FAIL (exit=${code})"
    fail=$((fail + 1))
  fi
  echo
done

echo "=============================="
echo "Smoke score: ${pass}/${REPEATS} passed (${fail} failed)"
echo "Model: ${MODEL}  Context: ${CTX}"
echo "Artifacts: ${run_dir}"
if (( pass == REPEATS )); then
  echo "All smoke runs passed."
  exit 0
fi
echo "Some smoke runs failed."
exit 1
