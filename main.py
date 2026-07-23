import asyncio
import os

from dotenv import load_dotenv

from ollama_runtime import (
    DEFAULT_CONTEXT_SIZE,
    DEFAULT_MAX_STEPS,
    DEFAULT_MODEL,
    create_agent,
    create_llm,
    wait_for_ollama,
)


async def main() -> None:
    load_dotenv()

    model = os.getenv("OLLAMA_MODEL", DEFAULT_MODEL)
    context_size = int(os.getenv("OLLAMA_NUM_CTX", str(DEFAULT_CONTEXT_SIZE)))
    max_steps = int(os.getenv("AGENT_MAX_STEPS", str(DEFAULT_MAX_STEPS)))

    wait_for_ollama()

    task = """
Open https://example.com.

Return:
1. The page title.
2. The first visible heading.

Allowed domains:
- example.com

Forbidden actions:
- Do not leave example.com.
- Do not download anything.
- Do not submit forms.
- Do not sign in.
- Stop after completing the requested extraction.
- Ask for manual review before irreversible actions.
""".strip()

    agent = create_agent(
        task=task,
        llm=create_llm(model, context_size),
        allowed_domains=["example.com"],
    )

    history = await agent.run(max_steps=max_steps)

    print(f"Model: {model}")
    print(f"Successful: {history.is_successful()}")
    print(f"Result: {history.final_result()}")


if __name__ == "__main__":
    asyncio.run(main())
