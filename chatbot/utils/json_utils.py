"""Robust JSON extraction from raw LLM responses.

LLMs often wrap JSON in markdown code fences or add prose before/after it, and
some (notably DeepSeek) emit slightly malformed JSON — trailing commas, a stray
control character in a string. ``parse_json_safe`` extracts the first JSON
object, repairs the common defects, and returns an empty dict on failure
instead of raising — callers decide how to degrade.
"""
import json
import logging
import re
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", re.IGNORECASE)
# Trailing comma before a closing brace/bracket: `… 0.1 ,\n }` → `… 0.1 }`.
_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")


def _extract_object(text: str) -> Optional[str]:
    """Return the first complete ``{...}`` object by brace balancing, or None.

    A greedy ``\\{[\\s\\S]*\\}`` over-captures when prose follows the JSON, and a
    lazy one stops at the first inner ``}``. Balancing braces (while skipping
    string literals) returns exactly the first complete top-level object.
    """
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def parse_json_safe(raw: str) -> Dict:
    """Extract and parse the first JSON object from a raw LLM response.

    Tries a ```json … ``` fenced block first, then the first balanced ``{ … }``
    span. On a decode error, retries once after stripping trailing commas.

    Args:
        raw: Raw text from an LLM call.

    Returns:
        Parsed dict, or an empty dict if no valid JSON object is found.
    """
    text = raw.strip()
    fence_match = _FENCE_RE.search(text)
    if fence_match:
        candidate = fence_match.group(1)
    else:
        candidate = _extract_object(text)
    if candidate is None:
        logger.warning("No JSON object found | raw[:200]: %s", raw[:200])
        return {}

    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        repaired = _TRAILING_COMMA_RE.sub(r"\1", candidate)
        try:
            data = json.loads(repaired)
        except json.JSONDecodeError as exc:
            logger.warning("JSON parse failed: %s | raw[:200]: %s", exc, raw[:200])
            return {}
    return data if isinstance(data, dict) else {}
