"""MCP Prompt definitions for common browser automation workflows."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from mcp.types import GetPromptResult, Prompt, PromptArgument, PromptMessage, TextContent


@dataclass(frozen=True)
class PromptSpec:
    name: str
    title: str
    description: str
    arguments: tuple[PromptArgument, ...]
    render: Callable[[dict[str, str]], str]

    @property
    def required_arguments(self) -> tuple[str, ...]:
        return tuple(arg.name for arg in self.arguments if arg.required)


def list_prompts() -> list[Prompt]:
    """Return deterministic MCP prompt definitions."""

    return [
        Prompt(
            name=spec.name,
            title=spec.title,
            description=spec.description,
            arguments=list(spec.arguments),
        )
        for spec in PROMPTS
    ]


def get_prompt(name: str, arguments: dict[str, str] | None) -> GetPromptResult:
    """Return rendered prompt messages after required argument validation."""

    spec = PROMPT_MAP.get(name)
    if spec is None:
        raise ValueError(f"Unknown prompt: {name}")

    values = arguments or {}
    for required in spec.required_arguments:
        if not values.get(required):
            raise ValueError(f"Missing required prompt argument: {required}")

    text = spec.render(values)
    return GetPromptResult(
        description=spec.description,
        messages=[
            PromptMessage(
                role="user",
                content=TextContent(type="text", text=text),
            )
        ],
    )


def _arg(name: str, description: str, *, required: bool) -> PromptArgument:
    return PromptArgument(name=name, description=description, required=required)


def _navigate_and_summarize(values: dict[str, str]) -> str:
    focus = values.get("focus", "the main content")
    return f"""Use DrissionMCP to summarize a page.

Target URL: {values["url"]}
Focus: {focus}

Steps:
1. Call `page_navigate` with the target URL.
2. Use `wait_for_element` only when a specific selector is needed.
3. Call `element_get_text` with an empty selector to read page text.
4. Use `page_get_url` and include the final source URL in the answer.
5. Summarize concisely and mention uncertainty if the page content is incomplete.
"""


def _extract_structured_data(values: dict[str, str]) -> str:
    selector_hint = values.get("selector_hint", "")
    hint_line = f"Selector hint: {selector_hint}" if selector_hint else "Selector hint: none"
    return f"""Extract structured data with DrissionMCP.

Target URL: {values["url"]}
Schema: {values["schema_description"]}
{hint_line}

Steps:
1. Call `page_navigate`.
2. Inspect content with `element_get_text`; use `element_get_html` when structure matters.
3. If a selector is provided, use `element_find` before extraction.
4. Return only JSON matching the requested schema and include no unsupported fields.
5. Do not use destructive tools for this read-only extraction task.
"""


def _fill_form_safely(values: dict[str, str]) -> str:
    fields = values.get("fields_json", "{}")
    return f"""Fill a form safely with DrissionMCP.

Target URL: {values["url"]}
Goal: {values["form_goal"]}
Fields JSON: {fields}

Steps:
1. Call `page_navigate`.
2. Inspect the form with `element_find`, `element_get_text`, or `element_get_html`.
3. Type values with `element_type`; never echo secrets in the final answer.
4. Do not submit, click final confirmation buttons, or trigger destructive actions until
   explicit user confirmation is received.
5. After filling, summarize what was entered and ask for confirmation before submit.
"""


def _debug_page_issue(values: dict[str, str]) -> str:
    return f"""Debug a page issue with DrissionMCP.

Target URL: {values["url"]}
Issue: {values["issue_description"]}

Steps:
1. Call `page_navigate` and then `page_get_url`.
2. Use `wait_for_element` for the suspected selector if known.
3. Inspect page text with `element_get_text` and targeted HTML with `element_get_html`.
4. Use `page_screenshot` only when visual evidence is needed.
5. Report likely causes, exact tool evidence, and the next safest action.
"""


PROMPTS: tuple[PromptSpec, ...] = (
    PromptSpec(
        name="browser_navigate_and_summarize",
        title="Navigate and Summarize",
        description="Navigate to a page and summarize the requested content.",
        arguments=(
            _arg("url", "Absolute URL to navigate to.", required=True),
            _arg("focus", "Optional summary focus.", required=False),
        ),
        render=_navigate_and_summarize,
    ),
    PromptSpec(
        name="browser_extract_structured_data",
        title="Extract Structured Data",
        description="Navigate, inspect content, and return JSON matching a schema.",
        arguments=(
            _arg("url", "Absolute URL to navigate to.", required=True),
            _arg("schema_description", "Desired JSON schema in prose.", required=True),
            _arg("selector_hint", "Optional selector to inspect first.", required=False),
        ),
        render=_extract_structured_data,
    ),
    PromptSpec(
        name="browser_fill_form_safely",
        title="Fill Form Safely",
        description="Fill form fields while requiring confirmation before submission.",
        arguments=(
            _arg("url", "Absolute URL containing the form.", required=True),
            _arg("form_goal", "What the form should accomplish.", required=True),
            _arg("fields_json", "Optional JSON object of field values.", required=False),
        ),
        render=_fill_form_safely,
    ),
    PromptSpec(
        name="browser_debug_page_issue",
        title="Debug Page Issue",
        description="Gather page evidence for a browser automation issue.",
        arguments=(
            _arg("url", "Absolute URL to inspect.", required=True),
            _arg("issue_description", "Observed issue or failing selector.", required=True),
        ),
        render=_debug_page_issue,
    ),
)

PROMPT_MAP = {spec.name: spec for spec in PROMPTS}
