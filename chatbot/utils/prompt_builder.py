"""Prompt construction for the open-vocabulary architecture analysis pipeline.

All functions are pure string builders — no I/O, no LLM calls. The pipeline
stages are:

- Agent A (Gemini vision)   → fill a structured EVIDENCE SHEET (12 dimensions)
- KB grounding (pure code)  → resolve proposed style names to KB candidates
- Panel (3 judges)          → each independently scores the candidates → mixture
- Agent 7 (GPT-4o + image)  → arbiter: final mixture grounded in evidence + KB
"""
import json
from typing import Any, Dict, List, Optional

from chatbot.utils.schemas import EvidenceSheet, PanelVerdict, StyleEntry


# The 12 evidence-sheet dimensions Agent A must consider, with a short hint
# each so the VLM knows what to look at. Order is the reading order in prompts.
EVIDENCE_DIMENSIONS: List[tuple[str, str]] = [
    ("massing", "overall volume/silhouette and how blocks are composed"),
    ("roof", "roof form: flat, pitched, domed, onion, hipped, spire, shikhara…"),
    ("supports", "columns, piers, walls, buttresses, pilotis — vertical supports"),
    ("arch", "arch/opening shape: pointed, round, horseshoe, ogee, trabeated…"),
    ("openings", "windows and doors: proportion, rhythm, tracery, rose window…"),
    ("facade", "facade composition: symmetry, bays, layering, articulation"),
    ("ornament", "ornament type/density: floral, geometric, figural, plain…"),
    ("material", "visible facade materials: stone, brick, concrete, glass, wood…"),
    ("verticals", "vertical vs horizontal emphasis of the composition"),
    ("vault_dome", "vaults/domes/ceilings if visible (ribbed, coffered, muqarnas…)"),
    ("spatial_org", "plan/spatial organisation cues (axial, central, courtyard…)"),
    ("diagnostic", "the single MOST distinctive, style-revealing feature present"),
]


def build_agent_a_prompt(family_names: Optional[List[str]] = None) -> str:
    """Agent A (vision): fill the structured 12-dimension evidence sheet.

    Returns a prompt instructing the model to describe the building across all
    evidence dimensions and propose OPEN-VOCABULARY style names (it may name any
    world style, not a fixed list), plus a ranked building-level
    ``style_hypotheses`` and 2-3 building-level ``families`` chosen from the
    knowledge-base family list (coarse-to-fine — a family is easier to get right
    than the exact style, and the orchestrator expands it into candidates). No
    confidence numbers and no bounding boxes are requested — both are unreliable.

    Args:
        family_names: KB family display names to constrain the ``families`` field
            to (e.g. "Islamic", "East Asian"). When None/empty the families
            instruction is omitted (backward compatible).
    """
    dim_lines = "\n".join(
        f"  - {name}: {hint}" for name, hint in EVIDENCE_DIMENSIONS
    )
    families_csv = ", ".join(family_names) if family_names else ""
    families_instr = (
        ('Also add "families": the 2-3 broad architectural FAMILIES the building '
         "most likely belongs to, chosen ONLY from this list: "
         f"{families_csv}. A family is a coarse grouping (easier to judge than "
         "the exact style); pick the ones whose typical buildings look most like "
         "this one.\n")
        if families_csv
        else ""
    )
    families_example = (
        '  "families": ["Medieval European"],\n' if families_csv else ""
    )
    example = (
        "```json\n"
        "{\n"
        '  "items": [\n'
        "    {\n"
        '      "dimension": "arch",\n'
        '      "feature": "pointed (lancet) arches over the portals and windows",\n'
        '      "suggested_styles": ["Gothic"],\n'
        '      "note": "pointed arch distinguishes from round-arched Romanesque"\n'
        "    },\n"
        "    {\n"
        '      "dimension": "supports",\n'
        '      "feature": "flying buttresses along the side aisles",\n'
        '      "suggested_styles": ["Gothic", "French Gothic"],\n'
        '      "note": ""\n'
        "    }\n"
        "  ],\n"
        '  "style_hypotheses": ["French Gothic", "Gothic", "Gothic Revival"],\n'
        f"{families_example}"
        '  "proposed_styles": ["Gothic", "French Gothic", "Romanesque"],\n'
        '  "overall_note": "large religious building with strong Gothic cues"\n'
        "}\n"
        "```"
    )
    return (
        "You are an expert architectural historian examining ONE building photograph.\n"
        "Fill a structured EVIDENCE SHEET describing what you actually SEE. Do NOT "
        "jump to a single conclusion — record observations per dimension.\n\n"
        "Evidence dimensions to cover (include an item for every dimension you can "
        "observe; skip one only if it is genuinely not visible):\n"
        f"{dim_lines}\n\n"
        "For EACH item provide:\n"
        '  - "dimension": one of the names above.\n'
        '  - "feature": a concrete description of what you see for that dimension.\n'
        '  - "suggested_styles": a list of architectural style names this feature '
        "points to. Use OPEN VOCABULARY — name ANY world style (e.g. Mughal, "
        "Khmer, Byzantine, Shinto, Art Nouveau…), not a fixed list. May be empty.\n"
        '  - "note": optional short remark (e.g. what it distinguishes from).\n\n'
        "Do NOT output any confidence score or probability, and do NOT output "
        "bounding boxes or coordinates — only observations.\n\n"
        'After the items, add "style_hypotheses": your 3-6 BEST GUESSES for the '
        "WHOLE building's style, RANKED most-likely first and ordered SPECIFIC → "
        "GENERAL. Name the precise regional/period variant when you can (e.g. "
        '"Spanish Colonial Revival", "Mission Revival", "Venetian Gothic", '
        '"Mughal") and then its broader family. This is a building-level judgement '
        "— do NOT just repeat the per-dimension cues, which tend to be generic.\n"
        f"{families_instr}"
        'Then add "proposed_styles" (every style name from style_hypotheses AND the '
        'per-item suggestions, de-duplicated) and "overall_note" (one-sentence '
        "holistic impression).\n\n"
        "Return ONLY a fenced JSON block in exactly this shape:\n"
        f"{example}"
    )


