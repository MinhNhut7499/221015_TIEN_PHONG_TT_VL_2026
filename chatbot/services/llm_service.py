"""Pluggable LLM service layer.

Design contract
---------------
All concrete LLM integrations (Gemini, OpenAI, local GGUF, etc.) MUST inherit
from BaseLLMService and implement both abstract methods.

To add a new LLM backend:
    1. Create a new file in chatbot/services/ (e.g., gemini_service.py).
    2. Implement BaseLLMService.
    3. Update the factory function get_llm_service() below — no other file changes needed.

The rest of the application only ever calls get_llm_service() and works
against the BaseLLMService interface, so swapping providers is zero-refactor.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


# ── Abstract interface ─────────────────────────────────────────────────────────

class BaseLLMService(ABC):
    """Abstract contract that every LLM service implementation must satisfy."""

    @abstractmethod
    async def analyze_image(
        self,
        image_path: str,
        prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Analyze an architectural image and return a structured result dict.

        Args:
            image_path: Relative or absolute path to the image file.
            prompt: Optional user-supplied natural-language instruction that
                    overrides the default analysis prompt.

        Returns:
            A dict with at minimum the keys:
                - "status": "completed" | "failed"
                - "architectural_style": str
                - "confidence": float (0.0 – 1.0)
                - "description": str
                - "raw_response": Any  (the unprocessed LLM output)
        """

    @abstractmethod
    async def is_available(self) -> bool:
        """Return True if the service is configured and reachable right now."""


# ── Stub implementation ────────────────────────────────────────────────────────

class StubLLMService(BaseLLMService):
    """No-op LLM service used when LLM_API_KEY is not yet configured.

    Returns a clearly-labelled placeholder response so the rest of the
    application can run end-to-end without a real LLM key during development.
    Replace by providing LLM_API_KEY in .env and updating get_llm_service().
    """

    async def analyze_image(
        self,
        image_path: str,
        _prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return a stub response indicating LLM is not yet configured."""
        return {
            "status": "stub",
            "architectural_style": "unknown",
            "confidence": 0.0,
            "description": (
                "LLM analysis is not yet enabled. "
                "Set LLM_API_KEY in .env to activate."
            ),
            "raw_response": None,
            "image_path": image_path,
        }

    async def is_available(self) -> bool:
        """Always returns False — the stub never connects to a real backend."""
        return False


# ── Factory ────────────────────────────────────────────────────────────────────

def get_llm_service() -> BaseLLMService:
    """Return the appropriate LLM service instance based on current configuration.

    Resolution order:
        1. If LLM_API_KEY is set  → instantiate the real provider (to be added).
        2. Otherwise              → return StubLLMService.

    When adding a real provider, replace the comment block below with:
        from chatbot.services.gemini_service import GeminiService
        return GeminiService(api_key=settings.LLM_API_KEY)
    """
    from app.config import settings  # local import avoids circular dependency at startup
    from chatbot.services import provider_credentials

    gemini_cred = provider_credentials.get_credentials("gemini")
    if gemini_cred.key:
        from chatbot.services.gemini_service import GeminiService as _GeminiLLM

        class _GeminiAdapter(BaseLLMService):
            """Thin adapter wrapping GeminiService to satisfy the simple BaseLLMService interface."""

            def __init__(self) -> None:
                self._svc = _GeminiLLM(
                    api_key=gemini_cred.key,
                    model=settings.LLM_MODEL or "gemini-1.5-flash",
                )

            async def analyze_image(
                self,
                image_path: str,
                prompt: Optional[str] = None,
            ) -> Dict[str, Any]:
                """Delegate to GeminiService using the image file at image_path."""
                from chatbot.utils.image_utils import encode_image_base64
                from pathlib import Path
                image_bytes = Path(image_path).read_bytes()
                b64 = encode_image_base64(image_bytes)
                text = await self._svc.generate_with_image(
                    prompt=prompt or "Describe the architectural style of this building.",
                    image_base64=b64,
                )
                return {
                    "status": "completed",
                    "architectural_style": text[:100],
                    "confidence": 0.0,
                    "description": text,
                    "raw_response": text,
                    "image_path": image_path,
                }

            async def is_available(self) -> bool:
                return await self._svc.is_available()

        return _GeminiAdapter()

    return StubLLMService()
