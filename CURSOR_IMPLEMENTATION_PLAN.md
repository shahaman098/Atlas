# Cursor Implementation Plan: Local Browser Use Automation with Open Models

## Objective

Build a reproducible local Browser Use automation project for a 16 GB M1 Pro Mac using Ollama-hosted open models.

The intended runtime path is:

```text
Python Browser Use agent
-> isolated Chromium session
-> DOM/accessibility-tree browser state
-> local Ollama model
-> one browser action per step
-> supervised, short, domain-constrained tasks
```

The first implementation must be DOM-only. Do not enable screenshots or vision until the baseline benchmark is stable.

## Non-Goals

- Do not connect to the user's normal Chrome profile in the initial implementation.
- Do not support autonomous purchasing, payments, deletion, account changes, sign-in, or irreversible actions.
- Do not expose Ollama outside `127.0.0.1`.
- Do not make this an unattended production agent before benchmark acceptance.
- Do not start with high context lengths such as 32K or 64K on the 16 GB machine.

## Target Stack

- macOS on Apple Silicon, 16 GB unified memory.
- Python `3.12`.
- `uv` for project and dependency management.
- Browser Use pinned to `0.13.6`.
- Ollama for local open-weight models.
- Primary candidate: `qwen3.5:9b`.
- Fallback model: `llama3.1:8b`.
- Browser Use isolated Chromium session.

## Repository Files to Create

Create this minimal project structure:

```text
.
├── .env.example
├── .gitignore
├── README.md
├── CURSOR_IMPLEMENTATION_PLAN.md
├── main.py
├── ollama_runtime.py
├── pyproject.toml
└── scripts/
    ├── benchmark.py
    └── check_ollama.sh
```

Optional after baseline:

```text
.
└── results/
    └── benchmark-runs.csv
```

## Phase 1: System Setup Instructions

Document these commands in `README.md`.

Install tools:

```bash
brew install uv
brew install --cask ollama
```

Open Ollama once from Applications, then configure conservative memory settings:

```bash
launchctl setenv OLLAMA_FLASH_ATTENTION 1
launchctl setenv OLLAMA_KV_CACHE_TYPE q8_0
launchctl setenv OLLAMA_MAX_LOADED_MODELS 1
launchctl setenv OLLAMA_NUM_PARALLEL 1
launchctl setenv OLLAMA_CONTEXT_LENGTH 8192
```

After setting these variables, quit and reopen Ollama.

Pull the models:

```bash
ollama pull qwen3.5:9b
ollama pull llama3.1:8b
```

Verify Ollama:

```bash
curl http://127.0.0.1:11434/api/version
ollama list
```

## Phase 2: Python Project

Create `pyproject.toml`:

```toml
[project]
name = "local-browser-agent"
version = "0.1.0"
description = "Local Browser Use automation with Ollama open models"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
  "browser-use==0.13.6",
  "python-dotenv>=1.0.1",
]

[tool.uv]
dev-dependencies = []
```

Create `.gitignore`:

```gitignore
.venv/
__pycache__/
.env
browser_data/
results/
*.gif
```

Create `.env.example`:

```env
OLLAMA_MODEL=qwen3.5:9b
OLLAMA_NUM_CTX=6144
AGENT_MAX_STEPS=8
```

Setup commands:

```bash
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e .
uvx browser-use install
```

## Phase 3: Minimum DOM-Only Agent

Create `main.py`.

Requirements:

- Load `.env` with `python-dotenv`.
- Use `ChatOllama`.
- Default model is `qwen3.5:9b`.
- Default context is `6144` (safer on 16 GB; raise to `8192` only after validating stability).
- Keep `use_vision=False`.
- Keep `max_actions_per_step=1`.
- Keep `max_history_items=6` (library requires `> 5`; 6 is the lowest allowed).
- Pass context via `ollama_options={"num_ctx": ...}` (Browser Use 0.13.6 has no `num_ctx=` kwarg).
- Keep `generate_gif=False`.
- Keep `max_failures=3`.
- Keep `llm_timeout=180`.
- Keep `step_timeout=240`.
- Use `agent.run(max_steps=8)` by default.
- Print model, success flag, and final result.

Initial safe task:

```text
Open https://example.com.

Return:
1. The page title.
2. The first visible heading.

Safety constraints:
- Do not leave example.com.
- Do not download anything.
- Do not submit forms.
- Do not sign in.
```

Expected code shape:

```python
import asyncio
import os

from dotenv import load_dotenv
from browser_use import Agent, ChatOllama


DEFAULT_MODEL = "qwen3.5:9b"
DEFAULT_CONTEXT_SIZE = 6144
DEFAULT_MAX_STEPS = 8


async def main() -> None:
    load_dotenv()

    model = os.getenv("OLLAMA_MODEL", DEFAULT_MODEL)
    context_size = int(os.getenv("OLLAMA_NUM_CTX", str(DEFAULT_CONTEXT_SIZE)))
    max_steps = int(os.getenv("AGENT_MAX_STEPS", str(DEFAULT_MAX_STEPS)))

    llm = ChatOllama(model=model, ollama_options={"num_ctx": context_size})

    task = """
Open https://example.com.

Return:
1. The page title.
2. The first visible heading.

Safety constraints:
- Do not leave example.com.
- Do not download anything.
- Do not submit forms.
- Do not sign in.
""".strip()

    agent = Agent(
        task=task,
        llm=llm,
        use_vision=False,
        use_thinking=False,
        max_history_items=6,
        max_actions_per_step=1,
        max_failures=3,
        llm_timeout=180,
        step_timeout=240,
        generate_gif=False,
    )

    history = await agent.run(max_steps=max_steps)

    print(f"Model: {model}")
    print(f"Successful: {history.is_successful()}")
    print(f"Result: {history.final_result()}")


if __name__ == "__main__":
    asyncio.run(main())
```

