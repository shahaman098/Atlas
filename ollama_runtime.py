"""Shared Ollama + Browser Use helpers for the local browser agent."""

from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request

from browser_use import Agent, Browser, ChatOllama, Tools

DEFAULT_MODEL = "qwen3.5:9b"
DEFAULT_CONTEXT_SIZE = 6144
DEFAULT_MAX_STEPS = 8
OLLAMA_VERSION_URL = "http://127.0.0.1:11434/api/version"

# Keep only actions local open models can use reliably for DOM-only tasks.
EXCLUDED_ACTIONS = [
    "search",
    "search_page",
    "write_file",
    "replace_file",
    "read_file",
    "upload_file",
    "save_as_pdf",
    "screenshot",
    "evaluate",
    "switch",
    "close",
]

SYSTEM_EXTENSION = """
You are running a supervised DOM-only local browser agent.
Follow ONLY the current user request. Never invent shopping, Reddit, Coursera,
Amazon, Google Shopping, or any other unrelated task.
If a navigation is blocked, stay on an allowed page and finish with extract/done.
Prefer navigate -> extract -> done for read-only tasks.
Never submit forms unless the user request explicitly requires it.
""".strip()


def ollama_options(context_size: int) -> dict[str, int]:
    # Cap generation length so structured-action JSON is less likely to be cut off
    # when the DOM prompt already fills most of the context window.
    return {"num_ctx": context_size, "num_predict": 768}


def ollama_reachable(timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(OLLAMA_VERSION_URL, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return "version" in payload
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return False


def restart_ollama() -> None:
    """Restart the macOS Ollama app when the local API wedges."""
    subprocess.run(["killall", "Ollama"], check=False, capture_output=True)
    time.sleep(2)
    subprocess.run(["open", "-a", "Ollama"], check=False, capture_output=True)


def wait_for_ollama(
    *,
    timeout_seconds: float = 90.0,
    poll_seconds: float = 1.0,
    restart_if_needed: bool = True,
) -> None:
    start = time.monotonic()
    deadline = start + timeout_seconds
    restarted = False
    while time.monotonic() < deadline:
        if ollama_reachable():
            return
        if (
            restart_if_needed
            and not restarted
            and (time.monotonic() - start) >= 20
        ):
            restart_ollama()
            restarted = True
        time.sleep(poll_seconds)

    raise RuntimeError(
        f"Ollama API not reachable at {OLLAMA_VERSION_URL} within {timeout_seconds:.0f}s"
    )


def unload_ollama_models() -> None:
    """Best-effort unload to reduce memory pressure between agent runs."""
    try:
        result = subprocess.run(
            ["ollama", "ps"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return

    lines = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    if len(lines) <= 1:
        return

    for line in lines[1:]:
        model = line.split()[0]
        if model.upper() == "NAME":
            continue
        subprocess.run(
            ["ollama", "stop", model],
            check=False,
            capture_output=True,
            timeout=30,
        )


def create_llm(model: str, context_size: int) -> ChatOllama:
    return ChatOllama(
        model=model,
        ollama_options=ollama_options(context_size),
    )


def create_browser(*, allowed_domains: list[str] | None = None) -> Browser:
    """Isolated Chromium tuned for a 16 GB Mac.

    Default extensions are disabled because Browser Use's bundled uBlock CRX
    currently fails validation and has been associated with tab detach crashes.
    Headless reduces compositor/window memory pressure.
    """
    return Browser(
        headless=True,
        enable_default_extensions=False,
        auto_download_pdfs=False,
        keep_alive=False,
        allowed_domains=allowed_domains,
    )


def create_agent(
    *,
    task: str,
    llm: ChatOllama,
    allowed_domains: list[str] | None = None,
) -> Agent:
    tools = Tools(exclude_actions=EXCLUDED_ACTIONS)
    return Agent(
        task=task,
        llm=llm,
        browser=create_browser(allowed_domains=allowed_domains),
        tools=tools,
        extend_system_message=SYSTEM_EXTENSION,
        use_vision=False,
        use_thinking=False,
        use_judge=False,
        flash_mode=True,
        max_history_items=6,
        max_actions_per_step=1,
        max_failures=3,
        max_clickable_elements_length=6000,
        include_attributes=["id", "name", "type", "placeholder", "aria-label", "title"],
        llm_timeout=180,
        step_timeout=240,
        generate_gif=False,
    )
