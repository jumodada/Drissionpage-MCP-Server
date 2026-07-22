"""File-related element tools for DrissionPage MCP."""

from __future__ import annotations
from typing import TYPE_CHECKING
from pydantic import Field
from ..limits import MAX_WAIT_SECONDS
from ..policy import PolicyDeniedError, validate_upload_paths
from ..response_errors import ErrorCode
from .base import ToolInput, ToolType, define_tool, ToolOutcome
from ..tool_outputs import ElementUploadFileData

if TYPE_CHECKING:
    from ..context import DrissionPageContext


class UploadFileInput(ToolInput):
    """Input schema for file uploads."""

    selector: str = Field(
        ..., description="CSS/XPath/DrissionPage locator for an input[type=file]."
    )
    paths: list[str] = Field(
        ...,
        min_length=1,
        description="One or more local file paths under DP_MCP_UPLOAD_ROOT. Absolute paths are accepted but never echoed back in tool results.",
    )
    timeout: int = Field(
        default=10,
        ge=0,
        le=MAX_WAIT_SECONDS,
        description="Timeout in seconds to wait for the file input.",
    )


@define_tool(
    name="element_upload_file",
    title="Upload File",
    description="Set files on an input[type=file]. Paths must exist under DP_MCP_UPLOAD_ROOT and response data only returns safe file names.",
    input_schema=UploadFileInput,
    tool_type=ToolType.DESTRUCTIVE,
    output_model=ElementUploadFileData,
    failure_message=lambda args, exc: (
        lambda e: f"Failed to upload file into '{args.selector}': {e}"
    )(exc),
)
async def element_upload_file(
    context: "DrissionPageContext", args: UploadFileInput
) -> "ToolOutcome":
    """Upload one or more files into a file input."""
    outcome = ToolOutcome()
    try:
        safe_paths = validate_upload_paths(args.paths)
    except PolicyDeniedError as exc:
        outcome.add_error(
            str(exc), ErrorCode.POLICY_DENIED, rule=exc.rule, value=exc.value
        )
        return outcome
    tab = context.current_tab_or_die()
    result = await tab.elements.upload(
        args.selector, [str(path) for path in safe_paths], timeout=args.timeout
    )
    outcome.add_result(
        f"Uploaded {result['file_count']} file{('' if result['file_count'] == 1 else 's')}",
        **result,
    )
    return outcome
