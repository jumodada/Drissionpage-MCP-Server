"""Form inspection tools for DrissionPage MCP."""

from typing import TYPE_CHECKING

from pydantic import Field

from .base import ToolInput, ToolType, define_tool, tool_errors

if TYPE_CHECKING:
    from ..context import DrissionPageContext
    from ..response import ToolResponse


class FormInspectInput(ToolInput):
    """Input schema for inspecting forms and their controls."""

    selector: str = Field(
        default="",
        description=(
            "Optional CSS selector or XPath for a form or container. Empty means "
            "all forms on the current page."
        ),
    )
    include_values: bool = Field(
        default=False,
        description=(
            "Include current non-password field values. Password values are never "
            "returned."
        ),
    )
    max_forms: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of forms to return",
    )
    max_fields_per_form: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Maximum number of controls to return per form",
    )


@define_tool(
    name="form_inspect",
    title="Inspect Forms",
    description=(
        "Inspect forms and controls with labels, selectors, methods, actions, "
        "requirements, options, and safe optional values."
    ),
    input_schema=FormInspectInput,
    tool_type=ToolType.READ_ONLY,
    idempotent=True,
)
async def form_inspect(
    context: "DrissionPageContext", args: FormInspectInput, response: "ToolResponse"
) -> None:
    """Inspect forms on the current page."""
    async with tool_errors(
        response,
        lambda e: f"Failed to inspect forms for selector {args.selector!r}: {e}",
    ):
        tab = context.current_tab_or_die()
        result = await tab.inspect_forms(
            selector=args.selector,
            include_values=args.include_values,
            max_forms=args.max_forms,
            max_fields_per_form=args.max_fields_per_form,
        )

        response.add_code("page.run_js(<bounded form inspection script>)")
        response.add_result(
            f"Inspected {result['returned']} of {result['count']} forms",
            **result,
        )


tools = [form_inspect]
