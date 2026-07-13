"""Model-facing guidance exposed through MCP initialization, resources, and prompts."""

from __future__ import annotations

from typing import Any

from . import __version__

SUPPORTED_DRISSIONPAGE_RANGE = "DrissionPage>=4.1.1.4,<5"
MODEL_USAGE_RESOURCE_URI = "drissionpage://guide/model-usage"
MODEL_USAGE_PROMPT_NAME = "drissionpage_mcp_usage_playbook"

VISION_DECISION_RULES: tuple[str, ...] = (
    "Use element_find/element_click when a reliable selector or accessibility-backed element is available.",
    "Use page_pointer_move when the target is visually identifiable and the goal is hover, reveal, canvas positioning, or inspection without clicking.",
    "Use page_click_xy when the target is visually identifiable and activation requires a click but selector-based interaction is unavailable or unreliable.",
    "Use page_pointer_drag only for a visually identified drag from one viewport point to another; keep press/move/release in this single failure-safe call.",
    "Use a non-full-page page_screenshot for visual coordinates; pointer coordinate tools expect viewport CSS pixels, not full-page document coordinates or resized image pixels.",
    "If the MCP host resized the screenshot, map image coordinates back to the original viewport using page_evaluate to read window.innerWidth and window.innerHeight.",
    "After every visual action, verify a bounded observable state change before retrying; do not repeat coordinate actions blindly.",
)

POINTER_PROFILE_GUIDANCE: dict[str, str] = {
    "natural": "Default for vision-guided UI clicks; uses a curved, eased, physically timed pointer action chain.",
    "precise": "Use for small or tightly packed ordinary UI targets where reduced jitter is preferable.",
    "direct": "Use only when immediate deterministic coordinate movement is explicitly required; it is not the default visual interaction profile.",
}

VISION_VERIFICATION_OPTIONS: tuple[str, ...] = (
    "element_get_property or element_get_text when a selector becomes available",
    "page_observe for bounded visible-state changes",
    "wait_until for dynamic element, text, or URL conditions",
    "page_screenshot for visual-only state confirmation",
)

VISION_RECOVERY_RULES: tuple[str, ...] = (
    "If the target moved or the page changed, take a fresh viewport screenshot and identify new coordinates.",
    "If the pointer action produced no observable change, inspect the page state before one bounded retry; do not reuse stale coordinates repeatedly.",
    "If coordinates appear offset, check screenshot resizing, browser viewport dimensions, page zoom, and full_page usage before retrying.",
    "If a reliable selector is discovered, switch back to element tools instead of continuing coordinate interaction.",
)


def server_instructions(version: str = __version__) -> str:
    """Return compact MCP initialization instructions for connected models."""

    return f"""DrissionPage MCP {version} provides structured and vision-guided browser automation for DrissionPage 4.x.
Compatibility: use {SUPPORTED_DRISSIONPAGE_RANGE}; do not assume DrissionPage 5 beta/internal builds are supported.
Discovery: when tool choice or arguments are uncertain, read drissionpage://guide/model-usage for workflow decisions and drissionpage://tools/catalog for compact input guidance; use tools/list for complete JSON Schemas.
Tool choice: prefer the highest-level matching workflow, then reliable selector-based element tools. Use browser_open_and_snapshot for navigate+inspect, browser_extract_links for link discovery, page_snapshot for more selectors/content, and page_navigate only for navigation without immediate context.
Vision fallback: when no reliable selector exists, use page_screenshot with full_page=false and identify viewport CSS coordinates. Use page_pointer_move with profile=natural for hover/reveal/inspection, page_click_xy when activation requires a click, or page_pointer_drag for one bounded start-to-end drag; then verify a bounded state change. Never pass full-page document coordinates or resized image pixels directly; use page_evaluate viewport dimensions to correct client-side image scaling.
Pointer profiles: natural is the default visual UI profile; precise is for small/tightly packed ordinary controls; direct is only for explicitly immediate deterministic movement. Supply start_x and start_y together only when the pointer origin is known.
Forms: use form_inspect, then form_fill_preview; treat requires_confirmation=true as a hard stop before submit and never echo field secrets.
Autonomous verification workflow: page_detect_challenges performs read-only signal detection; use a fresh viewport screenshot, choose page_pointer_move/page_click_xy/page_click_xy_batch/page_pointer_drag by intent, then page_wait_challenge_result or wait_until for bounded classification and retry with fresh evidence. These are general capabilities for authorized automation and technical exchange; bypassing human-verification systems is not recommended and completion is not guaranteed.
Network: use network_listen_start before the triggering action, network_listen_wait for bounded HTTP/XHR/Fetch metadata, then network_listen_stop; this is observation only, not interception or request mutation.
Recovery: inspect structuredContent.error and follow the first actionable error.details.hints entry. Retry only after new evidence or corrected input; stop and report the repeated blocker when the same failure recurs. After a visual action use element state, page_observe, wait_until, or a fresh page_screenshot. Do not repeat stale coordinate actions blindly; re-observe, correct coordinate mapping, or switch to a discovered selector.
Safety: respect error.details.hints, navigation policy errors, DP_MCP_SCREENSHOT_ROOT for saved screenshots, and DP_MCP_UPLOAD_ROOT for uploads.
Responses: prefer structuredContent; otherwise parse the first text block under ### JSON_RESULT. Legacy alias tools are not public."""


