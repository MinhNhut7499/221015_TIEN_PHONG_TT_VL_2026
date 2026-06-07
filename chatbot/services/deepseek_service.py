"""DeepSeek text LLM service for bulk text agents (3b, 4, 5, 6).

DeepSeek exposes an OpenAI-compatible API, so we reuse the openai SDK
with a custom base_url. All calls are text-only (no vision).
"""
from openai import AsyncOpenAI

from app.config import settings
from chatbot.utils.llm_retry import with_retry


class DeepSeekService:
    """DeepSeek chat service using the OpenAI-compatible API.

    Used by pipeline_runner.py for agents that require text reasoning:
    Agent 3b (contradiction parse), Agent 4 (per-component conclusion),
    Agent 5 (primary advocate), Agent 6 (alternative hypothesist).
    """

    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        """Configure the DeepSeek client.

        Args:
            api_key: DeepSeek API key.
            base_url: DeepSeek API base URL (default: https://api.deepseek.com/v1).
            model: Model name (default: deepseek-chat).
        """
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    async def chat(self, prompt: str, temperature: float = 0.3) -> str:
        """Send a single-turn text prompt and return the raw response text.

        Args:
            prompt: Full prompt string (system + user combined as user message).
            temperature: Sampling temperature (lower = more deterministic).

        Returns:
            Raw text content from DeepSeek.

        Raises:
            RuntimeError: If the API returns no content.
        """
        response = await with_retry(
            lambda: self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
            ),
            attempts=settings.LLM_MAX_RETRIES + 1,
            base_delay=settings.LLM_RETRY_BASE_DELAY_SEC,
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("DeepSeek returned empty response")
        return content.strip()

    async def is_available(self) -> bool:
        """Return True if the DeepSeek API is reachable."""
        try:
            await self.chat("Reply with the single word: ok", temperature=0.0)
            return True
        except Exception:
            return False
