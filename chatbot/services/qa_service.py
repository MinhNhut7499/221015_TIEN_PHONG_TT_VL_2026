"""Grounded follow-up Q&A over a single stored analysis result.

Backs ``POST /analyze/{image_id}/ask``. Given the full stored analysis
(AnalyzeResponse-shaped dict) and a user question, it builds a context-bound
prompt (evidence sheet + mixture + judge panel + KB descriptions of the
candidate styles) and asks a text LLM to answer in "gated" mode: strictly from
the analysis for image-specific questions, flagged reference knowledge for
general architecture questions, and a polite decline for off-topic questions.

No new state is persisted — the conversation is stateless (the client sends the
prior turns), so this adds no DB schema change.
"""
import logging
from typing import Any, Dict, List, Optional

from app.config import settings
from chatbot.services.deepseek_service import DeepSeekService
from chatbot.services.style_kb_service import get_style_kb
from chatbot.utils.prompt_builder import build_qa_prompt

logger = logging.getLogger(__name__)


class StyleQAService:
    """Answer follow-up questions about one analysis, grounded in its evidence."""

    def __init__(self, text_llm: DeepSeekService) -> None:
        """Initialise with a text LLM and the shared style knowledge base.

        Args:
            text_llm: Text chat service used to generate the answer.
        """
        self._text = text_llm
        self._kb = get_style_kb()

    async def answer(
        self,
        analysis: Dict[str, Any],
        question: str,
        history: Optional[List[Dict[str, str]]],
        lang: str,
    ) -> str:
        """Return a grounded answer to ``question`` about ``analysis``.

        Args:
            analysis: The stored analysis result (AnalyzeResponse-shaped dict).
            question: The user's current question.
            history: Prior conversation turns (``{"role", "content"}``); only the
                last ``QA_MAX_HISTORY`` are kept to bound the prompt.
            lang: ``"vi"`` or ``"en"`` — the language for the answer.

        Returns:
            The assistant's answer text.
        """
        trimmed = self._trim_history(history)
        kb_text = self._kb_text_for(analysis)
        prompt = build_qa_prompt(analysis, kb_text, question, trimmed, lang)
        return await self._text.chat(prompt, temperature=settings.QA_TEMPERATURE)

    def _trim_history(
        self, history: Optional[List[Dict[str, str]]]
    ) -> List[Dict[str, str]]:
        """Keep only the most recent valid turns, capped at ``QA_MAX_HISTORY``."""
        if not history:
            return []
        valid = [
            {"role": h.get("role", ""), "content": h.get("content", "")}
            for h in history
            if isinstance(h, dict) and h.get("content")
        ]
        return valid[-settings.QA_MAX_HISTORY:]

    def _kb_text_for(self, analysis: Dict[str, Any]) -> str:
        """Render KB descriptions for the candidate styles named in the result."""
        names: List[str] = list(analysis.get("candidate_names") or [])
        if not names:
            primary = analysis.get("style")
            if primary:
                names = [primary]
        seen: set[str] = set()
        entries = []
        for name in names:
            entry = self._kb.match(name)
            if entry is not None and entry.id not in seen:
                seen.add(entry.id)
                entries.append(entry)
        return self._kb.descriptions_for(entries) if entries else ""


# Lazy singleton — created only when the first Q&A request arrives, so missing
# API keys do not break import/startup (mirrors get_orchestrator).
_qa_service: Optional[StyleQAService] = None


def get_qa_service() -> StyleQAService:
    """Return the singleton StyleQAService, creating it on first call.

    Raises:
        RuntimeError: If the DeepSeek API key is not configured.
    """
    global _qa_service
    if _qa_service is None:
        from chatbot.services import provider_credentials

        cred = provider_credentials.get_credentials("deepseek")
        if not cred.key:
            raise RuntimeError("Q&A is not configured. Set DEEPSEEK_API_KEY in .env")
        text_llm = DeepSeekService(
            api_key=cred.key,
            base_url=cred.base_url or settings.DEEPSEEK_BASE_URL,
            model=cred.model,
        )
        _qa_service = StyleQAService(text_llm)
    return _qa_service


def reset_qa_service() -> None:
    """Drop the cached Q&A service so it is rebuilt with fresh provider keys."""
    global _qa_service
    _qa_service = None
