"""Optional local safety policy for browser automation tools.

Defaults preserve local stdio behavior. Operators can opt in to allowlist-first
URL controls, blocklists, private-network denial, and screenshot save-root
restrictions through environment variables without adding runtime dependencies.
"""

from __future__ import annotations

import ipaddress
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import SplitResult, quote, urlsplit

from .env import env_bool
from .response_errors import ErrorCode

ENV_NAV_ALLOWLIST = "DP_MCP_NAV_ALLOWLIST"
ENV_NAV_BLOCKLIST = "DP_MCP_NAV_BLOCKLIST"
ENV_BLOCK_PRIVATE = "DP_MCP_BLOCK_PRIVATE_NETWORK"
ENV_SCREENSHOT_ROOT = "DP_MCP_SCREENSHOT_ROOT"
ENV_UPLOAD_ROOT = "DP_MCP_UPLOAD_ROOT"
ENV_DOWNLOAD_ROOT = "DP_MCP_DOWNLOAD_ROOT"
ENV_ARTIFACT_ROOT = "DP_MCP_ARTIFACT_ROOT"
ENV_DENY_DOWNLOAD = "DP_MCP_DENY_DOWNLOAD"


class PolicyDeniedError(ValueError):
    """Raised when an opt-in safety policy rejects a requested action."""

    def __init__(self, message: str, *, rule: str, value: str):
        super().__init__(message)
        self.code = ErrorCode.POLICY_DENIED
        self.rule = rule
        # Tool handlers expose this field in public error details.
        self.value = "<redacted>"


