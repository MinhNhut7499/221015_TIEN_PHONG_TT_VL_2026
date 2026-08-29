"""Agent A — VLM evidence extractor for the open-vocabulary pipeline.

Stage A of the pipeline: a vision-language model looks at one building
photograph and fills a structured EVIDENCE SHEET — ~12 dimensions, each with a
free-text feature description and OPEN-VOCABULARY style suggestions, plus a
building-level ``style_hypotheses`` list. No confidence numbers and no bounding
boxes are produced (both are unreliable; see EvidenceItem docstring).

``MultiEvidenceExtractor`` runs the extraction several times across providers
(default Gemini×2 + GPT×2) so the candidate set can be voted by frequency
downstream — this stabilises the candidate set and filters one-off hallucinated
style names.
"""
import asyncio
import logging
import time
from typing import Awaitable, Callable, List, Optional, Tuple

from app.config import settings
from chatbot.services.gemini_service import GeminiService
from chatbot.services.grok_service import GrokService
from chatbot.services.openai_service import OpenAIService
from chatbot.utils.circuit_breaker import call_with_fallback
from chatbot.utils.image_utils import encode_image_base64
from chatbot.utils.json_utils import parse_json_safe
from chatbot.utils.prompt_builder import build_agent_a_prompt
from chatbot.utils.schemas import EvidenceItem, EvidenceSheet

logger = logging.getLogger(__name__)


def parse_evidence_sheet(raw: str) -> EvidenceSheet:
    """Parse a VLM JSON response into an EvidenceSheet.

    Builds ``proposed_styles`` from the building-level ``style_hypotheses``
    (placed first, ranked) merged with every item's ``suggested_styles`` and any
    explicit top-level ``proposed_styles`` (de-duplicated, order preserved).
    Returns an empty sheet on an unparseable response — never raises.
    """
    data = parse_json_safe(raw)
    if not data:
        logger.warning("Agent A returned unparseable evidence sheet")
        return EvidenceSheet()

    items: List[EvidenceItem] = []
    for raw_item in data.get("items", []):
        if not isinstance(raw_item, dict):
            continue
        dimension = str(raw_item.get("dimension", "")).strip()
        feature = str(raw_item.get("feature", "")).strip()
        if not dimension or not feature:
            continue
        suggested = [
            str(s).strip()
            for s in raw_item.get("suggested_styles", [])
            if str(s).strip()
        ]
        items.append(
            EvidenceItem(
                dimension=dimension,
                feature=feature,
                suggested_styles=suggested,
                note=str(raw_item.get("note") or "").strip(),
            )
        )

    proposed = _dedup_proposed(
        items, data.get("style_hypotheses"), data.get("proposed_styles")
    )
    raw_families = data.get("families")
    families = (
        [str(f).strip() for f in raw_families if str(f).strip()]
        if isinstance(raw_families, list)
        else []
    )
    return EvidenceSheet(
        items=items,
        proposed_styles=proposed,
        proposed_families=families,
        overall_note=str(data.get("overall_note") or "").strip(),
    )


def _dedup_proposed(
    items: List[EvidenceItem],
    style_hypotheses: Optional[object],
    proposed_styles: Optional[object],
) -> List[str]:
    """Merge building-level hypotheses, per-item cues, and any top-level list.

    ``style_hypotheses`` (Agent A's ranked whole-building guesses) go FIRST so
    the specific/correct style leads the candidate set; then each item's
    ``suggested_styles``; then any explicit top-level ``proposed_styles``. All
    de-duplicated case-insensitively with order preserved.
    """
    ordered: List[str] = []
    seen: set[str] = set()

    def _add(name: str) -> None:
        cleaned = name.strip()
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            ordered.append(cleaned)

    if isinstance(style_hypotheses, list):
        for style in style_hypotheses:
            _add(str(style))
    for item in items:
        for style in item.suggested_styles:
            _add(style)
    if isinstance(proposed_styles, list):
        for style in proposed_styles:
            _add(str(style))
    return ordered


