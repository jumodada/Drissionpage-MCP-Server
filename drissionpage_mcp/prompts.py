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
4. Navigation is the only destructive setup step allowed for this extraction task. After the page is open, use read-only inspection tools and do not click, type, submit, or mutate page state.
5. Return only JSON matching the requested schema and include no unsupported fields.
"""


def _vision_guided_interaction(values: dict[str, str]) -> str:
    url = values.get("url", "")
    verification_goal = values.get("verification_goal", "")
    url_line = f"Target URL: {url}" if url else "Target URL: use the current page"
    verification_line = (
        f"Verification goal: {verification_goal}"
        if verification_goal
        else "Verification goal: infer the smallest observable state change that proves success"
    )
    return f"""Operate a visual browser control with DrissionMCP.

{url_line}
Interaction goal: {values["interaction_goal"]}
{verification_line}

Decision sequence:
1. If a URL is provided, call `browser_open_and_snapshot`; otherwise inspect the current page.
2. Prefer semantic interaction: if `page_snapshot`, `element_find`, or accessibility-backed data exposes a reliable target, use `element_click` and skip coordinate interaction.
3. Use vision only when no reliable selector exists. Call `page_screenshot` with `full_page=false`; pointer coordinate tools accept viewport CSS pixels, not full-page document coordinates, device pixels, or coordinates copied from a resized image without conversion.
4. If the MCP host resized the screenshot, call `page_evaluate` to read `window.innerWidth` and `window.innerHeight`, then map image coordinates back to the original viewport:
   `viewport_x = image_x * viewport_width / image_width`
   `viewport_y = image_y * viewport_height / image_height`.
5. Choose the pointer profile:
   - `natural`: default for ordinary vision-guided UI clicks.
   - `precise`: small or tightly packed ordinary controls where reduced jitter is preferable.
   - `direct`: only when immediate deterministic movement is explicitly required.
6. Choose the action by intent: call `page_pointer_drag_element` when stable source/destination selectors exist, using destination `track_ratio` for a known thumb and track; geometry is resolved immediately before the drag. Call `page_pointer_move` to hover or reveal content without activation; call `page_click_xy` when activation requires a click; call `page_pointer_drag` for one visually identified coordinate drag, adding ordered `waypoints` only when a canvas, map, box-selection, or visual-editor gesture must follow a bounded multi-segment path. Selector-first drag supports one same-origin iframe and CSS paths through nested open Shadow DOM; closed Shadow DOM and cross-origin iframe internals are not promised. Keep drag press/move/release in one failure-safe call instead of emulating persistent button state. Pass viewport coordinates, chosen `profile`, and a concise `element` description. Supply `start_x` and `start_y` together only when the pointer origin is known; otherwise omit both.
7. Verify before retrying. Prefer `element_get_property`/`element_get_text` when a selector becomes available, `wait_until` for dynamic conditions, `page_observe` for bounded state changes, or a fresh `page_screenshot` for visual-only confirmation.
8. If verification fails, re-observe the page. For a moved target, take a fresh viewport screenshot and compute new coordinates. For an offset action, check screenshot scaling, viewport dimensions, zoom, and `full_page`. Do not repeat stale coordinate actions blindly.
9. When verification-like signals are relevant, use `page_detect_challenges` for read-only detection, then choose a fresh visual action and poll with `page_wait_challenge_result` or generic `wait_until`. The model remains fully autonomous and should use bounded retries with fresh evidence.
10. These are general capabilities for authorized automation and technical exchange. Users may compose them independently, but bypassing human-verification systems is not recommended and completion must not be promised.
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
                "verification_goal",
                "Optional observable state that proves the interaction succeeded.",
                required=False,
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
