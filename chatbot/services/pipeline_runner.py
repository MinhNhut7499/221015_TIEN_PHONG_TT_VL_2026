"""Open-vocabulary analysis pipeline (Tier 2 of the new architecture).

The orchestrator runs Stage A (Agent A evidence extraction) and Stage B (KB
grounding) before calling this runner, which performs the judging:

    Stage C  Panel of 3 independent judges (Gemini / DeepSeek / OpenAI) — each
             scores the KB candidates into a mixture from the SAME evidence sheet
    Stage D  Inter-judge agreement = mean pairwise Spearman of their rankings
    Stage E  Arbiter (OpenAI GPT-4o + full image) → final mixture, grounded in
             evidence + KB + the panel's verdicts
    Stage F  Abstention — low inter-judge agreement (PRIMARY signal) ‖ low
             margin / high entropy (secondary) ⇒ mark uncertain + return top-K

The runner takes a :class:`PipelineInput` (evidence sheet + candidate names +
candidate KB text + full image) and returns a :class:`FinalAnalysisResult`.
LLM self-reported confidence is NOT trusted: uncertainty comes from inter-judge
agreement (decisions #71, #73, #75).
"""
import asyncio
import contextvars
import json
import logging
import math
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, TypeVar

from app.config import settings
from app.services import kb_suggestion_store
from chatbot.services.deepseek_service import DeepSeekService
from chatbot.services.gemini_service import GeminiService
from chatbot.services.grok_service import GrokService
from chatbot.services.openai_service import OpenAIService
from chatbot.services.style_kb_service import StyleKbService
from chatbot.services.style_panel import StylePanel
from chatbot.utils.circuit_breaker import get_circuit_breaker
from chatbot.utils.consensus import panel_agreement, weighted_mean_distribution
from chatbot.utils.distribution import build_style_distribution_safe, safe_float
from chatbot.utils.json_utils import parse_json_safe
from chatbot.utils.prompt_builder import (
    build_agent7_prompt,
    build_runoff_prompt,
    build_translation_prompt,
)
from chatbot.utils.schemas import (
    AgentRunRecord,
    EvidenceItem,
    EvidenceSheet,
    FinalAnalysisResult,
    PanelVerdict,
    PipelineInput,
    StyleCandidate,
    StyleDistribution,
    StyleEntry,
)

logger = logging.getLogger(__name__)

_TIMEOUT = settings.PIPELINE_AGENT_TIMEOUT_SEC
# Max evidence rows translated per LLM call (keeps JSON output under the cap).
_EVIDENCE_TRANSLATE_BATCH = 6
_ARBITER_AGENT = "Arbiter"
_RUNOFF_AGENT = "Run-off"

_T = TypeVar("_T")

# Per-analysis telemetry sink. Set at the start of ``run()`` to a fresh list;
# the ContextVar value is shared by reference so agent calls record into the
# same per-request list without threading it through every signature.
_telemetry_var: contextvars.ContextVar[Optional[List[AgentRunRecord]]] = (
    contextvars.ContextVar("agent_telemetry", default=None)
)


_RAW_TRUNCATE = 8000  # cap stored raw/parsed strings to keep AgentRuns rows small

# Large enough to capture every KB entry with positive feature support when the
# escape hatch checks an out-of-candidate style against the observed evidence.
_ESCAPE_FEATURE_TOP_N = 1000


