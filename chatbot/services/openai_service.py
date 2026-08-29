"""OpenAI service for the final arbitration agent (Agent 7).

Agent 7 uses chain-of-thought forcing: the prompt instructs the model to
work through Steps 1-3 before emitting a ```json ... ``` block.
The caller extracts that block with a regex.

The model is configured via ``settings.OPENAI_MODEL``. Note that GPT-5.x
reasoning models reject a non-default ``temperature`` (HTTP 400), so this
service never forwards ``temperature`` to the API.
"""
import re

from openai import AsyncOpenAI

from app.config import settings
from chatbot.utils.llm_retry import with_retry


_JSON_BLOCK_RE = re.compile(r"```json\s*(\{[\s\S]*?\})\s*```", re.IGNORECASE)
_FALLBACK_JSON_RE = re.compile(r"\{[\s\S]*\}")


class OpenAIService:
    """OpenAI service for final structured output (Agent 7).

    Uses chain-of-thought prompting — the model reasons through Steps 1-3
    before emitting a JSON block. extract_json() parses that block.
    """

    def __init__(self, api_key: str, model: str = "gpt-5.4-mini") -> None:
        """Configure the OpenAI client.

        Args:
            api_key: OpenAI API key.
            model: Model name (default: gpt-5.4-mini).
        """
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    @property
    def model_name(self) -> str:
        """Return the configured model name (single source for telemetry labels)."""
        return self._model

    async def chat_structured(
        self,
        prompt: str,
        image_base64: str | None = None,
        json_mode: bool = False,
    ) -> str:
        """Send a prompt (optionally with an image) and return the raw response.

        When ``image_base64`` is provided, the prompt is sent as a multimodal
        message so the model can inspect the full building image alongside the
        text. Two callers:
          - Arbiter (Agent 7): ``json_mode=False`` → CoT prose + a ```json```
            block; caller uses ``extract_json()``.
          - Vision panel judge: ``json_mode=True`` → a strict JSON object so the
            verdict is always parseable.

        Args:
            prompt: Full prompt.
            image_base64: Optional base64-encoded JPEG of the full building image.
            json_mode: Force ``response_format={"type": "json_object"}`` (the
                prompt must mention JSON).

        Returns:
            Full raw text response.

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
        extra = {"response_format": {"type": "json_object"}} if json_mode else {}
        response = await with_retry(
            lambda: self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": user_content}],
                **extra,
            ),
            attempts=settings.LLM_MAX_RETRIES + 1,
            base_delay=settings.LLM_RETRY_BASE_DELAY_SEC,
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("OpenAI returned empty response")
        return content.strip()

    async def chat_text(
        self, prompt: str, temperature: float = 0.3, json_mode: bool = True
    ) -> str:
        """Send a text-only prompt and return the raw response (no CoT, no image).

        Used for the OpenAI panel judge in the consensus stage. When
        ``json_mode`` is True the response is forced to a JSON object so it is
        always parseable (the prompt must mention JSON).

        Args:
            prompt: Full text prompt.
            temperature: Accepted for caller compatibility but NOT forwarded to
                the API — GPT-5.x reasoning models reject a non-default
                ``temperature`` (HTTP 400).
            json_mode: Request ``response_format={"type": "json_object"}``.

        Returns:
            Raw text content from the model.

        Raises:
            RuntimeError: If the API returns no content.
        """
        extra = {"response_format": {"type": "json_object"}} if json_mode else {}
        response = await with_retry(
            lambda: self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                **extra,
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