@dataclass(frozen=True)
class SafetyPolicy:
    """Environment-backed safety controls for local browser automation."""

    navigation_allowlist: tuple[str, ...] = field(default_factory=tuple)
    navigation_blocklist: tuple[str, ...] = field(default_factory=tuple)
    block_private_network: bool = False
    screenshot_root: Path | None = None
    upload_root: Path | None = None
    download_root: Path | None = None
    artifact_root: Path | None = None
    deny_download: bool = False

    @classmethod
    def from_env(cls) -> SafetyPolicy:
        """Build a policy from process environment variables."""

        root = os.getenv(ENV_SCREENSHOT_ROOT)
        upload_root = os.getenv(ENV_UPLOAD_ROOT)
        download_root = os.getenv(ENV_DOWNLOAD_ROOT)
        artifact_root = os.getenv(ENV_ARTIFACT_ROOT)
        return cls(
            navigation_allowlist=_split_env(os.getenv(ENV_NAV_ALLOWLIST)),
            navigation_blocklist=_split_env(os.getenv(ENV_NAV_BLOCKLIST)),
            block_private_network=env_bool(ENV_BLOCK_PRIVATE),
            screenshot_root=Path(root).expanduser().resolve() if root else None,
            upload_root=(
                Path(upload_root).expanduser().resolve() if upload_root else None
            ),
            download_root=Path(download_root).expanduser() if download_root else None,
            artifact_root=(
                Path(artifact_root).expanduser() if artifact_root else None
            ),
            deny_download=env_bool(ENV_DENY_DOWNLOAD),
        )

    def validate_navigation(self, url: str) -> None:
        """Validate a navigation URL before browser startup or tab creation."""

        if not (
            self.navigation_allowlist
            or self.navigation_blocklist
            or self.block_private_network
        ):
            return

        try:
            parsed = urlsplit(url)
            _ = parsed.port
        except ValueError as exc:
            raise PolicyDeniedError(
                "Navigation URL must be a valid absolute http(s) URL.",
                rule="navigation_url",
                value=url,
            ) from exc
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or "\\" in parsed.netloc + parsed.path
        ):
            raise PolicyDeniedError(
                "Navigation URL must be an absolute http(s) URL.",
                rule="navigation_url",
                value=url,
            )
        if not _canonical_host_spelling(parsed.hostname or ""):
            raise PolicyDeniedError(
                "Navigation URL has a non-canonical hostname spelling.",
                rule="navigation_url",
                value=url,
            )
        host = parsed.hostname or ""
        if self.navigation_allowlist and not _matches_any(
            url, host, self.navigation_allowlist
        ):
            raise PolicyDeniedError(
                "Navigation target is not in DP_MCP_NAV_ALLOWLIST.",
                rule=ENV_NAV_ALLOWLIST,
                value=url,
            )

        if self.navigation_blocklist and _matches_any(
            url, host, self.navigation_blocklist
        ):
            raise PolicyDeniedError(
                "Navigation target is blocked by DP_MCP_NAV_BLOCKLIST.",
                rule=ENV_NAV_BLOCKLIST,
                value=url,
            )

        if self.block_private_network and _is_private_or_local_host(host):
            raise PolicyDeniedError(
                "Navigation to a private/local host is blocked.",
                rule=ENV_BLOCK_PRIVATE,
                value=url,
            )

    def validate_screenshot_path(self, path: str) -> Path:
        """Validate an optional screenshot save path before writing files."""

        if not path:
            raise PolicyDeniedError(
                "Screenshot file saves require a non-empty path.",
                rule=ENV_SCREENSHOT_ROOT,
                value="<redacted>",
            )

        if self.screenshot_root is None:
            raise PolicyDeniedError(
                "Screenshot file saves require DP_MCP_SCREENSHOT_ROOT.",
                rule=ENV_SCREENSHOT_ROOT,
                value=path,
            )

        candidate = Path(path).expanduser()
        requested = (
            candidate.resolve()
            if candidate.is_absolute()
            else (self.screenshot_root / candidate).resolve()
        )
        try:
            requested.relative_to(self.screenshot_root)
        except ValueError as exc:
            raise PolicyDeniedError(
                "Screenshot path must be inside DP_MCP_SCREENSHOT_ROOT.",
                rule=ENV_SCREENSHOT_ROOT,
                value=path,
            ) from exc
        return requested

    def validate_upload_paths(self, paths: Iterable[str]) -> list[Path]:
        """Validate file-upload paths before exposing them to the browser."""

        requested_paths = [str(path) for path in paths if str(path)]
        if not requested_paths:
            raise PolicyDeniedError(
                "File upload requires at least one path.",
                rule=ENV_UPLOAD_ROOT,
                value="",
            )

        if self.upload_root is None:
            raise PolicyDeniedError(
                "File uploads require DP_MCP_UPLOAD_ROOT.",
                rule=ENV_UPLOAD_ROOT,
                value="<redacted>",
            )

        resolved: list[Path] = []
        for path in requested_paths:
            requested = Path(path).expanduser().resolve()
            try:
                requested.relative_to(self.upload_root)
            except ValueError as exc:
                raise PolicyDeniedError(
                    "Upload path must be inside DP_MCP_UPLOAD_ROOT.",
                    rule=ENV_UPLOAD_ROOT,
                    value="<redacted>",
                ) from exc
            if not requested.is_file():
                raise PolicyDeniedError(
                    "Upload path must exist and be a file.",
                    rule=ENV_UPLOAD_ROOT,
                    value="<redacted>",
                )
            resolved.append(requested)
        return resolved

    def validate_external_download(self) -> None:
        """Reject browser downloads when the operator enabled the deny switch."""

        if self.deny_download:
            raise PolicyDeniedError(
                "Browser downloads are disabled by local policy.",
                rule=ENV_DENY_DOWNLOAD,
                value="<redacted>",
            )

    def validate_download_root(self) -> Path:
        """Return the configured download root after checking its boundary."""

        if self.download_root is None:
            raise PolicyDeniedError(
                "Browser downloads require DP_MCP_DOWNLOAD_ROOT.",
                rule=ENV_DOWNLOAD_ROOT,
                value="<redacted>",
            )
        if self.download_root.is_symlink():
            raise PolicyDeniedError(
                "DP_MCP_DOWNLOAD_ROOT must not be a symlink.",
                rule=ENV_DOWNLOAD_ROOT,
                value="<redacted>",
            )
        if self.download_root.exists() and not self.download_root.is_dir():
            raise PolicyDeniedError(
                "DP_MCP_DOWNLOAD_ROOT must identify a directory.",
                rule=ENV_DOWNLOAD_ROOT,
                value="<redacted>",
            )
        return self.download_root.resolve()

    def validate_artifact_root(self) -> Path:
        """Return the configured generated-artifact root after boundary checks."""

        if self.artifact_root is None:
            raise PolicyDeniedError(
                "Page exports require DP_MCP_ARTIFACT_ROOT.",
                rule=ENV_ARTIFACT_ROOT,
                value="<redacted>",
            )
        if self.artifact_root.is_symlink():
            raise PolicyDeniedError(
                "DP_MCP_ARTIFACT_ROOT must not be a symlink.",
                rule=ENV_ARTIFACT_ROOT,
                value="<redacted>",
            )
        if self.artifact_root.exists() and not self.artifact_root.is_dir():
            raise PolicyDeniedError(
                "DP_MCP_ARTIFACT_ROOT must identify a directory.",
                rule=ENV_ARTIFACT_ROOT,
                value="<redacted>",
            )
        return self.artifact_root.resolve()

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
            "upload_root": self.upload_root is not None,
            "download_root": self.download_root is not None,
            "artifact_root": self.artifact_root is not None,
            "deny_download": self.deny_download,
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
                "upload_root": {
                    "configured": self.upload_root is not None,
                    **({"value": "<redacted>"} if self.upload_root is not None else {}),
                },
                "download_root": {
                    "configured": self.download_root is not None,
                    **(
                        {"value": "<redacted>"}
                        if self.download_root is not None
                        else {}
                    ),
                },
                "artifact_root": {
                    "configured": self.artifact_root is not None,
                    **(
                        {"value": "<redacted>"}
                        if self.artifact_root is not None
                        else {}
                    ),
                },
                "deny_download": self.deny_download,
            },
        }