def _record_run(
    agent_name: str,
    model_id: str,
    latency_ms: float,
    success: bool,
    raw: Optional[str] = None,
    parsed: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    """Append one agent-run record to the active telemetry sink, if any.

    ``raw``/``parsed`` are the LLM's raw response and the parsed JSON (truncated)
    and ``error`` the failure message — persisted so a run can be audited (the
    AgentRuns rows were all-NULL in the 503 debug).
    """
    sink = _telemetry_var.get()
    if sink is not None:
        sink.append(
            AgentRunRecord(
                agent_name=agent_name,
                model_id=model_id,
                latency_ms=int(latency_ms),
                parse_success=success,
                raw_output=raw[:_RAW_TRUNCATE] if raw else None,
                parsed_output=parsed[:_RAW_TRUNCATE] if parsed else None,
                error=error[:_RAW_TRUNCATE] if error else None,
            )
        )


class PipelineRunner:
    """Run the open-vocabulary judging panel + arbiter.

    Receives the judging panel and the arbiter LLM via constructor injection so
    they can be swapped or mocked in tests without touching this class.
    """

    def __init__(
        self,
        panel: StylePanel,
        arbiter_llm: OpenAIService,
        text_llm: DeepSeekService,
        kb: Optional[StyleKbService] = None,
        gemini_llm: Optional[GeminiService] = None,
        grok_llm: Optional[GrokService] = None,
    ) -> None:
        """Store the injected panel, arbiter, translator, KB, and arbiter backups.

        Args:
            panel: StylePanel running the three independent judges (Stage C).
            arbiter_llm: OpenAIService for the arbiter (Stage E, vision-capable).
            text_llm: DeepSeekService used for the bilingual translation pass
                (DeepSeek's JSON mode is reliable; routing translation through
                the arbiter's JSON mode returned empty responses).
            kb: StyleKbService used for the recall escape hatch — matching an
                arbiter-proposed style that is outside the candidate set back to
                an existing KB entry (lifts the candidate ceiling without
                polluting the KB). When None the escape hatch is disabled.
            gemini_llm: Optional Gemini vision service used ONLY as an arbiter
                fallback (A4b) when the primary OpenAI arbiter has a long outage.
            grok_llm: Optional Grok vision service, the second arbiter fallback.
                Neither replaces a panel judge — the panel stays three
                independent providers.
        """
        self._panel = panel
        self._arbiter_llm = arbiter_llm
        self._text = text_llm
        self._kb = kb
        self._gemini = gemini_llm
        self._grok = grok_llm

    async def run(self, pipeline_input: PipelineInput) -> FinalAnalysisResult:
        """Run the panel → consensus → arbiter → abstention flow.

        Args:
            pipeline_input: Evidence sheet + candidate names/KB text + full image.

        Returns:
            FinalAnalysisResult with the open-vocabulary style mixture, narrative,
            the panel verdicts + agreement, abstention flags, and telemetry.
        """
        start = time.monotonic()
        telemetry: List[AgentRunRecord] = []
        _telemetry_var.set(telemetry)

        sheet = pipeline_input.evidence_sheet or EvidenceSheet()
        candidate_names = pipeline_input.candidate_names
        kb_text = pipeline_input.candidate_kb_text
        allowed = set(candidate_names)
        evidence_votes = _build_evidence_votes(sheet)
        fallback_primary = _fallback_primary(evidence_votes, candidate_names)

        warnings: List[str] = []
        if not candidate_names:
            warnings.append("No KB candidates matched the proposed styles")
        if not sheet.items:
            warnings.append("Evidence sheet was empty (Agent A produced no items)")

        # Stage C — the panel never raises (per-judge errors are captured). Every
        # judge now SEES THE IMAGE alongside the evidence sheet (decision
        # 2026-06-19) so each judge ≈ its base vision model.
        panel_verdicts = await self._panel.judge(
            sheet, candidate_names, kb_text, evidence_votes, allowed,
            fallback_primary, full_image_base64=pipeline_input.full_image_base64,
            on_run=_record_run,
        )
        valid_dists = [
            v.style_distribution.distribution
            for v in panel_verdicts
            if not v.failed and v.style_distribution is not None
        ]
        n_failed = len(panel_verdicts) - len(valid_dists)
        if n_failed:
            warnings.append(f"{n_failed} of {len(panel_verdicts)} judges failed")
        # Weight each judge by decisiveness (used for the panel-average fallback).
        judge_weights = _judge_weights(valid_dists)

        # Stage D — inter-judge agreement (None when < 2 valid judges).
        agreement = panel_agreement(valid_dists, candidate_names)

        # Stage E — arbiter; on failure fall back to the panel-average mixture.
        translation: Dict[str, Any] = {}
        evidence_sheet_vi: Optional[EvidenceSheet] = None
        degraded = bool(warnings)
        try:
            final = await self._arbiter(
                panel_verdicts, agreement, sheet, candidate_names, kb_text,
                pipeline_input.full_image_base64, allowed, fallback_primary,
                pipeline_input.free_read_styles,
            )
            # W1 — let the panel decide the final mixture (panel / consensus
            # modes); "arbiter" mode leaves the arbiter's mixture unchanged.
            final = decide_final_distribution(
                settings.DECISION_MODE, final, valid_dists, judge_weights,
                candidate_names, agreement, allowed, fallback_primary,
            )
            # Contrastive run-off — when the final top-2 are close, re-decide
            # between just those two using their KB signatures (best-effort; never
            # raises, leaves ``final`` unchanged on any failure).
            try:
                final = await self._runoff(
                    final, sheet, pipeline_input.full_image_base64
                )
            except Exception as exc:  # noqa: BLE001 — run-off is best-effort
                logger.warning("Run-off stage failed; keeping arbiter result: %s", exc)
            # The arbiter answered, but on a BACKUP provider (A4b) → degraded run.
            arbiter_provider = final.get("arbiter_provider")
            if arbiter_provider and arbiter_provider != "openai":
                degraded = True
                warnings.append(
                    f"Arbiter used fallback provider: {arbiter_provider}"
                )
            # Translation is OFF the critical path when DEFER_TRANSLATION is set:
            # run() returns the English result immediately and the Vietnamese is
            # produced lazily on first re-open (it never feeds the decision, so
            # deferring is accuracy-neutral). False = translate inline as before.
            if settings.ENABLE_BILINGUAL and not settings.DEFER_TRANSLATION:
                translation, evidence_sheet_vi = await self.translate(
                    explanation=final.get("explanation", ""),
                    key_evidence=final.get("key_evidence", []),
                    composition_explanation=final.get("composition_explanation"),
                    evidence_per_style=final.get("evidence_per_style"),
                    evidence_sheet=sheet,
                )
        except Exception as exc:  # boundary: arbiter outage
            logger.warning("Arbiter failed; using panel-average fallback: %s", exc)
            warnings.append("Arbiter unavailable; panel-average fallback used")
            degraded = True
            final = _panel_fallback(
                valid_dists, judge_weights, candidate_names, fallback_primary, allowed
            )

        # Open-set gate — an out-of-KB style may only stay primary if the panel
        # cleared the HIGHER agreement bar; otherwise demote it to the best in-KB
        # style. Then record which displayed styles are out-of-KB (for the badge +
        # the suggestion queue).
        out_of_kb_names = set(pipeline_input.out_of_kb_names)
        out_of_kb_styles: List[str] = []
        if out_of_kb_names:
            final, demoted = _gate_out_of_kb_primary(
                final, out_of_kb_names, len(valid_dists), agreement,
                allowed, fallback_primary,
            )
            if demoted:
                degraded = True
                warnings.append(
                    "Out-of-KB candidate below the display bar — demoted to the "
                    "best in-KB style"
                )
            gated_dist: Optional[StyleDistribution] = final.get("style_distribution")
            if gated_dist is not None:
                out_of_kb_styles = [
                    s for s in gated_dist.distribution if s in out_of_kb_names
                ]
            if out_of_kb_styles:
                warnings.append(
                    "Result includes a style outside the curated KB — pending "
                    "human review"
                )
                kb_suggestion_store.record(out_of_kb_styles)

        final_dist: Optional[StyleDistribution] = final.get("style_distribution")
        primary_style = final["style"]
        # Confidence reflects RUN QUALITY, not just the arbiter's mixture sharpness:
        # the primary mass is discounted when judges failed, extraction calls were
        # lost, or the extraction calls disagreed (decision A3 / the 503 debug).
        run_quality = _run_quality(
            valid_judges=len(valid_dists),
            attempted_judges=len(panel_verdicts),
            extraction_completeness=pipeline_input.extraction_completeness,
            extraction_agreement=pipeline_input.extraction_agreement,
        )
        # ``sharpness`` = the arbiter's raw primary mass (drives the abstention
        # conf-gate, unchanged); ``primary_conf`` is the REPORTED confidence,
        # additionally discounted by run quality so a degraded run reads lower.
        sharpness = float(final["confidence"])
        primary_conf = round(sharpness * run_quality, 4)
        margin, entropy = (
            _distribution_stats(final_dist.distribution)
            if final_dist is not None
            else (None, None)
        )

        # Stage F — abstention. Inter-judge agreement is the PRIMARY signal;
        # margin/entropy/conf are secondary. Surface top-K when uncertain.
        uncertain = False
        candidates: List[StyleCandidate] = []
        if final_dist is not None:
            ranked = sorted(
                final_dist.distribution.items(), key=lambda kv: kv[1], reverse=True
            )
            candidates = [
                StyleCandidate(style=s, probability=round(p, 4))
                for s, p in ranked[: settings.UNCERTAINTY_TOP_K]
            ]
        if len(valid_dists) < 2:
            uncertain = True  # cannot establish consensus with < 2 judges
        elif (
            len(valid_dists) >= 3
            and agreement is not None
            and agreement < settings.PANEL_AGREEMENT_MIN
        ):
            # Only trust the agreement signal with ≥3 judges; a 2-judge agreement
            # is a single correlation and was a misleading "0.88" in the 503 run.
            uncertain = True
        if final_dist is not None and not uncertain:
            uncertain = (
                (margin is not None and margin < settings.UNCERTAINTY_MARGIN_MIN)
                or (entropy is not None and entropy > settings.UNCERTAINTY_ENTROPY_MAX)
                or (
                    settings.UNCERTAINTY_CONF_MIN > 0
                    and sharpness < settings.UNCERTAINTY_CONF_MIN
                )
            )
        if uncertain:
            warnings.append("Low-confidence result — returning top-K candidates")

        # Hybrid (multi-style) — INDEPENDENT of abstention. True when the final
        # mixture has ≥ 2 significant styles OR the extraction calls disagreed.
        # A hybrid is a confident, fully-explained mixture, not a refusal.
        extraction_agreement = pipeline_input.extraction_agreement
        hybrid = _is_hybrid(final_dist, extraction_agreement)
        if hybrid:
            warnings.append(
                "Hybrid/eclectic building — multiple coexisting styles "
                "(see evidence per style)"
            )

        # Overall run health (A4b) — persisted in DetailJson for auditing.
        run_status = _run_status(
            valid_judges=len(valid_dists),
            attempted_judges=len(panel_verdicts),
            extraction_completeness=pipeline_input.extraction_completeness,
            degraded=degraded,
        )

        elapsed_ms = (time.monotonic() - start) * 1000.0
        return FinalAnalysisResult(
            style=primary_style,
            confidence=primary_conf,
            run_status=run_status,
            explanation=final.get("explanation", ""),
            key_evidence=final.get("key_evidence", []),
            panel_verdicts=panel_verdicts,
            panel_agreement=agreement,
            processing_time_ms=round(elapsed_ms, 1),
            style_distribution=final_dist,
            composition_explanation=final.get("composition_explanation"),
            evidence_per_style=final.get("evidence_per_style"),
            evidence_sheet=sheet,
            evidence_sheet_vi=evidence_sheet_vi,
            explanation_vi=translation.get("explanation_vi"),
            key_evidence_vi=translation.get("key_evidence_vi"),
            composition_explanation_vi=translation.get("composition_explanation_vi"),
            evidence_per_style_vi=translation.get("evidence_per_style_vi"),
            degraded=degraded,
            warnings=warnings,
            certainty_margin=margin,
            distribution_entropy=entropy,
            uncertain=uncertain,
            candidates=candidates,
            hybrid=hybrid,
            extraction_agreement=extraction_agreement,
            candidate_names=list(candidate_names),
            out_of_kb_styles=out_of_kb_styles,
            agent_runs=telemetry,
        )

    def _expand_allowed_with_kb(
        self,
        raw_dist: Dict[str, Any],
        allowed: set,
        observed_features: List[str],
    ) -> tuple[Dict[str, float], set]:
        """Admit arbiter-proposed styles outside the candidate set via the KB.

        For each style name the arbiter emitted that is NOT already an allowed
        candidate, try to match it to an existing KB entry. A match is renamed to
        its canonical KB name and that name is added to ``allowed`` (lifting the
        candidate ceiling). A name with NO KB match is kept as-is and will be
        filtered out downstream — the KB is never polluted with invented styles.

        When ``RECALL_ESCAPE_REQUIRE_EVIDENCE`` is on, a KB-matched style is
        admitted only if the OBSERVED evidence also supports it — its KB
        defining-features overlap what Agent A described
        (:meth:`StyleKbService.retrieve_by_features`). This stops the arbiter
        from naming a real KB style the image shows no sign of. A KB match with
        no evidence support is left in the mixture unrenamed, so
        ``build_style_distribution_safe`` drops it like any out-of-set name.

        Disabled (returns the inputs unchanged) when no KB was injected or
        ``RECALL_ESCAPE_HATCH`` is False.
        """
        if self._kb is None or not settings.RECALL_ESCAPE_HATCH:
            return raw_dist, allowed
        allowed_lower = {a.lower() for a in allowed}
        new_allowed = set(allowed)
        remapped: Dict[str, float] = {}
        # Evidence-supported KB names (lazy — only computed when a genuine
        # out-of-candidate name appears and the evidence gate is enabled).
        supported_names: Optional[set] = None
        for key, value in raw_dist.items():
            if not isinstance(key, str) or not key.strip():
                continue
            name = key.strip()
            prob = safe_float(value)
            if name.lower() in allowed_lower:
                remapped[name] = remapped.get(name, 0.0) + prob
                continue
            entry = self._kb.match(name)
            if entry is None:
                remapped[name] = remapped.get(name, 0.0) + prob  # filtered later
                continue
            if settings.RECALL_ESCAPE_REQUIRE_EVIDENCE:
                if supported_names is None:
                    supported_names = {
                        e.name
                        for e in self._kb.retrieve_by_features(
                            observed_features, _ESCAPE_FEATURE_TOP_N
                        )
                    }
                if entry.name not in supported_names:
                    # KB-real but the evidence does not back it → do not admit.
                    remapped[name] = remapped.get(name, 0.0) + prob  # filtered later
                    continue
            new_allowed.add(entry.name)
            allowed_lower.add(entry.name.lower())
            remapped[entry.name] = remapped.get(entry.name, 0.0) + prob
        return remapped, new_allowed

    def _arbiter_chain(
        self, prompt: str, full_image_b64: Optional[str]
    ) -> List[tuple]:
        """Ordered (provider_key, model_id, raw-call) arbiter chain.

        OpenAI leads; Gemini then Grok follow as fallbacks (A4b) only when they
        were injected AND there is an image for them to inspect. All emit CoT
        prose + a ```json``` block parsed the same way.
        """
        chain: List[tuple] = [
            (
                "openai",
                getattr(self._arbiter_llm, "model_name", settings.OPENAI_MODEL),
                lambda: self._arbiter_llm.chat_structured(
                    prompt, image_base64=full_image_b64
                ),
            )
        ]
        if full_image_b64:
            if self._gemini is not None:
                chain.append((
                    "gemini",
                    getattr(self._gemini, "model_name", settings.GEMINI_MODEL),
                    lambda: self._gemini.generate_with_image(
                        prompt, image_base64=full_image_b64, temperature=0.4
                    ),
                ))
            if self._grok is not None:
                chain.append((
                    "grok",
                    getattr(self._grok, "model_name", settings.GROK_MODEL),
                    lambda: self._grok.chat_structured(
                        prompt, image_base64=full_image_b64
                    ),
                ))
        return chain

    async def _arbiter(
        self,
        panel_verdicts: List[PanelVerdict],
        agreement: Optional[float],
        sheet: EvidenceSheet,
        candidate_names: List[str],
        kb_text: str,
        full_image_b64: Optional[str],
        allowed: set,
        fallback_primary: str,
        free_read_styles: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Arbiter: reconcile the panel into a final STYLE MIXTURE.

        Tries OpenAI first, then the injected Gemini/Grok backups (A4b),
        skipping any provider whose circuit is open. Only when EVERY provider
        fails does this raise — letting ``run()`` degrade to the panel average.
        ``free_read_styles`` is the unconstrained image read surfaced as an extra
        independent opinion (decision C).
        """
        prompt = build_agent7_prompt(
            panel_verdicts, agreement, sheet, candidate_names, kb_text,
            free_read_styles,
        )
        chain = self._arbiter_chain(prompt, full_image_b64)
        breaker = get_circuit_breaker()
        last_exc: Optional[BaseException] = None
        for ignore_open in (False, True):
            attempted = False
            for key, model_id, call in chain:
                if not ignore_open and breaker.is_open(key):
                    continue
                attempted = True
                try:
                    return await self._run_arbiter_attempt(
                        key, model_id, call, sheet, allowed, fallback_primary
                    )
                except Exception as exc:  # noqa: BLE001 — try the next provider
                    last_exc = exc
            if attempted:
                break  # a closed provider was tried; no need for the last-resort pass
        raise last_exc or RuntimeError("Arbiter unavailable")

    async def _run_arbiter_attempt(
        self,
        provider_key: str,
        model_id: str,
        call: Callable[[], Awaitable[str]],
        sheet: EvidenceSheet,
        allowed: set,
        fallback_primary: str,
    ) -> Dict[str, Any]:
        """Run one arbiter provider attempt: call → parse → build result.

        Records telemetry + circuit-breaker success/failure. Raises on call or
        parse failure so the caller can fall through to the next provider.
        """
        breaker = get_circuit_breaker()
        start = time.monotonic()
        raw: Optional[str] = None
        try:
            raw = await asyncio.wait_for(call(), timeout=_TIMEOUT)
            json_str = OpenAIService.extract_json(raw)
            data = json.loads(json_str)
        except Exception as exc:
            breaker.record_failure(provider_key)
            _record_run(_ARBITER_AGENT, model_id,
                        (time.monotonic() - start) * 1000.0, False,
                        raw=raw, error=str(exc))
            raise
        breaker.record_success(provider_key)
        _record_run(_ARBITER_AGENT, model_id,
                    (time.monotonic() - start) * 1000.0, True,
                    raw=raw, parsed=json_str)
        result = self._build_arbiter_result(data, sheet, allowed, fallback_primary)
        result["arbiter_provider"] = provider_key
        return result

    def _build_arbiter_result(
        self,
        data: Dict[str, Any],
        sheet: EvidenceSheet,
        allowed: set,
        fallback_primary: str,
    ) -> Dict[str, Any]:
        """Turn a parsed arbiter JSON object into the final-result dict."""
        raw_dist = data.get("style_distribution")
        if not isinstance(raw_dist, dict) or not raw_dist:
            raw_dist = {str(data.get("style", fallback_primary)): 1.0}
        # Recall escape hatch: a style the arbiter named OUTSIDE the candidate set
        # is admitted only if it matches an existing KB entry AND (when enabled)
        # the observed evidence backs it — lifts the candidate ceiling without
        # polluting the KB or admitting an unsupported style (decision #72 / A2).
        observed_features = [it.feature for it in sheet.items if it.feature]
        raw_dist, allowed = self._expand_allowed_with_kb(
            raw_dist, allowed, observed_features
        )
        style_dist = build_style_distribution_safe(raw_dist, fallback_primary, allowed)

        composition_explanation = str(
            data.get("composition_explanation", data.get("explanation", ""))
        )
        raw_evidence = data.get("evidence_per_style") or {}
        raw_key_evidence = [
            str(b) for b in data.get("key_evidence", []) if str(b).strip()
        ]
        evidence_per_style: Dict[str, List[str]] = {}
        if isinstance(raw_evidence, dict):
            for style_name, bullets in raw_evidence.items():
                if style_name in style_dist.distribution and isinstance(bullets, list):
                    cleaned = [str(b) for b in bullets if str(b).strip()]
                    if cleaned:
                        evidence_per_style[style_name] = cleaned

        # Prefer legacy key_evidence for the primary style when the arbiter
        # emitted the old single-label schema.
        if style_dist.primary not in evidence_per_style and raw_key_evidence:
            evidence_per_style[style_dist.primary] = raw_key_evidence

        # Back-fill any style in the mixture that has no evidence bullets.
        for style_name in style_dist.distribution:
            if style_name not in evidence_per_style:
                evidence_per_style[style_name] = [
                    "(no specific evidence enumerated by the arbiter)"
                ]

        key_evidence = evidence_per_style.get(style_dist.primary, raw_key_evidence)
        return {
            "style": style_dist.primary,
            "confidence": style_dist.distribution[style_dist.primary],
            "explanation": composition_explanation,
            "key_evidence": key_evidence,
            "style_distribution": style_dist,
            "composition_explanation": composition_explanation,
            "evidence_per_style": evidence_per_style or None,
        }

    async def translate(
        self,
        *,
        explanation: str,
        key_evidence: List[str],
        composition_explanation: Optional[str],
        evidence_per_style: Optional[Dict[str, List[str]]],
        evidence_sheet: Optional[EvidenceSheet],
    ) -> tuple[Dict[str, Any], Optional[EvidenceSheet]]:
        """Translate the narrative + evidence sheet into Vietnamese.

        Two independent best-effort calls in parallel (narrative + sheet):
        splitting keeps each JSON small/reliable so a failure in one does not
        blank the other. Public so it can be invoked off the critical path (lazy,
        on first re-open) as well as inline. Never raises.

        Returns:
            A ``(translation_dict, evidence_sheet_vi)`` pair. ``translation_dict``
            holds the ``*_vi`` narrative fields (empty on failure);
            ``evidence_sheet_vi`` is the translated sheet (None on failure).
        """
        translation, sheet_vi = await asyncio.gather(
            self._translate_result(
                explanation=explanation,
                key_evidence=key_evidence,
                composition_explanation=composition_explanation,
                evidence_per_style=evidence_per_style,
            ),
            self._translate_evidence_sheet(evidence_sheet),
        )
        return translation, sheet_vi

    async def _translate_result(
        self,
        explanation: str,
        key_evidence: List[str],
        composition_explanation: Optional[str],
        evidence_per_style: Optional[Dict[str, List[str]]],
    ) -> Dict[str, Any]:
        """Translate the final English narrative into Vietnamese (one text call).

        Covers ONLY the narrative fields (explanation / key_evidence /
        composition / evidence_per_style) so the payload — and the JSON the model
        must return — stays small and reliable. The 12-dimension evidence sheet
        is translated separately (``_translate_evidence_sheet``) so a failure in
        one half never blanks the other (which would drop the whole result back
        to English).

        Best-effort: on any failure returns an empty dict so the caller leaves
        the ``*_vi`` fields unset and the frontend falls back to English. Uses
        the DeepSeek text LLM (its JSON mode is reliable).
        """
        payload = {
            "explanation": explanation,
            "key_evidence": key_evidence,
            "composition_explanation": composition_explanation or "",
            "evidence_per_style": evidence_per_style or {},
        }
        prompt = build_translation_prompt(payload)
        try:
            raw = await asyncio.wait_for(
                self._text.chat(prompt, temperature=0.2, json_mode=True),
                timeout=_TIMEOUT,
            )
        except Exception as exc:  # noqa: BLE001 — boundary: translation is best-effort
            logger.warning("Bilingual translation call failed: %s", exc)
            return {}
        data = parse_json_safe(raw)
        if not data:
            return {}

        ke_vi = data.get("key_evidence")
        eps_vi = data.get("evidence_per_style")
        return {
            "explanation_vi": (
                str(data["explanation"]) if data.get("explanation") else None
            ),
            "key_evidence_vi": (
                [str(b) for b in ke_vi] if isinstance(ke_vi, list) else None
            ),
            "composition_explanation_vi": (
                str(data["composition_explanation"])
                if data.get("composition_explanation")
                else None
            ),
            "evidence_per_style_vi": (
                {
                    str(k): [str(b) for b in v]
                    for k, v in eps_vi.items()
                    if isinstance(v, list)
                }
                if isinstance(eps_vi, dict)
                else None
            ),
        }

    async def _translate_evidence_sheet(
        self, evidence_sheet: Optional[EvidenceSheet]
    ) -> Optional[EvidenceSheet]:
        """Translate the 12-dimension evidence sheet into Vietnamese (own call).

        Translates each item's ``feature`` / ``note`` and the ``overall_note``,
        preserving ``dimension`` + ``suggested_styles``. Runs SEPARATELY from the
        narrative translation, and splits the rows into small batches translated
        concurrently so no single call's JSON output can be truncated (decision
        #89). Best-effort: a failed batch leaves those rows in English, and an
        empty merge returns None → the frontend falls back to the English sheet.
        """
        if evidence_sheet is None or not evidence_sheet.items:
            return None

        indexed = [
            {"i": i, "feature": it.feature, "note": it.note}
            for i, it in enumerate(evidence_sheet.items)
        ]
        # Translate in small batches so each call's JSON output stays well under
        # the model's output cap — a single 12-item payload overflows and gets
        # truncated, blanking the whole sheet (decision #89).
        batches = [
            indexed[k:k + _EVIDENCE_TRANSLATE_BATCH]
            for k in range(0, len(indexed), _EVIDENCE_TRANSLATE_BATCH)
        ]

        async def _translate_batch(items: List[Dict[str, Any]]) -> Dict[str, Any]:
            prompt = build_translation_prompt({"evidence_items": items})
            raw = await asyncio.wait_for(
                self._text.chat(prompt, temperature=0.2, json_mode=True),
                timeout=_TIMEOUT,
            )
            return parse_json_safe(raw)

        async def _translate_note(note: str) -> Optional[str]:
            prompt = build_translation_prompt({"overall_note": note})
            raw = await asyncio.wait_for(
                self._text.chat(prompt, temperature=0.2, json_mode=True),
                timeout=_TIMEOUT,
            )
            data = parse_json_safe(raw)
            val = data.get("overall_note") if isinstance(data, dict) else None
            return str(val) if val else None

        has_note = bool(evidence_sheet.overall_note)
        tasks: List[Awaitable[Any]] = [_translate_batch(b) for b in batches]
        if has_note:
            tasks.append(_translate_note(evidence_sheet.overall_note))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        note_result = results[-1] if has_note else None
        batch_results = results[:-1] if has_note else results

        # Merge translated items by global index; a failed batch simply leaves
        # those rows in English (partial translation beats all-or-nothing).
        merged: List[Dict[str, Any]] = []
        for res in batch_results:
            if isinstance(res, Exception):
                logger.warning("Evidence-sheet translation batch failed: %s", res)
                continue
            items = res.get("evidence_items") if isinstance(res, dict) else None
            if isinstance(items, list):
                merged.extend(items)

        if not merged:
            return None
        sheet_vi = _rebuild_translated_sheet(evidence_sheet, merged)
        if sheet_vi is not None and isinstance(note_result, str):
            sheet_vi.overall_note = note_result
        return sheet_vi

    async def _runoff(
        self,
        final: Dict[str, Any],
        sheet: EvidenceSheet,
        full_image_b64: Optional[str],
    ) -> Dict[str, Any]:
        """Contrastive run-off between the final top-2 styles (conversion lever).

        Fires only when the two highest-mass styles are within
        ``RUNOFF_MARGIN_MAX`` — the regime where the right style is available but
        the decision is genuinely torn. A focused vision call contrasts the two
        finalists' KB signatures against the image; its verdict is fused
        MULTIPLICATIVELY with the current split (``_apply_runoff``) so it only
        overturns the lead when confident. Best-effort: returns ``final``
        unchanged when disabled, no KB/image, the margin is decisive, a finalist
        is not in the KB, or the vision call fails.
        """
        if not settings.RUNOFF_ENABLED or self._kb is None or not full_image_b64:
            return final
        dist: Optional[StyleDistribution] = final.get("style_distribution")
        if dist is None:
            return final
        ranked = sorted(
            dist.distribution.items(), key=lambda kv: kv[1], reverse=True
        )
        if len(ranked) < 2:
            return final
        (name_a, prob_a), (name_b, prob_b) = ranked[0], ranked[1]
        if prob_a - prob_b >= settings.RUNOFF_MARGIN_MAX:
            return final  # decisive — no run-off needed
        entry_a = self._kb.match(name_a)
        entry_b = self._kb.match(name_b)
        if entry_a is None or entry_b is None:
            return final

        verdict = await self._runoff_verdict(entry_a, entry_b, sheet, full_image_b64)
        if verdict is None:
            return final
        ro_a, ro_b = verdict
        new_raw = _apply_runoff(dist.distribution, name_a, name_b, ro_a, ro_b)
        style_dist = build_style_distribution_safe(
            new_raw, name_a, set(dist.distribution)
        )

        out = dict(final)
        out["style"] = style_dist.primary
        out["confidence"] = style_dist.distribution[style_dist.primary]
        out["style_distribution"] = style_dist
        # Re-point key_evidence to the (possibly new) primary style.
        eps = out.get("evidence_per_style") or {}
        out["key_evidence"] = eps.get(style_dist.primary) or out.get("key_evidence", [])
        return out

    def _runoff_chain(self, prompt: str, full_image_b64: str) -> List[tuple]:
        """Ordered (provider_key, model_id, raw-call) chain for the run-off call.

        Prefers Grok (cheap, fast vision), then Gemini, then the OpenAI arbiter —
        all vision-capable. Only providers that were injected are included.
        """
        chain: List[tuple] = []
        if self._grok is not None:
            chain.append((
                "grok",
                getattr(self._grok, "model_name", settings.GROK_MODEL),
                lambda: self._grok.chat_structured(prompt, image_base64=full_image_b64),
            ))
        if self._gemini is not None:
            chain.append((
                "gemini",
                getattr(self._gemini, "model_name", settings.GEMINI_MODEL),
                lambda: self._gemini.generate_with_image(
                    prompt, image_base64=full_image_b64, temperature=0.2
                ),
            ))
        chain.append((
            "openai",
            getattr(self._arbiter_llm, "model_name", settings.OPENAI_MODEL),
            lambda: self._arbiter_llm.chat_structured(prompt, image_base64=full_image_b64),
        ))
        return chain

    async def _runoff_verdict(
        self,
        entry_a: "StyleEntry",
        entry_b: "StyleEntry",
        sheet: EvidenceSheet,
        full_image_b64: str,
    ) -> Optional[tuple]:
        """Run the contrastive vision call → (mass_a, mass_b) for the two finalists.

        Tries each provider in the run-off chain (skipping any whose circuit is
        open), parsing the two-way ``style_distribution``. Returns the two
        non-negative masses for ``entry_a``/``entry_b`` by case-insensitive name,
        or None when every provider fails or omits a finalist. Records telemetry
        + circuit-breaker outcome per attempt.
        """
        prompt = build_runoff_prompt(entry_a, entry_b, sheet)
        breaker = get_circuit_breaker()
        for key, model_id, call in self._runoff_chain(prompt, full_image_b64):
            if breaker.is_open(key):
                continue
            start = time.monotonic()
            raw: Optional[str] = None
            try:
                raw = await asyncio.wait_for(call(), timeout=_TIMEOUT)
                data = parse_json_safe(raw)
                sd = data.get("style_distribution") if isinstance(data, dict) else None
                if not isinstance(sd, dict):
                    raise ValueError("run-off returned no style_distribution")
                lut = {
                    k.lower(): safe_float(v)
                    for k, v in sd.items()
                    if isinstance(k, str)
                }
                mass_a = lut.get(entry_a.name.lower())
                mass_b = lut.get(entry_b.name.lower())
                if mass_a is None or mass_b is None or (mass_a <= 0 and mass_b <= 0):
                    raise ValueError("run-off omitted a finalist")
            except Exception as exc:  # noqa: BLE001 — try the next provider
                breaker.record_failure(key)
                _record_run(_RUNOFF_AGENT, model_id,
                            (time.monotonic() - start) * 1000.0, False,
                            raw=raw, error=str(exc))
                continue
            breaker.record_success(key)
            _record_run(_RUNOFF_AGENT, model_id,
                        (time.monotonic() - start) * 1000.0, True,
                        raw=raw, parsed=json.dumps(sd))
            return max(0.0, mass_a), max(0.0, mass_b)
        return None


# ── Module-level helpers ──────────────────────────────────────────────────────

def _rebuild_translated_sheet(
    sheet: Optional[EvidenceSheet], translated_items: Any
) -> Optional[EvidenceSheet]:
    """Rebuild an EvidenceSheet with Vietnamese ``feature``/``note`` strings.

    Maps the translated items back onto the original sheet by index, preserving
    each item's ``dimension`` and ``suggested_styles`` (only feature/note are
    translated). Returns None when there is nothing to translate or the
    translation payload is unusable, so the frontend falls back to the English
    sheet.
    """
    if sheet is None or not sheet.items or not isinstance(translated_items, list):
        return None
    by_index: Dict[int, Dict[str, Any]] = {
        entry["i"]: entry
        for entry in translated_items
        if isinstance(entry, dict) and isinstance(entry.get("i"), int)
    }
    new_items: List[EvidenceItem] = []
    for i, item in enumerate(sheet.items):
        tr = by_index.get(i, {})
        feature = tr.get("feature")
        note = tr.get("note")
        new_items.append(
            EvidenceItem(
                dimension=item.dimension,
                feature=str(feature) if feature else item.feature,
                suggested_styles=list(item.suggested_styles),
                note=str(note) if note is not None else item.note,
            )
        )
    return EvidenceSheet(
        items=new_items,
        proposed_styles=list(sheet.proposed_styles),
        overall_note=sheet.overall_note,
    )


def _apply_runoff(
    distribution: Dict[str, float],
    name_a: str,
    name_b: str,
    ro_a: float,
    ro_b: float,
) -> Dict[str, float]:
    """Fuse a run-off verdict into the top-2 of a mixture, multiplicatively.

    The two finalists keep their COMBINED mass; how it is split is updated by
    treating the run-off as independent evidence: ``p_new ∝ p_old × p_runoff``.
    A confident run-off (e.g. 0.2/0.8) can overturn a small arbiter lead, while a
    large arbiter lead survives a mild run-off — so a correct top-1 is not flipped
    on a coin toss. Every other style is left untouched. Returns the input
    unchanged when the run-off carries no usable signal.

    Args:
        distribution: The current style → probability mixture.
        name_a: The current top-1 style name (must be a key of ``distribution``).
        name_b: The current runner-up style name (must be a key).
        ro_a: Run-off mass for ``name_a`` (≥ 0).
        ro_b: Run-off mass for ``name_b`` (≥ 0).

    Returns:
        A new distribution dict with the top-2 re-split (not yet normalised).
    """
    combined = distribution.get(name_a, 0.0) + distribution.get(name_b, 0.0)
    weight_a = distribution.get(name_a, 0.0) * max(0.0, ro_a)
    weight_b = distribution.get(name_b, 0.0) * max(0.0, ro_b)
    total = weight_a + weight_b
    if combined <= 0 or total <= 0:
        return dict(distribution)
    updated = dict(distribution)
    updated[name_a] = combined * weight_a / total
    updated[name_b] = combined * weight_b / total
    return updated


def _gate_out_of_kb_primary(
    final: Dict[str, Any],
    out_of_kb_names: set,
    valid_judges: int,
    agreement: Optional[float],
    allowed: set,
    fallback_primary: str,
) -> tuple[Dict[str, Any], bool]:
    """Demote an out-of-KB primary unless the panel cleared the higher bar.

    An out-of-KB style has no curated provenance, so it may only stay the primary
    result when the inter-judge agreement is strong enough: ≥ 3 valid judges AND
    ``agreement >= OUT_OF_KB_AGREEMENT_MIN``. Otherwise its mass is dropped and the
    mixture is rebuilt from the in-KB remainder, returning the best in-KB style as
    primary. A non-out-of-KB primary is returned unchanged.

    Returns:
        ``(final, demoted)`` — the (possibly rebuilt) result dict and whether a
        demotion happened.
    """
    dist: Optional[StyleDistribution] = final.get("style_distribution")
    if dist is None or dist.primary not in out_of_kb_names:
        return final, False
    meets_bar = (
        valid_judges >= 3
        and agreement is not None
        and agreement >= settings.OUT_OF_KB_AGREEMENT_MIN
    )
    if meets_bar:
        return final, False
    in_kb_allowed = {a for a in allowed if a not in out_of_kb_names}
    remaining = {
        s: p for s, p in dist.distribution.items() if s not in out_of_kb_names
    }
    if not remaining:
        remaining = {fallback_primary: 1.0}
    style_dist = build_style_distribution_safe(
        remaining, fallback_primary, in_kb_allowed or None
    )
    out = dict(final)
    out["style"] = style_dist.primary
    out["confidence"] = style_dist.distribution[style_dist.primary]
    out["style_distribution"] = style_dist
    eps = out.get("evidence_per_style") or {}
    out["key_evidence"] = eps.get(style_dist.primary) or out.get("key_evidence", [])
    return out, True


def _build_evidence_votes(sheet: EvidenceSheet) -> Dict[str, float]:
    """Tally how many evidence dimensions support each proposed style.

    Counts FREQUENCY (one vote per dimension that suggests the style); it does
    NOT multiply by any self-reported confidence (unreliable). The result is a
    SOFT ranking hint for the prompts / fallback — not a final probability.
    """
    acc: Dict[str, float] = {}
    for item in sheet.items:
        for style in item.suggested_styles:
            name = style.strip()
            if name:
                acc[name] = acc.get(name, 0.0) + 1.0
    total = sum(acc.values()) or 1.0
    return {k: v / total for k, v in acc.items()}


def _fallback_primary(evidence_votes: Dict[str, float], candidate_names: List[str]) -> str:
    """Pick a primary style without an LLM (top candidate by evidence votes)."""
    if candidate_names:
        return max(candidate_names, key=lambda n: evidence_votes.get(n, 0.0))
    if evidence_votes:
        return max(evidence_votes, key=evidence_votes.get)
    return "Unknown"


def _is_hybrid(
    final_dist: Optional[StyleDistribution], extraction_agreement: Optional[float]
) -> bool:
    """Decide whether the result is a multi-style (hybrid) building.

    True when EITHER the final mixture carries ≥ 2 styles each at least
    ``HYBRID_MASS_MIN`` of the mass (the arbiter produced a genuine mixture), OR
    the extraction calls disagreed — ``extraction_agreement`` below
    ``EXTRACTION_AGREEMENT_MIN`` — which signals a multi-style/ambiguous reading
    even when the arbiter forced a thin single-label winner. Independent of the
    ``uncertain`` abstention flag.
    """
    significant = 0
    if final_dist is not None:
        significant = sum(
            1
            for p in final_dist.distribution.values()
            if p >= settings.HYBRID_MASS_MIN
        )
    if significant >= 2:
        return True
    return (
        extraction_agreement is not None
        and extraction_agreement < settings.EXTRACTION_AGREEMENT_MIN
    )


def _distribution_stats(distribution: Dict[str, float]) -> tuple[float, float]:
    """Return (certainty_margin, Shannon entropy in nats) for a mixture.

    ``margin`` = primary − second-best probability (1.0 for a 1-hot, 0.0 when
    the top two are tied). ``entropy`` = -Σ p·ln(p) over positive probabilities.
    """
    probs = sorted((p for p in distribution.values() if p > 0), reverse=True)
    if not probs:
        return 0.0, 0.0
    margin = probs[0] - (probs[1] if len(probs) > 1 else 0.0)
    entropy = -sum(p * math.log(p) for p in probs)
    return round(margin, 4), round(entropy, 4)


def _judge_weights(distributions: List[Dict[str, float]]) -> List[float]:
    """Weight each judge by decisiveness (lower entropy → higher weight).

    A judge whose mixture is peaked (a confident ranking) contributes more to the
    panel average than one spreading mass evenly. Weights are floored at 0.1 so
    no valid judge is silenced; a 1-style mixture gets full weight.
    """
    weights: List[float] = []
    for dist in distributions:
        probs = [p for p in dist.values() if p > 0]
        if len(probs) <= 1:
            weights.append(1.0)
            continue
        entropy = -sum(p * math.log(p) for p in probs)
        norm = entropy / math.log(len(probs))  # in [0, 1]
        weights.append(max(0.1, 1.0 - norm))
    return weights


def _run_quality(
    valid_judges: int,
    attempted_judges: int,
    extraction_completeness: float,
    extraction_agreement: Optional[float],
) -> float:
    """Return a [0,1] run-quality multiplier for the final confidence.

    Penalises a degraded run: missing judges, lost extraction calls, and
    disagreeing extraction calls each pull it down. Structural (no tuned
    threshold), so it does not overfit the benchmark:

        quality = geo_mean(judge_completeness, extraction_completeness)
                  × (0.5 + 0.5·extraction_agreement)
    """
    judge_completeness = (valid_judges / attempted_judges) if attempted_judges else 1.0
    ext_complete = max(0.0, min(1.0, extraction_completeness))
    base = math.sqrt(max(0.0, judge_completeness) * ext_complete)
    agree = 0.5 if extraction_agreement is None else max(0.0, min(1.0, extraction_agreement))
    return base * (0.5 + 0.5 * agree)


def _run_status(
    valid_judges: int,
    attempted_judges: int,
    extraction_completeness: float,
    degraded: bool,
) -> str:
    """Classify the run's health into completed / degraded / failed (A4b).

    ``failed`` = no judge produced a usable verdict (the result is only a
    fallback guess); ``degraded`` = some judge or extraction call was lost, or
    the arbiter fell back / inputs were thin (``degraded`` flag); otherwise
    ``completed``. Stored in DetailJson; the AnalysisStatus DB column keeps its
    documented vocabulary.
    """
    if valid_judges == 0:
        return "failed"
    if (
        degraded
        or extraction_completeness < 1.0
        or valid_judges < attempted_judges
    ):
        return "degraded"
    return "completed"


def _merge_narrative(
    arbiter_final: Dict[str, Any], panel_dist: StyleDistribution
) -> Dict[str, Any]:
    """Swap in the panel's mixture but keep the arbiter's narrative (W1).

    The arbiter still authored the explanation / evidence-per-style; only the
    decided distribution (and its derived primary / confidence / key_evidence) is
    replaced by the panel's. ``key_evidence`` is re-pointed to the new primary
    when the arbiter enumerated evidence for it.
    """
    primary = panel_dist.primary
    evidence_per_style = arbiter_final.get("evidence_per_style") or {}
    key_evidence = evidence_per_style.get(primary) or arbiter_final.get("key_evidence", [])
    out = dict(arbiter_final)
    out["style"] = primary
    out["confidence"] = panel_dist.distribution[primary]
    out["style_distribution"] = panel_dist
    out["key_evidence"] = key_evidence
    return out


def decide_final_distribution(
    mode: str,
    arbiter_final: Dict[str, Any],
    valid_dists: List[Dict[str, float]],
    judge_weights: List[float],
    candidate_names: List[str],
    agreement: Optional[float],
    allowed: set,
    fallback_primary: str,
) -> Dict[str, Any]:
    """Choose the final mixture per ``DECISION_MODE`` (W1 redesign).

    - ``arbiter``   : the arbiter's own mixture (baseline; unchanged behaviour).
    - ``panel``     : the decisiveness-weighted mean of the judges; the arbiter
                      contributes only the narrative.
    - ``consensus`` : the panel mean when the panel is DECISIVE (agreement ≥
                      ``PANEL_AGREEMENT_MIN`` AND a clear margin); otherwise the
                      arbiter breaks the tie. Also defers to the arbiter when it
                      used the escape hatch (primary outside the candidate set) so
                      the recall-lifting upside survives.

    Falls back to the arbiter's mixture whenever the panel produced nothing
    usable. The arbiter is ALWAYS still called upstream (for the narrative and the
    tie-break signal); this function only decides which distribution becomes final.
    """
    if mode == "arbiter" or not valid_dists:
        return arbiter_final
    panel_mean = weighted_mean_distribution(valid_dists, candidate_names, judge_weights)
    if not panel_mean:
        return arbiter_final
    panel_dist = build_style_distribution_safe(panel_mean, fallback_primary, allowed)
    if mode == "panel":
        return _merge_narrative(arbiter_final, panel_dist)
    # mode == "consensus"
    arbiter_primary = arbiter_final.get("style")
    escaped = arbiter_primary is not None and arbiter_primary not in set(candidate_names)
    panel_margin, _ = _distribution_stats(panel_dist.distribution)
    panel_decisive = (
        agreement is not None
        and agreement >= settings.PANEL_AGREEMENT_MIN
        and panel_margin >= settings.UNCERTAINTY_MARGIN_MIN
    )
    if escaped or not panel_decisive:
        return arbiter_final  # arbiter breaks the tie / lifts the recall ceiling
    return _merge_narrative(arbiter_final, panel_dist)


def _panel_fallback(
    valid_dists: List[Dict[str, float]],
    judge_weights: List[float],
    candidate_names: List[str],
    fallback_primary: str,
    allowed: set,
) -> Dict[str, Any]:
    """Build a final-result dict from the panel average when the arbiter fails.

    Uses the decisiveness-weighted mean of the valid judges' distributions
    (better than a single evidence-vote guess); degrades to a 1-hot on
    ``fallback_primary`` when no judge succeeded.
    """
    mean = weighted_mean_distribution(valid_dists, candidate_names, judge_weights)
    if mean:
        style_dist = build_style_distribution_safe(mean, fallback_primary, allowed)
        note = "Arbiter unavailable; final mixture is the panel average."
    else:
        style_dist = build_style_distribution_safe(
            {fallback_primary: 1.0}, fallback_primary, None
        )
        note = "Arbiter and panel unavailable; evidence-vote fallback used."
    primary_prob = style_dist.distribution[style_dist.primary]
    return {
        "style": style_dist.primary,
        "confidence": primary_prob,
        "explanation": note,
        "key_evidence": [],
        "style_distribution": style_dist,
        "composition_explanation": None,
        "evidence_per_style": None,
    }
