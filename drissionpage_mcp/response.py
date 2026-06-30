"""Response handling for DrissionPage MCP tools."""

import base64
import json
import logging
import struct
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union, cast

from mcp.types import ImageContent, TextContent

logger = logging.getLogger(__name__)

JSON_RESULT_SENTINEL = "### JSON_RESULT"


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


@dataclass
class ToolResult:
    """Stable tool result payload for MCP structuredContent and TextContent mirror."""

    ok: bool
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[ToolError] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "ok": self.ok,
            "message": self.message,
        }
        if self.ok or self.data:
            payload["data"] = self.data
        if self.error is not None:
            payload["error"] = self.error.to_dict()
        return payload

    @classmethod
    def success(cls, message: str = "", **data: Any) -> "ToolResult":
        return cls(ok=True, message=message, data=data)

    @classmethod
    def failure(
        cls,
        code: Union[str, ErrorCode],
        message: str,
        **details: Any,
    ) -> "ToolResult":
        code_value = code.value if isinstance(code, ErrorCode) else str(code)
        return cls(
            ok=False,
            message=message,
            error=ToolError(code=code_value, message=message, details=details),
        )


def _json_text(payload: Dict[str, Any]) -> TextContent:
    """Build the sentinel TextContent mirror for structured tool results."""

    body = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return TextContent(
        type="text", text=f"{JSON_RESULT_SENTINEL}\n```json\n{body}\n```"
    )


def classify_error(exc: Exception, tool_name: str = "") -> ErrorCode:
    """Best-effort mapping from runtime exceptions to stable tool error codes."""

    if getattr(exc, "code", None) == ErrorCode.POLICY_DENIED:
        return ErrorCode.POLICY_DENIED

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
                "Open a page before calling page or element inspection tools.",
                tool="page_navigate",
            )
        ]

    if code_value == ErrorCode.MCP_ARGUMENT_INVALID.value:
        return [
            _hint(
                "check_input_schema",
                "Use exact snake_case argument names from the tool input schema.",
            )
        ]

    if code_value == ErrorCode.TOOL_NOT_FOUND.value:
        return [
            _hint(
                "list_available_tools",
                "Call tools/list and use one of the public tool names.",
            )
        ]

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


def tool_data_schema_title(tool_name: str) -> str:
    """Return the public data schema title for a tool."""

    return cast(str, TOOL_DATA_SCHEMAS.get(tool_name, _GENERIC_DATA_SCHEMA)["title"])


def tool_result_output_schema(tool_name: str = "") -> Dict[str, Any]:
    """Return the MCP outputSchema for a tool-specific result envelope."""

    data_schema = TOOL_DATA_SCHEMAS.get(tool_name, _GENERIC_DATA_SCHEMA)
    return {
        "type": "object",
        "oneOf": [
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["ok", "message", "data"],
                "properties": {
                    "ok": {"const": True},
                    "message": {"type": "string"},
                    "data": data_schema,
                },
            },
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["ok", "message", "error"],
                "properties": {
                    "ok": {"const": False},
                    "message": {"type": "string"},
                    "error": ERROR_SCHEMA,
                    "data": {"type": "object", "additionalProperties": True},
                },
            },
        ],
    }


def _data_schema(
    title: str,
    properties: Dict[str, Any],
    required: Sequence[str],
) -> Dict[str, Any]:
    return {
        "title": title,
        "type": "object",
        "additionalProperties": False,
        "required": list(required),
        "properties": properties,
    }


STRING = {"type": "string"}
BOOLEAN = {"type": "boolean"}
INTEGER = {"type": "integer"}
NUMBER = {"type": "number"}
ANY_JSON: Dict[str, Any] = {}
SELECTOR_METADATA_SCHEMA = {
    "selector": STRING,
    "locator": STRING,
    "selector_strategy": STRING,
    "selector_normalized": BOOLEAN,
}
SELECTOR_METADATA_REQUIRED = [
    "selector",
    "locator",
    "selector_strategy",
    "selector_normalized",
]

ERROR_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["code", "message"],
    "properties": {
        "code": {"type": "string"},
        "message": {"type": "string"},
        "details": {"type": "object", "additionalProperties": True},
    },
}

SCREENSHOT_METADATA_SCHEMA = _data_schema(
    "ScreenshotMetadata",
    {
        "mime_type": STRING,
        "inline": BOOLEAN,
        "encoding": STRING,
        "path": STRING,
        "full_page": BOOLEAN,
        "bytes": INTEGER,
        "width": INTEGER,
        "height": INTEGER,
    },
    ["mime_type"],
)

