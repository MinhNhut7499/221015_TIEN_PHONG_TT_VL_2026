"""Analysis orchestrator: entry point for the open-vocabulary pipeline.

Responsibilities:
1. Stage A — Agent A (MultiEvidenceExtractor) runs the evidence extraction
   several times across providers and returns the resulting sheets.
2. Stage B — KB grounding (StyleKbService) votes the proposed style names by
   frequency into a top-K candidate set; names outside the KB are queued for
   human review.
3. Delegate to PipelineRunner.run(PipelineInput) → FinalAnalysisResult
   (panel of 3 judges → consensus → arbiter).

No YOLO / ResNet / material models are used — recognition is open-vocabulary
and adding a style means adding a KB row, not retraining.
"""
import asyncio
import logging
import time
from typing import Callable, List, Optional

from app.config import settings
from app.services import kb_suggestion_store
from chatbot.services.deepseek_service import DeepSeekService
from chatbot.services.evidence_extractor import MultiEvidenceExtractor
from chatbot.services.gemini_service import GeminiService
from chatbot.services.grok_service import GrokService
from chatbot.services.openai_service import OpenAIService
from chatbot.services.pipeline_runner import PipelineRunner
from chatbot.services import provider_credentials
from chatbot.services.style_kb_service import get_style_kb
from chatbot.services.style_panel import StylePanel
from chatbot.utils.image_utils import encode_image_base64
from chatbot.utils.json_utils import parse_json_safe
from chatbot.utils.prompt_builder import build_free_read_prompt
from chatbot.utils.schemas import (
    AgentRunRecord,
    EvidenceItem,
    EvidenceSheet,
    FinalAnalysisResult,
    PipelineInput,
)

logger = logging.getLogger(__name__)


def _merge_sheets(sheets: List[EvidenceSheet]) -> EvidenceSheet:
    """Merge several extraction sheets into one for the judges.

    Items are de-duplicated by (dimension, lowercased feature) so distinct
    observations across calls are kept but exact repeats collapsed. The
    ``overall_note`` is taken from the richest sheet (most items); proposed
    styles are the order-preserving union (candidates themselves are voted
    separately in Stage B).
    """
    merged_items: List[EvidenceItem] = []
    seen_items: set[tuple[str, str]] = set()
    note, note_count = "", -1
    proposed: List[str] = []
    seen_styles: set[str] = set()
    families: List[str] = []
    seen_families: set[str] = set()

    for sheet in sheets:
        if len(sheet.items) > note_count:
            note_count, note = len(sheet.items), sheet.overall_note
        for item in sheet.items:
            key = (item.dimension, item.feature.strip().lower())
            if key not in seen_items:
                seen_items.add(key)
                merged_items.append(item)
        for name in sheet.proposed_styles:
            if name.lower() not in seen_styles:
                seen_styles.add(name.lower())
                proposed.append(name)
        for fam in sheet.proposed_families:
            if fam.lower() not in seen_families:
                seen_families.add(fam.lower())
                families.append(fam)

    return EvidenceSheet(
        items=merged_items,
        proposed_styles=proposed,
        proposed_families=families,
        overall_note=note,
    )


def _format_oov_cards(clusters: list) -> str:
    """Render synthetic KB-style cards for out-of-KB candidate clusters.

    Each card is tagged PROPOSED (not in the curated KB) and lists the observed
    features that cited it, so the judges have grounding material without a real
    KB entry. Mirrors the layout of ``StyleKbService.descriptions_for``.
    """
    lines: List[str] = []
    for c in clusters:
        lines.append(f"- {c.name} (PROPOSED — not in curated KB)")
        if c.features:
            lines.append(f"    observed features: {'; '.join(c.features)}")
    return "\n".join(lines)


def _parse_free_read_styles(raw: str) -> List[str]:
    """Parse the free-read JSON (``{"styles": [...]}``) into a clean name list."""
    data = parse_json_safe(raw)
    styles = data.get("styles") if isinstance(data, dict) else None
    if not isinstance(styles, list):
        return []
    return [s.strip() for s in styles if isinstance(s, str) and s.strip()]


def is_pipeline_configured() -> bool:
    """Return True if all core LLM providers have a key (DB-managed or .env)."""
    return provider_credentials.is_pipeline_configured()


