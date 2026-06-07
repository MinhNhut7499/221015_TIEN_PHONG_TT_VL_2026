"""7-agent architecture analysis pipeline.

Architecture:
    Tier 1 (asyncio.gather — parallel per component):
        Agent 1 (Gemini vision)   → geometric feature description
        Agent 2 (Gemini ×3 MC)    → style probability distribution
        Agent 3a (rule check)     → hard rule contradiction detection
        Agent 3b (DeepSeek)       → contradiction interpretation (if needed)
        Agent 4 (DeepSeek)        → per-component style conclusion

    compute_aggregated_votes()    → weighted sum (pure code)

    Tier 2 (sequential):
        Agent 5 (DeepSeek)        → primary advocate
        Agent 6 (DeepSeek)        → alternative hypothesist (label only)
        Agent 7 (OpenAI GPT-4o)   → final arbitrator with CoT
"""
import asyncio
import json
import logging
import math
from typing import Dict, List

from app.config import settings
from chatbot.services.deepseek_service import DeepSeekService
from chatbot.services.gemini_service import GeminiService
from chatbot.services.openai_service import OpenAIService
from chatbot.utils.prompt_builder import (
    build_agent1_prompt,
    build_agent2_prompt,
    build_agent3b_prompt,
    build_agent4_prompt,
    build_agent5_prompt,
    build_agent6_prompt,
    build_agent7_prompt,
    build_translation_prompt,
)
from chatbot.services.fuser_service import FuserService
from chatbot.utils.fusion import numeric_fuse
from chatbot.utils.rule_checker import (
    check_material_consistency,
    check_prior_vote_agreement,
    check_rules,
    compute_attribute_affinity,
)
from chatbot.utils.schemas import (
    Agent1Output,
    Agent2Output,
    Agent3Output,
    Agent4Output,
    Agent5Output,
    Agent6Output,
    AttributeVector,
    ComponentAnalysis,
    DetectedComponent,
    FinalAnalysisResult,
    MaterialDistribution,
    PipelineInput,
    STYLE_CLASSES,
    StyleCandidate,
    StyleDistribution,
)
from typing import Any, Optional

logger = logging.getLogger(__name__)

_AGENT2_TEMPERATURES = [0.5, 0.7, 0.9]
_TIMEOUT = settings.PIPELINE_AGENT_TIMEOUT_SEC
_SECONDARY_THRESHOLD = 0.15
"""Minimum normalised probability for a style to enter ``StyleDistribution.secondary``."""


