"""Prompt construction for the 7-agent architecture analysis pipeline.

All functions are pure string builders — no I/O, no LLM calls.
Each function corresponds to one agent's prompt strategy documented in the plan.
"""
import json
from typing import Any, Dict, List, Optional

from chatbot.utils.schemas import (
    Agent5Output,
    Agent6Output,
    AttributeVector,
    MATERIAL_CLASSES,
    MaterialDistribution,
    STYLE_CLASSES,
)


_STYLE_LIST = ", ".join(STYLE_CLASSES)
_MATERIAL_LIST = ", ".join(MATERIAL_CLASSES)

# Guidance for commonly-confused style pairs, injected into Agent 7's CoT.
# Targets the observed Art Nouveau→Gothic error: verticality + ornamentation
# alone must NOT default to Gothic — curvature/symmetry/organic-vs-geometric
# ornament and component evidence are the real discriminators.
_CONFUSABLE_GUIDANCE = (
    "DISCRIMINATOR — commonly-confused pairs (do not rely on a single cue):\n"
    "- Gothic vs Art Nouveau: BOTH can look tall + ornate, so verticality + "
    "ornamentation ALONE is NOT evidence for Gothic. Gothic = pointed arches, "
    "spires, vertical STONE tracery, GEOMETRIC repetition, moderate-high "
    "symmetry, LOW organic curvature. Art Nouveau = WHIPLASH/organic curves, "
    "ASYMMETRY, curved iron balconies, sinuous floral ornament, HIGH curvature "
    "+ HIGH edge-orientation entropy. Decisive components: spire → Gothic; "
    "curved_iron_balcony → Art Nouveau.\n"
    "- Art Deco vs Neoclassical: both symmetric + vertical; Art Deco = "
    "geometric/zigzag ornament, setbacks; Neoclassical = columns/pediments, "
    "plain surfaces.\n\n"
)


def build_material_prompt() -> str:
    """Prompt for the Gemini-backed material classifier (VQA-style, BMAT-like).

    Asks the model to look at the central building in the attached image and
    return a JSON object with two parts: a probability ``distribution`` over the
    5 controlled MaterialType classes (sums to ~1.0) and an ``observed_materials``
    list of the actual materials seen — including ones outside the 5 classes.
    """
    example = (
        '{"distribution": {"concrete": 0.6, "glass": 0.2, "stone": 0.1, '
        '"brick": 0.05, "metal": 0.05}, '
        '"observed_materials": ["exposed concrete", "glass curtain wall"]}'
    )
    return (
        "You are an expert in building construction materials.\n"
        "Look at the CENTRAL building in the attached image and identify its "
        "facade materials.\n\n"
        f"Controlled material classes: {_MATERIAL_LIST}\n\n"
        "Return ONLY a valid JSON object, no explanation, with exactly two keys:\n"
        f'1. "distribution": probability scores (0.0-1.0) over the {len(MATERIAL_CLASSES)} '
        "controlled classes above. Scores must sum to 1.0.\n"
        '2. "observed_materials": a list of the materials you actually see, in '
        "free text — include specific or out-of-list materials when relevant "
        '(e.g. "weathered steel", "terracotta", "wood", "stucco").\n\n'
        f"Example:\n{example}"
    )


def _format_observed_materials(material: MaterialDistribution) -> str:
    """One-line free-text material cue, or '' when none were observed.

    Surfaces the vision backend's free-form material observations (possibly
    outside the 5 controlled classes) so the LLM agents can use fine-grained
    cues such as ``weathered steel`` or ``board-formed concrete``.
    """
    if not material.observed_materials:
        return ""
    return f"Observed materials (free-form): {', '.join(material.observed_materials)}\n"


def _format_material_stream(
    material: MaterialDistribution,
    material_available: bool,
    label: str = "EVIDENCE STREAM 2",
) -> str:
    """Render the material evidence block, or an 'unavailable' note.

    When ``material_available`` is False (the classifier is the deterministic
    mock), the material signal is pure noise — so it is withheld from the LLM
    rather than presented as evidence, which would otherwise inflate hedging.
    """
    if not material_available:
        return (
            f"{label} — Material: unavailable "
            "(classifier is mock; not used this run).\n\n"
        )
    material_dist_str = ", ".join(
        f"{m}: {p:.2f}"
        for m, p in sorted(material.distribution.items(), key=lambda x: x[1], reverse=True)
    )
    return (
        f"{label} — Material classifier: dominant={material.dominant} "
        f"(confidence {material.confidence:.2f})\n"
        f"  Distribution: {material_dist_str}\n"
        f"{_format_observed_materials(material)}\n"
    )


