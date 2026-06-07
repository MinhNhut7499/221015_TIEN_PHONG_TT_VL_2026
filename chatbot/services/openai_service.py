"""OpenAI GPT-4o service for the final arbitration agent (Agent 7).

Agent 7 uses chain-of-thought forcing: the prompt instructs the model to
work through Steps 1-3 before emitting a ```json ... ``` block.
The caller extracts that block with a regex.
"""
import re

from openai import AsyncOpenAI

from app.config import settings
from chatbot.utils.llm_retry import with_retry


_JSON_BLOCK_RE = re.compile(r"```json\s*(\{[\s\S]*?\})\s*```", re.IGNORECASE)
_FALLBACK_JSON_RE = re.compile(r"\{[\s\S]*\}")


class OpenAIService:
    """OpenAI GPT-4o service for final structured output (Agent 7).

    Uses chain-of-thought prompting — the model reasons through Steps 1-3
    before emitting a JSON block. extract_json() parses that block.
    """

    def __init__(self, api_key: str, model: str = "gpt-4o") -> None:
        """Configure the OpenAI client.

        Args:
            api_key: OpenAI API key.
            model: Model name (default: gpt-4o).
        """
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def chat_structured(
        self, prompt: str, image_base64: str | None = None
    ) -> str:
        """Send a CoT-structured prompt and return the full raw response text.

        When ``image_base64`` is provided, the prompt is sent as a multimodal
        message so GPT-4o can inspect the full building image alongside the
        text reasoning. The caller should pass the result to ``extract_json()``
        to get the final JSON decision block.

        Args:
            prompt: Full CoT prompt from build_agent7_prompt().
            image_base64: Optional base64-encoded JPEG of the full building image.

        Returns:
            Full raw text response including the CoT steps and JSON block.

        Raises:
            RuntimeError: If the API returns no content.
        """
        if image_base64:
            user_content: list | str = [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_base64}"
                    },
                },
            ]
        else:
            user_content = prompt
        response = await with_retry(
            lambda: self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": user_content}],
                temperature=0.2,
            ),
            attempts=settings.LLM_MAX_RETRIES + 1,
            base_delay=settings.LLM_RETRY_BASE_DELAY_SEC,
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("OpenAI returned empty response")
        return content.strip()

    @staticmethod
    def extract_json(raw_text: str) -> str:
        """Extract the JSON decision block from Agent 7's CoT response.

        Tries ```json ... ``` markers first, falls back to finding the last
        `{...}` block in the text.

        Args:
            raw_text: Full raw response from chat_structured().

        Returns:
            JSON string extracted from the response.

        Raises:
            ValueError: If no JSON block can be found.
        """
        match = _JSON_BLOCK_RE.search(raw_text)
        if match:
            return match.group(1)
        match = _FALLBACK_JSON_RE.search(raw_text)
        if match:
            return match.group(0)
        raise ValueError(f"No JSON block found in Agent 7 response: {raw_text[:200]}")

    async def is_available(self) -> bool:
        """Return True if the OpenAI API is reachable."""
        try:
            await self.chat_structured("Reply with: ```json\n{\"ok\": true}\n```")
            return True
        except Exception:
            return False
