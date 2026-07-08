"""Model-facing guidance exposed through MCP initialization, resources, and prompts."""

from __future__ import annotations

from typing import Any

from . import __version__

SUPPORTED_DRISSIONPAGE_RANGE = "DrissionPage>=4.1.1.4,<5"
MODEL_USAGE_RESOURCE_URI = "drissionpage://guide/model-usage"
MODEL_USAGE_PROMPT_NAME = "drissionpage_mcp_usage_playbook"


def server_instructions(version: str = __version__) -> str:
    """Return compact MCP initialization instructions for connected models."""

    return f"""DrissionPage MCP {version} is structured browser automation for DrissionPage 4.x.
Compatibility: use {SUPPORTED_DRISSIONPAGE_RANGE}; do not assume DrissionPage 5 beta/internal builds are supported.
Default flow: choose the highest-level workflow that matches the task before low-level primitives. Use browser_open_and_snapshot for navigate+inspect, browser_extract_links for link discovery, page_snapshot for more selectors/content, and page_navigate only when you need navigation without an immediate snapshot.
Forms: use form_inspect, then form_fill_preview; treat requires_confirmation=true as a hard stop before submit and never echo field secrets.
Network: use network_listen_start before the triggering action, network_listen_wait for bounded HTTP/XHR/Fetch metadata, then network_listen_stop; this is observation only, not interception or request mutation.
Safety: respect error.details.hints, navigation policy errors, DP_MCP_SCREENSHOT_ROOT for saved screenshots, and DP_MCP_UPLOAD_ROOT for uploads.
Responses: prefer structuredContent; otherwise parse the first text block under ### JSON_RESULT. Legacy alias tools are not public."""


def usage_playbook_text(*, task: str = "", version: str = __version__) -> str:
    """Return a prompt-friendly playbook for using DrissionPage MCP."""

    task_line = f"Task context: {task}\n\n" if task else ""
    return f"""Use DrissionPage MCP {version} safely and efficiently.

{task_line}Core rules:
- Target {SUPPORTED_DRISSIONPAGE_RANGE}; DrissionPage 5 beta/internal builds are unsupported.
- Prefer workflow helpers before low-level primitives when they match the task.
- For page summary or inspection, start with browser_open_and_snapshot; use page_navigate only when you intentionally do not need immediate page context.
- Use page_snapshot for selectors/content, page_observe after actions, and wait_until for dynamic UI instead of fixed sleeps.
- For forms, call form_inspect then form_fill_preview. Do not submit until explicit user confirmation; do not echo secrets.
- For links, use browser_extract_links with bounded limit and same_origin_only when useful.
- For network observation, call network_listen_start, trigger the page action, call network_listen_wait, then network_listen_stop. This is observation only.
- Prefer structuredContent; otherwise parse ### JSON_RESULT. Follow error.details.hints when tools fail.
"""


def model_usage_payload(version: str = __version__) -> dict[str, Any]:
    """Return compact JSON guidance for MCP resources."""

    return {
        "available": True,
        "version": version,
        "compatibility": {
            "drissionpage": SUPPORTED_DRISSIONPAGE_RANGE,
            "drissionpage_5_supported": False,
        },
        "instructions": server_instructions(version),
        "workflow_routes": [
            {
                "task": "summarize_or_inspect",
                "preferred_sequence": [
                    "browser_open_and_snapshot",
                    "page_snapshot",
                    "page_get_url",
                ],
                "use_when": "Need page context, content, selectors, forms, or console hints after opening a URL.",
            },
            {
                "task": "link_discovery",
                "preferred_sequence": ["browser_extract_links"],
                "use_when": "Need bounded link text and URLs from the current page.",
            },
            {
                "task": "safe_form_fill",
                "preferred_sequence": [
                    "form_inspect",
                    "form_fill_preview",
                    "explicit confirmation",
                    "element_click",
                ],
                "use_when": "Need to prefill controls without submitting or leaking field values.",
            },
            {
                "task": "network_observation",
                "preferred_sequence": [
                    "network_listen_start",
                    "trigger action",
                    "network_listen_wait",
                    "network_listen_stop",
                ],
                "use_when": "Need observe-only HTTP/XHR/Fetch evidence around a page action.",
            },
        ],
        "default_flow": [
            "browser_open_and_snapshot for navigate plus context",
            "page_snapshot or page_observe",
            "wait_until for dynamic conditions",
            "element_click/element_type or specialized tools",
            "page_observe/page_console_logs for verification",
        ],
        "forms": {
            "flow": ["form_inspect", "form_fill_preview", "explicit confirmation", "element_click"],
            "boundary": "form_fill_preview fills controls but never submits; values are redacted by default.",
        },
        "network": {
            "flow": ["network_listen_start", "trigger action", "network_listen_wait", "network_listen_stop"],
            "boundary": "observation only for HTTP/XHR/Fetch metadata; no interception, mocking, or request mutation.",
        },
        "response_handling": [
            "Prefer structuredContent when available.",
            "Fallback to the first text block under ### JSON_RESULT.",
            "Use error.details.hints for recovery.",
        ],
        "tested": {
            "browser_backed": True,
            "evidence": [
                "browser_open_and_snapshot local fixture",
                "browser_extract_links local fixture",
                "form_fill_preview no-submit redaction fixture",
                "network listener local Fetch/XHR fixture",
                "drissionpage-mcp doctor --launch-browser",
                "ruff, mypy, full pytest, browser integration, 95% coverage gate",
            ],
        },
    }
