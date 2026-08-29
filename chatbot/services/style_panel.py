"""Stage C — the panel of independent VISION judges for the open-vocabulary pipeline.

Three judges from three providers (Gemini / OpenAI / Grok) each score the KB
candidates into a probability mixture while LOOKING AT THE IMAGE together with
the evidence sheet. Earlier the judges read only the text evidence sheet, which
made them strictly weaker than the raw vision models they are built from (each
raw model classifies the image directly). Giving every judge the image lifts
each one to ≈ its base model and makes equal judge weights legitimate — three
symmetric image-seeing opinions whose disagreement is a real ensemble signal
(decision 2026-06-19).

They never see one another's output, so their verdicts are independent and the
inter-judge agreement (computed downstream in ``chatbot/utils/consensus.py``) is
a meaningful, model-agnostic uncertainty signal — replacing the unreliable
self-reported confidence (decisions #71, #73).

Every judge requests strict JSON output, so a malformed-JSON response no longer
silently drops a judge's verdict.
"""
import asyncio
import json
import time
from typing import Awaitable, Callable, List, Optional

from app.config import settings
from chatbot.services.gemini_service import GeminiService
from chatbot.services.grok_service import GrokService
from chatbot.services.openai_service import OpenAIService
from chatbot.utils.distribution import build_style_distribution_safe
from chatbot.utils.json_utils import parse_json_safe
from chatbot.utils.prompt_builder import build_panel_judge_prompt
from chatbot.utils.schemas import EvidenceSheet, PanelVerdict

_TIMEOUT = settings.PIPELINE_AGENT_TIMEOUT_SEC

# Callback the runner passes to record per-judge telemetry:
# (agent_name, model_id, latency_ms, success, raw=..., parsed=..., error=...).
RunRecorder = Callable[..., None]

# A judge call: (prompt, image_base64) -> raw JSON text.
JudgeCall = Callable[[str, Optional[str]], Awaitable[str]]


class StylePanel:
    """Run the three independent VISION judges in parallel and collect verdicts."""

    def __init__(
        self,
        gemini: GeminiService,
        openai: OpenAIService,
        grok: GrokService,
    ) -> None:
        """Store the three vision judge LLM services.

        Only the judges named in ``settings.panel_models_list`` are activated,
        so the panel can be trimmed (e.g. to save quota) via the PANEL_MODELS
        env var without code changes. All three are vision-capable and receive
        the building image alongside the evidence sheet.
        """

        # Each judge call takes (prompt, image_base64) and returns raw JSON text.
        def _gemini_call(p: str, img: Optional[str]) -> Awaitable[str]:
            return gemini.generate_with_image(
                p, image_base64=img or "", temperature=0.4, json_mode=True
            )

        def _openai_call(p: str, img: Optional[str]) -> Awaitable[str]:
            return openai.chat_structured(p, image_base64=img, json_mode=True)

        def _grok_call(p: str, img: Optional[str]) -> Awaitable[str]:
            return grok.chat_structured(p, image_base64=img, json_mode=True)

        # judge label → (telemetry agent name, model id, vision call).
        # Model id read from the injected service so an admin model override is
        # reflected in telemetry (single source of truth); falls back to the
        # settings default for lightweight test doubles without the attribute.
        all_judges = {
            "gemini": (
                "Panel: Gemini",
                getattr(gemini, "model_name", settings.GEMINI_MODEL),
                _gemini_call,
            ),
            "openai": (
                "Panel: OpenAI",
                getattr(openai, "model_name", settings.OPENAI_MODEL),
                _openai_call,
            ),
            "grok": (
                "Panel: Grok",
                getattr(grok, "model_name", settings.GROK_MODEL),
                _grok_call,
            ),
        }
        enabled = settings.panel_models_list or list(all_judges.keys())
        self._judges = [
            (key, *all_judges[key]) for key in enabled if key in all_judges
        ]

    async def judge(
        self,
        sheet: Optional[EvidenceSheet],
        candidate_names: List[str],
        kb_text: str,
        evidence_votes: dict,
        allowed: set,
        fallback_primary: str,
        full_image_base64: Optional[str] = None,
        on_run: Optional[RunRecorder] = None,
    ) -> List[PanelVerdict]:
        """Run every enabled judge in parallel and return their verdicts.

        Each judge gets the SAME prompt AND the SAME image. A judge whose call or
        parse fails yields a ``PanelVerdict`` with ``failed=True`` (excluded from
        consensus) instead of bringing the panel down.
        """
        prompt = build_panel_judge_prompt(
            sheet, candidate_names, kb_text, evidence_votes
        )
        tasks = [
            self._run_judge(label, agent_name, model_id, call, prompt,
                            full_image_base64, allowed, fallback_primary, on_run)
            for label, agent_name, model_id, call in self._judges
        ]
        return list(await asyncio.gather(*tasks))

    async def _run_judge(
        self,
        label: str,
        agent_name: str,
        model_id: str,
        call: JudgeCall,
        prompt: str,
        image_base64: Optional[str],
        allowed: set,
        fallback_primary: str,
        on_run: Optional[RunRecorder],
    ) -> PanelVerdict:
        """Call one vision judge, parse its mixture, and record telemetry."""
        start = time.monotonic()
        success = False
        raw: Optional[str] = None
        error_msg: Optional[str] = None
        verdict = PanelVerdict(judge=label, model_id=model_id, failed=True)
        try:
            raw = await asyncio.wait_for(call(prompt, image_base64), timeout=_TIMEOUT)
            data = parse_json_safe(raw)
            raw_dist = data.get("style_distribution")
            if not isinstance(raw_dist, dict) or not raw_dist:
                raise ValueError("judge returned no usable style_distribution")
            dist = build_style_distribution_safe(raw_dist, fallback_primary, allowed)
            verdict = PanelVerdict(
                judge=label,
                model_id=model_id,
                style_distribution=dist,
                reasoning=str(data.get("reasoning", "")),
                failed=False,
            )
            success = True
        except Exception as exc:  # noqa: BLE001 — boundary: one judge must not sink the panel
            error_msg = str(exc)
            verdict = PanelVerdict(judge=label, model_id=model_id, failed=True)
        if on_run is not None:
            parsed = (
                json.dumps(verdict.style_distribution.distribution)
                if verdict.style_distribution is not None
                else None
            )
            on_run(agent_name, model_id, (time.monotonic() - start) * 1000.0,
                   success, raw=raw, parsed=parsed, error=error_msg)
        return verdict