def _format_fused_anchor(fused_prior: Optional[Dict[str, float]]) -> str:
    """Render the numeric fused prior as a starting-point anchor, or '' if None."""
    if not fused_prior:
        return ""
    return (
        "NUMERIC FUSED PRIOR (component votes + CNN prior; attribute = tie-break) "
        "— START HERE:\n"
        f"{_format_score_dict(fused_prior)}\n"
        "  This is the deterministic baseline. Adjust it ONLY when the evidence "
        "above gives a strong, specific reason; otherwise stay close to it.\n\n"
    )


def _format_attributes_compact(attributes: AttributeVector) -> str:
    """Single-line attribute summary for per-component prompts (Agent 2/4).

    Optimised for low token cost — used inside Agent 2 prompts which run
    ×3 (Monte Carlo) per component.
    """
    return (
        f"symmetry={attributes.symmetry_score:.2f}, "
        f"vert/horiz={attributes.vertical_dominance:.2f}/"
        f"{attributes.horizontal_dominance:.2f}, "
        f"curvature={attributes.curvature_score:.2f}, "
        f"roughness={attributes.surface_roughness:.2f}, "
        f"edge_density={attributes.edge_density:.2f}, "
        f"edge_entropy={attributes.edge_orientation_entropy:.2f}"
    )


def _format_attributes_verbose(attributes: AttributeVector) -> str:
    """Multi-line attribute block with units for cross-component prompts (Agent 5/7).

    Includes scale hints so the LLM can calibrate the values without
    extra explanation in the surrounding prose.
    """
    return (
        "Building-level visual attributes (full image, classical CV):\n"
        f"  symmetry_score:           {attributes.symmetry_score:.3f}"
        "  (0.0–1.0; 1.0 = perfect mirror-symmetry)\n"
        f"  vertical_dominance:       {attributes.vertical_dominance:.3f}"
        "  (0.0–1.0; share of vertical lines via Hough)\n"
        f"  horizontal_dominance:     {attributes.horizontal_dominance:.3f}"
        "  (0.0–1.0; share of horizontal lines via Hough)\n"
        f"  curvature_score:          {attributes.curvature_score:.3f}"
        "  (0.0–1.0; share of curved structure)\n"
        f"  surface_roughness:        {attributes.surface_roughness:.3f}"
        "  (0.0–1.0; GLCM contrast — Haralick texture)\n"
        f"  edge_density:             {attributes.edge_density:.3f}"
        "  (0.0–1.0; multi-scale Canny — proxy for ornament amount)\n"
        f"  edge_orientation_entropy: {attributes.edge_orientation_entropy:.3f}"
        "  (0.0–2.89; low = geometric ornament, high = organic curves)"
    )


def build_agent1_prompt(component_type: str) -> str:
    """Agent 1 (Gemini vision): describe geometric features without naming a style.

    Args:
        component_type: YOLO label for the detected component (e.g. "dome").

    Returns:
        Prompt string instructing Gemini to describe visual geometry only.
    """
    return (
        f"You are an architectural expert analysing a cropped region of a building photograph.\n"
        f"The detected component type is: {component_type}\n\n"
        "Describe the GEOMETRIC and VISUAL features of this component in detail:\n"
        "- Shape, proportions, curvature\n"
        "- Materials visible (stone, concrete, glass, iron…)\n"
        "- Surface texture and ornamental details\n"
        "- Structural role it appears to serve\n\n"
        "IMPORTANT: Do NOT name any architectural style. Describe only what you see geometrically."
    )


