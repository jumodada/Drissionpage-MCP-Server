"""Response handling for DrissionPage MCP tools."""

import base64
import json
import logging
import struct
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

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
    """Stable tool result payload for MCP structuredContent/fallback text."""

    ok: bool
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[ToolError] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "ok": self.ok,
            "message": self.message,
        }
        if self.data:
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
    """Build the sentinel text fallback for clients without structuredContent."""

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


def tool_result_output_schema() -> Dict[str, Any]:
    """Return the shared MCP outputSchema for every tool result envelope."""

    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["ok", "message"],
        "properties": {
            "ok": {"type": "boolean"},
            "message": {"type": "string"},
            "data": {"type": "object", "additionalProperties": True},
            "error": {
                "type": "object",
                "additionalProperties": False,
                "required": ["code", "message"],
                "properties": {
                    "code": {"type": "string"},
                    "message": {"type": "string"},
                    "details": {"type": "object", "additionalProperties": True},
                },
            },
        },
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
        self._tool_result = ToolResult.failure(error_code, error, **details)
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
        """Return the stable structuredContent-compatible payload."""
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
        """Get all response content with machine-readable fallback first."""
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