ELEMENT_INFO_SCHEMA = _data_schema(
    "ElementInfo",
    {
        "found": {"const": True},
        **SELECTOR_METADATA_SCHEMA,
        "text": STRING,
        "tag": STRING,
        "html": STRING,
        "visible": BOOLEAN,
    },
    ["found", *SELECTOR_METADATA_REQUIRED, "text"],
)

ELEMENT_ATTRIBUTES_SCHEMA = {
    "type": "object",
    "additionalProperties": {"type": ["string", "null"]},
}

OUTLINE_ELEMENT_SCHEMA = _data_schema(
    "OutlineElement",
    {
        "index": INTEGER,
        "tag": STRING,
        "text": STRING,
        "selector": STRING,
        "attributes": ELEMENT_ATTRIBUTES_SCHEMA,
        "html": STRING,
        "href": STRING,
        "method": STRING,
        "action": STRING,
    },
    ["index", "tag", "text", "selector", "attributes"],
)

OUTLINE_COUNTS_SCHEMA = {
    "type": "object",
    "additionalProperties": INTEGER,
}

FORM_FIELD_OPTION_SCHEMA = _data_schema(
    "FormFieldOption",
    {
        "text": STRING,
        "value": STRING,
        "selected": BOOLEAN,
    },
    ["text", "value", "selected"],
)

FORM_FIELD_SCHEMA = _data_schema(
    "FormField",
    {
        "index": INTEGER,
        "tag": STRING,
        "type": STRING,
        "name": STRING,
        "label": STRING,
        "selector": STRING,
        "placeholder": STRING,
        "required": BOOLEAN,
        "disabled": BOOLEAN,
        "readonly": BOOLEAN,
        "checked": BOOLEAN,
        "value": {"type": ["string", "null"]},
        "attributes": ELEMENT_ATTRIBUTES_SCHEMA,
        "options": {"type": "array", "items": FORM_FIELD_OPTION_SCHEMA},
    },
    [
        "index",
        "tag",
        "type",
        "name",
        "label",
        "selector",
        "placeholder",
        "required",
        "disabled",
        "readonly",
        "checked",
        "value",
        "attributes",
        "options",
    ],
)

FORM_SUMMARY_SCHEMA = _data_schema(
    "FormSummary",
    {
        "index": INTEGER,
        "selector": STRING,
        "id": STRING,
        "name": STRING,
        "method": STRING,
        "action": STRING,
        "text": STRING,
        "fields": {"type": "array", "items": FORM_FIELD_SCHEMA},
    },
    ["index", "selector", "id", "name", "method", "action", "text", "fields"],
)

FORM_INSPECT_LIMITS_SCHEMA = _data_schema(
    "FormInspectLimits",
    {
        "max_forms": INTEGER,
        "max_fields_per_form": INTEGER,
    },
    ["max_forms", "max_fields_per_form"],
)

FORM_INSPECT_TRUNCATION_SCHEMA = _data_schema(
    "FormInspectTruncation",
    {
        "forms": BOOLEAN,
        "fields": BOOLEAN,
    },
    ["forms", "fields"],
)

PAGE_SNAPSHOT_TRUNCATION_SCHEMA = _data_schema(
    "PageSnapshotTruncation",
    {
        "text": BOOLEAN,
        "elements": BOOLEAN,
        "returned_elements": INTEGER,
    },
    ["text", "elements", "returned_elements"],
)

PAGE_SNAPSHOT_LIMITS_SCHEMA = _data_schema(
    "PageSnapshotLimits",
    {
        "max_elements": INTEGER,
        "max_text_chars": INTEGER,
    },
    ["max_elements", "max_text_chars"],
)

META_SCHEMA = _data_schema(
    "ResponseMeta",
    {
        "approx_tokens": INTEGER,
        "json_chars": INTEGER,
        "truncated": BOOLEAN,
    },
    ["approx_tokens", "json_chars", "truncated"],
)

TAB_SUMMARY_SCHEMA = _data_schema(
    "TabSummary",
    {
        "id": STRING,
        "native_id": STRING,
        "url": STRING,
        "title": STRING,
        "active": BOOLEAN,
        "connected": BOOLEAN,
    },
    ["id", "native_id", "url", "title", "active", "connected"],
)

