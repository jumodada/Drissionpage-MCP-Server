"""Environment parsing helpers for DrissionPage MCP internals."""

from __future__ import annotations

import os
from typing import Any

_TRUTHY_VALUES = {"1", "true", "yes", "y", "on"}


def env_bool(name: str, default: bool = False) -> bool:
    """Return an environment-backed boolean using DrissionMCP truthy parsing."""

    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in _TRUTHY_VALUES


def redacted_env_path(*names: str) -> dict[str, Any]:
    """Return redacted metadata for the first configured path environment variable."""

    for name in names:
        value = os.getenv(name)
        if value:
            return {
                "configured": True,
                "env": name,
                "value": "<redacted>",
                "exists": os.path.exists(value),
            }
    return {"configured": False, "env": "", "value": "", "exists": False}
