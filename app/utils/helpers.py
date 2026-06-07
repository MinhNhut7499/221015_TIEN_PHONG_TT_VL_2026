"""General-purpose utility functions shared across the application.

Keep functions here stateless and side-effect-free where possible.
Functions that depend on settings are clearly labelled.
"""
from pathlib import Path

from app.config import settings


def get_file_extension(filename: str) -> str:
    """Return the lowercase extension of *filename* without the leading dot.

    Examples:
        "photo.JPG"  → "jpg"
        "image.png"  → "png"
        "noext"      → ""
    """
    return Path(filename).suffix.lstrip(".").lower()


def validate_image_extension(extension: str) -> bool:
    """Return True if *extension* is in the configured allowed list."""
    return extension in settings.allowed_extensions_list


def ensure_directory(path: str) -> Path:
    """Create *path* and all parent directories if they do not already exist.

    Returns the resolved Path object so callers can use it directly.
    """
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def build_file_path(directory: str, filename: str) -> Path:
    """Return a Path joining *directory* and *filename*."""
    return Path(directory) / filename


def sanitize_filename(filename: str) -> str:
    """Replace unsafe filesystem characters in *filename* with underscores.

    Strips leading/trailing dots to prevent hidden-file edge cases.
    Does NOT truncate or enforce uniqueness — callers handle that.
    """
    safe_chars = frozenset(
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789._-"
    )
    sanitized = "".join(c if c in safe_chars else "_" for c in filename)
    return sanitized.strip(".")


def format_file_size(size_bytes: int) -> str:
    """Return a human-readable string representation of *size_bytes*.

    Examples:
        1024       → "1.00 KB"
        1048576    → "1.00 MB"
    """
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes //= 1024
    return f"{size_bytes:.2f} TB"
