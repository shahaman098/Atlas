# Local Browser Use Agent

Reproducible local Browser Use automation for a 16 GB M1 Pro Mac using Ollama-hosted open models.

Runtime path:

```text
Python Browser Use agent
-> isolated Chromium session
-> DOM/accessibility-tree browser state
-> local Ollama model
-> one browser action per step
-> supervised, short, domain-constrained tasks
```

DOM-only is the default. Screenshots / vision stay disabled until the baseline benchmark is stable.

## Docs for humans and Cursor agents

| Doc | Purpose |
| --- | --- |
| [AGENTS.md](AGENTS.md) | **Start here in Cursor** — project context, constraints, layout, lessons learned |
| [README.md](README.md) | Setup, run, benchmark, troubleshooting |
| [CURSOR_IMPLEMENTATION_PLAN.md](CURSOR_IMPLEMENTATION_PLAN.md) | Original phased plan and acceptance gate |
| [.cursor/rules/](.cursor/rules/) | Always-on Cursor rules for this repo |

On a new Cursor machine: clone → open folder → agent should load `AGENTS.md` + `.cursor/rules` automatically.

## Goals

- Start DOM-first (`use_vision=False`).
- Use one action per step.
- Keep the first model choice conservative.
- Run in an isolated browser session by default.
- Treat real workflows as supervised, not unattended production automation.

## Recommended setup

Install the tools:

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

Quit and reopen Ollama after setting those variables.

Pull models:

```bash
ollama pull qwen3.5:9b
ollama pull llama3.1:8b
```

Verify Ollama:

```bash
./scripts/check_ollama.sh
```

Create the project environment:

```bash
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e .
uvx browser-use install
```

## Environment

Copy `.env.example` to `.env` if you want overrides:

```env
OLLAMA_MODEL=qwen3.5:9b
OLLAMA_NUM_CTX=6144
AGENT_MAX_STEPS=8
```

Default context is `6144` on this 16 GB machine. `8192` can wedge Ollama on heavier pages.

## Run

```bash
uv run python main.py
```

Fallback model:

```bash
OLLAMA_MODEL=llama3.1:8b uv run python main.py
```

## Memory reduction ladder

If the machine swaps, Ollama disconnects, Chromium tabs detach, or the model loops / times out:

```bash
# restart Ollama if the API wedges
killall Ollama; open -a Ollama
./scripts/check_ollama.sh

OLLAMA_NUM_CTX=6144 uv run python main.py
OLLAMA_MODEL=qwen3.5:9b OLLAMA_NUM_CTX=4096 uv run python main.py
OLLAMA_MODEL=llama3.1:8b OLLAMA_NUM_CTX=4096 uv run python main.py
```

Selection logic:

- Prefer `qwen3.5:9b` when it completes cleanly (it correctly solved `example.com` in baseline testing).
- Prefer `llama3.1:8b` only if Qwen repeatedly times out, wedges Ollama, or produces malformed actions — and still verify the final answer; Llama can hallucinate off-task content under pressure.
- Close other heavy apps before benchmarks; a 16 GB Mac can swap hard with Chromium + a 9B model loaded.

## Benchmark

Run the fixed DOM-only task suite and append CSV rows to `results/benchmark-runs.csv`:

```bash
uv run python scripts/benchmark.py
```

Overrides:

```bash
BENCHMARK_MODELS=qwen3.5:9b,llama3.1:8b \
BENCHMARK_TASK_IDS=1,2,3,4,5 \
BENCHMARK_REPEATS=3 \
BENCHMARK_COOLDOWN_SECONDS=5 \
OLLAMA_NUM_CTX=6144 \
uv run python scripts/benchmark.py
```

Smoke one cheap task:

```bash
BENCHMARK_MODELS=qwen3.5:9b BENCHMARK_TASK_IDS=1 BENCHMARK_REPEATS=1 uv run python scripts/benchmark.py
```

Acceptance gate (from the plan): the chosen model should reach at least 12 successful runs out of 15 attempts, with no form submissions, downloads, sign-ins, or uncontrolled navigation.

## Safety

Every real task string should state:

- Allowed domains
- Forbidden actions
- Do not submit forms
- Do not download files
- Do not sign in
- Stop after max_steps
- Ask for manual review before irreversible actions

Initial policy:

- Isolated headless Chromium only (no system Chrome profile yet).
- Default browser extensions disabled (bundled uBlock CRX currently fails validation).
- No passwords in prompts.
- No payment or destructive account actions.
- No unattended high-impact workflows.

## Troubleshooting

| Symptom | What to try |
| --- | --- |
| `Connection refused` to Ollama | Open the Ollama app, then run `./scripts/check_ollama.sh`. |
| Model not found | `ollama pull qwen3.5:9b` or `ollama pull llama3.1:8b`. |
| Slow / swapping on 16 GB | Drop context via the memory reduction ladder; keep only one model loaded. |
| Ollama API dies mid-run | Restart the Ollama app (`killall Ollama; open -a Ollama`), then `./scripts/check_ollama.sh`. Prefer `OLLAMA_NUM_CTX=6144` or `4096`. |
| Chromium tab detach / CDP refused | Memory pressure. Quit other apps, restart Ollama, retry with lower `OLLAMA_NUM_CTX`. |
| Malformed actions / loops | Keep `max_actions_per_step=1`, shorten the task, or switch to `llama3.1:8b`. |
| Browser binary missing | Re-run `uvx browser-use install`. |
| Vision enabled early | Do not. Keep `use_vision=False` until DOM-only benchmarks pass. |

## Notes

- Keep `use_vision=False` until the DOM-only flow is stable.
- Keep `max_actions_per_step=1`.
- Keep `max_history_items=6` (Browser Use 0.13.6 requires `> 5`).
- Use `Browser.from_system_chrome()` only later, after you are comfortable with the isolated default session.
- Browser Use must stay supervised for real workflows.
