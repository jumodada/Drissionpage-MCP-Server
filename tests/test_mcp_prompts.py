"""MCP Prompts coverage for 0.4.0 guided browser workflows."""

from __future__ import annotations

import pytest
from mcp.types import GetPromptRequest, GetPromptRequestParams, ListPromptsRequest

from drissionpage_mcp.server import DrissionPageMCPServer


PROMPT_NAMES = [
    "drissionpage_mcp_usage_playbook",
    "browser_navigate_and_summarize",
    "browser_extract_structured_data",
    "browser_fill_form_safely",
    "browser_vision_guided_interaction",
    "browser_debug_page_issue",
]


@pytest.mark.asyncio
async def test_list_prompts_is_deterministic_and_argumented() -> None:
    server = DrissionPageMCPServer()
    handler = server.server.request_handlers[ListPromptsRequest]

    result = await handler(ListPromptsRequest(method="prompts/list"))

    prompts = result.root.prompts
    assert [prompt.name for prompt in prompts] == PROMPT_NAMES
    for prompt in prompts:
        assert prompt.title
        assert prompt.description
        assert prompt.arguments
    usage = prompts[0]
    assert [(arg.name, arg.required) for arg in usage.arguments] == [
        ("task", False),
    ]
    summarize = prompts[1]
    assert [(arg.name, arg.required) for arg in summarize.arguments] == [
        ("url", True),
        ("focus", False),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("prompt_name", PROMPT_NAMES)
async def test_get_prompt_returns_modern_tool_guidance(prompt_name: str) -> None:
    server = DrissionPageMCPServer()

    result = await _get_prompt(
        server,
        prompt_name,
        {
            "url": "https://example.test/",
            "focus": "headings",
            "schema_description": "items: list of names",
            "selector_hint": "#items",
            "form_goal": "fill a contact form",
            "fields_json": '{"name":"Ada"}',
            "issue_description": "missing button",
            "interaction_goal": "click a canvas toolbar control identified visually",
            "task": "inspect a page and fill a form without submitting",
        },
    )

    assert result.root.description
    assert len(result.root.messages) == 1
    text = result.root.messages[0].content.text
    assert "page_navigate" in text or "browser_open_and_snapshot" in text
    assert "element_input_text" not in text
    assert "wait_sleep" not in text
    if prompt_name == "drissionpage_mcp_usage_playbook":
        assert "DrissionPage>=4.1.1.4,<5" in text
        assert "form_fill_preview" in text
        assert "network_listen_start" in text
        assert "observation only" in text.lower()
        assert "page_click_xy" in text
        assert "viewport CSS coordinates" in text
        assert "profile=natural" in text
    if prompt_name == "browser_fill_form_safely":
        assert "form_fill_preview" in text
        assert "confirmation" in text.lower()
        assert "do not submit" in text.lower()
    if prompt_name == "browser_vision_guided_interaction":
        assert "page_screenshot" in text
        assert "viewport CSS coordinates" in text
        assert "page_click_xy" in text
        assert 'profile="natural"' in text
        assert "Verify the result" in text


@pytest.mark.asyncio
async def test_prompts_prefer_workflow_helpers_for_common_ai_sequences() -> None:
    server = DrissionPageMCPServer()

    summarize = await _get_prompt(
        server,
        "browser_navigate_and_summarize",
        {"url": "https://example.test/", "focus": "headings"},
    )
    summarize_text = summarize.root.messages[0].content.text
    assert "browser_open_and_snapshot" in summarize_text
    assert summarize_text.index("browser_open_and_snapshot") < summarize_text.index(
        "page_snapshot"
    )

    extract = await _get_prompt(
        server,
        "browser_extract_structured_data",
        {
            "url": "https://example.test/",
            "schema_description": "items: list of names",
            "selector_hint": "#items",
        },
    )
    extract_text = extract.root.messages[0].content.text
    assert "browser_open_and_snapshot" in extract_text
    assert "Return only JSON" in extract_text

    debug = await _get_prompt(
        server,
        "browser_debug_page_issue",
        {
            "url": "https://example.test/",
            "issue_description": "missing button",
        },
    )
    debug_text = debug.root.messages[0].content.text
    assert "browser_open_and_snapshot" in debug_text
    assert "page_snapshot" in debug_text
    assert "error.details.hints" in debug_text


@pytest.mark.asyncio
async def test_vision_prompt_prefers_selectors_then_natural_pointer_and_verification() -> (
    None
):
    server = DrissionPageMCPServer()

    result = await _get_prompt(
        server,
        "browser_vision_guided_interaction",
        {
            "url": "https://example.test/editor",
            "interaction_goal": "activate the visually identified canvas tool",
        },
    )
    text = result.root.messages[0].content.text

    assert text.index("element_click") < text.index("page_screenshot")
    assert text.index("page_screenshot") < text.index("page_click_xy")
    assert text.index("page_click_xy") < text.index("Verify the result")
    assert "start_x" in text and "start_y" in text
    assert "do not repeat clicks blindly" in text


@pytest.mark.asyncio
async def test_get_prompt_validates_required_arguments() -> None:
    server = DrissionPageMCPServer()

    with pytest.raises(ValueError, match="Missing required prompt argument: url"):
        await _get_prompt(server, "browser_navigate_and_summarize", {})


async def _get_prompt(
    server: DrissionPageMCPServer,
    name: str,
    arguments: dict[str, str],
):
    handler = server.server.request_handlers[GetPromptRequest]
    return await handler(
        GetPromptRequest(
            method="prompts/get",
            params=GetPromptRequestParams(name=name, arguments=arguments),
        )
    )