class AnalysisOrchestrator:
    """Wire Agent A + KB grounding + the judging pipeline.

    Instantiated once at application startup as a lazy singleton.
    Raises RuntimeError if called without the required API keys.
    """

    def __init__(self) -> None:
        """Initialise the LLM services, the evidence extractor, and the KB.

        Credentials come from the DB-backed resolver (admin-managed keys) with a
        transparent fallback to the .env values; the services are built once and
        rebuilt by ``reset_orchestrator`` when a key changes.
        """
        gemini_cred = provider_credentials.get_credentials("gemini")
        deepseek_cred = provider_credentials.get_credentials("deepseek")
        openai_cred = provider_credentials.get_credentials("openai")
        grok_cred = provider_credentials.get_credentials("xai")
        vision_llm = GeminiService(
            api_key=gemini_cred.key,
            model=gemini_cred.model,
        )
        text_llm = DeepSeekService(
            api_key=deepseek_cred.key,
            base_url=deepseek_cred.base_url or settings.DEEPSEEK_BASE_URL,
            model=deepseek_cred.model,
        )
        final_llm = OpenAIService(
            api_key=openai_cred.key,
            model=openai_cred.model,
        )
        grok_llm = GrokService(
            api_key=grok_cred.key,
            model=grok_cred.model,
            base_url=grok_cred.base_url or settings.XAI_BASE_URL,
        )
        # Kept for the free read (decision C): a direct, unconstrained image read
        # by the strong OpenAI vision model, decorrelated from Gemini extraction.
        self._free_read_llm = final_llm
        self._kb = get_style_kb()
        family_names = [
            name for fid in self._kb.family_ids()
            if (name := self._kb.family_name(fid))
        ]
        self._extractor = MultiEvidenceExtractor(
            gemini=vision_llm, openai=final_llm, grok=grok_llm,
            family_names=family_names,
        )
        panel = StylePanel(gemini=vision_llm, openai=final_llm, grok=grok_llm)
        # gemini_llm/grok_llm are arbiter FALLBACKS only (A4b): if the OpenAI
        # arbiter has a long outage, the arbiter role retries on Gemini → Grok
        # before degrading to the panel average. They do NOT replace a judge.
        self._runner = PipelineRunner(
            panel=panel, arbiter_llm=final_llm, text_llm=text_llm, kb=self._kb,
            gemini_llm=vision_llm, grok_llm=grok_llm,
        )

    async def _free_read(
        self,
        image_base64: str,
        on_run: Callable[..., None],
    ) -> List[str]:
        """Free read: name the style directly from the image (decision C).

        A strong vision model answers WITHOUT the candidate list or evidence
        sheet — an opinion decorrelated from the sheet-grounded panel. Returns the
        ranked style names (empty when disabled or on failure — best-effort, never
        raises). Records one "Free Read" telemetry row.
        """
        if not settings.FREE_READ_ENABLED:
            return []
        start = time.monotonic()
        try:
            raw = await self._free_read_llm.chat_structured(
                build_free_read_prompt(), image_base64=image_base64
            )
        except Exception as exc:  # noqa: BLE001 — boundary: free read is best-effort
            logger.warning("Free read failed: %s", exc)
            on_run("Free Read", settings.OPENAI_MODEL,
                   (time.monotonic() - start) * 1000.0, False, error=str(exc))
            return []
        styles = _parse_free_read_styles(raw)
        on_run("Free Read", settings.OPENAI_MODEL,
               (time.monotonic() - start) * 1000.0, bool(styles))
        return styles

    async def translate_payload(self, payload: dict) -> dict:
        """Translate a stored analysis payload's narrative + evidence sheet to VI.

        Used for lazy, off-critical-path translation: the analyse pipeline returns
        the English result immediately (DEFER_TRANSLATION) and this is invoked the
        first time the analysis is re-opened in Vietnamese, then cached. The
        translation never feeds the decision, so it is accuracy-neutral.

        Args:
            payload: The stored AnalyzeResponse-shaped dict (from DetailJson),
                with ``explanation`` / ``key_evidence`` / ``composition_explanation``
                / ``evidence_per_style`` / ``evidence_sheet``.

        Returns:
            A dict with only the non-empty ``*_vi`` fields to merge into the
            payload (``explanation_vi``, ``key_evidence_vi``,
            ``composition_explanation_vi``, ``evidence_per_style_vi``,
            ``evidence_sheet_vi``). Empty when translation fails entirely.
        """
        raw_sheet = payload.get("evidence_sheet")
        evidence_sheet = (
            EvidenceSheet.model_validate(raw_sheet)
            if isinstance(raw_sheet, dict)
            else None
        )
        translation, evidence_sheet_vi = await self._runner.translate(
            explanation=payload.get("explanation", "") or "",
            key_evidence=payload.get("key_evidence", []) or [],
            composition_explanation=payload.get("composition_explanation"),
            evidence_per_style=payload.get("evidence_per_style"),
            evidence_sheet=evidence_sheet,
        )
        result: dict = {k: v for k, v in translation.items() if v is not None}
        if evidence_sheet_vi is not None:
            result["evidence_sheet_vi"] = evidence_sheet_vi.model_dump()
        return result

    async def analyze(self, image_bytes: bytes) -> FinalAnalysisResult:
        """Run the full open-vocabulary pipeline on raw image bytes.

        Args:
            image_bytes: Raw bytes of the uploaded image.

        Returns:
            FinalAnalysisResult with the style mixture, narrative, and evidence.
        """
        # Stage A — several evidence sheets across providers, then merged.
        # Agent A telemetry is collected here (the runner's telemetry sink only
        # covers the panel + arbiter) so Agent A shows real run counts/success
        # in the admin agents tab instead of 0%.
        agent_a_runs: List[AgentRunRecord] = []

        def _record_agent_a(
            agent_name: str,
            model_id: str,
            latency_ms: float,
            success: bool,
            error: Optional[str] = None,
        ) -> None:
            """Append one Agent A run record (matches the runner's recorder shape)."""
            agent_a_runs.append(
                AgentRunRecord(
                    agent_name=agent_name,
                    model_id=model_id,
                    latency_ms=int(latency_ms),
                    parse_success=success,
                    error=error[:2000] if error else None,
                )
            )

        analyze_start = time.monotonic()
        # encode_image_base64 is CPU-bound (PIL decode + resize + JPEG encode);
        # run it in a worker thread so it does not block the event loop and stall
        # other concurrent requests. Output is identical (same bytes in/out).
        image_base64 = await asyncio.to_thread(encode_image_base64, image_bytes)
        # Stage A + the free read (decision C) run concurrently — both only need
        # the image and are independent.
        stage_a_start = time.monotonic()
        sheets, free_read_styles = await asyncio.gather(
            self._extractor.extract_many(
                image_bytes, on_run=_record_agent_a, image_base64=image_base64
            ),
            self._free_read(image_base64, _record_agent_a),
        )
        stage_a_ms = (time.monotonic() - stage_a_start) * 1000.0
        sheet = _merge_sheets(sheets)
        # Fraction of extraction calls that survived (provider failures lower it)
        # → feeds the runner's run-quality confidence penalty.
        attempted = len(settings.evidence_extraction_calls_list) or 1
        extraction_completeness = min(1.0, len(sheets) / attempted)

        # Stage B — candidate set. With RECALL_MULTICHANNEL (default) three recall
        # channels are merged: voted names + feature retrieval + family expansion
        # (Phase 1). Set it False (and RETRIEVAL_TOP_K=8) to reproduce the legacy
        # voted-name-only baseline for an A/B comparison.
        proposed_lists = [s.proposed_styles for s in sheets]
        # The free read is an extra recall channel: its named styles vote into the
        # candidate set (so an answer the extraction sheets missed is still
        # available). It is kept OUT of ``proposed_lists`` so it does not skew the
        # extraction-agreement metric, which measures only the Stage A calls.
        candidate_lists = (
            proposed_lists + [free_read_styles] if free_read_styles else proposed_lists
        )
        if settings.RECALL_MULTICHANNEL:
            observed_features = [item.feature for item in sheet.items]
            candidates, out_of_kb = self._kb.build_candidate_set_multi(
                candidate_lists,
                observed_features=observed_features,
                proposed_families=sheet.proposed_families,
                min_votes=settings.EVIDENCE_MIN_VOTES,
                top_k=settings.RETRIEVAL_TOP_K,
                feature_top_n=settings.FEATURE_RETRIEVAL_TOP_N,
            )
        else:
            candidates, out_of_kb = self._kb.build_candidate_set_voted(
                candidate_lists,
                min_votes=settings.EVIDENCE_MIN_VOTES,
                top_k=settings.RETRIEVAL_TOP_K,
            )
        # How much the extraction calls agreed on the proposed styles — low →
        # multi-style/hybrid image (drives the runner's ``hybrid`` flag).
        extraction_agreement = self._kb.extraction_agreement(proposed_lists)
        if out_of_kb:
            logger.info("Out-of-KB style names (suggestion queue): %s", out_of_kb)
            kb_suggestion_store.record(out_of_kb)

        # Open-set escape (OUT_OF_KB_*): keep strongly-voted out-of-KB names as
        # tagged candidates with a synthetic card from the observed evidence, so
        # the panel can judge them. A higher agreement bar (enforced in the runner)
        # decides whether such a style is actually displayed.
        candidate_names = [c.name for c in candidates]
        candidate_kb_text = self._kb.descriptions_for(candidates)
        out_of_kb_names: List[str] = []
        if settings.OUT_OF_KB_ENABLED:
            oov = self._kb.cluster_out_of_kb(
                candidate_lists,
                settings.OUT_OF_KB_MIN_VOTES,
                evidence_items=sheet.items,
            )
            # Require observed-evidence support (synthetic-card material) — the
            # open-set analogue of RECALL_ESCAPE_REQUIRE_EVIDENCE.
            oov = [c for c in oov if c.features][: settings.OUT_OF_KB_MAX_CANDIDATES]
            if oov:
                out_of_kb_names = [c.name for c in oov]
                candidate_names = candidate_names + out_of_kb_names
                candidate_kb_text = candidate_kb_text + "\n" + _format_oov_cards(oov)
                logger.info("Out-of-KB candidates admitted to panel: %s", out_of_kb_names)
        logger.info(
            "Pipeline starting: %d extraction calls, %d merged evidence items, "
            "%d proposed styles, families=%s → %d KB candidates, "
            "extraction_agreement=%s (%s)",
            len(sheets),
            len(sheet.items),
            len(sheet.proposed_styles),
            sheet.proposed_families or "-",
            len(candidates),
            extraction_agreement,
            ", ".join(c.name for c in candidates),
        )

        result = await self._runner.run(
            PipelineInput(
                evidence_sheet=sheet,
                candidate_names=candidate_names,
                candidate_kb_text=candidate_kb_text,
                full_image_base64=image_base64,
                extraction_agreement=extraction_agreement,
                extraction_completeness=extraction_completeness,
                free_read_styles=free_read_styles,
                out_of_kb_names=out_of_kb_names,
            )
        )
        # Prepend Agent A's telemetry so all five pipeline agents are attributed.
        if agent_a_runs:
            result.agent_runs = agent_a_runs + list(result.agent_runs or [])

        # Report the TRUE end-to-end wall time to the caller. ``run_ms`` (the
        # runner's own timer) covers only the panel → arbiter → run-off portion
        # and excludes Stage A (multi-extraction + free read), which is the
        # heaviest part — so the runner figure understates real latency. Override
        # ``processing_time_ms`` with the full analyze() span (Stage A onward).
        total_ms = round((time.monotonic() - analyze_start) * 1000.0, 1)
        run_ms = result.processing_time_ms
        result.processing_time_ms = total_ms

        # Stage-level wall-time + image payload size (latency monitoring). Stage A
        # runs the extraction calls + free read in parallel; ``run_ms`` is the
        # panel → arbiter → run-off portion. ``encoded_kb`` shows the resize
        # effect (it carries the resized JPEG sent to every vision call).
        logger.info(
            "stage_timing %s",
            {
                "total_ms": total_ms,
                "stage_a_ms": round(stage_a_ms, 1),
                "run_ms": run_ms,
                "raw_kb": round(len(image_bytes) / 1024.0, 1),
                "encoded_kb": round(len(image_base64) / 1024.0, 1),
                "max_dim": settings.VISION_IMAGE_MAX_DIM,
            },
        )
        return result


