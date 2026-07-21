"""Stable error taxonomy and recovery hints for MCP tool responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Union


class ErrorCode(str, Enum):
    """Stable machine-readable tool error codes."""

    BROWSER_START_FAILED = "BROWSER_START_FAILED"
    BROWSER_NOT_INITIALIZED = "BROWSER_NOT_INITIALIZED"
    PAGE_NAVIGATION_FAILED = "PAGE_NAVIGATION_FAILED"
    ELEMENT_NOT_FOUND = "ELEMENT_NOT_FOUND"
    SELECTOR_INVALID = "SELECTOR_INVALID"
    TIMEOUT = "TIMEOUT"
    SCREENSHOT_FAILED = "SCREENSHOT_FAILED"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"
    TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
    MCP_ARGUMENT_INVALID = "MCP_ARGUMENT_INVALID"
    POLICY_DENIED = "POLICY_DENIED"
    UNSUPPORTED_OPERATION = "UNSUPPORTED_OPERATION"
    OPERATION_KEY_CONFLICT = "OPERATION_KEY_CONFLICT"
    OPERATION_IN_FLIGHT = "OPERATION_IN_FLIGHT"
    TASK_LEDGER_FULL = "TASK_LEDGER_FULL"
    PRECONDITION_FAILED = "PRECONDITION_FAILED"


@dataclass
class ToolError:
    """Stable tool error payload."""

    code: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            payload["details"] = self.details
        return payload


def classify_error(exc: Exception, tool_name: str = "") -> ErrorCode:
    """Best-effort mapping from runtime exceptions to stable tool error codes."""

    exc_code = getattr(exc, "code", None)
    if isinstance(exc_code, ErrorCode):
        return exc_code
    if isinstance(exc_code, str):
        try:
            return ErrorCode(exc_code)
        except ValueError:
            pass
    if isinstance(exc, TimeoutError):
        return ErrorCode.TIMEOUT

    text = str(exc).lower()
    tool = tool_name.lower()
    rules = (
        (
            "selector" in text and ("invalid" in text or "syntax" in text),
            ErrorCode.SELECTOR_INVALID,
        ),
        (
            "element not found" in text or "noneelement" in text,
            ErrorCode.ELEMENT_NOT_FOUND,
        ),
        ("timeout" in text or "timed out" in text, ErrorCode.TIMEOUT),
        (
            "no active tab" in text or "browser context not initialized" in text,
            ErrorCode.BROWSER_NOT_INITIALIZED,
        ),
        (
            "navigation failed" in text
            or "failed to navigate" in text
            or tool.startswith("page_navigate"),
            ErrorCode.PAGE_NAVIGATION_FAILED,
        ),
        (
            "screenshot" in text or tool == "page_screenshot",
            ErrorCode.SCREENSHOT_FAILED,
        ),
        (
            "policy" in text or "allowlist" in text or "blocklist" in text,
            ErrorCode.POLICY_DENIED,
        ),
        (
            "unsupported" in text or "not supported" in text or "unavailable" in text,
            ErrorCode.UNSUPPORTED_OPERATION,
        ),
        (
            "browser" in text
            and ("start" in text or "initialize" in text or "launch" in text),
            ErrorCode.BROWSER_START_FAILED,
        ),
    )
    return next((code for matches, code in rules if matches), ErrorCode.UNKNOWN_ERROR)


HintSpec = tuple[str, str, str, str, str]
HintBuilder = Callable[[str, str, str], list[HintSpec]]

_HINT_TABLE = """
ELEMENT|inspect_page_snapshot|Inspect the bounded page outline and recommended selectors.|page_snapshot||
ELEMENT|find_similar_elements|Search repeated candidates with a broader CSS/XPath selector.|element_find_all||
ELEMENT|wait_for_element|Wait for the selector before retrying the action.|wait_for_element||
ELEMENT|check_iframe_or_dynamic_content|If the element is inside an iframe, shadow root, or delayed UI state, inspect that context first.|||
SELECTOR_EXTRA|check_selector_syntax|Use bare CSS selectors, XPath-looking strings, or explicit css:/xpath:/text:/tag:/@attr locators.|||
TIMEOUT|increase_timeout|Retry with a larger timeout if the page is expected to load slowly.|||
TIMEOUT|inspect_current_page|Check the current URL and page outline before retrying.|page_get_url||
TIMEOUT|inspect_page_snapshot|Use the bounded page snapshot to confirm the expected content exists.|page_snapshot||
TIMEOUT_ELEMENT|wait_for_element|Wait for a more specific selector before the next action.|wait_for_element||
TIMEOUT_UNTIL|wait_until|Use a condition-specific wait for dynamic UI state such as clickable, hidden, text, or URL changes.|wait_until||
POLICY|review_navigation_allowlist|Check whether DP_MCP_NAV_ALLOWLIST or DP_MCP_NAV_BLOCKLIST rejected the target URL.|||DP_MCP_NAV_ALLOWLIST
POLICY|review_private_network_policy|If navigating to localhost/private IPs, check DP_MCP_BLOCK_PRIVATE_NETWORK.|||DP_MCP_BLOCK_PRIVATE_NETWORK
POLICY_UPLOAD|configure_upload_root|Upload files from DP_MCP_UPLOAD_ROOT and pass only paths inside that directory.|||DP_MCP_UPLOAD_ROOT
POLICY_SCREENSHOT|configure_screenshot_root|Save screenshots under DP_MCP_SCREENSHOT_ROOT or choose an allowed path.|||DP_MCP_SCREENSHOT_ROOT
UNSUPPORTED|check_drissionpage_version|Use a supported DrissionPage 4.x release that exposes this browser API.||python -m drissionpage_mcp.cli doctor|
UNSUPPORTED|run_doctor|Run diagnostics from the same environment as the MCP client.||drissionpage-mcp doctor --launch-browser|
UNSUPPORTED|fallback_to_primitives|Use lower-level page or element tools when the workflow helper is unavailable.|||
UNSUPPORTED_LISTENER|verify_listener_api|Check that the current DrissionPage 4.x tab exposes tab.listen.start/wait/stop.|||
BROWSER_START_FAILED|run_doctor|Run browser diagnostics from the same environment as the MCP client.||drissionpage-mcp doctor --launch-browser|
BROWSER_START_FAILED|configure_browser_path|Set an explicit Chrome/Chromium executable path when GUI clients cannot see shell PATH.|||CHROME_PATH
BROWSER_START_FAILED|enable_headless|Enable headless browser mode for remote, CI, or container environments.|||DP_HEADLESS
BROWSER_START_FAILED|disable_sandbox_if_containerized|Use no-sandbox only when the browser runs inside a restricted container.|||DP_NO_SANDBOX
SCREENSHOT_FAILED|confirm_active_page|Confirm the browser is still connected and a page is open.|page_get_url||
SCREENSHOT_FAILED|try_viewport_screenshot|Retry a viewport screenshot before requesting a full-page screenshot.|page_screenshot||
SCREENSHOT_FAILED|check_screenshot_path|If saving to disk, use a writable absolute path or configure DP_MCP_SCREENSHOT_ROOT.|||DP_MCP_SCREENSHOT_ROOT
PAGE_NAVIGATION_FAILED|check_url|Verify the URL is reachable from the MCP client environment.|||
PAGE_NAVIGATION_FAILED|run_doctor|Run browser diagnostics if navigation failed because the browser could not start.||drissionpage-mcp doctor --launch-browser|
PAGE_NAVIGATION_FAILED|inspect_current_page|If a previous page is still open, inspect the current URL before retrying.|page_get_url||
BROWSER_NOT_INITIALIZED|navigate_first|Open a page with the workflow helper when you need immediate page context; use page_navigate only for navigation-only retries.|browser_open_and_snapshot||
BROWSER_NOT_INITIALIZED|navigation_only_retry|Use page_navigate when you only need to navigate and will inspect the page separately.|page_navigate||
MCP_ARGUMENT_INVALID|check_input_schema|Use exact snake_case argument names from the tool input schema.|||
MCP_ARGUMENT_INVALID|inspect_tools_catalog|Read drissionpage://tools/catalog for compact required/default field guidance or tools/list for the complete JSON Schema before retrying.|||
TOOL_NOT_FOUND|list_available_tools|Call tools/list and use one of the public tool names.|||
TOOL_NOT_FOUND|read_model_usage_guide|Read drissionpage://guide/model-usage to choose workflow helpers before low-level primitives.|||
"""


def _parse_hint_table(table: str) -> dict[str, tuple[HintSpec, ...]]:
    groups: dict[str, list[HintSpec]] = {}
    for row in table.strip().splitlines():
        category, action, message, tool, command, env = row.split("|", 5)
        groups.setdefault(category, []).append((action, message, tool, command, env))
    return {category: tuple(specs) for category, specs in groups.items()}


_HINT_SPECS = _parse_hint_table(_HINT_TABLE)


def recovery_hints(
    code: Union[str, ErrorCode],
    *,
    tool_name: str = "",
    message: str = "",
) -> List[Dict[str, str]]:
    """Return deterministic, machine-readable recovery hints for common failures."""

    code_value = code.value if isinstance(code, ErrorCode) else str(code)
    builder = _DYNAMIC_HINT_BUILDERS.get(code_value)
    specs = (
        builder(code_value, tool_name.lower(), message.lower())
        if builder is not None
        else list(_HINT_SPECS.get(code_value, ()))
    )
    return _materialize_hints(specs)


def _element_hints(code: str, _tool: str, _message: str) -> list[HintSpec]:
    specs = list(_HINT_SPECS["ELEMENT"])
    if code == ErrorCode.SELECTOR_INVALID.value:
        specs[0:0] = _HINT_SPECS["SELECTOR_EXTRA"]
    return specs


def _timeout_hints(_code: str, tool: str, _message: str) -> list[HintSpec]:
    specs = list(_HINT_SPECS["TIMEOUT"])
    if not tool.startswith("wait_for_element"):
        specs += _HINT_SPECS["TIMEOUT_ELEMENT"]
    if tool != "wait_until":
        specs += _HINT_SPECS["TIMEOUT_UNTIL"]
    return specs


def _policy_hints(_code: str, _tool: str, message: str) -> list[HintSpec]:
    specs = list(_HINT_SPECS["POLICY"])
    if "upload" in message or "file" in message:
        specs[0:0] = _HINT_SPECS["POLICY_UPLOAD"]
    if "screenshot" in message or "path" in message:
        specs[0:0] = _HINT_SPECS["POLICY_SCREENSHOT"]
    return specs


def _unsupported_hints(_code: str, tool: str, message: str) -> list[HintSpec]:
    specs = list(_HINT_SPECS["UNSUPPORTED"])
    if "network" in tool or "listener" in message:
        specs[0:0] = _HINT_SPECS["UNSUPPORTED_LISTENER"]
    return specs


_DYNAMIC_HINT_BUILDERS: dict[str, HintBuilder] = {
    ErrorCode.ELEMENT_NOT_FOUND.value: _element_hints,
    ErrorCode.SELECTOR_INVALID.value: _element_hints,
    ErrorCode.TIMEOUT.value: _timeout_hints,
    ErrorCode.POLICY_DENIED.value: _policy_hints,
    ErrorCode.UNSUPPORTED_OPERATION.value: _unsupported_hints,
}


def _materialize_hints(specs: list[HintSpec]) -> List[Dict[str, str]]:
    return [
        _hint(action, message, tool=tool, command=command, env=env)
        for action, message, tool, command, env in specs
    ]


def _hint(
    action: str,
    message: str,
    *,
    tool: str = "",
    command: str = "",
    env: str = "",
) -> Dict[str, str]:
    hint = {"action": action, "message": message}
    if tool:
        hint["tool"] = tool
    if command:
        hint["command"] = command
    if env:
        hint["env"] = env
    return hint
