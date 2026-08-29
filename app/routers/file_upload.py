"""File upload router.

Accepts architectural image uploads from authenticated users,
validates format and size constraints, then persists the file
to the configured upload_temp directory with a UUID-based filename.
"""
import uuid
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.config import settings
from app.dependencies.auth import get_current_active_user
from app.utils.helpers import ensure_directory, get_file_extension, validate_image_extension

router = APIRouter()


# ── Response model ─────────────────────────────────────────────────────────────

class UploadResponse(BaseModel):
    """Structured response returned after a successful image upload."""

    file_id: str
    original_filename: str
    content_type: str
    size_bytes: int
    stored_path: str
    uploaded_by: str


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post(
    "/image",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload an architectural image",
    description=(
        "Accepts a single image file (jpg, jpeg, png, webp). "
        f"Maximum size: {settings.MAX_FILE_SIZE_MB} MB. "
        "Requires a valid JWT Bearer token."
    ),
)
async def upload_image(
    file: UploadFile = File(..., description="Image file to upload"),
    current_user: Dict[str, Any] = Depends(get_current_active_user),
) -> UploadResponse:
    """Validate, store, and acknowledge an uploaded image file.

    Args:
        file: The multipart file received from the client.
        current_user: The authenticated JWT payload (rejected if deactivated).

    Returns:
        UploadResponse with the assigned file_id and storage path.

    Raises:
        HTTPException 400: Missing filename.
        HTTPException 401: Invalid or missing JWT.
        HTTPException 403: Account deactivated.
        HTTPException 413: File exceeds size limit.
        HTTPException 422: Unsupported file extension.
    """
    _assert_filename_present(file)
    _assert_extension_allowed(file.filename)  # type: ignore[arg-type]

    content: bytes = await file.read()
    _assert_size_within_limit(content)

    file_id = str(uuid.uuid4())
    extension = get_file_extension(file.filename)  # type: ignore[arg-type]
    stored_filename = f"{file_id}.{extension}"
    stored_path = _persist_file(content, stored_filename)

    return UploadResponse(
        file_id=file_id,
        original_filename=file.filename or stored_filename,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(content),
        stored_path=stored_path,
        uploaded_by=current_user.get("sub", ""),
    )


# ── Validation helpers ─────────────────────────────────────────────────────────

def _assert_filename_present(file: UploadFile) -> None:
    """Raise HTTPException 400 if the uploaded file has no filename."""
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must have a filename",
        )


def _assert_extension_allowed(filename: str) -> None:
    """Raise HTTPException 422 if the file extension is not in the allowed list."""
    extension = get_file_extension(filename)
    if not validate_image_extension(extension):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"File type '.{extension}' is not supported. "
                f"Allowed types: {settings.allowed_extensions_list}"
            ),
        )


def _assert_size_within_limit(content: bytes) -> None:
    """Raise HTTPException 413 if the file content exceeds the configured maximum."""
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"File size {len(content):,} bytes exceeds the "
                f"{settings.MAX_FILE_SIZE_MB} MB limit"
            ),
        )


def _persist_file(content: bytes, filename: str) -> str:
    """Write *content* to the upload directory and return the relative file path."""
    upload_dir = ensure_directory(settings.UPLOAD_DIR)
    file_path: Path = upload_dir / filename
    file_path.write_bytes(content)
    return str(file_path)
