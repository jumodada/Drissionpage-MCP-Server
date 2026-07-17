"""Typed tool specifications and execution outcomes."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Generic, TypeVar, Union

from mcp.types import ImageContent, TextContent
from pydantic import BaseModel, ConfigDict

from ..response_errors import ErrorCode, ToolError, classify_error, recovery_hints
from ..response_media import build_screenshot_metadata

if TYPE_CHECKING:
    from ..context import DrissionPageContext

JSON_RESULT_SENTINEL = "### JSON_RESULT"
InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)


class ToolType(Enum):
    """Tool operation types."""

    READ_ONLY = "readOnly"
    DESTRUCTIVE = "destructive"


class ToolInput(BaseModel):
    """Strict input model for public MCP tools."""

    model_config = ConfigDict(extra="forbid")


class EmptyInput(ToolInput):
    """Empty input schema for tools that don't require arguments."""


@dataclass(slots=True)
class ToolOutcome:
    """Complete tool execution result, including MCP presentation metadata."""

    _content: list[Union[TextContent, ImageContent]] = field(default_factory=list)
    _code_snippets: list[str] = field(default_factory=list)
    _include_snapshot: bool = False
    _is_error: bool = False
    _message: str = ""
    _data: dict[str, Any] = field(default_factory=dict)
    _error: ToolError | None = None

    def add_text(self, text: str) -> None:
        self._content.append(TextContent(type="text", text=text))

    def add_error(
        self,
        error: str,
        code: str | ErrorCode | None = None,
        **details: Any,
    ) -> None:
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
        code_value = (
            error_code.value if isinstance(error_code, ErrorCode) else str(error_code)
        )
        self._message = error
        self._error = ToolError(code=code_value, message=error, details=error_details)
        self._content.append(TextContent(type="text", text=f"### Error\n{error}"))

    def add_result(self, message: str, **data: Any) -> None:
        self.set_result(message, data)
        self._content.append(TextContent(type="text", text=f"### Result\n{message}"))

    def set_result(self, message: str, data: dict[str, Any]) -> None:
        """Set structured success data without adding a presentation block."""

        self._message = message
        self._data = data

    def add_code(self, code: str) -> None:
        self._code_snippets.append(code)

    def add_image(self, image_data: str | bytes, mime_type: str = "image/png") -> None:
        if isinstance(image_data, bytes):
            image_data = base64.b64encode(image_data).decode()
        elif not isinstance(image_data, str):
            raise ValueError("Image data must be string or bytes")
        self._content.append(
            ImageContent(type="image", data=image_data, mimeType=mime_type)
        )

    def add_screenshot(
        self, screenshot_data: str, metadata: dict[str, Any] | None = None
    ) -> None:
        self.add_image(screenshot_data, "image/png")
        self.add_text("Screenshot taken.")
        screenshot_metadata = build_screenshot_metadata(screenshot_data)
        if metadata:
            screenshot_metadata.update(metadata)
        self._message = "Screenshot taken."
        self._data = {"screenshot": screenshot_metadata}

    def set_include_snapshot(self, include: bool = True) -> None:
        self._include_snapshot = include

    def structured_content(self) -> dict[str, Any]:
        if self._is_error:
            error = self._error or ToolError(
                code=ErrorCode.UNKNOWN_ERROR.value,
                message=self._message or "Unknown error occurred.",
                details={},
            )
            payload: dict[str, Any] = {
                "ok": False,
                "message": self._message or error.message,
                "error": error.to_dict(),
            }
            if self._data:
                payload["data"] = self._data
            return payload
        return {
            "ok": True,
            "message": self._message or "Operation completed successfully.",
            "data": self._data,
        }

    def content(self) -> list[Union[TextContent, ImageContent]]:
        content = list(self._content)
        if self._code_snippets:
            code_text = (
                "### Code\n```python\n" + "\n".join(self._code_snippets) + "\n```"
            )
            content.insert(0, TextContent(type="text", text=code_text))
        if not content:
            heading = "Error" if self._is_error else "Result"
            message = self._message or (
                "Unknown error occurred."
                if self._is_error
                else "Operation completed successfully."
            )
            content.append(TextContent(type="text", text=f"### {heading}\n{message}"))
        body = json.dumps(self.structured_content(), ensure_ascii=False, sort_keys=True)
        content.insert(
            0,
            TextContent(
                type="text", text=f"{JSON_RESULT_SENTINEL}\n```json\n{body}\n```"
            ),
        )
        return content

    @property
    def is_error(self) -> bool:
        return self._is_error

    @property
    def include_snapshot(self) -> bool:
        return self._include_snapshot


ToolHandler = Callable[["DrissionPageContext", InputT], Awaitable[ToolOutcome]]


@dataclass(frozen=True, slots=True)
class ToolSpec(Generic[InputT, OutputT]):
    """Single source of truth for one public MCP tool."""

    name: str
    title: str
    description: str
    input_model: type[InputT]
    output_model: type[OutputT]
    handler: ToolHandler[InputT]
    tool_type: ToolType = ToolType.READ_ONLY
    idempotent: bool = False
    failure_message: Callable[[InputT, Exception], str] | None = None

    @property
    def input_schema(self) -> type[InputT]:
        return self.input_model

    async def execute(
        self, context: "DrissionPageContext", args: InputT
    ) -> ToolOutcome:
        try:
            outcome = await self.handler(context, args)
            if not isinstance(outcome, ToolOutcome):
                raise TypeError(
                    f"Tool {self.name!r} returned {type(outcome).__name__}, expected ToolOutcome"
                )
            if not outcome.is_error:
                validated = self.output_model.model_validate(
                    outcome.structured_content()["data"]
                )
                outcome._data = validated.model_dump(mode="json", exclude_unset=True)
            return outcome
        except Exception as exc:
            outcome = ToolOutcome()
            message = (
                self.failure_message(args, exc)
                if self.failure_message is not None
                else f"Failed to execute {self.name}: {exc}"
            )
            outcome.add_error(message, classify_error(exc), tool_name=self.name)
            return outcome

    def output_schema(self) -> dict[str, Any]:
        from ..tool_outputs import tool_outcome_schema

        return tool_outcome_schema(self.output_model)  # type: ignore[arg-type]


def define_tool(
    *,
    name: str,
    title: str,
    description: str,
    input_schema: type[InputT],
    output_model: type[OutputT],
    tool_type: ToolType = ToolType.READ_ONLY,
    idempotent: bool = False,
    failure_message: Callable[[InputT, Exception], str] | None = None,
) -> Callable[[ToolHandler[InputT]], ToolSpec[InputT, OutputT]]:
    """Define a typed tool specification from a two-argument async handler."""

    def decorator(handler: ToolHandler[InputT]) -> ToolSpec[InputT, OutputT]:
        return ToolSpec(
            name=name,
            title=title,
            description=description,
            input_model=input_schema,
            output_model=output_model,
            handler=handler,
            tool_type=tool_type,
            idempotent=idempotent,
            failure_message=failure_message,
        )

    return decorator


__all__ = [
    "EmptyInput",
    "JSON_RESULT_SENTINEL",
    "ToolInput",
    "ToolOutcome",
    "ToolSpec",
    "ToolType",
    "classify_error",
    "define_tool",
]