def _format_evidence_sheet(sheet: Optional[EvidenceSheet]) -> str:
    """Render an EvidenceSheet as a readable evidence block for text agents."""
    if sheet is None or not sheet.items:
        return "EVIDENCE SHEET: (empty — no structured evidence extracted)\n"
    lines: List[str] = ["EVIDENCE SHEET (per-dimension observations):"]
    for item in sheet.items:
        styles = ", ".join(item.suggested_styles) if item.suggested_styles else "—"
        line = f"  - [{item.dimension}] {item.feature} → {styles}"
        if item.note:
            line += f" ({item.note})"
        lines.append(line)
    if sheet.overall_note:
        lines.append(f"  Overall: {sheet.overall_note}")
    return "\n".join(lines) + "\n"


def _format_score_dict(scores: Dict[str, float], top_n: Optional[int] = None) -> str:
    """Sort a score dict descending and render as a ``  Style: 0.123`` block.

    ``top_n`` truncates to the highest-scoring entries; ``None`` keeps all.
    """
    items = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    if top_n is not None:
        items = items[:top_n]
    return "\n".join(f"  {style}: {score:.3f}" for style, score in items)


# Shown only when an out-of-KB ("PROPOSED") candidate is present, so judges treat
# it on visual evidence alone without over-favouring or dismissing it.
_PROPOSED_CANDIDATE_NOTE = (
    "NOTE: candidates marked PROPOSED are NOT in the curated knowledge base — "
    "they were suggested from the image and have only the observed features above "
    "to go on. Score them strictly on the visual evidence, exactly like the other "
    "candidates: neither favour them for being novel nor dismiss them for lacking "
    "a KB entry.\n\n"
)


def _format_candidates(candidate_kb_text: str, candidate_names: List[str]) -> str:
    """Render the KB candidate block, falling back to a bare name list."""
    if candidate_kb_text.strip():
        return candidate_kb_text
    if candidate_names:
        return "\n".join(f"- {n}" for n in candidate_names)
    return "(no KB candidates matched — judge from the evidence sheet alone)"


