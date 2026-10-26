import asyncio
import os
import sys

from dotenv import load_dotenv

from ollama_runtime import (
    DEFAULT_CONTEXT_SIZE,
    DEFAULT_MAX_STEPS,
    DEFAULT_MODEL,
    create_agent,
    create_llm,
    wait_for_ollama,
)


async def main() -> int:
    load_dotenv()

    model = os.getenv("OLLAMA_MODEL", DEFAULT_MODEL)
    context_size = int(os.getenv("OLLAMA_NUM_CTX", str(DEFAULT_CONTEXT_SIZE)))
    max_steps = int(os.getenv("AGENT_MAX_STEPS", str(DEFAULT_MAX_STEPS)))

    wait_for_ollama()

    task = """
Open https://example.com.

Return exactly these two facts, then stop:
1. Page title (document title) — expected pattern: Example Domain
2. First visible heading — expected pattern: Example Domain

Allowed domains:
- example.com

Forbidden actions:
- Do not leave example.com.
- Do not download anything.
- Do not submit forms.
- Do not sign in.
- Do not keep extracting after you already have both facts — call done.
- Ask for manual review before irreversible actions.
""".strip()

    agent = create_agent(
        task=task,
        llm=create_llm(model, context_size),
        allowed_domains=["example.com"],
    )

    history = await agent.run(max_steps=max_steps)
    successful = bool(history.is_successful())
    result = history.final_result() or ""

    print(f"Model: {model}")
    print(f"Context: {context_size}")
    print(f"Successful: {successful}")
    print(f"Result: {result}")

    # Soft quality gate for the baseline smoke task.
    lowered = result.lower()
    quality_ok = (
        "example domain" in lowered
        and ("title" in lowered or "heading" in lowered)
    )
    print(f"Quality: {quality_ok}")
    return 0 if successful and quality_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