_GENERIC_DATA_SCHEMA = _data_schema(
    "GenericToolData",
    {},
    [],
)

TOOL_DATA_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "page_navigate": _data_schema(
        "PageNavigateData",
        {"url": STRING, "final_url": STRING, "new_tab": BOOLEAN, "tab_id": STRING},
        ["url", "final_url", "new_tab", "tab_id"],
    ),
    "tab_list": _data_schema(
        "TabListData",
        {
            "tabs": {"type": "array", "items": TAB_SUMMARY_SCHEMA},
            "count": INTEGER,
            "active_tab_id": STRING,
        },
        ["tabs", "count", "active_tab_id"],
    ),
    "tab_switch": _data_schema(
        "TabSwitchData",
        {"tab": TAB_SUMMARY_SCHEMA, "tab_id": STRING, "url": STRING},
        ["tab", "tab_id", "url"],
    ),
    "tab_close": _data_schema(
        "TabCloseData",
        {
            "closed": {"const": True},
            "tab_id": STRING,
            "remaining_count": INTEGER,
            "active_tab_id": STRING,
        },
        ["closed", "tab_id", "remaining_count", "active_tab_id"],
    ),
    "page_go_back": _data_schema("PageGoBackData", {"url": STRING}, ["url"]),
    "page_go_forward": _data_schema("PageGoForwardData", {"url": STRING}, ["url"]),
    "page_refresh": _data_schema("PageRefreshData", {"url": STRING}, ["url"]),
    "page_resize": _data_schema(
        "PageResizeData",
        {"width": INTEGER, "height": INTEGER},
        ["width", "height"],
    ),
    "page_screenshot": _data_schema(
        "PageScreenshotData",
        {"screenshot": SCREENSHOT_METADATA_SCHEMA},
        ["screenshot"],
    ),
    "page_snapshot": _data_schema(
        "PageSnapshotData",
        {
            "url": STRING,
            "title": STRING,
            "text_excerpt": STRING,
            "headings": {"type": "array", "items": OUTLINE_ELEMENT_SCHEMA},
            "links": {"type": "array", "items": OUTLINE_ELEMENT_SCHEMA},
            "buttons": {"type": "array", "items": OUTLINE_ELEMENT_SCHEMA},
            "inputs": {"type": "array", "items": OUTLINE_ELEMENT_SCHEMA},
            "forms": {"type": "array", "items": OUTLINE_ELEMENT_SCHEMA},
            "counts": OUTLINE_COUNTS_SCHEMA,
            "truncated": PAGE_SNAPSHOT_TRUNCATION_SCHEMA,
            "limits": PAGE_SNAPSHOT_LIMITS_SCHEMA,
            "meta": META_SCHEMA,
        },
        [
            "url",
            "title",
            "text_excerpt",
            "headings",
            "links",
            "buttons",
            "inputs",
            "forms",
            "counts",
            "truncated",
            "limits",
            "meta",
        ],
    ),
    "page_click_xy": _data_schema(
        "PageClickXYData",
        {"x": INTEGER, "y": INTEGER, "element": STRING, "url": STRING},
        ["x", "y", "element", "url"],
    ),
    "page_close": _data_schema(
        "PageCloseData",
        {"closed": {"const": True}},
        ["closed"],
    ),
    "page_get_url": _data_schema("PageGetUrlData", {"url": STRING}, ["url"]),
    "element_find": _data_schema(
        "ElementFindData",
        {"element": ELEMENT_INFO_SCHEMA},
        ["element"],
    ),
    "element_find_all": _data_schema(
        "ElementFindAllData",
        {
            **SELECTOR_METADATA_SCHEMA,
            "count": INTEGER,
            "returned": INTEGER,
            "limit": INTEGER,
            "truncated": BOOLEAN,
            "elements": {"type": "array", "items": OUTLINE_ELEMENT_SCHEMA},
            "meta": META_SCHEMA,
        },
        [
            *SELECTOR_METADATA_REQUIRED,
            "count",
            "returned",
            "limit",
            "truncated",
            "elements",
            "meta",
        ],
    ),
    "form_inspect": _data_schema(
        "FormInspectData",
        {
            "selector": STRING,
            "include_values": BOOLEAN,
            "count": INTEGER,
            "returned": INTEGER,
            "limits": FORM_INSPECT_LIMITS_SCHEMA,
            "truncated": FORM_INSPECT_TRUNCATION_SCHEMA,
            "forms": {"type": "array", "items": FORM_SUMMARY_SCHEMA},
            "meta": META_SCHEMA,
        },
        [
            "selector",
            "include_values",
            "count",
            "returned",
            "limits",
            "truncated",
            "forms",
            "meta",
        ],
    ),
    "element_click": _data_schema(
        "ElementClickData",
        {**SELECTOR_METADATA_SCHEMA, "url": STRING},
        [*SELECTOR_METADATA_REQUIRED, "url"],
    ),
    "element_type": _data_schema(
        "ElementTypeData",
        {
            **SELECTOR_METADATA_SCHEMA,
            "typed": {"const": True},
            "cleared": BOOLEAN,
        },
        [*SELECTOR_METADATA_REQUIRED, "typed", "cleared"],
    ),
    "element_get_text": _data_schema(
        "ElementGetTextData",
        {"text": STRING, **SELECTOR_METADATA_SCHEMA},
        ["text", *SELECTOR_METADATA_REQUIRED],
    ),
    "element_get_attribute": _data_schema(
        "ElementGetAttributeData",
        {
            **SELECTOR_METADATA_SCHEMA,
            "attribute": STRING,
            "value": {"type": ["string", "null"]},
        },
        [*SELECTOR_METADATA_REQUIRED, "attribute", "value"],
    ),
    "element_get_property": _data_schema(
        "ElementGetPropertyData",
        {**SELECTOR_METADATA_SCHEMA, "property": STRING, "value": ANY_JSON},
        [*SELECTOR_METADATA_REQUIRED, "property", "value"],
    ),
    "element_get_html": _data_schema(
        "ElementGetHtmlData",
        {"html": STRING, **SELECTOR_METADATA_SCHEMA},
        ["html", *SELECTOR_METADATA_REQUIRED],
    ),
    "wait_for_element": _data_schema(
        "WaitForElementData",
        {**SELECTOR_METADATA_SCHEMA, "found": {"const": True}, "timeout": NUMBER},
        [*SELECTOR_METADATA_REQUIRED, "found", "timeout"],
    ),
    "wait_for_url": _data_schema(
        "WaitForUrlData",
        {
            "url_pattern": STRING,
            "matched": {"const": True},
            "url": STRING,
            "timeout": NUMBER,
        },
        ["url_pattern", "matched", "url", "timeout"],
    ),
    "wait_time": _data_schema(
        "WaitTimeData",
        {"waited_seconds": NUMBER},
        ["waited_seconds"],
    ),
}