def build_panel_judge_prompt(
    evidence_sheet: Optional[EvidenceSheet],
    candidate_names: List[str],
    candidate_kb_text: str,
    evidence_votes: Dict[str, float],
) -> str:
    """One panel judge: independently score the KB candidates into a mixture.

    The SAME prompt + the SAME building image is given to each of the three
    vision judges (Gemini / OpenAI / Grok); they do not see each other's output,
    so their verdicts are independent and their agreement is meaningful. Each
    judge LOOKS AT THE IMAGE and uses the structured evidence sheet as a
    reasoning scaffold, plus the KB candidate descriptions and a SOFT
    evidence-vote table (a ranking hint, NOT a probability). Emits a JSON style
    mixture over the candidate names plus a short justification.
    """
    candidates_block = _format_candidates(candidate_kb_text, candidate_names)
    names_csv = ", ".join(candidate_names) if candidate_names else "(none)"
    proposed_note = _PROPOSED_CANDIDATE_NOTE if "PROPOSED" in candidates_block else ""
    votes_block = (
        "Evidence-support tally (how many evidence dimensions mention each style — "
        "a SOFT ranking hint only, NOT a probability; dimensions are not fully "
        "independent):\n"
        f"{_format_score_dict(evidence_votes)}\n\n"
        if evidence_votes
        else ""
    )
    return (
        "You are an independent expert judge in a panel of architectural "
        "historians. Many buildings combine influences from multiple "
        "periods/cultures — output a probability MIXTURE over styles, not a "
        "single label. You ARE shown the full building image (attached): look at "
        "it directly and treat the evidence sheet below as a structured reasoning "
        "aid, not a replacement for your own reading. You do not see the other "
        "judges' opinions.\n\n"
        f"{_format_evidence_sheet(evidence_sheet)}\n"
        "CANDIDATE STYLES (grounded in the knowledge base — score among these):\n"
        f"{candidates_block}\n\n"
        f"{proposed_note}"
        f"{votes_block}"
        "Decide a style mixture that the IMAGE and the evidence sheet best "
        "support:\n"
        f"- Use ONLY the candidate style names above: {names_csv}\n"
        "- Include 1 to 4 styles; omit implausible ones\n"
        "- Probabilities must sum to ~1.0\n"
        "- Weigh by how much of the building each style GOVERNS: the main "
        "mass/body and overall facade outweigh an isolated accent (a single "
        "striking roofline, tower, or ornament). Do not let one exotic detail "
        "dominate when the body clearly belongs to another style.\n"
        "- Concentrate mass when the evidence converges; spread it when the "
        "building is genuinely eclectic or the evidence is mixed\n"
        "- Justify using SPECIFIC evidence-sheet observations (cite the dimension "
        "and feature), not the vote tally alone\n\n"
        "Respond with ONLY a valid JSON object:\n"
        '{"style_distribution": {"Gothic": 0.7, "Romanesque": 0.3}, '
        '"reasoning": "Dominant Gothic because… with a Romanesque undertone in…"}'
    )


def _format_panel_verdicts(verdicts: List[PanelVerdict]) -> str:
    """Render the panel's verdicts (one block per judge) for the arbiter prompt."""
    blocks: List[str] = []
    for v in verdicts:
        if v.failed or v.style_distribution is None:
            blocks.append(f"Judge [{v.judge}]: (no verdict — call failed)")
            continue
        blocks.append(
            f"Judge [{v.judge}] mixture:\n"
            f"{_format_score_dict(v.style_distribution.distribution)}\n"
            f"  Reasoning: {v.reasoning}"
        )
    return "\n\n".join(blocks) if blocks else "(no panel verdicts available)"


def _format_free_read(free_read_styles: Optional[List[str]]) -> str:
    """Render the free-read opinion block for the arbiter prompt (empty if none)."""
    names = [s for s in (free_read_styles or []) if s and s.strip()]
    if not names:
        return ""
    most_likely = names[0]
    alternates = ", ".join(names[1:]) if len(names) > 1 else "(none)"
    return (
        "INDEPENDENT FREE READ — a separate expert model named the style DIRECTLY "
        "from the image, WITHOUT the candidate list or the evidence sheet (a "
        "fresh, unconstrained opinion whose errors are independent of the panel):\n"
        f"  most likely: {most_likely}; alternates: {alternates}\n"
        "Weigh it as one more independent vote — it is especially informative when "
        "it agrees with a candidate the panel underweighted, or when it offers the "
        "plain canonical style for a building the panel split into fine variants.\n\n"
    )


