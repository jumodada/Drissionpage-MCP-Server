"""MCP Prompt definitions for common browser automation workflows."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from mcp.types import (
    GetPromptResult,
    Prompt,
    PromptArgument,
    PromptMessage,
    TextContent,
)

from .guidance import MODEL_USAGE_PROMPT_NAME, usage_playbook_text


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
1. Call `browser_open_and_snapshot` with the target URL to navigate and gather
   bounded page context in one step.
2. Use `page_snapshot` if you need more selectors/content, or `page_navigate`
   only when you intentionally do not need an immediate snapshot.
3. Use `wait_for_element` only when a specific selector is needed.
4. Use `page_get_url` and include the final source URL in the answer.
5. Summarize concisely and mention uncertainty if the page content is incomplete.
"""


def _usage_playbook(values: dict[str, str]) -> str:
    return usage_playbook_text(task=values.get("task", ""))


def _extract_structured_data(values: dict[str, str]) -> str:
    selector_hint = values.get("selector_hint", "")
    hint_line = (
        f"Selector hint: {selector_hint}" if selector_hint else "Selector hint: none"
    )
    return f"""Extract structured data with DrissionMCP.

Target URL: {values["url"]}
Schema: {values["schema_description"]}
{hint_line}

Steps:
1. Call `browser_open_and_snapshot` to navigate and capture bounded page context.
2. Inspect with `page_snapshot`; use `element_get_html` only when structure matters.
3. If a selector is provided, use `element_find` before extraction; use
   `page_navigate` only for a deliberate navigation-only retry.
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
1. Call `page_navigate` or `browser_open_and_snapshot`.
2. Inspect forms with `form_inspect`.
3. Prefill fields with `form_fill_preview`; never echo secrets in the final answer.
4. Do not submit, click final confirmation buttons, or trigger destructive actions until
   explicit user confirmation is received.
5. After filling, summarize what was entered and ask for confirmation before submit.
"""


def _vision_guided_interaction(values: dict[str, str]) -> str:
    url = values.get("url", "")
    url_line = f"Target URL: {url}" if url else "Target URL: use the current page"
    return f"""Operate a visual browser control with DrissionMCP.

{url_line}
Interaction goal: {values["interaction_goal"]}

Steps:
1. If a URL is provided, call `browser_open_and_snapshot`; otherwise inspect the current page.
2. Prefer a reliable selector and `element_click` when semantic DOM or accessibility data is available.
3. When the target is visual-only, call `page_screenshot` with `full_page=false` or use `page_observe`. Identify the target in viewport CSS coordinates. If the MCP client resized the screenshot, convert image coordinates back to the original viewport coordinate space; use `page_evaluate` to read viewport dimensions when needed.
4. Call `page_click_xy` with `profile="natural"`, the target `x` and `y`, and a concise `element` description. Supply `start_x` and `start_y` together only when the pointer origin is known.
5. Verify the result with `page_observe`, a new `page_screenshot`, `element_get_property`, or another bounded state check. Use `wait_until` for dynamic transitions and do not repeat clicks blindly.
6. Use this workflow for legitimate UI automation, testing, accessibility, and technical research; do not claim guaranteed completion of security or anti-automation challenges.
"""


def _debug_page_issue(values: dict[str, str]) -> str:
    return f"""Debug a page issue with DrissionMCP.

Target URL: {values["url"]}
Issue: {values["issue_description"]}

Steps:
1. Call `browser_open_and_snapshot` to navigate and collect page evidence.
2. Use `page_snapshot` and `wait_for_element` for the suspected selector if known.
3. Use `page_navigate` only for a deliberate navigation-only retry, then
   confirm with `page_get_url`.
4. Use `page_screenshot` only when visual evidence is needed.
5. Report likely causes, exact tool evidence, `error.details.hints` if present,
   and the next safest action.
"""


PROMPTS: tuple[PromptSpec, ...] = (
    PromptSpec(
        name=MODEL_USAGE_PROMPT_NAME,
        title="DrissionPage MCP Usage Playbook",
        description="Explain how an MCP-connected model should use DrissionPage MCP safely.",
        arguments=(
            _arg("task", "Optional current browser automation task.", required=False),
        ),
        render=_usage_playbook,
    ),
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
            _arg(
                "selector_hint", "Optional selector to inspect first.", required=False
            ),
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
            _arg(
                "fields_json", "Optional JSON object of field values.", required=False
            ),
        ),
        render=_fill_form_safely,
    ),
    PromptSpec(
        name="browser_vision_guided_interaction",
        title="Vision-Guided Interaction",
        description="Use viewport visual evidence and a natural pointer action chain to operate a control without a reliable selector.",
        arguments=(
            _arg(
                "interaction_goal",
                "What visual control should be operated and why.",
                required=True,
            ),
            _arg(
                "url",
                "Optional absolute URL; omit to use the current page.",
                required=False,
            ),
        ),
        render=_vision_guided_interaction,
    ),
    PromptSpec(
        name="browser_debug_page_issue",
        title="Debug Page Issue",
        description="Gather page evidence for a browser automation issue.",
        arguments=(
            _arg("url", "Absolute URL to inspect.", required=True),
            _arg(
                "issue_description",
                "Observed issue or failing selector.",
                required=True,
            ),
        ),
        render=_debug_page_issue,
    ),
)

PROMPT_MAP = {spec.name: spec for spec in PROMPTS}