# Lazy singleton — created only when the first request arrives.
# Avoids ImportError at startup if API keys are missing.
_orchestrator: AnalysisOrchestrator | None = None


def get_orchestrator() -> AnalysisOrchestrator:
    """Return the singleton AnalysisOrchestrator, creating it on first call.

    Raises:
        RuntimeError: If called before the LLM API keys are configured.
    """
    global _orchestrator
    if _orchestrator is None:
        if not is_pipeline_configured():
            raise RuntimeError(
                "LLM pipeline is not configured. "
                "Set GEMINI_API_KEY, DEEPSEEK_API_KEY, and OPENAI_API_KEY in .env"
            )
        _orchestrator = AnalysisOrchestrator()
    return _orchestrator


def reset_orchestrator() -> None:
    """Drop the cached orchestrator so the next request rebuilds it.

    In-flight requests keep their captured reference (with the old keys baked
    in) and finish uninterrupted; only NEW requests pick up the change.
    """
    global _orchestrator
    _orchestrator = None


def reload_provider_runtime() -> None:
    """Reset every singleton that has provider keys baked in, after a key change.

    Invalidates the local credential snapshot, drops the orchestrator and Q&A
    singletons, and resets the provider circuit breaker. Call AFTER the DB
    transaction that changed the keys has committed and the epoch was bumped.
    """
    from chatbot.services import qa_service
    from chatbot.utils.circuit_breaker import get_circuit_breaker

    provider_credentials.invalidate_local()
    reset_orchestrator()
    qa_service.reset_qa_service()
    get_circuit_breaker().reset()


async def ensure_runtime_fresh(db) -> None:
    """Rebuild provider runtime if another worker changed a key (epoch moved).

    Cheap on the hot path (throttled epoch read); only rebuilds on an actual
    change. Call at the start of request handlers that use the LLM pipeline so
    multi-worker deployments converge within RUNTIME_EPOCH_TTL_SEC.
    """
    try:
        if await provider_credentials.ensure_fresh(db):
            reset_orchestrator()
            from chatbot.services import qa_service
            from chatbot.utils.circuit_breaker import get_circuit_breaker

            qa_service.reset_qa_service()
            get_circuit_breaker().reset()
    except Exception as exc:  # noqa: BLE001 — boundary: freshness check is best-effort
        logger.warning("Provider runtime freshness check skipped: %s", exc)