def build_agent7_prompt(
    panel_verdicts: List[PanelVerdict],
    panel_agreement: Optional[float],
    evidence_sheet: Optional[EvidenceSheet],
    candidate_names: List[str],
    candidate_kb_text: str,
    free_read_styles: Optional[List[str]] = None,
) -> str:
    """Agent 7 (GPT-4o): arbiter — final mixture grounded in evidence + KB.

    Receives the evidence sheet, KB candidate descriptions, the THREE
    independent panel verdicts, their inter-judge agreement score, AND the full
    building image (attached separately by the caller). Uses CoT before emitting
    a fenced JSON block with the final mixture, a composition explanation, and
    per-style evidence bullets. The arbiter is CONSTRAINED to the candidate
    names and to the visible evidence — it must not invent a style absent from
    both.
    """
    candidates_block = _format_candidates(candidate_kb_text, candidate_names)
    names_csv = ", ".join(candidate_names) if candidate_names else "(none)"
    panel_block = _format_panel_verdicts(panel_verdicts)
    if panel_agreement is None:
        agreement_line = (
            "Inter-judge agreement: undefined (too few valid judges) — be "
            "cautious and lean on the evidence and the image.\n\n"
        )
    else:
        agreement_line = (
            f"Inter-judge agreement (mean pairwise rank correlation): "
            f"{panel_agreement:.2f} — high (→1.0) means the judges concur so you "
            "can be decisive; low or negative means they disagree, so weigh the "
            "evidence and image carefully and spread mass if genuinely "
            "ambiguous.\n\n"
        )

    return (
        "You are the final ARBITER of an open-vocabulary, MULTI-STYLE "
        "architectural analysis. Buildings often blend influences — output a "
        "probability MIXTURE over styles, not a single label.\n\n"
        "You are ALSO shown the full building image (attached). Use it to verify "
        "overall proportions, facade composition, ornament density, and massing — "
        "context the structured evidence may miss.\n\n"
        f"{_format_evidence_sheet(evidence_sheet)}\n"
        "CANDIDATE STYLES (knowledge base — your verdict MUST use these names):\n"
        f"{candidates_block}\n\n"
        f"{_PROPOSED_CANDIDATE_NOTE if 'PROPOSED' in candidates_block else ''}"
        "PANEL OF INDEPENDENT JUDGES (each scored the evidence separately):\n"
        f"{panel_block}\n\n"
        f"{agreement_line}"
        f"{_format_free_read(free_read_styles)}"
        "Reason through these steps BEFORE answering:\n"
        "Step 1: Weigh the evidence-sheet observations. Note where they converge "
        "and conflict.\n"
        "Step 2: Compare the panel's verdicts — where do the judges agree, and "
        "where do they diverge? Treat a style only one judge favours with caution.\n"
        "Step 2.5: Verify against the full image — does the overall composition "
        "match? Any decisive cue the judges missed? Separate the building's MAIN "
        "MASS/BODY (dominant volume, overall facade, plan) from ACCENT features "
        "(an isolated roofline, tower, or ornament). Weigh each style by how much "
        "of the building it GOVERNS: the style of the main body is usually the "
        "primary, and a striking-but-localised accent is secondary — do not let "
        "one eye-catching detail outweigh the body it sits on.\n"
        "Step 2.6: If NO single style governs the building — two or more styles "
        "share the main mass roughly equally, or distinct parts belong to "
        "distinct styles — this is a HYBRID / ECLECTIC building. Say so EXPLICITLY "
        "in composition_explanation (name it a hybrid of the styles), give a "
        "balanced mixture rather than forcing one winner, and still justify each "
        "style with its own evidence. A hybrid is a valid, confident answer.\n"
        "Step 3: For EACH style in your final mixture, write 2–4 evidence bullets "
        "as COMPLETE, SELF-EXPLANATORY sentences for a non-expert. Each bullet must "
        "cite the SPECIFIC evidence-sheet observation (dimension + feature) it "
        "relies on and say what it implies. For a secondary style, also state why "
        "it is only a minor influence.\n\n"
        "Constraints:\n"
        f"- Prefer the candidate style names: {names_csv}\n"
        "- If the IMAGE clearly shows a well-known architectural style that is NOT "
        "in the candidate list, you MAY name it using its common English name — it "
        "will be validated against the knowledge base, and an unknown name is "
        "dropped. Use this only when the image evidence is strong.\n"
        "- Include 1 to 4 styles; probabilities sum to ~1.0\n"
        "- Do NOT fabricate a style unsupported by the image or the evidence sheet\n\n"
        "After the steps, output your verdict as a fenced JSON block:\n"
        "```json\n"
        "{\n"
        '  "style_distribution": {"Gothic": 0.78, "Romanesque": 0.22},\n'
        '  "composition_explanation": "Dominant Gothic with a Romanesque undertone because…",\n'
        '  "evidence_per_style": {\n'
        '    "Gothic": ["The pointed (lancet) arches recorded in the arch dimension '
        'and the flying buttresses give the vertical, skeletal structure that '
        'defines Gothic.", "The large rose window reinforces the Gothic reading."],\n'
        '    "Romanesque": ["A few round-arched openings at the base hint at an '
        'earlier Romanesque layer, but they are limited, so it stays secondary."]\n'
        "  }\n"
        "}\n"
        "```\n"
        "Every style in ``style_distribution`` MUST have a matching "
        "``evidence_per_style`` entry with at least 2 full-sentence bullets "
        "(a thin secondary style may have 1)."
    )