def build_agent2_prompt(
    component_type: str,
    feature_description: str,
    material: MaterialDistribution,
    attributes: Optional[AttributeVector] = None,
    material_available: bool = True,
) -> str:
    """Agent 2 (Gemini ×3 Monte Carlo): assign style probability distribution.

    Called three times with different temperatures; caller averages the results.

    Args:
        component_type: YOLO label for the component.
        feature_description: Output from Agent 1.
        material: Building-level material classification from YOLOv8s-cls.
        attributes: Optional building-level visual attributes from the global
            feature extractor. When provided, the values are injected as a
            compact one-line summary so Agent 2 can ground its per-component
            style scoring in whole-building geometry and texture context.

    Returns:
        Prompt string asking for a JSON probability distribution over 10 styles.
    """
    if material_available:
        material_line = (
            f"Building dominant material: {material.dominant} "
            f"(confidence {material.confidence:.2f})\n"
            f"{_format_observed_materials(material)}"
        )
        material_phrase = "the building material"
    else:
        material_line = "Building material: unavailable (not assessed this run)\n"
        material_phrase = None

    if attributes is not None:
        attribute_block = (
            f"Building-level visual cues (whole image): "
            f"{_format_attributes_compact(attributes)}\n"
        )
        cues = ["the component features"]
        if material_phrase:
            cues.append(material_phrase)
        cues.append("the building-level visual cues above")
        evidence_list = ", ".join(cues[:-1]) + f" AND {cues[-1]}"
    else:
        attribute_block = ""
        evidence_list = (
            f"the component features and {material_phrase} above"
            if material_phrase
            else "the component features above"
        )
    return (
        f"You are an architectural historian.\n"
        f"Component type: {component_type}\n"
        f"Feature description: {feature_description}\n"
        f"{material_line}"
        f"{attribute_block}"
        f"\nGiven {evidence_list}, assign probability scores (0.0–1.0) "
        f"to each of the following architectural styles. Scores must sum to 1.0.\n\n"
        f"Styles: {_STYLE_LIST}\n\n"
        "Respond with ONLY a valid JSON object, no explanation. Example:\n"
        '{"Gothic": 0.7, "Baroque": 0.1, "Renaissance": 0.0, '
        '"Neoclassical": 0.05, "Art Nouveau": 0.0, "Art Deco": 0.0, '
        '"Modernism": 0.0, "Deconstructivism": 0.05, "Brutalism": 0.1, "High-tech": 0.0}'
    )


def build_agent3b_prompt(
    component_type: str,
    style_distribution: Dict[str, float],
    top_style: str,
) -> str:
    """Agent 3b (DeepSeek): parse contradiction analysis when hard rules flag an issue.

    Only called when Agent 3a detects a rule violation and needs LLM interpretation.

    Args:
        component_type: YOLO label for the component.
        style_distribution: Agent 2's averaged style distribution.
        top_style: Highest-scoring style from Agent 2.

    Returns:
        Prompt asking DeepSeek to analyse the contradiction and return JSON.
    """
    dist_str = ", ".join(f"{k}: {v:.2f}" for k, v in style_distribution.items())
    return (
        f"You are an architectural analyst reviewing a classification conflict.\n\n"
        f"Component detected: {component_type}\n"
        f"Style distribution from visual analysis: {{{dist_str}}}\n"
        f"Top predicted style: {top_style}\n\n"
        f"A hard architectural rule flags a potential contradiction between the "
        f"component type '{component_type}' and the predicted style '{top_style}'.\n\n"
        "Analyse whether this is a genuine contradiction or can be explained "
        "(e.g. eclectic building, transitional period, photographing error).\n\n"
        "Respond with ONLY a valid JSON object:\n"
        '{"has_contradiction": true|false, '
        '"contradiction_analysis": "your analysis here", '
        '"violated_rules": ["rule1", "rule2"]}'
    )


def build_agent4_prompt(
    component_type: str,
    top3_styles: List[str],
    style_distribution: Dict[str, float],
    has_contradiction: bool,
    contradiction_analysis: str,
) -> str:
    """Agent 4 (DeepSeek): per-component MIXTURE distribution + reasoning.

    Agent 4 used to emit a single ``style + confidence`` label. In the
    multi-style mixture architecture it instead emits a probability
    distribution over the styles it considers plausible for this single
    component. The downstream caller derives the legacy ``style``/
    ``confidence`` fields from the primary entry of that distribution.

    Args:
        component_type: YOLO label.
        top3_styles: Top 3 styles from Agent 2 distribution (hint, not a
            hard constraint — Agent 4 may choose any styles from the full
            list).
        style_distribution: Full Agent 2 distribution for context.
        has_contradiction: Whether Agent 3 flagged a contradiction.
        contradiction_analysis: Agent 3's analysis text.

    Returns:
        Prompt asking for a JSON conclusion with a per-component
        ``style_distribution`` (top-K, sum=1) and ``reasoning``.
    """
    dist_str = ", ".join(f"{k}: {v:.2f}" for k, v in style_distribution.items())
    contradiction_note = (
        f"\nNOTE: A contradiction was detected — {contradiction_analysis}\n"
        "Reflect this uncertainty by spreading probability mass across "
        "multiple plausible styles instead of concentrating it on one."
        if has_contradiction
        else ""
    )
    return (
        f"You are an architectural style classifier reasoning about ONE "
        f"component of a building.\n\n"
        f"Component: {component_type}\n"
        f"Agent 2 style distribution: {{{dist_str}}}\n"
        f"Agent 2 top 3 candidates: {', '.join(top3_styles)}\n"
        f"{contradiction_note}\n\n"
        f"Available styles: {_STYLE_LIST}\n\n"
        "Output a probability distribution that reflects which style(s) this "
        "component supports. The distribution should:\n"
        "- Include 1 to 4 styles (omit those you consider implausible)\n"
        "- Have probabilities that sum to ~1.0\n"
        "- Concentrate mass on one style if the evidence is decisive\n"
        "- Spread mass across 2-3 styles if the component is genuinely "
        "ambiguous or eclectic\n\n"
        "Respond with ONLY a valid JSON object:\n"
        '{"style_distribution": {"Gothic": 0.7, "Renaissance": 0.2, '
        '"Baroque": 0.1}, "reasoning": "explanation"}'
    )


