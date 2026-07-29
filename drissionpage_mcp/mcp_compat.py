"""Compatibility boundary for the MCP Python SDK used by the server wiring."""

from __future__ import annotations

import importlib
import importlib.metadata
import re

from . import __version__

MCP_SDK_RANGE = ">=1.0.0,<2"
MCP_SDK_REQUIREMENT = f"mcp{MCP_SDK_RANGE}"
MCP_SDK_REPAIR_COMMAND = (
    'python -m pip install -U '
    f'"drissionpage-mcp>={__version__}" "{MCP_SDK_REQUIREMENT}"'
)


def installed_mcp_sdk_version() -> str:
    """Return the installed MCP SDK version without assuming a module attribute."""

    try:
        return importlib.metadata.version("mcp")
    except importlib.metadata.PackageNotFoundError:
        pass

    try:
        module = importlib.import_module("mcp")
    except Exception as exc:  # pragma: no cover - dependency metadata normally exists.
        return f"unavailable: {exc}"
    return str(getattr(module, "__version__", "unknown"))


def is_supported_mcp_sdk_version(version: str) -> bool:
    """Return whether a version is inside the server's tested MCP SDK major."""

    match = re.match(r"^\s*(\d+)(?:\.|$)", version)
    if not match:
        return False
    return int(match.group(1)) == 1


def ensure_supported_mcp_sdk(version: str | None = None) -> str:
    """Fail before handler registration when the installed SDK is incompatible."""

    installed = version or installed_mcp_sdk_version()
    if is_supported_mcp_sdk_version(installed):
        return installed
    raise RuntimeError(
        f"Unsupported MCP Python SDK version {installed!r}. "
        f"drissionpage-mcp {__version__} requires {MCP_SDK_REQUIREMENT}. "
        f"Repair the environment with: {MCP_SDK_REPAIR_COMMAND}"
    )


__all__ = [
    "MCP_SDK_RANGE",
    "MCP_SDK_REPAIR_COMMAND",
    "MCP_SDK_REQUIREMENT",
    "ensure_supported_mcp_sdk",
    "installed_mcp_sdk_version",
    "is_supported_mcp_sdk_version",
]