def validate_navigation(url: str) -> None:
    """Validate navigation against the current environment policy."""

    SafetyPolicy.from_env().validate_navigation(url)


def validate_screenshot_path(path: str) -> Path:
    """Validate screenshot path against the current environment policy."""

    return SafetyPolicy.from_env().validate_screenshot_path(path)


def validate_external_download() -> None:
    """Validate browser downloads against the current policy."""

    SafetyPolicy.from_env().validate_external_download()


def validate_download_root() -> Path:
    """Return the configured safe browser download root."""

    return SafetyPolicy.from_env().validate_download_root()


def validate_artifact_root() -> Path:
    """Return the configured safe generated-artifact root."""

    return SafetyPolicy.from_env().validate_artifact_root()


def validate_upload_paths(paths: Iterable[str]) -> list[Path]:
    """Validate upload paths against the current environment policy."""

    return SafetyPolicy.from_env().validate_upload_paths(paths)


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


def _matches_any(url: str, host: str, patterns: Iterable[str]) -> bool:
    parsed = urlsplit(url)
    normalized_host = _normalized_hostname(host)
    for pattern in patterns:
        item = pattern.strip()
        if not item:
            continue
        if item.lower().startswith(("http://", "https://")):
            if _matches_url_pattern(parsed, item):
                return True
            continue
        normalized_item = _normalized_hostname(item)
        if normalized_host == normalized_item or normalized_host.endswith(
            "." + normalized_item
        ):
            return True
    return False


def _matches_url_pattern(target: SplitResult, pattern: str) -> bool:
    """Match an absolute URL rule by scheme, host, effective port, and path."""

    try:
        rule = urlsplit(pattern)
        target_port = (
            target.port if target.port is not None else _default_port(target.scheme)
        )
        rule_port = (
            rule.port if rule.port is not None else _default_port(rule.scheme)
        )
    except ValueError:
        return False
    if (
        rule.scheme not in {"http", "https"}
        or not rule.hostname
        or not _canonical_host_spelling(rule.hostname)
    ):
        return False
    if target.scheme.lower() != rule.scheme.lower():
        return False
    if (
        target.hostname is None
        or _normalized_hostname(target.hostname)
        != _normalized_hostname(rule.hostname)
    ):
        return False
    if target_port != rule_port:
        return False
    target_path = _normalize_url_path(target.path or "/")
    rule_path = _normalize_url_path(rule.path or "/")
    path_prefix = rule_path if rule_path.endswith("/") else rule_path + "/"
    return target_path == rule_path or target_path.startswith(path_prefix)


def _default_port(scheme: str) -> int:
    return 443 if scheme.lower() == "https" else 80


def _normalize_url_path(path: str) -> str:
    # Normalize browser-serialized spaces/Unicode and equivalent unreserved
    # escapes while preserving reserved escapes and empty path segments.
    path = quote(path, safe="/%:@!$&'()*+,;=-._~%")
    path = re.sub(
        r"%([0-9a-fA-F]{2})",
        lambda match: _normalize_path_escape(match.group(1)),
        path,
    )
    segments: list[str] = []
    parts = path.split("/")[1:]
    for index, segment in enumerate(parts):
        dot_form = re.sub(r"%2e", ".", segment, flags=re.IGNORECASE)
        if dot_form == ".":
            if index == len(parts) - 1:
                segments.append("")
            continue
        if dot_form == "..":
            if segments:
                segments.pop()
            if index == len(parts) - 1:
                segments.append("")
            continue
        segments.append(segment)
    return "/" + "/".join(segments)


def _normalize_path_escape(hex_value: str) -> str:
    value = int(hex_value, 16)
    character = chr(value)
    if character.isascii() and (character.isalnum() or character in "-._~"):
        return character
    return f"%{value:02X}"


def _canonical_host_spelling(host: str) -> bool:
    """Reject encoded or Unicode host spellings under an active URL policy."""

    if not host or not host.isascii() or "%" in host:
        return False
    bracketed = host.startswith("[") and host.endswith("]")
    unbracketed = host[1:-1] if bracketed else host
    try:
        address = ipaddress.ip_address(unbracketed)
    except ValueError:
        # WHATWG URL parsing treats a numeric-looking final label as an IPv4
        # host, including noncanonical integer, hex, and octal forms.
        labels = unbracketed.rstrip(".").split(".")
        numeric_or_hex = all(
            re.fullmatch(r"(?:0x[0-9a-f]+|[0-9]+)", label, re.IGNORECASE)
            for label in labels
        )
        if numeric_or_hex:
            return False
        return not bracketed
    if address.version == 4:
        return not bracketed and str(address) == unbracketed
    return True


def _normalized_hostname(host: str) -> str:
    """Normalize DNS and IP literals for origin comparisons."""

    unbracketed = host[1:-1] if host.startswith("[") and host.endswith("]") else host
    try:
        address = ipaddress.ip_address(unbracketed)
    except ValueError:
        return host.lower().rstrip(".")
    return f"[{address.compressed}]" if address.version == 6 else str(address)


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