def _format_score_dict(scores: Dict[str, float], top_n: Optional[int] = None) -> str:
    """Sort a score dict descending and render as a ``  Style: 0.123`` block.

    ``top_n`` truncates to the highest-scoring entries; ``None`` keeps all.
    """
    items = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    if top_n is not None:
        items = items[:top_n]
    return "\n".join(f"  {style}: {score:.3f}" for style, score in items)


def build_agent5_prompt(
    vote_table: Dict[str, float],
    component_summaries: List[str],
    material: MaterialDistribution,
    style_prior: Optional[Dict[str, float]] = None,
    attribute_affinity: Optional[Dict[str, float]] = None,
    attributes: Optional[AttributeVector] = None,
    material_available: bool = True,
    fused_prior: Optional[Dict[str, float]] = None,
) -> str:
    """Agent 5 (DeepSeek): primary advocate — emit a STYLE MIXTURE distribution.

    Agent 5 fuses four independent evidence streams and proposes a
    distribution over styles plus a composition narrative. The legacy
    single-label ``style``/``confidence`` are derived downstream from the
    primary entry of the emitted distribution.

    Args:
        vote_table: Aggregated weighted votes across all components.
        component_summaries: Brief per-component conclusions from Agent 4.
        material: Building-level material classification (YOLOv8s-cls).
        style_prior: Optional 10-dim CNN style prior P(style|image) from the
            ResNet50 head. When ``None`` this evidence stream is omitted.
        attribute_affinity: Optional 10-dim cosine similarity between the
            observed AttributeVector and ``STYLE_ATTRIBUTE_PROFILES``.
        attributes: Optional building-level AttributeVector for the verbose
            attribute block.

    Returns:
        Prompt asking for a JSON ``style_distribution`` + ``composition_narrative``.
    """
    vote_str = _format_score_dict(vote_table)
    summaries_str = "\n".join(f"- {s}" for s in component_summaries)
    stream2 = _format_material_stream(material, material_available)

    stream3 = (
        "EVIDENCE STREAM 3 — CNN global style prior P(style|image) from ResNet50:\n"
        f"{_format_score_dict(style_prior)}\n\n"
        if style_prior is not None
        else ""
    )
    stream4 = (
        "EVIDENCE STREAM 4 — Attribute-profile affinity — TIE-BREAKER ONLY "
        "(hand-crafted prototypes, LOW discriminative power):\n"
        f"{_format_score_dict(attribute_affinity)}\n"
        "  Use ONLY to break a near-tie between styles already ranked close by "
        "the component votes + CNN prior. Do NOT let it override them.\n\n"
        if attribute_affinity is not None
        else ""
    )
    attribute_block = (
        f"{_format_attributes_verbose(attributes)}\n\n"
        if attributes is not None
        else ""
    )
    anchor_block = _format_fused_anchor(fused_prior)

    return (
        "You are an architectural historian analysing the style of a building. "
        "Many buildings combine influences from multiple periods — your task is "
        "to output a probability MIXTURE over styles, not a single label.\n\n"
        f"EVIDENCE STREAM 1 — Component vote table "
        f"(normalised weighted votes):\n{vote_str}\n\n"
        f"{stream2}"
        f"{stream3}{stream4}{attribute_block}"
        f"{anchor_block}"
        f"Per-component analysis summaries:\n{summaries_str}\n\n"
        f"Available styles: {_STYLE_LIST}\n\n"
        "Output a style mixture distribution that reflects the joint evidence:\n"
        "- Include 1 to 4 styles (omit those that are implausible)\n"
        "- Probabilities must sum to ~1.0\n"
        "- Concentrate mass when all evidence streams converge\n"
        "- Spread mass when streams disagree or the building is eclectic\n"
        "- Cite specific cross-stream evidence in the composition narrative\n\n"
        "Respond with ONLY a valid JSON object:\n"
        '{"style_distribution": {"Gothic": 0.55, "Renaissance": 0.28, '
        '"Baroque": 0.17}, '
        '"composition_narrative": "Dominant Gothic with Renaissance influence because..."}'
    )


