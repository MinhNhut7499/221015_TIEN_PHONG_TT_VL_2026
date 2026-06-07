"""Gemini Flash LLM service for vision-based agents (Agent 1 and Agent 2).

Used by pipeline_runner.py for:
- Agent 1: geometric feature description (vision + text)
- Agent 2: style probability distribution (vision + text, ×3 Monte Carlo)
"""
import base64

from google import genai
from google.genai import types

from app.config import settings
from chatbot.utils.llm_retry import with_retry


class GeminiService:
    """Google Gemini Flash vision service.

    Uses the google-genai SDK (async-native) for vision + text generation.
    """

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash") -> None:
        """Configure the Gemini client.

        Args:
            api_key: Google AI Studio API key.
            model: Gemini model name (default: gemini-2.5-flash).
        """
        self._client = genai.Client(api_key=api_key)
        self._model_name = model

    async def generate_with_image(
        self,
        prompt: str,
        image_base64: str,
        temperature: float = 0.7,
    ) -> str:
        """Send a prompt with an embedded image to Gemini and return raw text.

        Args:
            prompt: Text instruction for the model.
            image_base64: Base64-encoded JPEG image string.
            temperature: Sampling temperature (higher = more creative).

        Returns:
            Raw text response from Gemini.

        Raises:
            RuntimeError: If Gemini returns an empty or blocked response.
        """
        image_bytes = base64.b64decode(image_base64)
        image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")

        response = await with_retry(
            lambda: self._client.aio.models.generate_content(
                model=self._model_name,
                contents=[prompt, image_part],
                config=types.GenerateContentConfig(temperature=temperature),
            ),
            attempts=settings.LLM_MAX_RETRIES + 1,
            base_delay=settings.LLM_RETRY_BASE_DELAY_SEC,
        )

        if not response.text:
            raise RuntimeError(
                f"Gemini returned empty response for model {self._model_name}"
            )
        return response.text.strip()

    async def is_available(self) -> bool:
        """Return True if the Gemini API key is set and the service is reachable."""
        try:
            await self.generate_with_image(
                prompt="Reply with the single word: ok",
                image_base64=_MINIMAL_JPEG_B64,
                temperature=0.0,
            )
            return True
        except Exception:
            return False


# Minimal 1×1 white JPEG for health-check calls (avoids network overhead).
_MINIMAL_JPEG_B64 = (
    "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8U"
    "HRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgN"
    "DRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIy"
    "MjL/wAARCAABAAEDASIAAhEBAxEB/8QAFgABAQEAAAAAAAAAAAAAAAAABgUE/8QAFBABAA"
    "AAAAAAAAAAAAAAAAAAAP/EABQBAQAAAAAAAAAAAAAAAAAAAAD/xAAUEQEAAAAAAAAAAAAA"
    "AAAAAAAA/9oADAMBAAIRAxEAPwCwABmX/9k="
)
