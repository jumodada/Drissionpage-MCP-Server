"""Form inspection tools for DrissionPage MCP."""

from typing import TYPE_CHECKING
from pydantic import Field
from ..metadata import with_response_meta
from .base import ToolInput, ToolType, define_tool, ToolOutcome
from ..tool_outputs import FormInspectData

if TYPE_CHECKING:
    from ..context import DrissionPageContext


class FormInspectInput(ToolInput):
    """Input schema for inspecting forms and their controls."""

    selector: str = Field(
        default="",
        description="Optional CSS selector or XPath for a form or container. Empty means all forms on the current page.",
    )
    include_values: bool = Field(
        default=False,
        description="Include current non-password field values. Password values are never returned.",
    )
    max_forms: int = Field(
        default=10, ge=1, le=50, description="Maximum number of forms to return"
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
    description="Inspect forms and controls with labels, selectors, methods, actions, requirements, options, and safe optional values.",
    input_schema=FormInspectInput,
    tool_type=ToolType.READ_ONLY,
    idempotent=True,
    output_model=FormInspectData,
    failure_message=lambda args, exc: (
        lambda e: f"Failed to inspect forms for selector {args.selector!r}: {e}"
    )(exc),
)
async def form_inspect(
    context: "DrissionPageContext", args: FormInspectInput
) -> "ToolOutcome":
    """Inspect forms on the current page."""
    outcome = ToolOutcome()
    tab = context.current_tab_or_die()
    result = await tab.workflows.inspect_forms(
        selector=args.selector,
        include_values=args.include_values,
        max_forms=args.max_forms,
        max_fields_per_form=args.max_fields_per_form,
    )
    outcome.add_code("page.run_js(<bounded form inspection script>)")
    outcome.add_result(
        f"Inspected {result['returned']} of {result['count']} forms",
        **with_response_meta(result),
    )
    return outcome