def build_free_read_prompt() -> str:
    """Free read: name the building's style directly from the image.

    Deliberately UNCONSTRAINED — no candidate list, no evidence sheet — so the
    model answers the way a base vision model does (the reads that score ~78.5%
    on the benchmark). It is told to give the canonical first-glance style and
    NOT to over-refine into a fine sub-period/Revival unless clearly warranted,
    which both mirrors how a base model answers and avoids the system's tendency
    to drift to a Revival twin. The output seeds the candidate set and is shown
    to the arbiter as an independent, decorrelated opinion. The image is attached
    by the caller.
    """
    return (
        "You are an expert architectural historian. Look at the attached building "
        "photograph and name its architectural style DIRECTLY, as you would at an "
        "expert first glance.\n"
        "- Give the SINGLE most likely overall style first, then up to two "
        "alternates, most likely first.\n"
        "- Use the common English style name (e.g. Byzantine, Mughal, Gothic, "
        "Art Deco, Romanesque).\n"
        "- Judge the MAIN building/body, not an isolated decorative detail.\n"
        "- Do NOT over-refine into a narrow sub-period or a 'Revival' variant "
        "unless the image clearly demands it — prefer the canonical style name.\n\n"
        "Return ONLY a JSON object:\n"
        '{"styles": ["Most likely style", "Alternate 1", "Alternate 2"]}'
    )


def _format_runoff_features(entry: StyleEntry) -> str:
    """Render one finalist's KB signature as a short discriminating checklist."""
    feats = entry.defining_features or list(entry.expected_profile.values())
    if not feats:
        return f"- {entry.name}: (no distinctive features recorded)"
    bullets = "\n".join(f"    • {f}" for f in feats)
    region = ", ".join(entry.region)
    head = f"- {entry.name}"
    if region or entry.period:
        head += f" ({', '.join(p for p in [region, entry.period] if p)})"
    return f"{head} — signature features:\n{bullets}"