def build_agent6_prompt(agent5_style: str) -> str:
    """Agent 6 (DeepSeek): alternative hypothesist — weak adversarial check.

    Intentionally receives ONLY Agent 5's label to avoid anchoring bias.
    Must construct its own independent chain of reasoning.

    Args:
        agent5_style: The style label chosen by Agent 5 (no reasoning passed).

    Returns:
        Prompt asking for the best alternative style hypothesis.
    """
    return (
        "You are an architectural historian providing an alternative interpretation.\n\n"
        f"Another analyst concluded: '{agent5_style}'\n\n"
        f"Available styles: {_STYLE_LIST}\n\n"
        "What is the SECOND most plausible style? You must propose an alternative — "
        "do not simply agree with the first analyst. "
        "Build your own case independently without using the first analyst's reasoning.\n\n"
        "Respond with ONLY a valid JSON object:\n"
        '{"style": "StyleName", "confidence": 0.6, "reasoning": "your independent reasoning"}'
    )


def build_agent7_prompt(
    agent5: Agent5Output,
    agent6: Agent6Output,
    vote_table: Dict[str, float],
    material: MaterialDistribution,
    style_prior: Optional[Dict[str, float]] = None,
    attribute_affinity: Optional[Dict[str, float]] = None,
    attributes: Optional[AttributeVector] = None,
    material_available: bool = True,
    cross_check_note: Optional[str] = None,
    fused_prior: Optional[Dict[str, float]] = None,
) -> str:
    """Agent 7 (OpenAI GPT-4o): final arbitrator — emit the building's STYLE MIXTURE.

    Receives all four evidence streams plus Agent 5/6 outputs and the full
    image (attached separately by the caller). Uses Step 1 / Step 2 / Step 3
    CoT structure before emitting a JSON block containing a probability
    mixture, a composition explanation and per-style evidence bullets.

    Args:
        agent5: Primary advocate output (now carries ``style_distribution``).
        agent6: Alternative hypothesist output (single-label adversary).
        vote_table: Aggregated component votes.
        material: Building-level material classification.
        style_prior: Optional CNN style prior from the ResNet50 head.
        attribute_affinity: Optional cosine affinity vs STYLE_ATTRIBUTE_PROFILES.
        attributes: Optional AttributeVector for the verbose attribute block.

    Returns:
        Prompt that forces CoT reasoning followed by a fenced JSON block.
    """
    vote_str = _format_score_dict(vote_table)
    stream2 = _format_material_stream(material, material_available)
    stream3 = (
        "EVIDENCE STREAM 3 — CNN global style prior P(style|image) from ResNet50:\n"
        f"{_format_score_dict(style_prior)}\n\n"
        if style_prior is not None
        else ""
    )
    stream4 = (
        "EVIDENCE STREAM 4 — Attribute-profile affinity — TIE-BREAKER ONLY "
        "(hand-crafted prototypes, LOW discriminative power):\n"
        f"{_format_score_dict(attribute_affinity)}\n"
        "  Use ONLY to break a near-tie between styles already ranked close by "
        "the component votes + CNN prior. Do NOT let it override them.\n\n"
        if attribute_affinity is not None
        else ""
    )
    cross_check_block = (
        f"⚠ CROSS-STREAM CHECK: {cross_check_note}\n\n"
        if cross_check_note
        else ""
    )
    material_step = (
        "Step 2.6: Verify material consistency — does the dominant material "
        f"'{material.dominant}' match the styles you intend to give the most "
        "probability mass?\n"
        if material_available
        else ""
    )
    attribute_block = (
        f"{_format_attributes_verbose(attributes)}\n\n"
        if attributes is not None
        else ""
    )
    anchor_block = _format_fused_anchor(fused_prior)

    # Agent 5 may carry a mixture distribution; show it when available.
    if agent5.style_distribution is not None:
        agent5_block = (
            f"Primary advocate (Analyst A — Agent 5) mixture:\n"
            f"{_format_score_dict(agent5.style_distribution.distribution)}\n"
            f"  Composition narrative: "
            f"{agent5.composition_narrative or agent5.reasoning}\n\n"
        )
    else:
        agent5_block = (
            f"Primary advocate (Analyst A — Agent 5): style='{agent5.style}', "
            f"confidence={agent5.confidence:.2f}\n"
            f"  Reasoning: {agent5.reasoning}\n\n"
        )

    return (
        "You are the final arbitrator for a MULTI-STYLE architectural analysis "
        "system. Buildings often blend influences from multiple periods — your "
        "task is to output a probability MIXTURE over styles, not a single label.\n\n"
        "You are ALSO shown the full building image (attached). Use it to verify "
        "the overall proportions, facade composition, ornament density, and "
        "massing — context that per-component crops cannot capture.\n\n"
        f"EVIDENCE STREAM 1 — Aggregated component vote table (normalised):\n{vote_str}\n\n"
        f"{stream2}"
        f"{stream3}{stream4}{attribute_block}"
        f"{anchor_block}"
        f"{cross_check_block}"
        f"{agent5_block}"
        f"Alternative hypothesist (Analyst B — Agent 6): style='{agent6.style}', "
        f"confidence={agent6.confidence:.2f}\n"
        f"  Reasoning: {agent6.reasoning}\n\n"
        f"{_CONFUSABLE_GUIDANCE}"
        "Perform the following steps BEFORE giving your final answer:\n"
        "Step 1: Evaluate each evidence stream objectively. Note where they "
        "converge and where they conflict.\n"
        "Step 2: Assess Analyst A's mixture proposal against Analyst B's "
        "alternative.\n"
        "Step 2.5: Verify against the full image — does the overall composition "
        "match the proposed mixture? Are there visible cues that none of the "
        "analysts captured?\n"
        f"{material_step}"
        "Step 3: For EACH style that will appear in your final mixture, "
        "identify 2–4 concrete pieces of evidence that justify its inclusion.\n\n"
        "After completing Steps 1–3, output your final verdict as a fenced JSON "
        "block:\n"
        "```json\n"
        "{\n"
        '  "style_distribution": {"Gothic": 0.55, "Renaissance": 0.28, '
        '"Baroque": 0.17},\n'
        '  "composition_explanation": "Dominant X with Y influence because…",\n'
        '  "evidence_per_style": {\n'
        '    "Gothic": ["pointed arch + spire detected", "vertical_dominance=0.82"],\n'
        '    "Renaissance": ["dome with pediment", "symmetric facade"]\n'
        "  }\n"
        "}\n"
        "```\n"
        "Rules for the mixture:\n"
        "- Include 1 to 4 styles (omit those that are implausible)\n"
        "- Probabilities must sum to ~1.0\n"
        "- Every style in ``style_distribution`` MUST have a matching entry in "
        "``evidence_per_style`` with at least 2 bullets"
    )


