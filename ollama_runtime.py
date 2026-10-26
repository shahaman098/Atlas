"""Shared Ollama + Browser Use helpers for the local browser agent."""

from __future__ import annotations

import json
import re
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, TypeVar, overload

from browser_use import Agent, Browser, ChatOllama, Tools
from browser_use.llm.exceptions import ModelProviderError
from browser_use.llm.messages import BaseMessage
from browser_use.llm.ollama.serializer import OllamaMessageSerializer
from browser_use.llm.views import ChatInvokeCompletion
from pydantic import BaseModel

DEFAULT_MODEL = "qwen3.5:9b"
FALLBACK_MODEL = "llama3.1:8b"
DEFAULT_CONTEXT_SIZE = 8192
DEFAULT_MAX_STEPS = 10
OLLAMA_VERSION_URL = "http://127.0.0.1:11434/api/version"
OLLAMA_HOST = "http://127.0.0.1:11434"

T = TypeVar("T", bound=BaseModel)

_NARRATIVE_MARKERS = (
    "successfully navigated",
    "previous step",
    "browser state shows",
    "i have extracted",
    "both required",
    "page has loaded",
    "page loaded",
    "as requested",
    "task requires",
    "full content visible",
)


def _done_text_from_memory(memory_text: str) -> str:
    """Prefer compact title/heading/quote lines when repairing empty actions."""
    title_m = re.search(
        r"(?:page\s+|document\s+)?title(?:\s+\w+){0,4}\s*[:']?\s*['\"]([^'\"]+)['\"]",
        memory_text,
        re.I,
    )
    head_m = re.search(
        r"(?:first\s+visible\s+)?heading(?:\s+text)?(?:\s+\w+){0,4}\s*[:']?\s*['\"]([^'\"]+)['\"]",
        memory_text,
        re.I,
    )
    quote_m = re.search(
        r"(?:first\s+visible\s+)?quote(?:\s+text)?(?:\s+\w+){0,4}\s*[:']?\s*[\"“](.+?)[\"”]",
        memory_text,
        re.I | re.S,
    )
    author_m = re.search(
        r"(?:by|author)\s*[:']?\s*['\"]?([A-Z][^'\"\n,]{1,80})",
        memory_text,
        re.I,
    )

    title = title_m.group(1).strip() if title_m else None
    heading = head_m.group(1).strip() if head_m else None
    quote = " ".join(quote_m.group(1).split()) if quote_m else None
    author = author_m.group(1).strip().rstrip(".") if author_m else None

    if title and heading:
        return f"Page title: {title}\nFirst visible heading: {heading}"
    if title:
        return f"Page title: {title}"
    if heading:
        return f"First visible heading: {heading}"
    if quote and author:
        return f'Quote: "{quote}"\nAuthor: {author}'
    if quote:
        return f'Quote: "{quote}"'
    return memory_text


def _should_compact_done_text(text: str) -> bool:
    lowered = text.lower()
    if len(text) > 140:
        return True
    return any(marker in lowered for marker in _NARRATIVE_MARKERS)


def _normalize_done_item(item: dict[str, Any], memory_text: str) -> dict[str, Any]:
    done = item.get("done")
    if not isinstance(done, dict):
        return item
    text = done.get("text")
    if isinstance(text, str):
        text = text.replace("\\n", "\n").strip()
    if not isinstance(text, str) or not text:
        if memory_text:
            return {
                **item,
                "done": {
                    **done,
                    "text": _done_text_from_memory(memory_text),
                    "success": done.get("success", True),
                },
            }
        return item

    compact = _done_text_from_memory(f"{memory_text}\n{text}")
    if compact and compact != memory_text and _should_compact_done_text(text):
        text = compact
    return {
        **item,
        "done": {
            **done,
            "text": text,
            "success": done.get("success", True),
        },
    }


def _repair_agent_json(completion: str) -> str:
    """Fix common local-model schema mistakes before Pydantic validation.

    Qwen3.5 frequently returns a filled `memory` with `"action": []`, which
    Browser Use rejects (action min_items=1) and surfaces as empty-action
    / PydanticUndefined failures.
    """
    text = (completion or "").strip()
    if not text:
        return completion
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return completion
    if not isinstance(data, dict):
        return completion

    action = data.get("action")
    memory = data.get("memory")
    memory_text = memory.strip() if isinstance(memory, str) else ""
    done_text = (
        _done_text_from_memory(memory_text) if memory_text else "Task progress recorded."
    )

    # action should be a non-empty list of action objects.
    if isinstance(action, dict):
        data["action"] = [action]
        action = data["action"]
    if action is None:
        data["action"] = []
        action = data["action"]
    if isinstance(action, list) and len(action) == 0 and memory_text:
        data["action"] = [{"done": {"text": done_text, "success": True}}]
    elif isinstance(action, list):
        fixed: list[Any] = []
        for item in action:
            if item is None:
                continue
            if isinstance(item, dict) and item:
                fixed.append(_normalize_done_item(item, memory_text))
            elif isinstance(item, str) and item.strip():
                fixed.append({"done": {"text": item.strip(), "success": True}})
        if not fixed and memory_text:
            fixed = [{"done": {"text": done_text, "success": True}}]
        data["action"] = fixed

    if "memory" not in data or data["memory"] is None:
        data["memory"] = memory_text or "Continuing task."

    return json.dumps(data)