def build_runoff_prompt(
    entry_a: StyleEntry,
    entry_b: StyleEntry,
    evidence_sheet: Optional[EvidenceSheet],
) -> str:
    """Contrastive run-off: decide between the two finalists by their signatures.

    Used when the pipeline's final top-2 styles are close (the decision engine is
    torn). Instead of re-scoring the whole candidate set, this forces a FOCUSED
    comparison: each finalist's KB ``defining_features`` are laid out as a
    discriminating checklist, and the model — which is shown the building image —
    must report which finalist's signature features are actually PRESENT, then
    split the probability between exactly the two. The KB features act as a
    contrastive discriminator, not just a description.

    Args:
        entry_a: First finalist (the current top-1).
        entry_b: Second finalist (the current runner-up).
        evidence_sheet: The structured evidence sheet (reasoning aid).

    Returns:
        A prompt string; the building image is attached separately by the caller.
    """
    return (
        "You are an expert architectural historian making a FINAL, FOCUSED "
        f"decision between exactly TWO candidate styles for the building shown in "
        "the attached image. Both were plausible; decide which one the image "
        "ACTUALLY supports by checking each style's signature features.\n\n"
        "THE TWO FINALISTS and their distinctive (discriminating) features:\n"
        f"{_format_runoff_features(entry_a)}\n"
        f"{_format_runoff_features(entry_b)}\n\n"
        f"{_format_evidence_sheet(evidence_sheet)}\n"
        "Look at the IMAGE directly. For EACH finalist, judge how many of its "
        "signature features are genuinely present on the main building (not a "
        "single incidental detail). The style whose signature features are more "
        "fully and centrally present should receive the larger share. If the "
        "image is truly ambiguous between them, split closer to 50/50.\n\n"
        "Respond with ONLY a JSON object giving a probability over the two names "
        "(summing to 1.0), plus which discriminating features you actually saw:\n"
        "```json\n"
        "{\n"
        f'  "style_distribution": {{"{entry_a.name}": 0.7, "{entry_b.name}": 0.3}},\n'
        f'  "present": {{"{entry_a.name}": ["feature you saw", "..."], '
        f'"{entry_b.name}": []}},\n'
        '  "reasoning": "one sentence on the decisive difference"\n'
        "}\n"
        "```"
    )


def build_translation_prompt(payload: Dict[str, Any]) -> str:
    """Build a prompt that translates the final English narrative into Vietnamese.

    Args:
        payload: Dict with keys ``explanation`` (str), ``key_evidence``
            (List[str]), ``composition_explanation`` (str),
            ``evidence_per_style`` (Dict[str, List[str]]), and optionally
            ``evidence_items`` (List[{"i": int, "feature": str, "note": str}])
            — the 12-dimension evidence sheet rows to translate.

    Returns:
        A prompt instructing the model to return a JSON object with the same
        keys whose textual values are translated to natural Vietnamese, while
        the architectural style names (dict keys) are kept unchanged.
    """
    source = json.dumps(payload, ensure_ascii=False, indent=2)
    return (
        "You are a professional translator for an architecture analysis system.\n"
        "Translate every English text value in the JSON below into natural, "
        "fluent Vietnamese. Follow these rules strictly:\n"
        "- Keep the JSON structure and all keys EXACTLY the same.\n"
        "- Do NOT translate architectural style names (e.g. Gothic, Baroque, "
        "Mughal, Byzantine…) — keep them in English, including when they appear "
        "as keys of evidence_per_style.\n"
        "- For evidence_items, translate ONLY the 'feature' and 'note' strings; "
        "keep each 'i' (index) unchanged and the list order identical.\n"
        "- Keep technical tokens as-is.\n"
        "- Translate the human-readable sentences and bullet phrases only.\n\n"
        f"Source JSON:\n{source}\n\n"
        "Return ONLY a single JSON object with the translated values (no prose, "
        "no markdown fences)."
    )


