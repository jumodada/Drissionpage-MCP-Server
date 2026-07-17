"""Stable error taxonomy and recovery hints for MCP tool responses."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Union


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
        payload: Dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
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

    if "selector" in text and ("invalid" in text or "syntax" in text):
        return ErrorCode.SELECTOR_INVALID
    if "element not found" in text or "noneelement" in text:
        return ErrorCode.ELEMENT_NOT_FOUND
    if "timeout" in text or "timed out" in text:
        return ErrorCode.TIMEOUT
    if "no active tab" in text or "browser context not initialized" in text:
        return ErrorCode.BROWSER_NOT_INITIALIZED
    if (
        "navigation failed" in text
        or "failed to navigate" in text
        or tool.startswith("page_navigate")
    ):
        return ErrorCode.PAGE_NAVIGATION_FAILED
    if "screenshot" in text or tool == "page_screenshot":
        return ErrorCode.SCREENSHOT_FAILED
    if "policy" in text or "allowlist" in text or "blocklist" in text:
        return ErrorCode.POLICY_DENIED
    if "unsupported" in text or "not supported" in text or "unavailable" in text:
        return ErrorCode.UNSUPPORTED_OPERATION
    if "browser" in text and (
        "start" in text or "initialize" in text or "launch" in text
    ):
        return ErrorCode.BROWSER_START_FAILED
    return ErrorCode.UNKNOWN_ERROR


def recovery_hints(
    code: Union[str, ErrorCode],
    *,
    tool_name: str = "",
    message: str = "",
) -> List[Dict[str, str]]:
    """Return deterministic, machine-readable recovery hints for common failures."""

    code_value = code.value if isinstance(code, ErrorCode) else str(code)
    lowered_message = message.lower()
    lowered_tool = tool_name.lower()

    if code_value in {
        ErrorCode.ELEMENT_NOT_FOUND.value,
        ErrorCode.SELECTOR_INVALID.value,
    }:
        hints = [
            _hint(
                "inspect_page_snapshot",
                "Inspect the bounded page outline and recommended selectors.",
                tool="page_snapshot",
            ),
            _hint(
                "find_similar_elements",
                "Search repeated candidates with a broader CSS/XPath selector.",
                tool="element_find_all",
            ),
            _hint(
                "wait_for_element",
                "Wait for the selector before retrying the action.",
                tool="wait_for_element",
            ),
            _hint(
                "check_iframe_or_dynamic_content",
                "If the element is inside an iframe, shadow root, or delayed UI state, inspect that context first.",
            ),
        ]
        if code_value == ErrorCode.SELECTOR_INVALID.value:
            hints.insert(
                0,
                _hint(
                    "check_selector_syntax",
                    "Use bare CSS selectors, XPath-looking strings, or explicit css:/xpath:/text:/tag:/@attr locators.",
                ),
            )
        return hints

    if code_value == ErrorCode.TIMEOUT.value:
        hints = [
            _hint(
                "increase_timeout",
                "Retry with a larger timeout if the page is expected to load slowly.",
            ),
            _hint(
                "inspect_current_page",
                "Check the current URL and page outline before retrying.",
                tool="page_get_url",
            ),
            _hint(
                "inspect_page_snapshot",
                "Use the bounded page snapshot to confirm the expected content exists.",
                tool="page_snapshot",
            ),
        ]
        if not lowered_tool.startswith("wait_for_element"):
            hints.append(
                _hint(
                    "wait_for_element",
                    "Wait for a more specific selector before the next action.",
                    tool="wait_for_element",
                )
            )
        if lowered_tool != "wait_until":
            hints.append(
                _hint(
                    "wait_until",
                    "Use a condition-specific wait for dynamic UI state such as clickable, hidden, text, or URL changes.",
                    tool="wait_until",
                )
            )
        return hints

    if code_value == ErrorCode.BROWSER_START_FAILED.value:
        return [
            _hint(
                "run_doctor",
                "Run browser diagnostics from the same environment as the MCP client.",
                command="drissionpage-mcp doctor --launch-browser",
            ),
            _hint(
                "configure_browser_path",
                "Set an explicit Chrome/Chromium executable path when GUI clients cannot see shell PATH.",
                env="CHROME_PATH",
            ),
            _hint(
                "enable_headless",
                "Enable headless browser mode for remote, CI, or container environments.",
                env="DP_HEADLESS",
            ),
            _hint(
                "disable_sandbox_if_containerized",
                "Use no-sandbox only when the browser runs inside a restricted container.",
                env="DP_NO_SANDBOX",
            ),
        ]

    if code_value == ErrorCode.POLICY_DENIED.value:
        hints = [
            _hint(
                "review_navigation_allowlist",
                "Check whether DP_MCP_NAV_ALLOWLIST or DP_MCP_NAV_BLOCKLIST rejected the target URL.",
                env="DP_MCP_NAV_ALLOWLIST",
            ),
            _hint(
                "review_private_network_policy",
                "If navigating to localhost/private IPs, check DP_MCP_BLOCK_PRIVATE_NETWORK.",
                env="DP_MCP_BLOCK_PRIVATE_NETWORK",
            ),
        ]
        if "upload" in lowered_message or "file" in lowered_message:
            hints.insert(
                0,
                _hint(
                    "configure_upload_root",
                    "Upload files from DP_MCP_UPLOAD_ROOT and pass only paths inside that directory.",
                    env="DP_MCP_UPLOAD_ROOT",
                ),
            )
        if "screenshot" in lowered_message or "path" in lowered_message:
            hints.insert(
                0,
                _hint(
                    "configure_screenshot_root",
                    "Save screenshots under DP_MCP_SCREENSHOT_ROOT or choose an allowed path.",
                    env="DP_MCP_SCREENSHOT_ROOT",
                ),
            )
        return hints

    if code_value == ErrorCode.SCREENSHOT_FAILED.value:
        return [
            _hint(
                "confirm_active_page",
                "Confirm the browser is still connected and a page is open.",
                tool="page_get_url",
            ),
            _hint(
                "try_viewport_screenshot",
                "Retry a viewport screenshot before requesting a full-page screenshot.",
                tool="page_screenshot",
            ),
            _hint(
                "check_screenshot_path",
                "If saving to disk, use a writable absolute path or configure DP_MCP_SCREENSHOT_ROOT.",
                env="DP_MCP_SCREENSHOT_ROOT",
            ),
        ]

    if code_value == ErrorCode.PAGE_NAVIGATION_FAILED.value:
        return [
            _hint(
                "check_url",
                "Verify the URL is reachable from the MCP client environment.",
            ),
            _hint(
                "run_doctor",
                "Run browser diagnostics if navigation failed because the browser could not start.",
                command="drissionpage-mcp doctor --launch-browser",
            ),
            _hint(
                "inspect_current_page",
                "If a previous page is still open, inspect the current URL before retrying.",
                tool="page_get_url",
            ),
        ]

    if code_value == ErrorCode.BROWSER_NOT_INITIALIZED.value:
        return [
            _hint(
                "navigate_first",
                "Open a page with the workflow helper when you need immediate page context; use page_navigate only for navigation-only retries.",
                tool="browser_open_and_snapshot",
            ),
            _hint(
                "navigation_only_retry",
                "Use page_navigate when you only need to navigate and will inspect the page separately.",
                tool="page_navigate",
            ),
        ]

    if code_value == ErrorCode.MCP_ARGUMENT_INVALID.value:
        return [
            _hint(
                "check_input_schema",
                "Use exact snake_case argument names from the tool input schema.",
            ),
            _hint(
                "inspect_tools_catalog",
                "Read drissionpage://tools/catalog for compact required/default field guidance or tools/list for the complete JSON Schema before retrying.",
            ),
        ]

    if code_value == ErrorCode.TOOL_NOT_FOUND.value:
        return [
            _hint(
                "list_available_tools",
                "Call tools/list and use one of the public tool names.",
            ),
            _hint(
                "read_model_usage_guide",
                "Read drissionpage://guide/model-usage to choose workflow helpers before low-level primitives.",
            ),
        ]

    if code_value == ErrorCode.UNSUPPORTED_OPERATION.value:
        hints = [
            _hint(
                "check_drissionpage_version",
                "Use a supported DrissionPage 4.x release that exposes this browser API.",
                command="python -m drissionpage_mcp.cli doctor",
            ),
            _hint(
                "run_doctor",
                "Run diagnostics from the same environment as the MCP client.",
                command="drissionpage-mcp doctor --launch-browser",
            ),
            _hint(
                "fallback_to_primitives",
                "Use lower-level page or element tools when the workflow helper is unavailable.",
            ),
        ]
        if "network" in lowered_tool or "listener" in lowered_message:
            hints.insert(
                0,
                _hint(
                    "verify_listener_api",
                    "Check that the current DrissionPage 4.x tab exposes tab.listen.start/wait/stop.",
                ),
            )
        return hints

    return []


def _hint(
    action: str,
    message: str,
    *,
    tool: str = "",
    command: str = "",
    env: str = "",
) -> Dict[str, str]:
    hint = {
        "action": action,
        "message": message,
    }
    if tool:
        hint["tool"] = tool
    if command:
        hint["command"] = command
    if env:
        hint["env"] = env
    return hint