@dataclass
class ChatOllamaLocal(ChatOllama):
    """ChatOllama bound for local open models.

    Qwen3.5 supports Ollama "thinking" tokens. Leaving think enabled often
    burns `num_predict` on reasoning and returns empty `message.content`,
    which breaks Browser Use action JSON. Default think=False.
    """

    think: bool = False

    @overload
    async def ainvoke(
        self, messages: list[BaseMessage], output_format: None = None, **kwargs: Any
    ) -> ChatInvokeCompletion[str]: ...

    @overload
    async def ainvoke(
        self, messages: list[BaseMessage], output_format: type[T], **kwargs: Any
    ) -> ChatInvokeCompletion[T]: ...

    async def ainvoke(
        self,
        messages: list[BaseMessage],
        output_format: type[T] | None = None,
        **kwargs: Any,
    ) -> ChatInvokeCompletion[T] | ChatInvokeCompletion[str]:
        ollama_messages = OllamaMessageSerializer.serialize_messages(messages)
        try:
            chat_kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": ollama_messages,
                "options": self.ollama_options,
                "think": self.think,
            }
            if output_format is not None:
                chat_kwargs["format"] = output_format.model_json_schema()

            response = await self.get_client().chat(**chat_kwargs)
            completion = response.message.content or ""

            if output_format is None:
                return ChatInvokeCompletion(completion=completion, usage=None)

            repaired = _repair_agent_json(completion)
            try:
                parsed = output_format.model_validate_json(repaired)
                return ChatInvokeCompletion(completion=parsed, usage=None)
            except Exception:
                # One corrective retry for stubborn empty/malformed action arrays.
                retry_messages = [
                    *ollama_messages,
                    {"role": "assistant", "content": completion},
                    {
                        "role": "user",
                        "content": (
                            'Invalid output: `action` must be a non-empty JSON array '
                            "with exactly one action object. If the task is complete, "
                            'return {"memory":"...","action":[{"done":{"text":"...","success":true}}]}. '
                            "Keep done.text short and factual only."
                        ),
                    },
                ]
                retry_kwargs = dict(chat_kwargs)
                retry_kwargs["messages"] = retry_messages
                response2 = await self.get_client().chat(**retry_kwargs)
                repaired2 = _repair_agent_json(response2.message.content or "")
                parsed2 = output_format.model_validate_json(repaired2)
                return ChatInvokeCompletion(completion=parsed2, usage=None)
        except Exception as e:
            raise ModelProviderError(message=str(e), model=self.name) from e


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
You are a supervised DOM-only local browser agent optimized for reliability.

Hard rules:
- Follow ONLY the current user request.
- Never invent shopping, Reddit, Coursera, Amazon, Google Shopping, or unrelated sites.
- Never submit forms, download files, or sign in unless the user explicitly asks.
- Never return an empty action array. Always return exactly one concrete action object.
- When the requested facts are already known, call done immediately (do not return action: []).
- Stay inside allowed domains.

Page-loading playbook:
1) navigate to the target URL if not already there
2) if the DOM is empty or shows a temporary error (e.g. 503), wait once, then navigate again
3) only then extract or fill fields
4) call done

Read-only extraction:
- Prefer facts already visible in browser state over another extract call.
- Page title = document/browser title from state.
- First visible heading = first on-page heading text.

Form tasks:
- Fill only the requested fields.
- Never click submit.
- If the form page is unavailable after one wait+retry, done with success=false and say why.

done.text style:
- Short factual lines only. No narration ("successfully navigated", "browser state shows").
- Good: "Page title: Example Domain\\nFirst visible heading: Example Domain"
- Good: "Quote: \\"...\\"\\nAuthor: Jane Austen"
- Good: "Filled: Customer name, Telephone, E-mail address. Form not submitted."
""".strip()


def ollama_options(context_size: int) -> dict[str, int | float]:
    # Conservative generation for reliable structured Browser Use actions.
    # Cap length so JSON is less likely to be cut off on heavy DOM prompts.
    return {
        "num_ctx": context_size,
        "num_predict": 1024,
        "temperature": 0.1,
        "top_p": 0.9,
        "repeat_penalty": 1.1,
    }


def ollama_reachable(timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(OLLAMA_VERSION_URL, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return "version" in payload
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return False


def restart_ollama() -> None:
    """Restart local Ollama when the API wedges (app or `ollama serve`)."""
    subprocess.run(["killall", "Ollama"], check=False, capture_output=True)
    subprocess.run(["killall", "ollama"], check=False, capture_output=True)
    time.sleep(2)
    opened = subprocess.run(
        ["open", "/Applications/Ollama.app"],
        check=False,
        capture_output=True,
    )
    if opened.returncode != 0:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )


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


def create_llm(model: str, context_size: int) -> ChatOllamaLocal:
    """Build local ChatOllama with project context defaults and think disabled."""
    return ChatOllamaLocal(
        model=model,
        host=OLLAMA_HOST,
        ollama_options=ollama_options(context_size),
        think=False,
    )


def create_browser(*, allowed_domains: list[str] | None = None) -> Browser:
    """Isolated Chromium tuned for a 24 GB Apple Silicon Mac.

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
    llm: ChatOllamaLocal,
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
        max_failures=4,
        max_clickable_elements_length=5000,
        include_attributes=["id", "name", "type", "placeholder", "aria-label", "title"],
        llm_timeout=180,
        step_timeout=240,
        generate_gif=False,
    )