class PipelineRunner:
    """Orchestrates the 7-agent analysis pipeline for a list of components.

    Receives the three LLM services via constructor injection so they can be
    swapped or mocked in tests without touching this class.
    """

    def __init__(
        self,
        vision_llm: GeminiService,
        text_llm: DeepSeekService,
        final_llm: OpenAIService,
        fuser: Optional[FuserService] = None,
    ) -> None:
        """Store injected LLM services + optional learned fuser.

        Args:
            vision_llm: GeminiService for Agent 1 and Agent 2.
            text_llm: DeepSeekService for Agents 3b, 4, 5, 6.
            final_llm: OpenAIService for Agent 7.
            fuser: Optional learned FuserService. When provided (and global
                features are present) it produces the numeric prior anchor /
                fallback instead of the hand-weighted ``numeric_fuse``.
        """
        self._vision = vision_llm
        self._text = text_llm
        self._final = final_llm
        self._fuser = fuser

    async def run(self, pipeline_input: PipelineInput) -> FinalAnalysisResult:
        """Run the full 7-agent pipeline with both component and material inputs.

        Args:
            pipeline_input: Combined output of YOLOv8s-detection (components)
                and YOLOv8s-cls (material classification).

        Returns:
            FinalAnalysisResult with style, confidence, explanation, evidence.

        Raises:
            asyncio.TimeoutError: If any agent exceeds PIPELINE_AGENT_TIMEOUT_SEC.
        """
        import time
        start = time.monotonic()

        components = pipeline_input.components
        material = pipeline_input.material
        material_available = pipeline_input.material_available
        # Global features are Optional during migration — None for legacy callers.
        global_features = pipeline_input.global_features
        if global_features is not None:
            attributes: Optional[AttributeVector] = global_features.attributes
            style_prior: Optional[Dict[str, float]] = global_features.style_prior
            attribute_affinity: Optional[Dict[str, float]] = compute_attribute_affinity(
                attributes
            )
            gradcam_b64: Optional[str] = global_features.gradcam_b64
        else:
            attributes = None
            style_prior = None
            attribute_affinity = None
            gradcam_b64 = None

        # Tier 1: parallel per-component analysis.
        # return_exceptions=True so a single component failure (e.g. Gemini 503
        # in Agent 1) drops only that component instead of crashing the request.
        warnings: List[str] = []
        if not components:
            warnings.append(
                "No components detected by YOLO; relying on CNN prior + attributes"
            )
        raw_results = await asyncio.gather(
            *[
                self._run_component(c, material, attributes, material_available)
                for c in components
            ],
            return_exceptions=True,
        )
        tier1_results: List[ComponentAnalysis] = []
        for component, outcome in zip(components, raw_results):
            if isinstance(outcome, BaseException):
                logger.warning(
                    "Component %s (%s) failed and was dropped: %s",
                    component.component_id,
                    component.component_type,
                    outcome,
                )
                continue
            tier1_results.append(outcome)

        dropped = len(components) - len(tier1_results)
        if dropped:
            warnings.append(
                f"{dropped}/{len(components)} component(s) dropped due to LLM errors"
            )
        agent2_degraded = sum(1 for ca in tier1_results if ca.agent2.degraded)
        if agent2_degraded:
            warnings.append(
                f"Agent 2 degraded on {agent2_degraded} component(s) "
                "(excluded from vote aggregation)"
            )
        degraded = bool(warnings)

        # Aggregation (pure code, no LLM). Raw weighted sums feed nothing else;
        # the prompts receive a NORMALISED copy so magnitudes are interpretable.
        vote_table = compute_aggregated_votes(tier1_results)
        votes_norm = _normalize_votes(vote_table)

        # P4 soft cross-check: flag when component votes and the CNN prior
        # disagree on the leading style (note injected into Agent 7's prompt).
        cross_check_note = (
            check_prior_vote_agreement(votes_norm, style_prior)
            if style_prior is not None
            else None
        )
        if cross_check_note:
            warnings.append("Low agreement between component votes and CNN prior")

        # Build component summaries for Tier 2 prompts
        summaries = [
            f"{ca.component_type} → {ca.agent4.style} ({ca.agent4.confidence:.2f}): "
            f"{ca.agent4.reasoning[:80]}"
            for ca in tier1_results
        ]

        # Numeric fused prior — used BOTH as an anchor in the LLM prompts AND
        # as the fallback verdict if the LLM fusion (Tier 2) is unavailable
        # (→ LLM is truly optional). Prefer the learned, calibrated fuser when
        # available; otherwise the hand-weighted numeric_fuse.
        fused_prior = self._compute_fused_prior(
            components=components,
            material=material,
            material_available=material_available,
            attributes=attributes,
            style_prior=style_prior,
            votes_norm=votes_norm,
            attribute_affinity=attribute_affinity,
        )
        # Always prefer the whole-image input so Agent 7 keeps visual context
        # even when YOLO detected 0 components.
        full_image_b64 = pipeline_input.full_image_base64 or (
            components[0].full_image_base64 if components else None
        )

        # Tier 2: sequential LLM fusion. Wrapped so a hard LLM failure (after
        # retries) degrades to the numeric fused prior instead of a 500.
        translation: Dict[str, Any] = {}
        try:
            agent5 = await self._agent5(
                votes_norm,
                summaries,
                material,
                style_prior,
                attribute_affinity,
                attributes,
                material_available,
                fused_prior,
            )
            agent6 = await self._agent6(agent5.style)
            final = await self._agent7(
                agent5,
                agent6,
                votes_norm,
                material,
                full_image_b64,
                style_prior,
                attribute_affinity,
                attributes,
                material_available,
                cross_check_note,
                fused_prior,
            )
            if settings.ENABLE_BILINGUAL:
                translation = await self._translate_result(
                    explanation=final.get("explanation", ""),
                    key_evidence=final.get("key_evidence", []),
                    composition_explanation=final.get("composition_explanation"),
                    evidence_per_style=final.get("evidence_per_style"),
                )
        except Exception as exc:  # boundary: total LLM-fusion outage
            logger.warning("Tier-2 LLM fusion failed; using numeric fusion: %s", exc)
            warnings.append("LLM fusion unavailable; numeric fusion used")
            degraded = True
            agent5, agent6, final = _numeric_fallback(fused_prior)

        final_dist: Optional[StyleDistribution] = final.get("style_distribution")
        primary_style = final["style"]
        primary_conf = float(final["confidence"])
        margin, entropy = (
            _distribution_stats(final_dist.distribution)
            if final_dist is not None
            else (None, None)
        )

        # Abstention: flag low-confidence results and surface top-K candidates.
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
            uncertain = (
                (margin is not None and margin < settings.UNCERTAINTY_MARGIN_MIN)
                or (entropy is not None and entropy > settings.UNCERTAINTY_ENTROPY_MAX)
                or (
                    settings.UNCERTAINTY_CONF_MIN > 0
                    and primary_conf < settings.UNCERTAINTY_CONF_MIN
                )
            )
        if uncertain:
            warnings.append("Low-confidence result — returning top-K candidates")

        elapsed_ms = (time.monotonic() - start) * 1000.0
        return FinalAnalysisResult(
            style=primary_style,
            confidence=primary_conf,
            explanation=final.get("explanation", ""),
            key_evidence=final.get("key_evidence", []),
            components=tier1_results,
            agent5=agent5,
            agent6=agent6,
            processing_time_ms=round(elapsed_ms, 1),
            style_distribution=final_dist,
            composition_explanation=final.get("composition_explanation"),
            evidence_per_style=final.get("evidence_per_style"),
            gradcam_b64=gradcam_b64,
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
        )

    async def _translate_result(
        self,
        explanation: str,
        key_evidence: List[str],
        composition_explanation: Optional[str],
        evidence_per_style: Optional[Dict[str, List[str]]],
    ) -> Dict[str, Any]:
        """Translate the final English narrative into Vietnamese (one text call).

        Returns a dict with keys ``explanation_vi`` / ``key_evidence_vi`` /
        ``composition_explanation_vi`` / ``evidence_per_style_vi``. On any
        failure (LLM error, bad JSON) returns an empty dict so the caller leaves
        the ``*_vi`` fields unset and the frontend falls back to English.
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
                self._text.chat(prompt, temperature=0.2),
                timeout=_TIMEOUT,
            )
        except Exception as exc:  # noqa: BLE001 — boundary: translation is best-effort
            logger.warning("Bilingual translation call failed: %s", exc)
            return {}
        data = _parse_json_safe(raw)
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

    def _compute_fused_prior(
        self,
        *,
        components: List[DetectedComponent],
        material: MaterialDistribution,
        material_available: bool,
        attributes: Optional[AttributeVector],
        style_prior: Optional[Dict[str, float]],
        votes_norm: Dict[str, float],
        attribute_affinity: Optional[Dict[str, float]],
    ) -> Dict[str, float]:
        """Prior anchor: learned fuser when available, else hand-weighted fuse."""
        if self._fuser is not None and style_prior is not None and attributes is not None:
            try:
                return self._fuser.predict(
                    style_prior, attributes, components, material, material_available
                )
            except Exception as exc:  # boundary: model load / predict failure
                logger.warning("Learned fuser failed; using numeric_fuse: %s", exc)
        return numeric_fuse(
            votes_norm,
            style_prior,
            attribute_affinity,
            weight_votes=settings.FUSION_WEIGHT_VOTES,
            weight_prior=settings.FUSION_WEIGHT_PRIOR,
            weight_attribute=settings.FUSION_WEIGHT_ATTRIBUTE,
        )

    async def _run_component(
        self,
        component: DetectedComponent,
        material: MaterialDistribution,
        attributes: Optional[AttributeVector] = None,
        material_available: bool = True,
    ) -> ComponentAnalysis:
        """Run Agents 1-4 for a single component, with material + attribute context.

        Args:
            component: A DetectedComponent from YOLO.
            material: Building-level material classification.
            attributes: Optional building-level visual attribute vector from the
                global feature extractor; forwarded to Agent 2's prompt so the
                per-component style scoring can be informed by whole-image
                geometry and texture.
            material_available: When False the material signal is mock noise, so
                it is withheld from Agent 2 and the material-consistency rule is
                skipped (it would otherwise raise spurious contradictions).

        Returns:
            ComponentAnalysis with all four agent outputs filled in.
        """
        ctype = component.component_type

        # Agent 1 — Gemini: geometric description (with image)
        agent1_text = await asyncio.wait_for(
            self._vision.generate_with_image(
                prompt=build_agent1_prompt(ctype),
                image_base64=component.crop_base64,
                temperature=0.4,
            ),
            timeout=_TIMEOUT,
        )
        agent1 = Agent1Output(
            component_id=component.component_id,
            feature_description=agent1_text,
        )

        # Agent 2 — Gemini ×3 Monte Carlo: style distribution
        # (with material + building-level attribute context)
        agent2 = await self._agent2(
            component, agent1, material, attributes, material_available
        )

        # Agent 3a — rule check (sync, no LLM); fuse component + material contradictions
        top_style = max(agent2.style_distribution, key=lambda k: agent2.style_distribution[k])
        agent3 = check_rules(ctype, top_style)
        material_msg = (
            check_material_consistency(material.dominant, top_style)
            if material_available
            else None
        )
        if material_msg is not None:
            agent3 = Agent3Output(
                component_id=component.component_id,
                has_contradiction=True,
                contradiction_analysis=(
                    f"{agent3.contradiction_analysis} | Material check: {material_msg}"
                    if agent3.has_contradiction
                    else material_msg
                ),
                violated_rules=agent3.violated_rules + [material_msg],
            )
        else:
            agent3 = Agent3Output(
                component_id=component.component_id,
                has_contradiction=agent3.has_contradiction,
                contradiction_analysis=agent3.contradiction_analysis,
                violated_rules=agent3.violated_rules,
            )

        # Agent 3b — DeepSeek fallback if contradiction detected
        if agent3.has_contradiction:
            agent3 = await self._agent3b(component, agent2, agent3)

        # Agent 4 — DeepSeek: per-component conclusion
        agent4 = await self._agent4(component, agent2, agent3)

        return ComponentAnalysis(
            component_id=component.component_id,
            component_type=ctype,
            detection_confidence=component.detection_confidence,
            bounding_box=component.bounding_box,
            agent1=agent1,
            agent2=agent2,
            agent3=agent3,
            agent4=agent4,
        )

    async def _agent2(
        self,
        component: DetectedComponent,
        agent1: Agent1Output,
        material: MaterialDistribution,
        attributes: Optional[AttributeVector] = None,
        material_available: bool = True,
    ) -> Agent2Output:
        """Agent 2: Monte Carlo ×3 style distribution, averaged.

        Receives Agent 1's feature description, the building's dominant
        material AND (optionally) the building-level AttributeVector so the
        per-component style scoring is informed by whole-image cues. The
        material line is withheld when ``material_available`` is False.
        """
        prompt = build_agent2_prompt(
            component.component_type,
            agent1.feature_description,
            material,
            attributes,
            material_available,
        )
        distributions: List[Dict[str, float]] = []

        for temp in _AGENT2_TEMPERATURES:
            try:
                raw = await asyncio.wait_for(
                    self._vision.generate_with_image(
                        prompt=prompt,
                        image_base64=component.crop_base64,
                        temperature=temp,
                    ),
                    timeout=_TIMEOUT,
                )
                dist = _parse_json_safe(raw)
                distributions.append({s: float(dist.get(s, 0.0)) for s in STYLE_CLASSES})
            except Exception as exc:
                logger.warning("Agent 2 call failed (temp=%.1f): %s", temp, exc)

        degraded = not distributions
        if degraded:
            # All Monte Carlo calls failed (e.g. Gemini 503). Use a placeholder
            # uniform so Agent 3a/4 don't break, but mark degraded so this
            # component is EXCLUDED from vote aggregation (a uniform vote would
            # otherwise inject noise across all styles).
            logger.warning(
                "Agent 2 fully degraded for component %s — excluded from votes",
                component.component_id,
            )
            uniform = 1.0 / len(STYLE_CLASSES)
            averaged = {s: uniform for s in STYLE_CLASSES}
        else:
            averaged = {
                style: sum(d.get(style, 0.0) for d in distributions) / len(distributions)
                for style in STYLE_CLASSES
            }
            total = sum(averaged.values()) or 1.0
            averaged = {k: v / total for k, v in averaged.items()}

        return Agent2Output(
            component_id=component.component_id,
            style_distribution=averaged,
            degraded=degraded,
        )

    async def _agent3b(
        self,
        component: DetectedComponent,
        agent2: Agent2Output,
        agent3_code: Agent3Output,
    ) -> Agent3Output:
        """Agent 3b: DeepSeek interprets a rule contradiction."""
        top_style = max(
            agent2.style_distribution, key=lambda k: agent2.style_distribution[k]
        )
        prompt = build_agent3b_prompt(
            component.component_type, agent2.style_distribution, top_style
        )
        try:
            raw = await asyncio.wait_for(
                self._text.chat(prompt, temperature=0.3),
                timeout=_TIMEOUT,
            )
            data = _parse_json_safe(raw)
            return Agent3Output(
                component_id=component.component_id,
                has_contradiction=bool(data.get("has_contradiction", True)),
                contradiction_analysis=str(data.get("contradiction_analysis", "")),
                violated_rules=list(data.get("violated_rules", [])),
            )
        except Exception as exc:
            logger.warning("Agent 3b failed, using code result: %s", exc)
            return Agent3Output(
                component_id=component.component_id,
                has_contradiction=agent3_code.has_contradiction,
                contradiction_analysis=agent3_code.contradiction_analysis,
                violated_rules=agent3_code.violated_rules,
            )

    async def _agent4(
        self,
        component: DetectedComponent,
        agent2: Agent2Output,
        agent3: Agent3Output,
    ) -> Agent4Output:
        """Agent 4: DeepSeek per-component MIXTURE distribution + reasoning.

        Agent 4 now emits a probability distribution over the styles it
        considers plausible for this single component. Legacy ``style``/
        ``confidence`` fields on Agent4Output are kept populated from the
        primary entry of that distribution for backward compatibility with
        the vote table and downstream prompts.
        """
        sorted_styles = sorted(
            agent2.style_distribution.items(), key=lambda x: x[1], reverse=True
        )
        top3 = [s for s, _ in sorted_styles[:3]]
        fallback_primary = top3[0] if top3 else STYLE_CLASSES[0]
        prompt = build_agent4_prompt(
            component_type=component.component_type,
            top3_styles=top3,
            style_distribution=agent2.style_distribution,
            has_contradiction=agent3.has_contradiction,
            contradiction_analysis=agent3.contradiction_analysis,
        )
        raw = await asyncio.wait_for(
            self._text.chat(prompt, temperature=0.3),
            timeout=_TIMEOUT,
        )
        data = _parse_json_safe(raw)
        # New mixture field; fall back to legacy {style, confidence} format
        # so we degrade gracefully if a model emits the old shape.
        raw_dist = data.get("style_distribution")
        if not isinstance(raw_dist, dict) or not raw_dist:
            legacy_style = str(data.get("style", fallback_primary))
            legacy_conf = _safe_float(data.get("confidence", 0.5))
            raw_dist = {legacy_style: max(legacy_conf, 1e-3)}
        style_dist = _build_style_distribution_safe(raw_dist, fallback_primary)
        primary_prob = style_dist.distribution[style_dist.primary]
        return Agent4Output(
            component_id=component.component_id,
            component_type=component.component_type,
            style=style_dist.primary,
            confidence=primary_prob,
            reasoning=str(data.get("reasoning", "")),
            style_distribution=style_dist,
        )

    async def _agent5(
        self,
        vote_table: Dict[str, float],
        summaries: List[str],
        material: MaterialDistribution,
        style_prior: Optional[Dict[str, float]] = None,
        attribute_affinity: Optional[Dict[str, float]] = None,
        attributes: Optional[AttributeVector] = None,
        material_available: bool = True,
        fused_prior: Optional[Dict[str, float]] = None,
    ) -> Agent5Output:
        """Agent 5: DeepSeek primary advocate — emit a STYLE MIXTURE.

        Receives all four evidence streams (vote table, material, CNN style
        prior, attribute affinity) plus the verbose AttributeVector and the
        numeric ``fused_prior`` anchor. Builds a ``StyleDistribution`` from the
        LLM-emitted mixture; falls back gracefully to a 1-hot on the top
        vote-table style if the LLM emits an empty or invalid distribution.
        """
        prompt = build_agent5_prompt(
            vote_table,
            summaries,
            material,
            style_prior,
            attribute_affinity,
            attributes,
            material_available,
            fused_prior,
        )
        raw = await asyncio.wait_for(
            self._text.chat(prompt, temperature=0.4),
            timeout=_TIMEOUT,
        )
        data = _parse_json_safe(raw)
        top_vote_style = (
            max(vote_table, key=lambda k: vote_table[k])
            if vote_table else STYLE_CLASSES[0]
        )
        raw_dist = data.get("style_distribution")
        if not isinstance(raw_dist, dict) or not raw_dist:
            # Backward-compat: accept legacy {style, confidence} shape.
            legacy_style = str(data.get("style", top_vote_style))
            legacy_conf = _safe_float(data.get("confidence", 0.5))
            raw_dist = {legacy_style: max(legacy_conf, 1e-3)}
        style_dist = _build_style_distribution_safe(raw_dist, top_vote_style)
        primary_prob = style_dist.distribution[style_dist.primary]
        composition_narrative = str(
            data.get("composition_narrative", data.get("reasoning", ""))
        )
        return Agent5Output(
            style=style_dist.primary,
            confidence=primary_prob,
            reasoning=composition_narrative,
            style_distribution=style_dist,
            composition_narrative=composition_narrative,
        )

    async def _agent6(self, agent5_style: str) -> Agent6Output:
        """Agent 6: DeepSeek alternative hypothesist (receives label only)."""
        prompt = build_agent6_prompt(agent5_style)
        raw = await asyncio.wait_for(
            self._text.chat(prompt, temperature=0.6),
            timeout=_TIMEOUT,
        )
        data = _parse_json_safe(raw)
        return Agent6Output(
            style=str(data.get("style", "Unknown")),
            confidence=float(data.get("confidence", 0.3)),
            reasoning=str(data.get("reasoning", "")),
        )

    async def _agent7(
        self,
        agent5: Agent5Output,
        agent6: Agent6Output,
        vote_table: Dict[str, float],
        material: MaterialDistribution,
        full_image_b64: Optional[str],
        style_prior: Optional[Dict[str, float]] = None,
        attribute_affinity: Optional[Dict[str, float]] = None,
        attributes: Optional[AttributeVector] = None,
        material_available: bool = True,
        cross_check_note: Optional[str] = None,
        fused_prior: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """Agent 7: GPT-4o final arbitrator — fuses 4 streams into a STYLE MIXTURE.

        Returns a dict the caller uses to populate both legacy and mixture
        fields on FinalAnalysisResult:

        - ``style``, ``confidence``, ``explanation``, ``key_evidence``:
          legacy single-label fields derived from the primary style.
        - ``style_distribution``: validated ``StyleDistribution``.
        - ``composition_explanation``: narrative from the LLM.
        - ``evidence_per_style``: per-style bullet evidence, filtered to
          styles present in the final distribution.
        """
        prompt = build_agent7_prompt(
            agent5,
            agent6,
            vote_table,
            material,
            style_prior,
            attribute_affinity,
            attributes,
            material_available,
            cross_check_note,
            fused_prior,
        )
        raw = await asyncio.wait_for(
            self._final.chat_structured(prompt, image_base64=full_image_b64),
            timeout=_TIMEOUT,
        )
        json_str = OpenAIService.extract_json(raw)
        data = json.loads(json_str)

        # Build StyleDistribution from the new mixture field; fall back to the
        # legacy {style, confidence} shape so older prompts still validate.
        raw_dist = data.get("style_distribution")
        if not isinstance(raw_dist, dict) or not raw_dist:
            legacy_style = str(data.get("style", agent5.style))
            legacy_conf = _safe_float(data.get("confidence", agent5.confidence))
            raw_dist = {legacy_style: max(legacy_conf, 1e-3)}
        style_dist = _build_style_distribution_safe(raw_dist, agent5.style)
        primary_prob = style_dist.distribution[style_dist.primary]

        composition_explanation = str(
            data.get("composition_explanation", data.get("explanation", ""))
        )
        # ``evidence_per_style``: keep only entries that map to styles present
        # in the final distribution. ``raw_key_evidence`` is the legacy
        # single-label bullet list — used both as the legacy ``key_evidence``
        # output AND as a fall-back source of bullets for the primary style
        # when the LLM emitted the old schema.
        raw_evidence = data.get("evidence_per_style") or {}
        raw_key_evidence = [
            str(b) for b in data.get("key_evidence", []) if str(b).strip()
        ]
        evidence_per_style: Dict[str, List[str]] = {}
        if isinstance(raw_evidence, dict):
            for style_name, bullets in raw_evidence.items():
                if (
                    style_name in style_dist.distribution
                    and isinstance(bullets, list)
                ):
                    cleaned_bullets = [str(b) for b in bullets if str(b).strip()]
                    if cleaned_bullets:
                        evidence_per_style[style_name] = cleaned_bullets

        # Prefer legacy ``key_evidence`` over a placeholder for the primary
        # style when Agent 7 returned the old schema (no ``evidence_per_style``).
        if style_dist.primary not in evidence_per_style and raw_key_evidence:
            evidence_per_style[style_dist.primary] = raw_key_evidence

        # Defensive: every style that appears in the mixture should still have
        # at least one bullet of justification. Back-fill any remaining gaps
        # with a placeholder so the response shape stays consistent for
        # downstream UI / DB persistence.
        missing_evidence = [
            s for s in style_dist.distribution if s not in evidence_per_style
        ]
        if missing_evidence:
            logger.warning(
                "Agent 7 omitted evidence_per_style for: %s — back-filling placeholders.",
                missing_evidence,
            )
            for style_name in missing_evidence:
                evidence_per_style[style_name] = [
                    "(no specific evidence enumerated by Agent 7)"
                ]

        # Legacy ``key_evidence`` mirrors the primary style's bullets — falls
        # back to the original ``data["key_evidence"]`` only if the LLM
        # emitted nothing else.
        key_evidence = evidence_per_style.get(style_dist.primary, raw_key_evidence)

        return {
            "style": style_dist.primary,
            "confidence": primary_prob,
            "explanation": composition_explanation,
            "key_evidence": key_evidence,
            "style_distribution": style_dist,
            "composition_explanation": composition_explanation,
            "evidence_per_style": evidence_per_style or None,
        }


def compute_aggregated_votes(
    components: List[ComponentAnalysis],
) -> Dict[str, float]:
    """Compute weighted style votes across all components.

    Each component's Agent 2 style distribution is multiplied by its
    detection confidence, then summed across all components. Components whose
    Agent 2 fully failed (``agent2.degraded``) are skipped — their placeholder
    uniform distribution would otherwise inject noise across every style.

    Args:
        components: Results from Tier 1 (per-component analyses).

    Returns:
        Dict mapping style name → aggregated weighted score (not normalised).
    """
    totals: Dict[str, float] = {s: 0.0 for s in STYLE_CLASSES}
    for ca in components:
        if ca.agent2.degraded:
            continue
        weight = ca.detection_confidence
        for style, prob in ca.agent2.style_distribution.items():
            if style in totals:
                totals[style] += prob * weight
    return totals


def _normalize_votes(votes: Dict[str, float]) -> Dict[str, float]:
    """Normalise raw weighted votes to sum=1.0; pass through if total is 0.

    The aggregated vote table is a weighted SUM (can exceed 1.0). Normalising
    before it enters the Agent 5/7 prompts makes the magnitudes interpretable
    as relative weights. An all-zero table (no votes) is returned unchanged.
    """
    total = sum(votes.values())
    if total <= 0:
        return dict(votes)
    return {k: v / total for k, v in votes.items()}


def _distribution_stats(distribution: Dict[str, float]) -> tuple[float, float]:
    """Return (certainty_margin, Shannon entropy in nats) for a mixture.

    ``margin`` = primary − second-best probability (1.0 for a 1-hot, 0.0 when
    the top two are tied). ``entropy`` = -Σ p·ln(p) over positive probabilities
    (0.0 for a 1-hot, higher = more spread / less certain).
    """
    probs = sorted((p for p in distribution.values() if p > 0), reverse=True)
    if not probs:
        return 0.0, 0.0
    margin = probs[0] - (probs[1] if len(probs) > 1 else 0.0)
    entropy = -sum(p * math.log(p) for p in probs)
    return round(margin, 4), round(entropy, 4)


def _numeric_fallback(
    fused_prior: Dict[str, float],
) -> tuple[Agent5Output, Agent6Output, Dict[str, Any]]:
    """Build (agent5, agent6, final-dict) from the numeric fused prior.

    Used when the Tier-2 LLM fusion is unavailable so the pipeline still
    returns a coherent verdict (degraded) instead of raising.
    """
    primary = max(fused_prior, key=fused_prior.get)
    style_dist = _build_style_distribution_safe(fused_prior, primary)
    primary_prob = style_dist.distribution[style_dist.primary]
    note = "Numeric fusion fallback (LLM fusion unavailable)."
    agent5 = Agent5Output(
        style=style_dist.primary,
        confidence=primary_prob,
        reasoning=note,
        style_distribution=style_dist,
        composition_narrative=None,
    )
    alt = style_dist.secondary[0] if style_dist.secondary else style_dist.primary
    agent6 = Agent6Output(style=alt, confidence=0.0, reasoning="n/a (numeric fallback)")
    final = {
        "style": style_dist.primary,
        "confidence": primary_prob,
        "explanation": note,
        "key_evidence": [],
        "style_distribution": style_dist,
        "composition_explanation": None,
        "evidence_per_style": None,
    }
    return agent5, agent6, final


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Convert an arbitrary JSON-decoded value to float, falling back on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _build_style_distribution_safe(
    raw: Dict[str, Any],
    fallback_primary: str,
) -> StyleDistribution:
    """Construct a validated StyleDistribution from a raw LLM-emitted dict.

    Filters out unknown style names, coerces values to non-negative floats,
    normalises to sum=1.0, then computes ``primary`` (argmax) and ``secondary``
    (styles whose normalised probability is at least ``_SECONDARY_THRESHOLD``,
    ranked descending and excluding primary).

    If the cleaned dict contains no positive probability, falls back to a
    1-hot distribution on ``fallback_primary`` so the caller always receives
    a valid object.
    """
    cleaned: Dict[str, float] = {}
    for key, value in raw.items():
        if key not in STYLE_CLASSES:
            continue
        prob = max(0.0, _safe_float(value, default=0.0))
        if prob > 0:
            cleaned[key] = prob
    if not cleaned:
        cleaned = {fallback_primary: 1.0}
    total = sum(cleaned.values())
    normalised = {k: v / total for k, v in cleaned.items()}
    primary = max(normalised, key=normalised.get)
    secondary = sorted(
        (s for s, p in normalised.items() if s != primary and p >= _SECONDARY_THRESHOLD),
        key=lambda s: -normalised[s],
    )
    return StyleDistribution(
        distribution=normalised,
        primary=primary,
        secondary=secondary,
    )


def _parse_json_safe(raw: str) -> Dict:
    """Extract and parse the first JSON object from a raw LLM response.

    Handles responses that wrap JSON in markdown code fences.

    Args:
        raw: Raw text from an LLM call.

    Returns:
        Parsed dict, or empty dict if parsing fails.
    """
    import re
    text = raw.strip()
    # Strip markdown code fence if present
    fence_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text, re.IGNORECASE)
    if fence_match:
        text = fence_match.group(1)
    else:
        # Find first {...} block
        brace_match = re.search(r"\{[\s\S]*\}", text)
        if brace_match:
            text = brace_match.group(0)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("JSON parse failed: %s | raw[:200]: %s", exc, raw[:200])
        return {}
