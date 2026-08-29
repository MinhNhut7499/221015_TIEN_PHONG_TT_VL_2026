"""xAI Grok service — the third VISION panel judge.

xAI exposes an OpenAI-compatible API, so this reuses the ``openai`` SDK with a
custom ``base_url``. Grok can inspect images, which lets the consensus panel be
three symmetric image-seeing judges (Gemini / OpenAI / Grok). Removing the old
text-only judge makes equal judge weights legitimate (decision 2026-06-19).
"""
from openai import AsyncOpenAI

from app.config import settings
from chatbot.utils.llm_retry import with_retry


class GrokService:
    """xAI Grok service for vision-grounded panel judging."""

    def __init__(
        self,
        api_key: str,
        model: str = "grok-4-vision",
        base_url: str = "https://api.x.ai/v1",
    ) -> None:
        """Configure the xAI client (OpenAI-compatible).

        Args:
            api_key: xAI API key (``settings.XAI_API_KEY``).
            model: Grok vision model name.
            base_url: xAI API base URL (OpenAI-compatible endpoint).
        """
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
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
        temperature: float = 0.4,
    ) -> str:
        """Send a prompt (optionally with an image) and return the raw response.

        Used by the Grok vision panel judge with ``json_mode=True`` so the
        verdict is always a parseable JSON object.

        Args:
            prompt: Full prompt.
            image_base64: Optional base64-encoded JPEG of the full building image.
            json_mode: Force ``response_format={"type": "json_object"}`` (the
                prompt must mention JSON).
            temperature: Sampling temperature (xAI accepts it).

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
                temperature=temperature,
                **extra,
            ),
            attempts=settings.LLM_MAX_RETRIES + 1,
            base_delay=settings.LLM_RETRY_BASE_DELAY_SEC,
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("Grok returned empty response")
        return content.strip()

    async def is_available(self) -> bool:
        """Return True if the xAI API is reachable."""
        try:
            await self.chat_structured(
                'Reply with a JSON object {"ok": true}.', json_mode=True
            )
            return True
        except Exception:
            return False
