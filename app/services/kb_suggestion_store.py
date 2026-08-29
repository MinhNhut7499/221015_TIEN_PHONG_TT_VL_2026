"""Out-of-KB style suggestion queue (file-backed).

When the open-vocabulary pipeline proposes a style name that matches no KB
entry, that name is recorded here so an admin can later review it and either
promote it into the KB (decision #72 — the KB is never grown automatically at
runtime) or dismiss it. Backed by a small JSON file next to the KB, kept
separate from ``styles.json`` so the curated KB diff stays clean.

The store is best-effort: ``record`` swallows its own errors so it can never
break an analysis request.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from app.config import settings

logger = logging.getLogger(__name__)

_WRITE_LOCK = threading.Lock()


def _store_path() -> Path:
    """Return the suggestions JSON path (sibling of the KB file)."""
    return Path(settings.STYLE_KB_PATH).with_name("style_suggestions.json")


def _load() -> Dict[str, Dict[str, Any]]:
    """Load the suggestion map, returning an empty map when absent/corrupt."""
    path = _store_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: Dict[str, Dict[str, Any]]) -> None:
    """Atomically write the suggestion map."""
    path = _store_path()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def record(names: List[str]) -> None:
    """Record out-of-KB style names, bumping their count and last-seen time.

    Best-effort: any failure is logged and swallowed so analysis never breaks.
    """
    cleaned = [n.strip() for n in names if n and n.strip()]
    if not cleaned:
        return
    try:
        now = datetime.now(timezone.utc).isoformat()
        with _WRITE_LOCK:
            data = _load()
            for name in cleaned:
                key = name.lower()
                entry = data.get(key)
                if entry is None:
                    data[key] = {"name": name, "count": 1, "first_seen": now, "last_seen": now}
                else:
                    entry["count"] = int(entry.get("count", 0)) + 1
                    entry["last_seen"] = now
                    entry["name"] = name
            _save(data)
    except OSError as exc:
        logger.warning("Failed to record style suggestions: %s", exc)


def list_suggestions() -> List[Dict[str, Any]]:
    """Return all queued suggestions, most frequent first."""
    items = list(_load().values())
    items.sort(key=lambda e: e.get("count", 0), reverse=True)
    return items


def dismiss(name: str) -> bool:
    """Remove one suggestion by name (case-insensitive). Returns True if removed."""
    key = (name or "").strip().lower()
    if not key:
        return False
    with _WRITE_LOCK:
        data = _load()
        if key not in data:
            return False
        del data[key]
        _save(data)
    return True
