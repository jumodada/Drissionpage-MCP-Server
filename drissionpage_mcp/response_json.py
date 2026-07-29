"""Strict JSON normalization for public MCP response payloads."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import Any


def json_safe_value(value: Any) -> Any:
    """Return a recursively JSON-safe value with non-finite numbers as null."""

    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return {str(key): json_safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [json_safe_value(item) for item in value]
    return str(value)


def strict_json_dumps(
    value: Any,
    *,
    ensure_ascii: bool = False,
    sort_keys: bool = False,
    separators: tuple[str, str] | None = None,
    indent: int | None = None,
) -> str:
    """Serialize public data as standards-compliant JSON."""

    return json.dumps(
        json_safe_value(value),
        ensure_ascii=ensure_ascii,
        sort_keys=sort_keys,
        separators=separators,
        indent=indent,
        allow_nan=False,
    )


def non_finite_number_label(value: Any) -> str | None:
    """Return the stable label for a non-finite Python number."""

    if not isinstance(value, float) or math.isfinite(value):
        return None
    if math.isnan(value):
        return "NaN"
    return "Infinity" if value > 0 else "-Infinity"