class MultiEvidenceExtractor:
    """Run Agent A several times across providers and return all sheets.

    The orchestrator aggregates the returned sheets: it votes the proposed
    styles by frequency (Stage B) and merges the evidence items for the judges.
    """

    def __init__(
        self,
        gemini: GeminiService,
        openai: OpenAIService,
        grok: Optional[GrokService] = None,
        family_names: Optional[List[str]] = None,
    ) -> None:
        """Store the vision LLMs used for extraction.

        Args:
            gemini: GeminiService (provider key ``gemini``).
            openai: OpenAIService (provider key ``openai``, vision via
                ``chat_structured``).
            grok: Optional GrokService (provider key ``grok``) used ONLY as a
                fallback when the primary extraction provider has a long outage
                (A4b). None → no Grok fallback.
            family_names: KB family display names to constrain Agent A's
                building-level ``families`` field (Phase 1a coarse-to-fine).
                None/empty → the families instruction is omitted.
        """
        self._gemini = gemini
        self._openai = openai
        self._grok = grok
        self._family_names = family_names or []

    async def extract_many(
        self,
        image_bytes: bytes,
        on_run: Optional[Callable[..., None]] = None,
        image_base64: Optional[str] = None,
    ) -> List[EvidenceSheet]:
        """Run every configured extraction call in parallel; return the sheets.

        Calls are listed in ``settings.EVIDENCE_EXTRACTION_CALLS`` (e.g.
        ``"gemini,gemini,openai,openai"``). A call that fails or returns an
        unparseable response is dropped (its sheet is omitted). Always returns at
        least one sheet — an empty one — so the caller never crashes.

        Args:
            image_bytes: Raw image bytes to analyse.
            on_run: Optional telemetry recorder, called once per extraction slot
                with ``(agent_name, model_id, latency_ms, success, error=...)`` so
                the orchestrator can attribute Agent A's runs in the AgentRuns
                table (previously Agent A emitted no telemetry → 0% success).
            image_base64: Pre-encoded base64 JPEG of the image. When provided it
                is reused as-is so the image is decoded/resized/encoded only ONCE
                per request (the orchestrator already encodes it for the free
                read + judges); falls back to encoding ``image_bytes`` if omitted.
        """
        image_b64 = image_base64 or encode_image_base64(image_bytes)
        prompt = build_agent_a_prompt(family_names=self._family_names)
        providers = settings.evidence_extraction_calls_list or ["gemini"]
        calls = [self._run_one(provider, prompt, image_b64, on_run) for provider in providers]
        results = await asyncio.gather(*calls, return_exceptions=True)

        sheets: List[EvidenceSheet] = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning("An evidence-extraction call failed: %s", result)
                continue
            sheets.append(result)
        return sheets or [EvidenceSheet()]

    def _fallback_chain(
        self, primary: str, prompt: str, image_b64: str
    ) -> List[Tuple[str, Callable[[], Awaitable[str]]]]:
        """Ordered (provider_key, raw-call factory) chain — primary then backups.

        Each factory wraps the provider's vision call in a per-attempt timeout.
        The primary provider leads; the other available providers (Grok included
        only when injected) follow as fallbacks for a long outage (A4b).
        """
        timeout = settings.PIPELINE_AGENT_TIMEOUT_SEC

        def _gemini() -> Awaitable[str]:
            return asyncio.wait_for(
                self._gemini.generate_with_image(
                    prompt, image_base64=image_b64, temperature=0.3
                ),
                timeout=timeout,
            )

        def _openai() -> Awaitable[str]:
            return asyncio.wait_for(
                self._openai.chat_structured(prompt, image_base64=image_b64),
                timeout=timeout,
            )

        factories: dict[str, Callable[[], Awaitable[str]]] = {
            "gemini": _gemini,
            "openai": _openai,
        }
        if self._grok is not None:
            def _grok() -> Awaitable[str]:
                return asyncio.wait_for(
                    self._grok.chat_structured(prompt, image_base64=image_b64),
                    timeout=timeout,
                )
            factories["grok"] = _grok

        primary_key = primary if primary in factories else "gemini"
        order = [primary_key] + [k for k in factories if k != primary_key]
        return [(key, factories[key]) for key in order]

    def _model_for(self, provider: str) -> str:
        """Return the model id for a provider key (from the injected service)."""
        svc = {
            "gemini": self._gemini,
            "openai": self._openai,
            "grok": self._grok,
        }.get(provider, self._gemini)
        default = {
            "gemini": settings.GEMINI_MODEL,
            "openai": settings.OPENAI_MODEL,
            "grok": settings.GROK_MODEL,
        }.get(provider, settings.GEMINI_MODEL)
        return getattr(svc, "model_name", default) if svc is not None else default

    async def _run_one(
        self,
        provider: str,
        prompt: str,
        image_b64: str,
        on_run: Optional[Callable[..., None]] = None,
    ) -> EvidenceSheet:
        """Run one extraction slot with provider fallback, parse to a sheet.

        Records one ``Agent A`` telemetry entry (success when the parsed sheet has
        items) via ``on_run`` before returning or re-raising, so a failed slot is
        still attributed in the AgentRuns table.
        """
        start = time.monotonic()
        model_id = self._model_for(provider)
        try:
            raw = await call_with_fallback(self._fallback_chain(provider, prompt, image_b64))
            sheet = parse_evidence_sheet(raw)
            if on_run is not None:
                success = bool(sheet.items)
                on_run(
                    "Agent A", model_id, (time.monotonic() - start) * 1000.0, success,
                    error=None if success else "empty or unparseable evidence sheet",
                )
            return sheet
        except Exception as exc:
            if on_run is not None:
                on_run(
                    "Agent A", model_id, (time.monotonic() - start) * 1000.0, False,
                    error=str(exc),
                )
            raise


class MockEvidenceExtractor:
    """Deterministic stand-in for the extractor (tests/dev).

    Returns a fixed, valid evidence sheet without any LLM call.
    """

    async def extract_many(
        self,
        image_bytes: bytes,
        on_run: Optional[Callable[..., None]] = None,
        image_base64: Optional[str] = None,
    ) -> List[EvidenceSheet]:
        """Return a single deterministic evidence sheet (ignores image content).

        Accepts ``on_run`` and ``image_base64`` for signature parity with
        ``MultiEvidenceExtractor`` (both ignored); records one successful
        ``Agent A`` run when a recorder is supplied.
        """
        if on_run is not None:
            on_run("Agent A", "mock", 0.0, True, error=None)
        items = [
            EvidenceItem(
                dimension="arch",
                feature="pointed (lancet) arches over the portals",
                suggested_styles=["Gothic"],
                note="pointed arch vs round-arched Romanesque",
            ),
            EvidenceItem(
                dimension="supports",
                feature="flying buttresses along the side aisles",
                suggested_styles=["Gothic", "French Gothic"],
            ),
            EvidenceItem(
                dimension="material",
                feature="light limestone ashlar",
                suggested_styles=["Gothic", "Romanesque"],
            ),
        ]
        return [
            EvidenceSheet(
                items=items,
                proposed_styles=["Gothic", "French Gothic", "Romanesque"],
                overall_note="large stone religious building with strong Gothic cues",
            )
        ]
