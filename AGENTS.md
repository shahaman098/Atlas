# AGENTS.md — Cursor / coding-agent context

This file is the primary onboarding brief for any Cursor (or similar) agent working in this repo on a new machine.

## End goal

Build a **personal, local-first browser automation agent** that can reliably complete short, supervised web tasks on a 16 GB Apple Silicon Mac **without depending on proprietary cloud LLMs**.

The finished system should let the owner:

1. Describe a constrained browser task in natural language.
2. Run it through Browser Use + isolated Chromium on their machine.
3. Have a local open model (Ollama today) decide DOM actions one step at a time.
4. Get a clear success/failure result they can trust for everyday research, form-prep, and site navigation work.
5. Keep hard safety rails: domain allowlists, no sign-in/payment/destruction by default, human review before irreversible actions.

**North star:** a reproducible open-model browser agent that is good enough for real personal workflows on consumer hardware, starting DOM-only and graduating to harder tasks (and optionally vision) only after measured reliability.

This is **not** an unattended general web agent, a shopping bot, or a product that auto-uses the owner's signed-in Chrome profile.

## Goals we are trying to achieve

### Product goals

- Own a working local browser agent loop: task → browser state → model → one action → result.
- Prefer **open-weight models** (local Ollama first; remote open-weight endpoint only if local models fail the acceptance gate).
- Stay useful on a **16 GB Mac** without constant swapping or wedging Ollama/Chromium.
- Make the repo clone-and-run reproducible for the owner across machines and Cursor sessions.
- Keep the operator in control: supervised runs, explicit domain limits, explicit forbidden actions.

### Technical goals

- DOM/accessibility-tree first (`use_vision=False`) until the baseline suite is stable.
- One browser action per step; short history; conservative context (`6144` default).
- Isolated headless Chromium by default (no system Chrome profile yet).
- Shared runtime factory so agent settings stay consistent (`ollama_runtime.py`).
- Measurable quality via a fixed benchmark suite and CSV results (target: **≥12/15** successful runs for the chosen model).
- Recover from local-runtime failures (Ollama wedge, memory pressure) instead of silently dying mid-suite.

### Safety goals

- No autonomous purchasing, payments, account changes, credential entry, or destructive actions.
- No form submit / file download / sign-in unless a future task explicitly requires it and is still supervised.
- Ollama remains on `127.0.0.1`.
- Every user-facing task prompt states allowed domains, forbidden actions, stop conditions, and “ask for manual review before irreversible actions”.

### Near-term milestones

1. **Baseline green:** `uv run python main.py` reliably extracts `example.com` title + heading.
2. **Acceptance gate:** chosen local model hits ≥12/15 on the DOM benchmark suite without safety violations.
3. **Model selection locked:** keep `qwen3.5:9b` or switch to `llama3.1:8b` based on measured completion quality vs memory pressure.
4. **Personal task pack:** add a small set of owner-approved, domain-locked real tasks (still supervised).
5. **Optional vision phase:** only after DOM acceptance, enable vision for canvas/maps/poor-a11y pages.
6. **Optional inference fallback:** if both local models fail acceptance, keep browser local and move inference to a remote open-weight OpenAI-compatible server (e.g. vLLM).

## What this project is today

Local, supervised **Browser Use** automation for Apple Silicon Macs (target: 16 GB) using **Ollama** open models.

```text
Python Browser Use agent
-> isolated headless Chromium
-> DOM / accessibility tree (no vision by default)
-> local Ollama model
-> one browser action per step
-> short, domain-constrained, supervised tasks
```

Human-facing setup and troubleshooting: [README.md](README.md).  
Phased build plan / acceptance criteria: [CURSOR_IMPLEMENTATION_PLAN.md](CURSOR_IMPLEMENTATION_PLAN.md).

## Hard constraints (do not violate)

- **DOM-only default**: keep `use_vision=False` until an explicit vision phase.
- **One action per step**: `max_actions_per_step=1`.
- **Isolated Chromium only**: do not wire `Browser.from_system_chrome()` or the user's normal Chrome profile unless the user explicitly asks.
- **No irreversible automation**: no payments, account deletion, password entry, sign-in flows, or unattended high-impact workflows.
- **Ollama stays local**: `127.0.0.1` only.
- **Pin Browser Use** to `0.13.6` unless the user asks to upgrade (API quirks below are version-specific).
- **Optimize for correctness before speed** on the benchmark path.

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

1. Keep changes aligned with the end goal and milestones above.
2. Add or change shared agent behavior in `ollama_runtime.py`.
3. Add benchmark tasks in `scripts/benchmark.py` (`TASKS` + `ALLOWED_DOMAINS`) with the same safety block.
4. Keep tasks short, single-purpose, and domain-locked.
5. Smoke with `uv run python main.py` before long benchmarks.
6. Record runs under `results/` (gitignored) and summarize with `uv run python scripts/summarize_benchmark.py`.

## Out of scope unless requested

- Vision mode / screenshots as default
- System Chrome profile reuse
- Closed/proprietary cloud model dependency as the primary path
- Remote/cloud browser backends
- Unattended production agents
- Raising context to 32K/64K on 16 GB machines
- Autonomous purchasing, account takeover, or credential-bearing workflows
