"""Analysis router — POST /analyze and GET /analyze/history.

POST /analyze accepts a file_id from a previous /upload/image call,
runs the full 7-agent LLM pipeline, persists the result to the database,
and returns the classification result.

GET /analyze/history returns every analysis owned by the calling user.
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies.auth import get_current_active_user
from app.models.orm_models import Agent, AgentRun, BuildingStyleResult, Image, Project, User
from app.services import wallet_service
from app.services.analysis_detail import build_detail_payload
from app.services.system_log_service import LEVEL_INFO, LEVEL_WARNING, log_event
from chatbot.services.analysis_orchestrator import (
    ensure_runtime_fresh,
    get_orchestrator,
    is_pipeline_configured,
)
from chatbot.services import provider_credentials
from chatbot.services.qa_service import get_qa_service
from chatbot.utils.schemas import (
    ComponentAnalysis,
    EvidenceSheet,
    PanelVerdict,
    StyleCandidate,
    StyleDistribution,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Injects auth, rejects deactivated accounts, and returns the full JWT payload.
_CurrentUser = Annotated[Dict[str, Any], Depends(get_current_active_user)]


# ── Request / Response models ──────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    """Request body for POST /analyze."""

    file_id: str


class AnalyzeResponse(BaseModel):
    """Structured result returned after the full 7-agent pipeline runs."""

    style: str
    confidence: float
    explanation: str
    key_evidence: List[str]
    components: List[ComponentAnalysis]
    processing_time_ms: float
    style_distribution: Optional[StyleDistribution] = None
    composition_explanation: Optional[str] = None
    evidence_per_style: Optional[Dict[str, List[str]]] = None
    evidence_sheet: Optional[EvidenceSheet] = None
    evidence_sheet_vi: Optional[EvidenceSheet] = None
    gradcam_b64: Optional[str] = None
    explanation_vi: Optional[str] = None
    key_evidence_vi: Optional[List[str]] = None
    composition_explanation_vi: Optional[str] = None
    evidence_per_style_vi: Optional[Dict[str, List[str]]] = None
    degraded: bool = False
    warnings: List[str] = []
    run_status: str = "completed"
    certainty_margin: Optional[float] = None
    distribution_entropy: Optional[float] = None
    uncertain: bool = False
    candidates: List[StyleCandidate] = []
    panel_verdicts: List[PanelVerdict] = []
    panel_agreement: Optional[float] = None
    hybrid: bool = False
    extraction_agreement: Optional[float] = None
    # Styles in the result that are NOT in the curated KB (open-set escape). The
    # client badges these "outside catalog — pending review". Empty unless
    # OUT_OF_KB_ENABLED and such a style cleared the higher agreement bar.
    out_of_kb_styles: List[str] = []
    image_id: Optional[str] = None
    # True when the Vietnamese translation was deferred off the critical path and
    # will be produced (and cached) the first time GET /analyze/history/{id} is
    # fetched. The frontend uses this to show a small "Đang tạo bản tiếng Việt…"
    # indicator and to auto-refetch the detail to fill in the ``*_vi`` fields.
    translation_pending: bool = False


class AskRequest(BaseModel):
    """Request body for POST /analyze/{image_id}/ask (grounded follow-up Q&A)."""

    question: str
    history: List[Dict[str, str]] = []
    lang: str = "en"


class AskResponse(BaseModel):
    """Answer to a follow-up question about a stored analysis."""

    answer: str


class HistoryResponse(BaseModel):
    """Analysis history for the calling user — one entry per image."""

    items: List[Dict[str, Any]]
    total: int


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post(
    "/",
    response_model=AnalyzeResponse,
    summary="Analyse an uploaded architectural image",
    description=(
        "Runs the 7-agent LLM pipeline on a previously uploaded image. "
        "Requires a valid JWT Bearer token and all three LLM API keys to be configured. "
        "Returns HTTP 503 if the LLM pipeline is not configured."
    ),
)
async def analyze_image(
    body: AnalyzeRequest,
    current_user: _CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> AnalyzeResponse:
    """Run the full pipeline on the uploaded image identified by file_id.

    Args:
        body: JSON body containing the file_id from a previous upload.
        current_user: Injected JWT payload (provides ``sub`` = user UUID).
        db: Async database session used to persist the result.

    Returns:
        AnalyzeResponse with style, confidence, explanation, and component details.

    Raises:
        HTTPException 404: If no uploaded file matches the given file_id.
        HTTPException 503: If LLM API keys are not configured.
    """
    # Load/refresh provider keys (DB-managed, multi-worker safe) BEFORE checking
    # configuration — otherwise a first request on a worker whose .env is empty
    # but whose DB holds keys would 503 spuriously.
    await ensure_runtime_fresh(db)
    if not is_pipeline_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "LLM pipeline is not configured. "
                "Set GEMINI_API_KEY, DEEPSEEK_API_KEY, and OPENAI_API_KEY in .env"
            ),
        )

    image_path = _find_upload_path(body.file_id)
    image_bytes = image_path.read_bytes()

    user_id = current_user.get("sub", "")
    # Admin is a special user: it uses the same analysis flow but is never
    # charged tokens (unlimited). Bypassing here keeps a single code path.
    is_admin = (current_user.get("role") or "").lower() == "admin"
    # Reserve tokens BEFORE the (expensive) pipeline so a 0-balance user is
    # rejected without burning LLM quota, and concurrent requests cannot overspend.
    # request_id keys the hold/refund so a retry can never double-charge/refund.
    request_id = uuid4().hex
    reserved_cost = 0
    if settings.BILLING_ENABLED and is_admin:
        await log_event(
            db, LEVEL_INFO, f"Admin analysis (token charge bypassed): {body.file_id}"
        )
    if settings.BILLING_ENABLED and not is_admin:
        state, cost = await wallet_service.reserve_analysis(db, user_id, request_id)
        if state == wallet_service.RESERVE_INSUFFICIENT:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=(
                    f"Insufficient token balance (need {cost}). "
                    "Please upgrade your plan or buy a token pack."
                ),
            )
        if state == wallet_service.RESERVE_CHARGED:
            reserved_cost = cost
            await db.commit()  # durably hold the charge before the long pipeline

    orchestrator = get_orchestrator()
    try:
        result = await orchestrator.analyze(image_bytes)
    except Exception:
        # Pipeline crashed → never charge for nothing: refund the reservation.
        if reserved_cost:
            await wallet_service.refund_analysis(db, user_id, request_id, reserved_cost)
            await db.commit()
        raise
    _log_metrics(body.file_id, result)

    # Settle the charge by run quality: completed = keep; failed = full refund;
    # degraded = partial refund. Committed together with the persisted result.
    run_status = getattr(result, "run_status", "completed")
    if reserved_cost and run_status == "failed":
        await wallet_service.refund_analysis(db, user_id, request_id, reserved_cost)
    elif reserved_cost and run_status == "degraded":
        await wallet_service.refund_analysis(
            db, user_id, request_id, reserved_cost, ratio=settings.DEGRADED_REFUND_RATIO
        )

    resp = AnalyzeResponse(
        style=result.style,
        confidence=result.confidence,
        explanation=result.explanation,
        key_evidence=result.key_evidence,
        components=result.components,
        processing_time_ms=result.processing_time_ms,
        style_distribution=result.style_distribution,
        composition_explanation=result.composition_explanation,
        evidence_per_style=result.evidence_per_style,
        evidence_sheet=result.evidence_sheet,
        evidence_sheet_vi=result.evidence_sheet_vi,
        gradcam_b64=result.gradcam_b64,
        explanation_vi=result.explanation_vi,
        key_evidence_vi=result.key_evidence_vi,
        composition_explanation_vi=result.composition_explanation_vi,
        evidence_per_style_vi=result.evidence_per_style_vi,
        degraded=result.degraded,
        warnings=result.warnings,
        run_status=getattr(result, "run_status", "completed"),
        certainty_margin=result.certainty_margin,
        distribution_entropy=result.distribution_entropy,
        uncertain=result.uncertain,
        candidates=result.candidates,
        panel_verdicts=result.panel_verdicts,
        panel_agreement=result.panel_agreement,
        hybrid=result.hybrid,
        extraction_agreement=result.extraction_agreement,
        out_of_kb_styles=getattr(result, "out_of_kb_styles", []),
    )

    try:
        new_image_id = await _persist_result(
            db, user_id, str(image_path), result, resp.model_dump_json()
        )
        if new_image_id:
            resp.image_id = new_image_id
        await log_event(
            db,
            LEVEL_INFO,
            f"Analysis completed: {result.style} ({result.confidence:.2f}) - {body.file_id}",
        )
    except Exception as exc:
        logger.warning("Failed to persist analysis result for user=%s: %s", user_id, exc)
        await db.rollback()
        await log_event(db, LEVEL_WARNING, f"Failed to persist analysis result: {body.file_id}")

    # Signal the frontend that the Vietnamese translation is coming (deferred,
    # fetchable via the detail endpoint). Only meaningful when persisted, still
    # English, and bilingual deferral is on.
    resp.translation_pending = bool(
        settings.ENABLE_BILINGUAL
        and settings.DEFER_TRANSLATION
        and resp.explanation_vi is None
        and resp.image_id is not None
    )
    return resp


@router.get(
    "/history",
    response_model=HistoryResponse,
    summary="Get analysis history for the current user",
    description="Returns every image (with style verdict, if any) belonging to the calling user.",
)
async def get_history(
    current_user: _CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> HistoryResponse:
    """Return the user's analysis history, newest-first.

    Args:
        current_user: Injected JWT payload (provides ``sub`` = user UUID).
        db: Async database session.

    Returns:
        HistoryResponse with one entry per uploaded image plus its final style verdict.
    """
    user_id = current_user.get("sub", "")
    result = await db.execute(
        select(Image, BuildingStyleResult, Project.ProjectName)
        .join(Project, Image.ProjectId == Project.ProjectId)
        .outerjoin(BuildingStyleResult, Image.ImageId == BuildingStyleResult.ImageId)
        .where(Project.UserId == user_id)
        .order_by(Image.UploadedAt.desc())
    )
    rows = result.all()
    items: List[Dict[str, Any]] = [
        {
            "image_id": img.ImageId,
            "image_path": img.ImagePath,
            "file_id": Path(img.ImagePath).stem if img.ImagePath else None,
            "project_name": project_name,
            "analysis_status": img.AnalysisStatus,
            "uploaded_at": img.UploadedAt.isoformat() if img.UploadedAt else None,
            "style": bsr.FinalStyle if bsr else None,
            "confidence": bsr.Confidence if bsr else None,
            "has_detail": bool(bsr and bsr.DetailJson) if bsr else False,
        }
        for img, bsr, project_name in rows
    ]
    return HistoryResponse(items=items, total=len(items))


@router.get(
    "/history/{image_id}",
    summary="Get the full stored result of a past analysis",
    description=(
        "Returns the full AnalyzeResponse JSON stored for a past analysis "
        "(DetailJson). Falls back to a summary built from the persisted "
        "style/confidence/explanation/evidence when DetailJson is absent "
        "(analyses created before full-result persistence existed)."
    ),
)
async def get_history_detail(
    image_id: str,
    current_user: _CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Return the stored result for one of the caller's past analyses.

    Args:
        image_id: The Images.ImageId of the analysis to retrieve.
        current_user: Injected JWT payload (provides ``sub`` = user UUID).
        db: Async database session.

    Returns:
        The full AnalyzeResponse-shaped dict (from DetailJson) or a summary dict.

    Raises:
        HTTPException 404: If the image does not exist or is not owned by the caller.
    """
    img, bsr = await _owned_image(db, current_user.get("sub", ""), image_id)
    payload = build_detail_payload(image_id, img, bsr)
    await _maybe_translate_detail(db, bsr, payload)
    # False once the Vietnamese is present (just produced or cached); True if a
    # translation could still be produced on a later open (e.g. a transient fail).
    payload["translation_pending"] = bool(
        settings.ENABLE_BILINGUAL
        and is_pipeline_configured()
        and not payload.get("explanation_vi")
    )
    return payload


