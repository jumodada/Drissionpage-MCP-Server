"""Optional local safety policy for browser automation tools.

Defaults preserve local stdio behavior. Operators can opt in to allowlist-first
URL controls, blocklists, private-network denial, and screenshot save-root
restrictions through environment variables without adding runtime dependencies.
"""

from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

from .response import ErrorCode

ENV_NAV_ALLOWLIST = "DP_MCP_NAV_ALLOWLIST"
ENV_NAV_BLOCKLIST = "DP_MCP_NAV_BLOCKLIST"
ENV_BLOCK_PRIVATE = "DP_MCP_BLOCK_PRIVATE_NETWORK"
ENV_SCREENSHOT_ROOT = "DP_MCP_SCREENSHOT_ROOT"


class PolicyDeniedError(ValueError):
    """Raised when an opt-in safety policy rejects a requested action."""

    def __init__(self, message: str, *, rule: str, value: str):
        super().__init__(message)
        self.code = ErrorCode.POLICY_DENIED
        self.rule = rule
        self.value = value


@dataclass(frozen=True)
class SafetyPolicy:
    """Environment-backed safety controls for local browser automation."""

    navigation_allowlist: tuple[str, ...] = field(default_factory=tuple)
    navigation_blocklist: tuple[str, ...] = field(default_factory=tuple)
    block_private_network: bool = False
    screenshot_root: Path | None = None

    @classmethod
    def from_env(cls) -> "SafetyPolicy":
        """Build a policy from process environment variables."""

        root = os.getenv(ENV_SCREENSHOT_ROOT)
        return cls(
            navigation_allowlist=_split_env(os.getenv(ENV_NAV_ALLOWLIST)),
            navigation_blocklist=_split_env(os.getenv(ENV_NAV_BLOCKLIST)),
            block_private_network=_env_bool(ENV_BLOCK_PRIVATE),
            screenshot_root=Path(root).expanduser().resolve() if root else None,
        )

    def validate_navigation(self, url: str) -> None:
        """Validate a navigation URL before browser startup or tab creation."""

        if not (
            self.navigation_allowlist
            or self.navigation_blocklist
            or self.block_private_network
        ):
            return

        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise PolicyDeniedError(
                "Navigation URL must be an absolute http(s) URL.",
                rule="navigation_url",
                value=url,
            )

        host = parsed.hostname or ""
        if self.navigation_allowlist and not _matches_any(
            url, host, self.navigation_allowlist
        ):
            raise PolicyDeniedError(
                f"Navigation to {host or url!r} is not in DP_MCP_NAV_ALLOWLIST.",
                rule=ENV_NAV_ALLOWLIST,
                value=url,
            )

        if self.navigation_blocklist and _matches_any(
            url, host, self.navigation_blocklist
        ):
            raise PolicyDeniedError(
                f"Navigation to {host or url!r} is blocked by DP_MCP_NAV_BLOCKLIST.",
                rule=ENV_NAV_BLOCKLIST,
                value=url,
            )

        if self.block_private_network and _is_private_or_local_host(host):
            raise PolicyDeniedError(
                f"Navigation to private/local host {host!r} is blocked.",
                rule=ENV_BLOCK_PRIVATE,
                value=url,
            )

    def validate_screenshot_path(self, path: str) -> None:
        """Validate an optional screenshot save path before writing files."""

        if not path:
            return

        if self.screenshot_root is None:
            raise PolicyDeniedError(
                "Screenshot file saves require DP_MCP_SCREENSHOT_ROOT.",
                rule=ENV_SCREENSHOT_ROOT,
                value=path,
            )

        requested = Path(path).expanduser().resolve()
        try:
            requested.relative_to(self.screenshot_root)
        except ValueError as exc:
            raise PolicyDeniedError(
                f"Screenshot path must be inside {self.screenshot_root}.",
                rule=ENV_SCREENSHOT_ROOT,
                value=path,
            ) from exc

    def profile(self) -> str:
        """Return a compact public profile name for configured controls."""

        return "restricted" if any(self.control_flags().values()) else "open-local"

    def control_flags(self) -> dict[str, bool]:
        """Return non-sensitive booleans for active policy controls."""

        return {
            "navigation_allowlist": bool(self.navigation_allowlist),
            "navigation_blocklist": bool(self.navigation_blocklist),
            "block_private_network": self.block_private_network,
            "screenshot_root": self.screenshot_root is not None,
        }

    def public_summary(self) -> dict[str, object]:
        """Return a redacted JSON-safe policy summary for MCP Resources."""

        return {
            "profile": self.profile(),
            "controls": {
                "navigation_allowlist": _redacted_sequence(self.navigation_allowlist),
                "navigation_blocklist": _redacted_sequence(self.navigation_blocklist),
                "block_private_network": self.block_private_network,
                "screenshot_root": {
                    "configured": self.screenshot_root is not None,
                    **(
                        {"value": "<redacted>"}
                        if self.screenshot_root is not None
                        else {}
                    ),
                },
            },
        }


def validate_navigation(url: str) -> None:
    """Validate navigation against the current environment policy."""

    SafetyPolicy.from_env().validate_navigation(url)


def validate_screenshot_path(path: str) -> None:
    """Validate screenshot path against the current environment policy."""

    SafetyPolicy.from_env().validate_screenshot_path(path)


def _split_env(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _redacted_sequence(values: tuple[str, ...]) -> dict[str, object]:
    configured = bool(values)
    payload: dict[str, object] = {"configured": configured, "count": len(values)}
    if configured:
        payload["values"] = "<redacted>"
    return payload


def _env_bool(name: str) -> bool:
    value = os.getenv(name)
    return bool(value and value.strip().lower() in {"1", "true", "yes", "y", "on"})


def _matches_any(url: str, host: str, patterns: Iterable[str]) -> bool:
    normalized_host = host.lower().rstrip(".")
    normalized_url = url.lower()
    for pattern in patterns:
        item = pattern.strip().lower().rstrip(".")
        if not item:
            continue
        if item.startswith(("http://", "https://")):
            if normalized_url.startswith(item):
                return True
            continue
        if normalized_host == item or normalized_host.endswith("." + item):
            return True
    return False


def _is_private_or_local_host(host: str) -> bool:
    normalized = host.lower().strip("[]").rstrip(".")
    if normalized in {"localhost", "localtest.me"} or normalized.endswith(".local"):
        return True
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    )