def usage_playbook_text(*, task: str = "", version: str = __version__) -> str:
    """Return a prompt-friendly playbook for using DrissionPage MCP."""

    task_line = f"Task context: {task}\n\n" if task else ""
    decision_rules = "\n".join(
        f"  {index}. {rule}" for index, rule in enumerate(VISION_DECISION_RULES, 1)
    )
    profiles = "\n".join(
        f"  - {name}: {description}"
        for name, description in POINTER_PROFILE_GUIDANCE.items()
    )
    verification = "\n".join(f"  - {item}" for item in VISION_VERIFICATION_OPTIONS)
    recovery = "\n".join(f"  - {item}" for item in VISION_RECOVERY_RULES)
    return f"""Use DrissionPage MCP {version} safely and efficiently.

{task_line}Core rules:
- Target {SUPPORTED_DRISSIONPAGE_RANGE}; DrissionPage 5 beta/internal builds are unsupported.
- If tool choice is uncertain, read drissionpage://guide/model-usage. For argument recovery, read drissionpage://tools/catalog for compact input guidance or tools/list for complete JSON Schemas.
- Prefer workflow helpers before low-level primitives when they match the task.
- For page summary or inspection, start with browser_open_and_snapshot; use page_navigate only when you intentionally do not need immediate page context.
- Use page_snapshot for selectors/content, page_observe after actions, and wait_until for dynamic UI instead of fixed sleeps.
- For forms, call form_inspect then form_fill_preview. Do not submit until explicit user confirmation; do not echo secrets.
- For links, use browser_extract_links with bounded limit and same_origin_only when useful.
- For network observation, call network_listen_start, trigger the page action, call network_listen_wait, then network_listen_stop. This is observation only.

Vision interaction decision rules:
{decision_rules}

Pointer profile selection:
{profiles}

Verification options:
{verification}

Recovery rules:
{recovery}

Recovery loop:
- Read structuredContent.error and follow the first actionable error.details.hints entry.
- Retry only after correcting input or collecting changed page evidence.
- If the same failure repeats, stop and report the blocker instead of looping.

Prefer structuredContent; otherwise parse ### JSON_RESULT.
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
        "discovery": {
            "workflow_guide": "drissionpage://guide/model-usage",
            "compact_tool_contracts": "drissionpage://tools/catalog",
            "complete_tool_schemas": "tools/list",
            "session_context": [
                "drissionpage://session/summary",
                "drissionpage://page/current",
            ],
        },
        "tool_selection": {
            "default": "workflow helper or reliable selector-based element tool",
            "vision_fallback": "page_pointer_move for visual hover/reveal, page_click_xy for visual activation, or page_pointer_drag for a bounded visual drag when no reliable selector exists",
            "rules": list(VISION_DECISION_RULES),
        },
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
                "task": "vision_guided_interaction",
                "preferred_sequence": [
                    "prefer element_find/element_click when reliable",
                    "page_screenshot full_page=false",
                    "identify and map viewport CSS coordinates",
                    "page_pointer_move, page_click_xy, or page_pointer_drag by interaction intent",
                    "bounded state verification",
                ],
                "use_when": "Need to operate a canvas, chart, map, visual editor, responsive control, or other visible UI surface without a reliable selector.",
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
            "selector-based element tools when reliable; otherwise bounded vision interaction",
            "page_observe/page_console_logs or element state for verification",
        ],
        "vision_interaction": {
            "decision_rules": list(VISION_DECISION_RULES),
            "flow": [
                "page_screenshot with full_page=false",
                "identify target in image",
                "map to viewport CSS pixels if the host resized the image",
                "page_pointer_move, page_click_xy, or page_pointer_drag by interaction intent, with profile=natural",
                "verify resulting page state before any retry",
            ],
            "coordinate_contract": {
                "accepted": "viewport CSS pixels",
                "not_accepted_directly": [
                    "full-page document coordinates",
                    "device physical pixels",
                    "coordinates from a resized screenshot without scale correction",
                ],
                "mapping_hint": "Read window.innerWidth/window.innerHeight with page_evaluate and scale image coordinates to the original viewport.",
            },
            "profiles": POINTER_PROFILE_GUIDANCE,
            "start_coordinate_rule": "start_x and start_y are optional but must be supplied together; omit both when the pointer origin is unknown",
            "verification": list(VISION_VERIFICATION_OPTIONS),
            "recovery": list(VISION_RECOVERY_RULES),
            "boundary": "Use for legitimate UI automation, testing, accessibility, and technical research; security or anti-automation challenge completion is not a guaranteed supported capability.",
        },
        "autonomous_visual_orchestration": {
            "flow": [
                "page_detect_challenges",
                "page_screenshot full_page=false",
                "vision analysis",
                "page_pointer_move, page_click_xy, page_click_xy_batch, or page_pointer_drag",
                "page_wait_challenge_result or wait_until",
                "fresh-evidence bounded retry",
            ],
            "boundary": "General autonomous capabilities for authorized automation and technical exchange. Users can compose them independently; bypassing human-verification systems is not recommended and no completion guarantee is made.",
        },
        "forms": {
            "flow": [
                "form_inspect",
                "form_fill_preview",
                "explicit confirmation",
                "element_click",
            ],
            "boundary": "form_fill_preview fills controls but never submits; values are redacted by default.",
        },
        "network": {
            "flow": [
                "network_listen_start",
                "trigger action",
                "network_listen_wait",
                "network_listen_stop",
            ],
            "boundary": "observation only for HTTP/XHR/Fetch metadata; no interception, mocking, or request mutation.",
        },
        "recovery_loop": [
            "Inspect structuredContent.error.",
            "Follow the first actionable error.details.hints entry.",
            "Retry only after corrected input or changed page evidence.",
            "Stop and report the blocker when the same failure repeats.",
        ],
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
                "vision-guided natural pointer click on shared browser fixture",
                "drissionpage-mcp doctor --launch-browser",
                "ruff, mypy, full pytest, browser integration, 95% coverage gate",
            ],
        },
    }
