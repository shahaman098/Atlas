#!/usr/bin/env python3
"""Run DOM-only Browser Use benchmark tasks and append CSV results."""

from __future__ import annotations

import asyncio
import csv
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ollama_runtime import (  # noqa: E402
    DEFAULT_CONTEXT_SIZE,
    create_agent,
    create_llm,
    ollama_reachable,
    unload_ollama_models,
    wait_for_ollama,
)

RESULTS_DIR = ROOT / "results"
DEFAULT_RESULTS_CSV = RESULTS_DIR / "benchmark-runs.csv"
CSV_FIELDS = [
    "timestamp",
    "model",
    "context_size",
    "task_id",
    "run_number",
    "success",
    "final_result",
    "error",
    "steps",
]

DEFAULT_MODELS = ("qwen3.5:9b", "llama3.1:8b")
DEFAULT_REPEATS = 3
DEFAULT_MAX_STEPS = 12
DEFAULT_COOLDOWN_SECONDS = 8

TASKS: dict[str, str] = {
    "1": """
Open https://example.com and return its title and first visible heading.

Allowed domains:
- example.com

Forbidden actions:
- Do not leave example.com.
- Do not download files.
- Do not submit forms.
- Do not sign in.
- Stop after max_steps.
- Ask for manual review before irreversible actions.
""".strip(),
    "2": """
Open https://docs.python.org/3/
Return only the page title.

Allowed domains:
- docs.python.org

Forbidden actions:
- Do not download files.
- Do not submit forms.
- Do not sign in.
- Do not leave docs.python.org.
- Stop after max_steps.
- Ask for manual review before irreversible actions.
""".strip(),
    "3": """
Open https://docs.docker.com/get-started/
Return the page title and one short quoted phrase from the page that contains the word Docker.

Allowed domains:
- docs.docker.com

Forbidden actions:
- Do not download files.
- Do not submit forms.
- Do not sign in.
- Stop after max_steps.
- Ask for manual review before irreversible actions.
""".strip(),
    "4": """
Open https://httpbin.org/forms/post
Fill these fields only, then stop without submitting:
- Customer name: Ada Lovelace
- Telephone: 555-0100
- E-mail address: ada@example.com

Report which fields you completed. Leave the form unsubmitted.

Allowed domains:
- httpbin.org

Forbidden actions:
- Do not click submit / do not submit the form.
- Do not download files.
- Do not sign in.
- Stop after max_steps.
- Ask for manual review before irreversible actions.
""".strip(),
    "5": """
Open https://quotes.toscrape.com/tag/humor/
Extract the first visible quote text and its author.
If that tag page is unavailable, open https://quotes.toscrape.com/ and extract one quote + author.

Allowed domains:
- quotes.toscrape.com

Forbidden actions:
- Do not download files.
- Do not submit forms.
- Do not sign in.
- Stop after max_steps.
- Ask for manual review before irreversible actions.
""".strip(),
}

ALLOWED_DOMAINS: dict[str, list[str]] = {
    "1": ["example.com"],
    "2": ["docs.python.org"],
    "3": ["docs.docker.com"],
    "4": ["httpbin.org"],
    "5": ["quotes.toscrape.com"],
}


def _env_models() -> list[str]:
    raw = os.getenv("BENCHMARK_MODELS", "").strip()
    if not raw:
        return list(DEFAULT_MODELS)
    return [part.strip() for part in raw.split(",") if part.strip()]


def _env_task_ids() -> list[str]:
    raw = os.getenv("BENCHMARK_TASK_IDS", "").strip()
    if not raw:
        return list(TASKS)
    task_ids = [part.strip() for part in raw.split(",") if part.strip()]
    unknown = [task_id for task_id in task_ids if task_id not in TASKS]
    if unknown:
        raise SystemExit(f"Unknown BENCHMARK_TASK_IDS: {', '.join(unknown)}")
    return task_ids


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _results_csv() -> Path:
    raw = os.getenv("BENCHMARK_CSV", "").strip()
    if raw:
        path = Path(raw)
        return path if path.is_absolute() else ROOT / path
    return DEFAULT_RESULTS_CSV


