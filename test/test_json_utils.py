"""Tests for robust JSON extraction (chatbot/utils/json_utils.py).

These lock in the hardening that fixes the silent advocate-dropping bug: a
slightly malformed LLM JSON (trailing comma) and prose after the object must
still parse, while genuine garbage degrades to an empty dict.
"""
from chatbot.utils.json_utils import parse_json_safe


def test_parses_plain_object() -> None:
    """A bare JSON object parses."""
    assert parse_json_safe('{"a": 1, "b": "x"}') == {"a": 1, "b": "x"}


def test_parses_fenced_block() -> None:
    """A ```json fenced block is extracted from surrounding prose."""
    raw = 'Here is my answer:\n```json\n{"style": "Gothic"}\n```\nThanks!'
    assert parse_json_safe(raw) == {"style": "Gothic"}


def test_repairs_trailing_commas() -> None:
    """Trailing commas before } / ] are stripped and the object parses."""
    raw = '{"distribution": {"X": 0.5, "Y": 0.5,}, "note": "ok",}'
    assert parse_json_safe(raw) == {"distribution": {"X": 0.5, "Y": 0.5}, "note": "ok"}


def test_balanced_braces_ignore_trailing_prose() -> None:
    """Returns the first complete object even when prose with braces follows."""
    raw = '{"a": {"b": 1}}\nNote: not { valid json } here.'
    assert parse_json_safe(raw) == {"a": {"b": 1}}


def test_brace_inside_string_does_not_truncate() -> None:
    """A brace inside a string literal must not end the object early."""
    raw = '{"note": "uses a { brace", "ok": true}'
    assert parse_json_safe(raw) == {"note": "uses a { brace", "ok": True}


def test_garbage_returns_empty_dict() -> None:
    """No JSON object present → empty dict (caller degrades)."""
    assert parse_json_safe("sorry, I cannot help with that") == {}


def test_json_array_returns_empty_dict() -> None:
    """A top-level array is not an object → empty dict."""
    assert parse_json_safe("[1, 2, 3]") == {}
