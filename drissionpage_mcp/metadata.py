"""Small response metadata helpers for bounded MCP payloads."""

from __future__ import annotations

import json
from typing import Any

APPROX_CHARS_PER_TOKEN = 3.5


def response_meta(payload: Any, *, truncated: bool | None = None) -> dict[str, Any]:
    """Return compact, deterministic size metadata for a JSON-like payload."""

    json_chars = len(_json(payload))
    return {
        "approx_tokens": int(json_chars / APPROX_CHARS_PER_TOKEN),
        "json_chars": json_chars,
        "truncated": bool(_infer_truncated(payload) if truncated is None else truncated),
    }


def with_response_meta(payload: dict[str, Any], *, truncated: bool | None = None) -> dict[str, Any]:
    """Return a shallow copy of *payload* with a ``meta`` field added."""

    data = dict(payload)
    data["meta"] = response_meta(data, truncated=truncated)
    return data


def _json(payload: Any) -> str:
    try:
        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            default=str,
        )
    except TypeError:
        return json.dumps(str(payload), ensure_ascii=False)


def _infer_truncated(value: Any) -> bool:
    if isinstance(value, dict):
        if isinstance(value.get("truncated"), bool):
            return bool(value["truncated"])
        if isinstance(value.get("truncated"), dict):
            return any(bool(item) for item in value["truncated"].values())
        return any(_infer_truncated(item) for item in value.values())
    if isinstance(value, list):
        return any(_infer_truncated(item) for item in value)
    return False
