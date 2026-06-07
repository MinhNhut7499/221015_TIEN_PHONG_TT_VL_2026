"""Analysis router — POST /analyze and GET /analyze/history.

POST /analyze accepts a file_id from a previous /upload/image call,
runs the full 7-agent LLM pipeline, persists the result to the database,
and returns the classification result.

GET /analyze/history returns every analysis owned by the calling user.
"""
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies.auth import get_current_user_payload
from app.models.orm_models import BuildingStyleResult, Image, Project, User
from chatbot.services.analysis_orchestrator import get_orchestrator, is_pipeline_configured
from chatbot.utils.schemas import ComponentAnalysis, StyleCandidate, StyleDistribution

logger = logging.getLogger(__name__)

router = APIRouter()

# Injects auth and returns the full JWT payload (caller gets sub, email, role).
_CurrentUser = Annotated[Dict[str, Any], Depends(get_current_user_payload)]


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
    gradcam_b64: Optional[str] = None
    explanation_vi: Optional[str] = None
    key_evidence_vi: Optional[List[str]] = None
    composition_explanation_vi: Optional[str] = None
    evidence_per_style_vi: Optional[Dict[str, List[str]]] = None
    degraded: bool = False
    warnings: List[str] = []
    certainty_margin: Optional[float] = None
    distribution_entropy: Optional[float] = None
    uncertain: bool = False
    candidates: List[StyleCandidate] = []


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
    orchestrator = get_orchestrator()
    result = await orchestrator.analyze(image_bytes)
    _log_metrics(body.file_id, result)

    user_id = current_user.get("sub", "")
    try:
        await _persist_result(db, user_id, str(image_path), result)
    except Exception as exc:
        logger.warning("Failed to persist analysis result for user=%s: %s", user_id, exc)
        await db.rollback()

    return AnalyzeResponse(
        style=result.style,
        confidence=result.confidence,
        explanation=result.explanation,
        key_evidence=result.key_evidence,
        components=result.components,
        processing_time_ms=result.processing_time_ms,
        style_distribution=result.style_distribution,
        composition_explanation=result.composition_explanation,
        evidence_per_style=result.evidence_per_style,
        gradcam_b64=result.gradcam_b64,
        explanation_vi=result.explanation_vi,
        key_evidence_vi=result.key_evidence_vi,
        composition_explanation_vi=result.composition_explanation_vi,
        evidence_per_style_vi=result.evidence_per_style_vi,
        degraded=result.degraded,
        warnings=result.warnings,
        certainty_margin=result.certainty_margin,
        distribution_entropy=result.distribution_entropy,
        uncertain=result.uncertain,
        candidates=result.candidates,
    )


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
        select(Image, BuildingStyleResult)
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
            "analysis_status": img.AnalysisStatus,
            "uploaded_at": img.UploadedAt.isoformat() if img.UploadedAt else None,
            "style": bsr.FinalStyle if bsr else None,
            "confidence": bsr.Confidence if bsr else None,
        }
        for img, bsr in rows
    ]
    return HistoryResponse(items=items, total=len(items))


# ── Helpers ────────────────────────────────────────────────────────────────────

def _log_metrics(file_id: str, result: Any) -> None:
    """Emit one structured monitoring record per analysis (K1).

    Aggregate these JSON lines for dashboards: latency p95, abstention rate,
    numeric-fallback rate, degraded rate, and predicted-style distribution
    (for prediction-drift detection).
    """
    fallback = any("numeric fusion" in w.lower() for w in result.warnings)
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
            "numeric_fallback": fallback,
            "n_warnings": len(result.warnings),
            "certainty_margin": result.certainty_margin,
            "distribution_entropy": result.distribution_entropy,
        },
    )


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
) -> None:
    """Persist the analysis verdict to Projects, Images, and BuildingStyleResults.

    Silently no-ops if ``user_id`` does not match a row in the Users table.
    This keeps test JWTs (which carry synthetic UUIDs) and legacy tokens working.
    """
    user_lookup = await db.execute(select(User.UserId).where(User.UserId == user_id))
    if user_lookup.scalar_one_or_none() is None:
        return

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
            CreatedAt=now,
        )
    )
    await db.commit()


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
