"""Response handling for DrissionPage MCP tools.

This module is the public compatibility entry point. Implementation details live in
smaller response_* modules so the envelope, error taxonomy, schema registry, and
media metadata helpers can evolve independently.
"""

import base64
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Union

from mcp.types import ImageContent, TextContent

from .response_errors import ErrorCode, ToolError, classify_error, recovery_hints
from .response_media import build_screenshot_metadata
from .response_schemas import tool_data_schema_title, tool_result_output_schema

JSON_RESULT_SENTINEL = "### JSON_RESULT"


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


class ToolResponse:
    """Response builder for tool executions."""

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

    def add_result(self, message: str, **data: Any) -> None:
        """Add result content to the response."""
        self._tool_result = ToolResult.success(message, **data)
        result_text = f"### Result\n{message}"
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


def _json_text(payload: Dict[str, Any]) -> TextContent:
    """Build the sentinel TextContent mirror for structured tool results."""

    body = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return TextContent(
        type="text", text=f"{JSON_RESULT_SENTINEL}\n```json\n{body}\n```"
    )


__all__ = [
    "ErrorCode",
    "JSON_RESULT_SENTINEL",
    "ToolError",
    "ToolResponse",
    "ToolResult",
    "build_screenshot_metadata",
    "classify_error",
    "recovery_hints",
    "tool_data_schema_title",
    "tool_result_output_schema",
]
