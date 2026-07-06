"""File-related element tools for DrissionPage MCP."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field

from ..limits import MAX_WAIT_SECONDS
from ..policy import PolicyDeniedError, validate_upload_paths
from ..response import ErrorCode
from .base import ToolInput, ToolType, define_tool, tool_errors

if TYPE_CHECKING:
    from ..context import DrissionPageContext
    from ..response import ToolResponse


class UploadFileInput(ToolInput):
    """Input schema for file uploads."""

    selector: str = Field(
        ...,
        description="CSS/XPath/DrissionPage locator for an input[type=file].",
    )
    paths: list[str] = Field(
        ...,
        min_length=1,
        description=(
            "One or more local file paths under DP_MCP_UPLOAD_ROOT. Absolute "
            "paths are accepted but never echoed back in tool results."
        ),
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
    description=(
        "Set files on an input[type=file]. Paths must exist under "
        "DP_MCP_UPLOAD_ROOT and response data only returns safe file names."
    ),
    input_schema=UploadFileInput,
    tool_type=ToolType.DESTRUCTIVE,
)
async def element_upload_file(
    context: "DrissionPageContext", args: UploadFileInput, response: "ToolResponse"
) -> None:
    """Upload one or more files into a file input."""

    try:
        safe_paths = validate_upload_paths(args.paths)
    except PolicyDeniedError as exc:
        response.add_error(
            str(exc),
            ErrorCode.POLICY_DENIED,
            rule=exc.rule,
            value=exc.value,
        )
        return

    async with tool_errors(
        response,
        lambda e: f"Failed to upload file into '{args.selector}': {e}",
    ):
        tab = context.current_tab_or_die()
        result = await tab.upload_file(
            args.selector,
            [str(path) for path in safe_paths],
            timeout=args.timeout,
        )

        response.add_code(f"page.ele({result['locator']!r}).input(<approved files>)")
        response.add_result(
            f"Uploaded {result['file_count']} file"
            f"{'' if result['file_count'] == 1 else 's'}",
            **result,
        )
        response.set_include_snapshot(True)


tools = [element_upload_file]
