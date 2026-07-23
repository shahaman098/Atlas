# Atlas — Local Browser Use Agent

Personal, local-first browser automation on a 16 GB Apple Silicon Mac using Browser Use + Ollama open models.

## End goal

A **reliable supervised browser agent** that runs on the owner's machine, uses **open-weight models**, and can complete short real web tasks without handing control to proprietary cloud LLMs or the owner's signed-in Chrome profile.

In practice that means:

- You describe a constrained task.
- An isolated Chromium session exposes DOM/accessibility state.
- A local open model chooses **one action per step**.
- The run stays domain-locked, supervised, and reviewable.
- Results are measurable (benchmark CSV + clear success/failure).

**Not the goal:** an unattended general web agent, shopping/payment bot, or anything that silently uses your normal logged-in browser.

## Goals

### Now

- Keep a reproducible clone → install → run path across machines and Cursor sessions.
- Stay DOM-only (`use_vision=False`) until the baseline is stable.
- Fit a 16 GB Mac: conservative context, one model loaded, recover when Ollama wedges.
- Pass the acceptance gate: **≥12 successful runs out of 15** for the chosen local model, with no form submits, downloads, sign-ins, or uncontrolled navigation.
- Prefer `qwen3.5:9b`; fall back to `llama3.1:8b` only if measurements say so.

### Next

- Add a small pack of personal, domain-locked supervised tasks once the benchmark is green.
- Optionally enable vision for canvas/maps/poor-accessibility pages after DOM acceptance.
- If both local models fail acceptance, keep the browser local and move inference to a remote open-weight OpenAI-compatible endpoint (e.g. vLLM).

### Always

- Open-model-first.
- Human-supervised for real workflows.
- Explicit allowed domains + forbidden actions on every task.
- No irreversible actions without manual review.

## Runtime path

```text
Python Browser Use agent
-> isolated headless Chromium
-> DOM / accessibility-tree browser state
-> local Ollama model
-> one browser action per step
-> supervised, short, domain-constrained tasks
```

## Docs for humans and Cursor agents

| Doc | Purpose |
| --- | --- |
| [AGENTS.md](AGENTS.md) | **Start here in Cursor** — end goal, milestones, constraints, layout, lessons |
| [README.md](README.md) | Setup, run, benchmark, troubleshooting |
| [CURSOR_IMPLEMENTATION_PLAN.md](CURSOR_IMPLEMENTATION_PLAN.md) | Phased plan and acceptance details |
| [.cursor/rules/](.cursor/rules/) | Always-on Cursor rules for this repo |

On a new Cursor machine: clone → open folder → agent should load `AGENTS.md` + `.cursor/rules` automatically.

## Resources another machine needs

These are **not** committed in git (too large / machine-local). A fresh clone must obtain them:

| Resource | Why | Approx size |
| --- | --- | --- |
| Homebrew | Installs `uv` + Ollama on macOS | small |
| `uv` + Python 3.12 | Project env / deps | small |
| Ollama app + local API | Runs open models on `127.0.0.1` | app install |
| `qwen3.5:9b` model | Primary local model | ~6.6 GB |
| `llama3.1:8b` model | Fallback local model | ~4.9 GB |
| Browser Use Chromium | Isolated browser binary | Playwright cache |
| Project `.venv` | Python packages including `browser-use==0.13.6` | hundreds of MB |

## Recommended setup (one command)

Requires Homebrew on macOS. Then:

```bash
./scripts/bootstrap.sh
```

That script will, as needed:

1. Install `uv`
2. Install/start Ollama
3. Create `.venv` with Python 3.12 and install this package
4. Run `uvx browser-use install` (Chromium)
5. `ollama pull` primary + fallback models
6. Copy `.env.example` → `.env` if missing
7. Run `./scripts/doctor.sh`

Useful flags:

```bash
SKIP_MODELS=1 ./scripts/bootstrap.sh   # deps/browser only; pull models later
SKIP_BROWSER=1 ./scripts/bootstrap.sh  # skip Chromium install
./scripts/doctor.sh                    # check what’s missing without installing
./scripts/check_ollama.sh              # API + model list only
```

### Manual setup (equivalent)

```bash
brew install uv
brew install --cask ollama
# open Ollama once from Applications
ollama pull qwen3.5:9b
ollama pull llama3.1:8b
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e .
uvx browser-use install
cp .env.example .env
./scripts/doctor.sh
```

Optional Ollama memory tuning (then quit/reopen Ollama):

```bash
launchctl setenv OLLAMA_FLASH_ATTENTION 1
launchctl setenv OLLAMA_KV_CACHE_TYPE q8_0
launchctl setenv OLLAMA_MAX_LOADED_MODELS 1
launchctl setenv OLLAMA_NUM_PARALLEL 1
launchctl setenv OLLAMA_CONTEXT_LENGTH 8192
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

- Prefer `qwen3.5:9b` when it completes cleanly.
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

Summarize:

```bash
uv run python scripts/summarize_benchmark.py
```

Acceptance gate: the chosen model should reach at least **12 successful runs out of 15**, with no form submissions, downloads, sign-ins, or uncontrolled navigation.

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