@router.get(
    "/image/{image_id}",
    summary="Serve the original uploaded image of a past analysis",
    description="Streams the original image file for one of the caller's analyses.",
)
async def get_history_image(
    image_id: str,
    current_user: _CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Stream the original uploaded image for one of the caller's analyses.

    Raises:
        HTTPException 404: If the image row/file does not exist or is not owned.
    """
    img, _ = await _owned_image(db, current_user.get("sub", ""), image_id)
    file_id = Path(img.ImagePath).stem if img.ImagePath else ""
    path = _find_upload_path(file_id)
    return FileResponse(str(path))


@router.post(
    "/{image_id}/ask",
    response_model=AskResponse,
    summary="Ask a grounded follow-up question about a past analysis",
    description=(
        "Answers a question about one of the caller's analyses, grounded in that "
        "analysis's evidence + KB candidate styles. The conversation is stateless: "
        "the client sends prior turns in ``history``. Returns 404 if the image is "
        "not owned by the caller, 503 if the LLM is not configured."
    ),
)
async def ask_about_analysis(
    image_id: str,
    body: AskRequest,
    current_user: _CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> AskResponse:
    """Answer a follow-up question about one of the caller's stored analyses.

    Args:
        image_id: The Images.ImageId of the analysis to ask about.
        body: The question, prior conversation history, and answer language.
        current_user: Injected JWT payload (provides ``sub`` = user UUID).
        db: Async database session.

    Returns:
        AskResponse with the assistant's answer.

    Raises:
        HTTPException 404: If the image is not owned by the caller.
        HTTPException 503: If the LLM is not configured.
    """
    await ensure_runtime_fresh(db)
    if not provider_credentials.get_credentials("deepseek").key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Q&A is not configured. Set DEEPSEEK_API_KEY in .env",
        )
    img, bsr = await _owned_image(db, current_user.get("sub", ""), image_id)
    analysis = build_detail_payload(image_id, img, bsr)
    qa = get_qa_service()
    answer = await qa.answer(analysis, body.question, body.history, body.lang)
    return AskResponse(answer=answer)


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _maybe_translate_detail(
    db: AsyncSession, bsr: Optional[BuildingStyleResult], payload: Dict[str, Any]
) -> None:
    """Lazily translate a stored analysis into Vietnamese on first re-open.

    With DEFER_TRANSLATION the pipeline returns English only (translation off the
    critical path); the Vietnamese is produced here the first time the analysis
    is opened, merged into ``payload`` for this response, and cached back into
    ``DetailJson`` so later opens skip the LLM. Also backfills older analyses
    stored without ``*_vi``.

    Best-effort: any failure leaves the English payload untouched (the frontend
    falls back to English) and never breaks the request. No-op when bilingual is
    off, the pipeline is unconfigured, there is no DetailJson to cache into, or
    the translation already exists.
    """
    if not settings.ENABLE_BILINGUAL or not is_pipeline_configured():
        return
    if bsr is None or not bsr.DetailJson or payload.get("explanation_vi"):
        return
    try:
        vi_fields = await get_orchestrator().translate_payload(payload)
        if not vi_fields:
            return
        payload.update(vi_fields)
        stored = json.loads(bsr.DetailJson)
        stored.update(vi_fields)
        bsr.DetailJson = json.dumps(stored, ensure_ascii=False)
        await db.commit()
    except Exception as exc:  # noqa: BLE001 — boundary: lazy translation is best-effort
        logger.warning(
            "Lazy translation failed for image %s: %s", payload.get("image_id"), exc
        )
        await db.rollback()


def _log_metrics(file_id: str, result: Any) -> None:
    """Emit one structured monitoring record per analysis (K1).

    Aggregate these JSON lines for dashboards: latency p95, abstention rate,
    numeric-fallback rate, degraded rate, and predicted-style distribution
    (for prediction-drift detection).
    """
    fallback = any("fallback" in w.lower() for w in result.warnings)
    logger.info(
        "analyze_metrics %s",
        {
            "file_id": file_id,
            "latency_ms": result.processing_time_ms,
            "style": result.style,
            "confidence": round(result.confidence, 4),
            "n_components": len(result.components),
            "degraded": result.degraded,
            "uncertain": result.uncertain,
            "hybrid": result.hybrid,
            "extraction_agreement": result.extraction_agreement,
            "numeric_fallback": fallback,
            "n_warnings": len(result.warnings),
            "certainty_margin": result.certainty_margin,
            "distribution_entropy": result.distribution_entropy,
        },
    )


async def _owned_image(db: AsyncSession, user_id: str, image_id: str):
    """Return the (Image, BuildingStyleResult|None) the caller owns, else 404.

    Authorises by joining Images → Projects and matching ``Project.UserId`` to
    the token subject, so a user cannot read another user's analyses.
    """
    result = await db.execute(
        select(Image, BuildingStyleResult)
        .join(Project, Image.ProjectId == Project.ProjectId)
        .outerjoin(BuildingStyleResult, Image.ImageId == BuildingStyleResult.ImageId)
        .where(Image.ImageId == image_id, Project.UserId == user_id)
    )
    row = result.first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No analysis found for image_id '{image_id}'",
        )
    return row


def _find_upload_path(file_id: str) -> Path:
    """Locate the on-disk file for ``file_id`` regardless of its extension.

    Raises:
        HTTPException 404: If no file matching file_id is found.
    """
    upload_dir = Path(settings.UPLOAD_DIR)
    matches = list(upload_dir.glob(f"{file_id}.*"))
    if not matches:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No uploaded file found for file_id '{file_id}'",
        )
    return matches[0]


async def _persist_result(
    db: AsyncSession,
    user_id: str,
    image_path: str,
    result: Any,
    detail_json: Optional[str] = None,
) -> Optional[str]:
    """Persist the analysis verdict to Projects, Images, and BuildingStyleResults.

    ``detail_json`` is the full AnalyzeResponse serialised as JSON, stored in
    ``BuildingStyleResults.DetailJson`` so the analysis can be re-opened later
    with full fidelity.

    Silently no-ops (returns None) if ``user_id`` does not match a row in the
    Users table. This keeps test JWTs (which carry synthetic UUIDs) and legacy
    tokens working. It also no-ops when the account is deactivated/anonymised
    (``IsActive`` False): a pipeline that started before the user self-deleted
    must not resurrect a Default project + Image row after deletion.

    Returns:
        The new ``Images.ImageId`` when a row was persisted, else None — so the
        caller can expose it for follow-up Q&A on the just-analysed image.
    """
    user_lookup = await db.execute(select(User.IsActive).where(User.UserId == user_id))
    is_active = user_lookup.scalar_one_or_none()
    if is_active is None or is_active is False:
        return None

    project_id = await _get_or_create_default_project(db, user_id)

    now = datetime.now(timezone.utc)
    image = Image(
        ImageId=str(uuid4()),
        ProjectId=project_id,
        ImagePath=image_path,
        AnalysisStatus="completed",
        UploadedAt=now,
        UpdatedAt=now,
    )
    db.add(image)
    await db.flush()

    db.add(
        BuildingStyleResult(
            ResultId=str(uuid4()),
            ImageId=image.ImageId,
            FinalStyle=result.style,
            Confidence=result.confidence,
            Explanation=result.explanation,
            KeyEvidence="\n".join(result.key_evidence) if result.key_evidence else None,
            DetailJson=detail_json,
            CreatedAt=now,
        )
    )
    await _persist_agent_runs(db, image.ImageId, getattr(result, "agent_runs", []) or [])
    await db.commit()
    return image.ImageId


async def _persist_agent_runs(db: AsyncSession, image_id: str, agent_runs: List[Any]) -> None:
    """Write one AgentRuns row per recorded agent invocation for this analysis.

    Maps the telemetry's ``agent_name`` to a seeded ``Agents.AgentId``; records
    whose agent name is not seeded are skipped.
    """
    if not agent_runs:
        return
    lookup = await db.execute(select(Agent.AgentId, Agent.AgentName))
    name_to_id: Dict[str, str] = {name: aid for aid, name in lookup.all()}
    for rec in agent_runs:
        agent_id = name_to_id.get(rec.agent_name)
        if agent_id is None:
            continue
        db.add(
            AgentRun(
                RunId=str(uuid4()),
                ImageId=image_id,
                AgentId=agent_id,
                ModelId=rec.model_id,
                ParseSuccess=rec.parse_success,
                LatencyMs=rec.latency_ms,
                AgentVersion=settings.APP_VERSION,
                RawOutput=getattr(rec, "raw_output", None),
                ParsedOutput=getattr(rec, "parsed_output", None),
                OutputData=getattr(rec, "error", None),
            )
        )


async def _get_or_create_default_project(db: AsyncSession, user_id: str) -> str:
    """Return the user's 'Default' project id, creating the row if missing."""
    result = await db.execute(
        select(Project.ProjectId).where(
            Project.UserId == user_id,
            Project.ProjectName == "Default",
        )
    )
    existing: Optional[str] = result.scalar_one_or_none()
    if existing is not None:
        return existing

    project = Project(
        ProjectId=str(uuid4()),
        UserId=user_id,
        ProjectName="Default",
        Description="Default project for ad-hoc analyses",
        CreatedAt=datetime.now(timezone.utc),
    )
    db.add(project)
    await db.flush()
    return project.ProjectId