class ToolResponse:
    """Handles responses from DrissionPage MCP tools."""

    def __init__(self):
        self._content: List[Union[TextContent, ImageContent]] = []
        self._code_snippets: List[str] = []
        self._include_snapshot = False
        self._is_error = False
        self._tool_result: Optional[ToolResult] = None

    def add_text(self, text: str) -> None:
        """Add text content to the response."""
        self._content.append(TextContent(type="text", text=text))

    def add_error(
        self,
        error: str,
        code: Optional[Union[str, ErrorCode]] = None,
        **details: Any,
    ) -> None:
        """Add error content to the response."""
        self._is_error = True
        error_code = code if code is not None else classify_error(Exception(error))
        error_details = dict(details)
        if "hints" not in error_details:
            hints = recovery_hints(
                error_code,
                tool_name=str(error_details.get("tool_name", "")),
                message=error,
            )
            if hints:
                error_details["hints"] = hints
        self._tool_result = ToolResult.failure(error_code, error, **error_details)
        error_text = f"### Error\n{error}"
        self._content.append(TextContent(type="text", text=error_text))

    def add_result(self, result: str, **data: Any) -> None:
        """Add result content to the response."""
        self._tool_result = ToolResult.success(result, **data)
        result_text = f"### Result\n{result}"
        self._content.append(TextContent(type="text", text=result_text))

    def set_tool_result(self, result: ToolResult) -> None:
        """Set an explicit structured result payload."""
        self._tool_result = result
        self._is_error = not result.ok

    def add_code(self, code: str) -> None:
        """Add code snippet to the response."""
        self._code_snippets.append(code)

    def add_image(
        self, image_data: Union[str, bytes], mime_type: str = "image/png"
    ) -> None:
        """Add image content to the response."""
        if isinstance(image_data, bytes):
            image_data = base64.b64encode(image_data).decode()
        elif not isinstance(image_data, str):
            raise ValueError("Image data must be string or bytes")

        self._content.append(
            ImageContent(type="image", data=image_data, mimeType=mime_type)
        )

    def add_screenshot(
        self,
        screenshot_data: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add screenshot image content plus stable JSON metadata."""
        self.add_image(screenshot_data, "image/png")
        self.add_text("Screenshot taken.")
        if self._tool_result is None:
            screenshot_metadata = build_screenshot_metadata(screenshot_data)
            if metadata:
                screenshot_metadata.update(metadata)
            self._tool_result = ToolResult.success(
                "Screenshot taken.",
                screenshot=screenshot_metadata,
            )

    def set_include_snapshot(self, include: bool = True) -> None:
        """Set whether to include a snapshot in the response."""
        self._include_snapshot = include

    def get_structured_content(self) -> Dict[str, Any]:
        """Return the stable structuredContent payload."""
        if self._tool_result is None:
            if self._is_error:
                self._tool_result = ToolResult.failure(
                    ErrorCode.UNKNOWN_ERROR,
                    "Unknown error occurred.",
                )
            else:
                self._tool_result = ToolResult.success(
                    "Operation completed successfully."
                )
        return self._tool_result.to_dict()

    def get_content(self) -> Sequence[Union[TextContent, ImageContent]]:
        """Get all response content with the machine-readable TextContent mirror first."""
        content = list(self._content)

        # Add code snippets if any. Do not mutate internal content here because
        # callers/tests may inspect the same response more than once.
        if self._code_snippets:
            code_text = (
                "### Code\n```python\n" + "\n".join(self._code_snippets) + "\n```"
            )
            content.insert(0, TextContent(type="text", text=code_text))

        # Add default content if empty.
        if not content:
            if self._is_error:
                content.append(
                    TextContent(type="text", text="### Error\nUnknown error occurred.")
                )
            else:
                content.append(
                    TextContent(
                        type="text",
                        text="### Result\nOperation completed successfully.",
                    )
                )

        content.insert(0, _json_text(self.get_structured_content()))
        return content

    def is_error(self) -> bool:
        """Check if the response contains an error."""
        return self._is_error

    def should_include_snapshot(self) -> bool:
        """Check if a snapshot should be included."""
        return self._include_snapshot

    def clear(self) -> None:
        """Clear all response content."""
        self._content.clear()
        self._code_snippets.clear()
        self._include_snapshot = False
        self._is_error = False
        self._tool_result = None


def build_screenshot_metadata(
    image_data: Optional[Union[str, bytes]] = None,
    *,
    path: str = "",
    full_page: Optional[bool] = None,
    inline: Optional[bool] = None,
) -> Dict[str, Any]:
    """Return compact metadata for an MCP screenshot result."""

    raw = _image_bytes(image_data) if image_data is not None else None
    if raw is None and path:
        raw = _path_bytes(path)
    width, height = _png_dimensions(raw)

    metadata: Dict[str, Any] = {
        "mime_type": "image/png",
    }
    if inline is not None:
        metadata["inline"] = inline
    elif image_data is not None:
        metadata["inline"] = True
    if image_data is not None and metadata.get("inline", True):
        metadata["encoding"] = "base64"
    if path:
        metadata["path"] = path
    if full_page is not None:
        metadata["full_page"] = full_page
    if raw is not None:
        metadata["bytes"] = len(raw)
    if width is not None and height is not None:
        metadata["width"] = width
        metadata["height"] = height
    return metadata


def _image_bytes(image_data: Union[str, bytes]) -> Optional[bytes]:
    if isinstance(image_data, bytes):
        return image_data
    try:
        return base64.b64decode(image_data, validate=True)
    except Exception:
        logger.debug("Could not decode screenshot base64 metadata", exc_info=True)
        return None


def _path_bytes(path: str) -> Optional[bytes]:
    try:
        return Path(path).read_bytes()
    except OSError:
        logger.debug("Could not read screenshot file metadata: %s", path, exc_info=True)
        return None


def _png_dimensions(raw: Optional[bytes]) -> Tuple[Optional[int], Optional[int]]:
    if not raw or len(raw) < 24:
        return None, None
    if raw[:8] != b"\x89PNG\r\n\x1a\n" or raw[12:16] != b"IHDR":
        return None, None
    width, height = struct.unpack(">II", raw[16:24])
    return width, height