def build_translation_prompt(payload: Dict[str, Any]) -> str:
    """Build a prompt that translates the final English narrative into Vietnamese.

    Args:
        payload: Dict with keys ``explanation`` (str), ``key_evidence``
            (List[str]), ``composition_explanation`` (str), and
            ``evidence_per_style`` (Dict[str, List[str]]).

    Returns:
        A prompt instructing the model to return a JSON object with the same
        keys whose textual values are translated to natural Vietnamese, while
        the 10 architectural style names (dict keys) are kept unchanged.
    """
    source = json.dumps(payload, ensure_ascii=False, indent=2)
    return (
        "You are a professional translator for an architecture analysis system.\n"
        "Translate every English text value in the JSON below into natural, "
        "fluent Vietnamese. Follow these rules strictly:\n"
        "- Keep the JSON structure and all keys EXACTLY the same.\n"
        "- Do NOT translate architectural style names (e.g. Gothic, Baroque, "
        "Renaissance, Neoclassical, Art Nouveau, Art Deco, Modernism, "
        "Deconstructivism, Brutalism, High-tech) - keep them in English, "
        "including when they appear as keys of evidence_per_style.\n"
        "- Keep technical attribute tokens (e.g. vertical_dominance=0.82) as-is.\n"
        "- Translate the human-readable sentences and bullet phrases only.\n\n"
        f"Source JSON:\n{source}\n\n"
        "Return ONLY a fenced JSON block with the translated values:\n"
        "```json\n{ ... }\n```"
    )