def _format_analysis_context(analysis: Dict[str, Any]) -> str:
    """Render a stored analysis result (dict) as a grounding context block.

    Pulls the fields useful for answering follow-up questions: the verdict,
    confidence, mixture distribution, key evidence, composition narrative, the
    12-dimension evidence sheet, the judge-panel primaries, and the KB-grounded
    candidate names. English fields are used (the question/answer language is
    handled separately).
    """
    lines: List[str] = []
    lines.append(f"FINAL VERDICT: {analysis.get('style', '—')} "
                 f"(confidence {float(analysis.get('confidence') or 0.0):.2f})")

    dist = (analysis.get("style_distribution") or {}).get("distribution") or {}
    if dist:
        ranked = sorted(dist.items(), key=lambda kv: kv[1], reverse=True)
        lines.append("STYLE MIXTURE: " + ", ".join(
            f"{s} {round(p * 100)}%" for s, p in ranked if p > 0))

    if analysis.get("explanation"):
        lines.append(f"EXPLANATION: {analysis['explanation']}")
    if analysis.get("composition_explanation"):
        lines.append(f"COMPOSITION: {analysis['composition_explanation']}")

    key_ev = analysis.get("key_evidence") or []
    if key_ev:
        lines.append("KEY EVIDENCE:")
        lines.extend(f"  - {e}" for e in key_ev)

    items = (analysis.get("evidence_sheet") or {}).get("items") or []
    if items:
        lines.append("EVIDENCE SHEET (per-dimension observations):")
        for it in items:
            styles = ", ".join(it.get("suggested_styles") or []) or "—"
            line = f"  - [{it.get('dimension')}] {it.get('feature')} -> {styles}"
            if it.get("note"):
                line += f" ({it['note']})"
            lines.append(line)

    verdicts = analysis.get("panel_verdicts") or []
    primaries = [
        f"{v.get('judge')}: {(v.get('style_distribution') or {}).get('primary')}"
        for v in verdicts
        if not v.get("failed") and (v.get("style_distribution") or {}).get("primary")
    ]
    if primaries:
        lines.append("JUDGE PANEL PRIMARIES: " + "; ".join(primaries))
    if analysis.get("panel_agreement") is not None:
        lines.append(f"PANEL AGREEMENT: {analysis['panel_agreement']}")

    cand = analysis.get("candidate_names") or []
    if cand:
        lines.append("KB CANDIDATE STYLES CONSIDERED: " + ", ".join(cand))

    return "\n".join(lines)


def build_qa_prompt(
    analysis: Dict[str, Any],
    kb_text: str,
    question: str,
    history: List[Dict[str, str]],
    lang: str,
) -> str:
    """Build a grounded Q&A prompt about one specific analysis result.

    The model answers in "gated" mode (decision confirmed with the user):
    questions about THIS image are answered strictly from the analysis context;
    general architecture-knowledge questions may be answered but must be flagged
    as reference knowledge; off-topic questions are politely declined.

    Args:
        analysis: The stored analysis result (AnalyzeResponse-shaped dict).
        kb_text: Rendered KB descriptions for the candidate styles (may be empty).
        question: The user's current question.
        history: Prior conversation turns as ``{"role", "content"}`` dicts.
        lang: ``"vi"`` or ``"en"`` — the language the answer must be written in.

    Returns:
        A single prompt string for a text LLM.
    """
    answer_lang = "Vietnamese" if lang == "vi" else "English"
    context = _format_analysis_context(analysis)
    kb_block = kb_text.strip() or "(no KB descriptions available)"

    convo = ""
    if history:
        turns = []
        for turn in history:
            role = "User" if turn.get("role") == "user" else "Assistant"
            turns.append(f"{role}: {turn.get('content', '')}")
        convo = "CONVERSATION SO FAR:\n" + "\n".join(turns) + "\n\n"

    return (
        "You are an architecture assistant helping a user understand ONE specific "
        "image-analysis result produced by this system. You are given the full "
        "analysis context and knowledge-base descriptions of the candidate styles.\n\n"
        "ANSWERING RULES (follow strictly):\n"
        "1. If the question is about THIS image / its result, answer ONLY from the "
        "ANALYSIS CONTEXT and KB DESCRIPTIONS below. Cite the concrete evidence "
        "(dimensions, features, judge votes, percentages). Never invent evidence, "
        "numbers, or features that are not present.\n"
        "2. If the question is about GENERAL architecture knowledge (not derivable "
        "from this analysis), you may answer briefly, but you MUST prefix that part "
        "with a clear note that it is reference knowledge, not drawn from this "
        "image's analysis.\n"
        "3. If the question is unrelated to architecture, politely decline and "
        "steer the user back to this analysis.\n"
        f"4. Write the entire answer in {answer_lang}. Keep architectural style "
        "names in English. Be concise and concrete.\n\n"
        f"ANALYSIS CONTEXT:\n{context}\n\n"
        f"KB DESCRIPTIONS (candidate styles):\n{kb_block}\n\n"
        f"{convo}"
        f"USER QUESTION: {question}\n\n"
        "Answer:"
    )
