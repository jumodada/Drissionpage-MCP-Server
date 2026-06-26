"""MCP Prompts coverage for 0.4.0 guided browser workflows."""

from __future__ import annotations

import pytest
from mcp.types import GetPromptRequest, GetPromptRequestParams, ListPromptsRequest

from drissionpage_mcp.server import DrissionPageMCPServer


PROMPT_NAMES = [
    "browser_navigate_and_summarize",
    "browser_extract_structured_data",
    "browser_fill_form_safely",
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
    summarize = prompts[0]
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
            "fields_json": "{\"name\":\"Ada\"}",
            "issue_description": "missing button",
        },
    )

    assert result.root.description
    assert len(result.root.messages) == 1
    text = result.root.messages[0].content.text
    assert "page_navigate" in text
    assert "element_input_text" not in text
    assert "wait_sleep" not in text
    if prompt_name == "browser_fill_form_safely":
        assert "confirmation" in text.lower()
        assert "do not submit" in text.lower()


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
