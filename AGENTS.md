# AGENTS.md — Cursor / coding-agent context

This file is the primary onboarding brief for any Cursor (or similar) agent working in this repo on a new machine.

## What this project is

Local, supervised **Browser Use** automation for Apple Silicon Macs (target: 16 GB M1/M2/M3) using **Ollama** open models.

```text
Python Browser Use agent
-> isolated headless Chromium
-> DOM / accessibility tree (no vision by default)
-> local Ollama model
-> one browser action per step
-> short, domain-constrained, supervised tasks
```

Human-facing setup and troubleshooting live in [README.md](README.md).  
Full original build plan / acceptance criteria live in [CURSOR_IMPLEMENTATION_PLAN.md](CURSOR_IMPLEMENTATION_PLAN.md).

## Hard constraints (do not violate)

- **DOM-only default**: keep `use_vision=False` until an explicit vision phase.
- **One action per step**: `max_actions_per_step=1`.
- **Isolated Chromium only**: do not wire `Browser.from_system_chrome()` or the user's normal Chrome profile unless the user explicitly asks.
- **No irreversible automation**: no payments, account deletion, password entry, sign-in flows, or unattended high-impact workflows.
- **Ollama stays local**: `127.0.0.1` only.
- **Pin Browser Use** to `0.13.6` unless the user asks to upgrade (API quirks below are version-specific).

## Layout

| Path | Role |
| --- | --- |
| `main.py` | Smoke-task entrypoint (`example.com` title + heading) |
| `ollama_runtime.py` | Shared LLM/browser/agent factory, Ollama health + restart, excluded actions |
| `scripts/benchmark.py` | Fixed DOM task suite → CSV |
| `scripts/check_ollama.sh` | Ollama API / model sanity check |
| `scripts/summarize_benchmark.py` | Success-rate summary for a CSV |
| `.env.example` | Env defaults (`OLLAMA_MODEL`, `OLLAMA_NUM_CTX`, `AGENT_MAX_STEPS`) |
| `results/` | Local CSV output (gitignored) |

## Runtime defaults that matter

Configured in `ollama_runtime.py` / `.env.example`:

- Primary model: `qwen3.5:9b`
- Fallback model: `llama3.1:8b`
- Default context: `6144` (safer than `8192` on 16 GB)
- `ollama_options={"num_ctx": ..., "num_predict": 768}` — Browser Use `ChatOllama` has **no** `num_ctx=` kwarg
- `max_history_items=6` (library requires `> 5`; 4 is invalid)
- `flash_mode=True`, `use_judge=False`
- Headless browser, `enable_default_extensions=False` (bundled uBlock CRX is broken)
- `allowed_domains` set per task
- Restricted tool surface via `Tools(exclude_actions=...)` (search/files/screenshot/evaluate/switch/close excluded)

## Lessons already learned (avoid re-breaking)

1. **`8192` context + heavy pages** can wedge Ollama or detach Chromium CDP on 16 GB. Prefer `6144` / `4096`.
2. **DuckDuckGo / multi-hop SERP tasks** caused severe off-task hallucination with 9B models. Current benchmark uses simpler single-site tasks; do not reintroduce SERP hops without evidence.
3. **Ollama API can die mid-suite** — `wait_for_ollama(restart_if_needed=True)` and `unload_ollama_models()` exist for a reason.
4. Prefer changing agent settings through **`ollama_runtime.create_agent` / `create_browser` / `create_llm`**, not by duplicating Agent construction in callers.
5. Every user-facing task string must include allowed domains + forbidden actions (forms / downloads / sign-in / stop / manual review).

## First commands on a new machine

```bash
brew install uv
brew install --cask ollama
ollama pull qwen3.5:9b
ollama pull llama3.1:8b
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e .
uvx browser-use install
./scripts/check_ollama.sh
uv run python main.py
```

## How to extend safely

1. Add or change shared agent behavior in `ollama_runtime.py`.
2. Add benchmark tasks in `scripts/benchmark.py` (`TASKS` + `ALLOWED_DOMAINS`) with the same safety block.
3. Keep tasks short, single-purpose, and domain-locked.
4. Smoke with `uv run python main.py` before long benchmarks.
5. Record runs under `results/` (gitignored) and summarize with `uv run python scripts/summarize_benchmark.py`.

## Out of scope unless requested

- Vision mode / screenshots as default
- System Chrome profile reuse
- Remote/cloud browser backends
- Unattended production agents
- Raising context to 32K/64K on 16 GB machines