## Phase 4: Ollama Check Script

Create `scripts/check_ollama.sh`.

Requirements:

- Use `set -euo pipefail`.
- Check the Ollama API endpoint.
- Print installed models.
- Print currently loaded models with `ollama ps`.

Expected script:

```bash
#!/usr/bin/env bash
set -euo pipefail

curl --fail --silent http://127.0.0.1:11434/api/version
echo
ollama list
ollama ps
```

Make it executable:

```bash
chmod +x scripts/check_ollama.sh
```

## Phase 5: Benchmark Harness

Create `scripts/benchmark.py`.

Purpose:

- Run a fixed set of benchmark tasks.
- Run each task multiple times per model.
- Record results as CSV.
- Keep agent settings identical across models except model name and context.

Initial benchmark tasks (tuned for local 9B DOM-only reliability):

```text
1. Open https://example.com and return its title and first visible heading.
2. Open https://docs.python.org/3/ and return the page title.
3. Open https://docs.docker.com/get-started/ and return the title plus one short Docker quote.
4. Open a public test form, enter supplied dummy information, do not submit, and report completed fields.
5. Open the humor-tagged quotes page (fallback: home) and extract one visible quote + author.
```

DuckDuckGo multi-hop search is deferred: local 9B models frequently hallucinate off-domain on heavy SERP pages even with `allowed_domains` set.
CSV fields:

```text
timestamp,model,context_size,task_id,run_number,success,final_result,error,steps
```

Implementation requirements:

- Default models: `qwen3.5:9b`, `llama3.1:8b`.
- Default repeats: `3`.
- Default context: `6144`.
- Allow overrides using environment variables:
  - `BENCHMARK_MODELS`, comma-separated.
  - `BENCHMARK_TASK_IDS`, comma-separated.
  - `BENCHMARK_REPEATS`.
  - `BENCHMARK_COOLDOWN_SECONDS`.
  - `OLLAMA_NUM_CTX`.
- Create `results/benchmark-runs.csv`.
- Keep `use_vision=False`.
- Keep `max_actions_per_step=1`.
- Keep `max_history_items=6`.
- Keep `generate_gif=False`.
- Wait for the Ollama API between runs; catch exceptions and write them to CSV.

Do not optimize for speed before correctness.

## Phase 6: Memory Reduction Ladder

Document and support these manual test commands:

```bash
OLLAMA_NUM_CTX=6144 uv run python main.py
OLLAMA_MODEL=llama3.1:8b OLLAMA_NUM_CTX=6144 uv run python main.py
OLLAMA_MODEL=llama3.1:8b OLLAMA_NUM_CTX=4096 uv run python main.py
```

Selection logic:

- Prefer `qwen3.5:9b` only if it matches or beats Llama's completion rate without extra schema errors or memory pressure.
- Prefer `llama3.1:8b` if Qwen times out, swaps, loops, or produces malformed actions.

## Phase 7: Acceptance Gate

The implementation is acceptable only when:

- `python -m py_compile main.py scripts/benchmark.py` passes.
- `scripts/check_ollama.sh` runs successfully when Ollama is open.
- `uv run python main.py` completes the `example.com` task.
- The chosen model reaches at least 12 successful runs out of 15 benchmark attempts.
- No benchmark run submits forms.
- No benchmark run downloads files.
- No benchmark run performs sign-in.
- No benchmark run leaves explicitly allowed domains.
- Memory pressure remains acceptable during runs.

## Phase 8: Vision Later

Only enable `use_vision=True` after DOM-only benchmarking passes.

Vision may be tested for:

- canvas interfaces;
- maps;
- charts;
- image-only controls;
- websites with poor accessibility metadata.

Keep these limits when testing vision:

```python
use_vision=True
max_actions_per_step=1
max_history_items=6
```

Start with:

```bash
OLLAMA_MODEL=qwen3.5:9b OLLAMA_NUM_CTX=6144 uv run python main.py
```

Do not make vision the default until it passes its own benchmark.

## Phase 9: Security Rules for Every Real Task

Every user-facing task string must include:

```text
Allowed domains:
Forbidden actions:
Do not submit forms:
Do not download files:
Do not sign in:
Stop after max_steps:
Ask for manual review before irreversible actions:
```

Initial default policy:

- Isolated Chromium only.
- No system Chrome profile.
- No passwords in prompts.
- No payment actions.
- No destructive account actions.
- No unattended execution for high-impact workflows.

## Phase 10: README Completion

Update `README.md` so a new developer can run:

```bash
brew install uv
brew install --cask ollama
ollama pull qwen3.5:9b
ollama pull llama3.1:8b
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e .
uvx browser-use install
uv run python main.py
```

Also include:

- troubleshooting section;
- memory reduction ladder;
- benchmark command;
- explanation that DOM-only is the default;
- warning that Browser Use must be supervised for real workflows.

## Cursor Completion Checklist

Cursor should finish by confirming:

- `pyproject.toml` exists and pins `browser-use==0.13.6`.
- `.env.example` exists.
- `.gitignore` exists.
- `main.py` exists and runs a DOM-only `example.com` task.
- `scripts/check_ollama.sh` exists and is executable.
- `scripts/benchmark.py` exists and writes CSV output.
- `README.md` explains setup, run, benchmark, and safety.
- Syntax checks pass.
- If Ollama is installed and running, the example task has been tested.

## Future Production Fallback

If both local models fail the benchmark, keep Browser Use and Chromium local, but move inference to a remote open-weight model served through an OpenAI-compatible endpoint such as vLLM.

This preserves the open-model requirement while avoiding the 16 GB Mac memory ceiling.

