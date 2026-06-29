"""MCP Resource definitions for DrissionPage MCP."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, cast

from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.types import Resource
from pydantic import AnyUrl

from .policy import SafetyPolicy
from .response import tool_data_schema_title
from .tools.base import Tool, ToolType

PAGE_TEXT_EXCERPT_CHARS = 4000
PAGE_HTML_EXCERPT_CHARS = 8000
RESOURCE_JSON_MAX_CHARS = 12000

SESSION_SUMMARY_URI = "drissionpage://session/summary"
PAGE_CURRENT_URI = "drissionpage://page/current"
TOOLS_CATALOG_URI = "drissionpage://tools/catalog"
POLICY_SUMMARY_URI = "drissionpage://policy/summary"

RESOURCE_URIS = [
    SESSION_SUMMARY_URI,
    PAGE_CURRENT_URI,
    TOOLS_CATALOG_URI,
    POLICY_SUMMARY_URI,
]


def list_resources() -> list[Resource]:
    """Return deterministic MCP resources exposed by the server."""

    return [
        Resource(
            uri=_uri(SESSION_SUMMARY_URI),
            name="session_summary",
            title="Session Summary",
            description="Current DrissionPage MCP browser/session state.",
            mimeType="application/json",
        ),
        Resource(
            uri=_uri(PAGE_CURRENT_URI),
            name="page_current",
            title="Current Page",
            description="Bounded current page summary with text and HTML excerpts.",
            mimeType="application/json",
        ),
        Resource(
            uri=_uri(TOOLS_CATALOG_URI),
            name="tools_catalog",
            title="Tools Catalog",
            description="Public tool list with safety annotations and data schemas.",
            mimeType="application/json",
        ),
        Resource(
            uri=_uri(POLICY_SUMMARY_URI),
            name="policy_summary",
            title="Policy Summary",
            description="Configured local safety policy without secret/path leakage.",
            mimeType="application/json",
        ),
    ]


def read_resource(
    uri: str,
    *,
    context: Any,
    tools: Mapping[str, Tool],
) -> list[ReadResourceContents]:
    """Read a resource without creating or initializing a browser."""

    normalized_uri = uri.rstrip("/")
    if normalized_uri == SESSION_SUMMARY_URI:
        payload = session_summary(context)
    elif normalized_uri == PAGE_CURRENT_URI:
        payload = current_page(context)
    elif normalized_uri == TOOLS_CATALOG_URI:
        payload = tools_catalog(tools)
    elif normalized_uri == POLICY_SUMMARY_URI:
        payload = SafetyPolicy.from_env().public_summary()
    else:
        raise ValueError(f"Unknown resource URI: {uri}")

    return [ReadResourceContents(content=_json_resource(payload), mime_type="application/json")]


def session_summary(context: Any) -> dict[str, Any]:
    """Return browser/session state without side effects."""

    policy = SafetyPolicy.from_env()
    browser_active = bool(context and context.is_active())
    tabs = list(context.tabs()) if context else []
    current_tab = context.current_tab() if context else None
    return {
        "available": True,
        "browser_active": browser_active,
        "tab_count": len(tabs),
        "current_url": getattr(current_tab, "url", "") if current_tab else "",
        "policy": {
            "profile": policy.profile(),
            "controls": policy.control_flags(),
        },
    }


def current_page(context: Any) -> dict[str, Any]:
    """Return a bounded current-page payload without initializing the browser."""

    tab = context.current_tab() if context else None
    if tab is None:
        return {
            "available": False,
            "reason": "NO_ACTIVE_TAB",
            "url": "",
            "title": "",
            "text_excerpt": "",
            "html_excerpt": "",
            "truncated": False,
            "limits": _limits(),
        }

    page = getattr(tab, "page", None)
    text, text_truncation = _truncate(
        _safe_string_attr(page, "text"),
        PAGE_TEXT_EXCERPT_CHARS,
    )
    html, html_truncation = _truncate(
        _safe_string_attr(page, "html"),
        PAGE_HTML_EXCERPT_CHARS,
    )
    payload: dict[str, Any] = {
        "available": True,
        "url": getattr(tab, "url", "") or "",
        "title": _safe_string_attr(page, "title"),
        "text_excerpt": text,
        "html_excerpt": html,
        "truncated": text_truncation["truncated"] or html_truncation["truncated"],
        "limits": _limits(),
    }
    if text_truncation["truncated"]:
        payload["text_truncation"] = text_truncation
    if html_truncation["truncated"]:
        payload["html_truncation"] = html_truncation
    return _fit_resource_budget(payload)


def tools_catalog(tools: Mapping[str, Tool]) -> dict[str, Any]:
    """Return public tools with annotations and schema names."""

    return {
        "tools": [
            {
                "name": tool.name,
                "title": tool.title,
                "readOnlyHint": tool.tool_type == ToolType.READ_ONLY,
                "destructiveHint": tool.tool_type == ToolType.DESTRUCTIVE,
                "idempotentHint": tool.idempotent,
                "output_schema": tool_data_schema_title(tool.name),
            }
            for tool in tools.values()
        ]
    }


def _json_resource(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _fit_resource_budget(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep oversized page resources within the global JSON budget."""

    if len(_json_resource(payload)) <= RESOURCE_JSON_MAX_CHARS:
        return payload

    fitted = dict(payload)
    original_json_length = len(_json_resource(fitted))
    for field, truncation_key in (
        ("html_excerpt", "html_truncation"),
        ("text_excerpt", "text_truncation"),
    ):
        while len(_json_resource(fitted)) > RESOURCE_JSON_MAX_CHARS and fitted.get(
            field
        ):
            current = str(fitted[field])
            overflow = len(_json_resource(fitted)) - RESOURCE_JSON_MAX_CHARS
            new_limit = max(0, len(current) - overflow - 128)
            fitted[field] = current[:new_limit]
            truncation = dict(fitted.get(truncation_key) or {})
            truncation.update(
                {
                    "truncated": True,
                    "original_length": max(
                        int(truncation.get("original_length", len(current))),
                        len(current),
                    ),
                    "limit": new_limit,
                }
            )
            fitted[truncation_key] = truncation
            fitted["truncated"] = True

    if len(_json_resource(fitted)) <= RESOURCE_JSON_MAX_CHARS:
        fitted["resource_truncation"] = {
            "truncated": True,
            "original_length": original_json_length,
            "limit": RESOURCE_JSON_MAX_CHARS,
        }
    return fitted


def _truncate(value: str, limit: int) -> tuple[str, dict[str, Any]]:
    if len(value) <= limit:
        return value, {"truncated": False, "original_length": len(value), "limit": limit}
    return value[:limit], {
        "truncated": True,
        "original_length": len(value),
        "limit": limit,
    }


def _safe_string_attr(obj: Any, attr: str) -> str:
    try:
        value = getattr(obj, attr, "")
    except Exception:
        return ""
    return "" if value is None else str(value)


def _limits() -> dict[str, int]:
    return {
        "text_chars": PAGE_TEXT_EXCERPT_CHARS,
        "html_chars": PAGE_HTML_EXCERPT_CHARS,
    }


def _uri(uri: str) -> AnyUrl:
    return cast(AnyUrl, uri)