def _ensure_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
            writer.writeheader()


def _append_row(path: Path, row: dict[str, object]) -> None:
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writerow(row)


def _step_count(history: object) -> int | str:
    for attr in ("number_of_steps", "steps"):
        value = getattr(history, attr, None)
        if callable(value):
            try:
                return int(value())
            except Exception:
                continue
        if isinstance(value, int):
            return value
        if isinstance(value, list):
            return len(value)
    action_history = getattr(history, "action_history", None)
    if callable(action_history):
        try:
            actions = action_history()
            if isinstance(actions, list):
                return len(actions)
        except Exception:
            pass
    return ""


def _prepare_ollama(cooldown_seconds: int) -> None:
    unload_ollama_models()
    if cooldown_seconds > 0:
        time.sleep(cooldown_seconds)
    wait_for_ollama(timeout_seconds=180.0, restart_if_needed=True)
    if not ollama_reachable():
        raise RuntimeError("Ollama became unreachable after wait")


async def _run_once(
    *,
    model: str,
    context_size: int,
    task_id: str,
    run_number: int,
    max_steps: int,
    cooldown_seconds: int,
    results_csv: Path,
) -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    task = TASKS[task_id]
    success = False
    final_result = ""
    error = ""
    steps: int | str = ""

    try:
        _prepare_ollama(cooldown_seconds)
        agent = create_agent(
            task=task,
            llm=create_llm(model, context_size),
            allowed_domains=ALLOWED_DOMAINS[task_id],
        )
        history = await agent.run(max_steps=max_steps)
        success = bool(history.is_successful())
        final_result = history.final_result() or ""
        steps = _step_count(history)
        if not success and not error:
            error = "agent_reported_unsuccessful"
    except Exception as exc:  # noqa: BLE001 - benchmark must capture failures
        error = f"{type(exc).__name__}: {exc}"
    finally:
        unload_ollama_models()

    _append_row(
        results_csv,
        {
            "timestamp": timestamp,
            "model": model,
            "context_size": context_size,
            "task_id": task_id,
            "run_number": run_number,
            "success": success,
            "final_result": final_result,
            "error": error,
            "steps": steps,
        },
    )
    status = "ok" if success else "fail"
    print(
        f"[{status}] model={model} task={task_id} run={run_number} "
        f"error={error or '-'}",
        flush=True,
    )


async def main() -> None:
    load_dotenv(ROOT / ".env")

    models = _env_models()
    task_ids = _env_task_ids()
    repeats = _env_int("BENCHMARK_REPEATS", DEFAULT_REPEATS)
    context_size = _env_int("OLLAMA_NUM_CTX", DEFAULT_CONTEXT_SIZE)
    max_steps = _env_int("AGENT_MAX_STEPS", DEFAULT_MAX_STEPS)
    cooldown_seconds = _env_int("BENCHMARK_COOLDOWN_SECONDS", DEFAULT_COOLDOWN_SECONDS)
    results_csv = _results_csv()

    if repeats < 1:
        raise SystemExit("BENCHMARK_REPEATS must be >= 1")

    wait_for_ollama(restart_if_needed=True)
    _ensure_csv(results_csv)
    print(
        f"Writing results to {results_csv}\n"
        f"models={models} tasks={task_ids} repeats={repeats} "
        f"context={context_size} max_steps={max_steps} "
        f"cooldown={cooldown_seconds}s",
        flush=True,
    )

    for model in models:
        for task_id in task_ids:
            for run_number in range(1, repeats + 1):
                await _run_once(
                    model=model,
                    context_size=context_size,
                    task_id=task_id,
                    run_number=run_number,
                    max_steps=max_steps,
                    cooldown_seconds=cooldown_seconds,
                    results_csv=results_csv,
                )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        raise SystemExit(130)
