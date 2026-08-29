"""Admin knowledge-base management service.

Read/write layer over the curated style knowledge base
(``chatbot/knowledge/styles.json``) for the admin "Knowledge Base" screen.
The KB stays a git-versioned JSON file (decision #68) — it is NOT moved into
SQL. Every mutation rewrites the file atomically and clears the cached
``StyleKbService`` so the live pipeline immediately sees the change.

Business rules enforced here (raised as ``ValueError``/``KeyError``; the router
maps them to 400/404/409):

- style ``id`` must be a non-empty slug, unique on create, immutable on update,
- ``parent`` (when given) must reference an existing family id,
- a family can only be deleted when no style still references it.

Writes are serialised one style per line (matching the existing file layout) so
each edit produces a small, reviewable git diff rather than reformatting the
whole file.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Tuple

from app.config import settings
from chatbot.services.style_kb_service import get_style_kb
from chatbot.utils.schemas import StyleEntry

logger = logging.getLogger(__name__)

# Serialises all KB file writes — prevents two admin requests interleaving and
# corrupting styles.json.
_WRITE_LOCK = threading.Lock()

# A valid style/family id: lowercase letters, digits and single hyphens.
_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# Order of the optional top-level metadata keys, preserved on rewrite.
_META_KEYS = ("schema_version", "note", "sources")


def _kb_path() -> Path:
    """Return the configured KB file path."""
    return Path(settings.STYLE_KB_PATH)


def _load_raw() -> Dict[str, Any]:
    """Load the raw KB document (metadata + families + styles)."""
    path = _kb_path()
    if not path.is_file():
        raise FileNotFoundError(f"Style KB not found at {str(path)!r}")
    return json.loads(path.read_text(encoding="utf-8"))


def _dump_kb(data: Dict[str, Any]) -> str:
    """Serialise the KB with one family/style per line for small git diffs."""
    lines: List[str] = ["{"]
    body: List[str] = []

    for key in _META_KEYS:
        if key in data:
            body.append(f"  {json.dumps(key)}: {json.dumps(data[key], ensure_ascii=False)}")

    families = data.get("families", {})
    fam_lines = [
        f"    {json.dumps(fid)}: {json.dumps(meta, ensure_ascii=False)}"
        for fid, meta in families.items()
    ]
    body.append('  "families": {\n' + ",\n".join(fam_lines) + "\n  }")

    styles = data.get("styles", [])
    style_lines = [f"    {json.dumps(s, ensure_ascii=False)}" for s in styles]
    body.append('  "styles": [\n' + ",\n".join(style_lines) + "\n  ]")

    lines.append(",\n".join(body))
    lines.append("}")
    return "\n".join(lines) + "\n"


def _save_raw(data: Dict[str, Any]) -> None:
    """Atomically rewrite the KB file and drop the cached StyleKbService."""
    path = _kb_path()
    payload = _dump_kb(data)
    with _WRITE_LOCK:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, path)
    # Force the next get_style_kb() to reload the rewritten file.
    get_style_kb.cache_clear()
    logger.info("KB rewritten: %d styles, %d families",
                len(data.get("styles", [])), len(data.get("families", {})))


def _validate_id(style_id: str) -> str:
    """Normalise and validate a style/family id slug."""
    cleaned = (style_id or "").strip().lower()
    if not cleaned:
        raise ValueError("id must not be empty")
    if not _ID_PATTERN.match(cleaned):
        raise ValueError("id must be a lowercase slug (letters, digits, hyphens)")
    return cleaned


# ── Styles ───────────────────────────────────────────────────────────────────

def list_styles() -> List[StyleEntry]:
    """Return every style entry in the KB (canonical order)."""
    return get_style_kb().all_styles()


def get_style(style_id: str) -> StyleEntry:
    """Return one style entry by id.

    Raises:
        KeyError: If no style has this id.
    """
    entry = get_style_kb().get(style_id)
    if entry is None:
        raise KeyError(f"No style with id '{style_id}'")
    return entry


def create_style(payload: StyleEntry) -> StyleEntry:
    """Append a new style entry to the KB.

    Raises:
        ValueError: If the id is invalid, already exists, or parent is unknown.
    """
    data = _load_raw()
    style_id = _validate_id(payload.id)
    existing_ids = {s["id"] for s in data.get("styles", [])}
    if style_id in existing_ids:
        raise ValueError(f"A style with id '{style_id}' already exists")
    entry = _prepare_entry(payload, style_id, data.get("families", {}))
    data.setdefault("styles", []).append(entry)
    _save_raw(data)
    return StyleEntry(**entry)


def update_style(style_id: str, payload: StyleEntry) -> StyleEntry:
    """Overwrite an existing style entry (id is immutable).

    Raises:
        KeyError: If no style has this id.
        ValueError: If the parent family is unknown.
    """
    data = _load_raw()
    styles = data.get("styles", [])
    index = next((i for i, s in enumerate(styles) if s["id"] == style_id), None)
    if index is None:
        raise KeyError(f"No style with id '{style_id}'")
    entry = _prepare_entry(payload, style_id, data.get("families", {}))
    styles[index] = entry
    _save_raw(data)
    return StyleEntry(**entry)


def delete_style(style_id: str) -> None:
    """Delete a style entry by id.

    Raises:
        KeyError: If no style has this id.
    """
    data = _load_raw()
    styles = data.get("styles", [])
    remaining = [s for s in styles if s["id"] != style_id]
    if len(remaining) == len(styles):
        raise KeyError(f"No style with id '{style_id}'")
    data["styles"] = remaining
    _save_raw(data)


def _prepare_entry(
    payload: StyleEntry, style_id: str, families: Dict[str, Any]
) -> Dict[str, Any]:
    """Validate and serialise a StyleEntry to its stored dict form."""
    if not payload.name.strip():
        raise ValueError("name must not be empty")
    parent = payload.parent
    if parent and parent not in families:
        raise ValueError(f"Unknown family '{parent}'")
    entry = payload.model_dump()
    entry["id"] = style_id
    return entry


# ── Families ─────────────────────────────────────────────────────────────────

def list_families() -> List[Dict[str, Any]]:
    """Return all families as ``{id, name}`` dicts."""
    data = _load_raw()
    return [
        {"id": fid, "name": meta.get("name", fid)}
        for fid, meta in data.get("families", {}).items()
    ]


def create_family(family_id: str, name: str) -> Dict[str, Any]:
    """Add a new family.

    Raises:
        ValueError: If the id is invalid or already exists, or name is empty.
    """
    fid = _validate_id(family_id)
    if not name.strip():
        raise ValueError("name must not be empty")
    data = _load_raw()
    families = data.setdefault("families", {})
    if fid in families:
        raise ValueError(f"A family with id '{fid}' already exists")
    families[fid] = {"name": name.strip(), "parent": None}
    _save_raw(data)
    return {"id": fid, "name": name.strip()}


def rename_family(family_id: str, name: str) -> Dict[str, Any]:
    """Rename an existing family.

    Raises:
        KeyError: If no family has this id.
        ValueError: If name is empty.
    """
    if not name.strip():
        raise ValueError("name must not be empty")
    data = _load_raw()
    families = data.get("families", {})
    if family_id not in families:
        raise KeyError(f"No family with id '{family_id}'")
    families[family_id]["name"] = name.strip()
    _save_raw(data)
    return {"id": family_id, "name": name.strip()}


def delete_family(family_id: str) -> None:
    """Delete a family, only if no style still references it.

    Raises:
        KeyError: If no family has this id.
        ValueError: If one or more styles still belong to the family.
    """
    data = _load_raw()
    families = data.get("families", {})
    if family_id not in families:
        raise KeyError(f"No family with id '{family_id}'")
    referencing = [s["id"] for s in data.get("styles", []) if s.get("parent") == family_id]
    if referencing:
        raise ValueError(
            f"Family '{family_id}' still has {len(referencing)} style(s); "
            f"reassign or delete them first"
        )
    del families[family_id]
    _save_raw(data)
