"""Deterministic MCP eval smoke checks for local protocol usefulness."""

from __future__ import annotations

import json

import pytest
from mcp.types import (
    GetPromptRequest,
    GetPromptRequestParams,
    ListPromptsRequest,
    ListResourcesRequest,
    ListToolsRequest,
    ReadResourceRequest,
    ReadResourceRequestParams,
)

from drissionpage_mcp.server import DrissionPageMCPServer


@pytest.mark.asyncio
async def test_eval_agent_can_discover_tools_resources_and_prompts() -> None:
    server = DrissionPageMCPServer()

    tools_result = await server.server.request_handlers[ListToolsRequest](
        ListToolsRequest(method="tools/list")
    )
    resources_result = await server.server.request_handlers[ListResourcesRequest](
        ListResourcesRequest(method="resources/list")
    )
    prompts_result = await server.server.request_handlers[ListPromptsRequest](
        ListPromptsRequest(method="prompts/list")
    )

    tool_names = {tool.name for tool in tools_result.root.tools}
    resource_uris = {str(resource.uri) for resource in resources_result.root.resources}
    prompt_names = {prompt.name for prompt in prompts_result.root.prompts}

    assert "page_navigate" in tool_names
    assert "page_snapshot" in tool_names
    assert "element_find_all" in tool_names
    assert "element_type" in tool_names
    assert "element_input_text" not in tool_names
    assert "drissionpage://tools/catalog" in resource_uris
    assert "browser_extract_structured_data" in prompt_names
    assert "browser_vision_guided_interaction" in prompt_names


@pytest.mark.asyncio
async def test_eval_tools_catalog_and_prompt_help_structured_extraction() -> None:
    server = DrissionPageMCPServer()

    catalog_result = await server.server.request_handlers[ReadResourceRequest](
        ReadResourceRequest(
            method="resources/read",
            params=ReadResourceRequestParams(uri="drissionpage://tools/catalog"),
        )
    )
    prompt_result = await server.server.request_handlers[GetPromptRequest](
        GetPromptRequest(
            method="prompts/get",
            params=GetPromptRequestParams(
                name="browser_extract_structured_data",
                arguments={
                    "url": "https://example.test/table",
                    "schema_description": "rows: list of {name, role}",
                    "selector_hint": "#people",
                },
            ),
        )
    )

    catalog = json.loads(catalog_result.root.contents[0].text)
    prompt_text = prompt_result.root.messages[0].content.text

    workflow_tool = next(
        tool for tool in catalog["tools"] if tool["name"] == "browser_open_and_snapshot"
    )
    assert "bounded snapshot" in workflow_tool["description"]
    assert any(tool["name"] == "page_snapshot" for tool in catalog["tools"])
    assert any(tool["name"] == "element_find_all" for tool in catalog["tools"])
    assert any(tool["name"] == "element_get_html" for tool in catalog["tools"])
    assert "browser_open_and_snapshot" in prompt_text
    assert prompt_text.index("browser_open_and_snapshot") < prompt_text.index(
        "element_get_html"
    )
    assert "element_get_html" in prompt_text
    assert "rows: list of {name, role}" in prompt_text


@pytest.mark.asyncio
async def test_eval_vision_prompt_teaches_selector_first_coordinate_mapping_and_recovery() -> (
    None
):
    server = DrissionPageMCPServer()

    guide_result = await server.server.request_handlers[ReadResourceRequest](
        ReadResourceRequest(
            method="resources/read",
            params=ReadResourceRequestParams(uri="drissionpage://guide/model-usage"),
        )
    )
    prompt_result = await server.server.request_handlers[GetPromptRequest](
        GetPromptRequest(
            method="prompts/get",
            params=GetPromptRequestParams(
                name="browser_vision_guided_interaction",
                arguments={
                    "interaction_goal": "activate a visually identified canvas tool",
                    "verification_goal": "the tool options panel becomes visible",
                },
            ),
        )
    )

    guide = json.loads(guide_result.root.contents[0].text)
    prompt_text = prompt_result.root.messages[0].content.text
    route = next(
        route
        for route in guide["workflow_routes"]
        if route["task"] == "vision_guided_interaction"
    )

    assert route["preferred_sequence"][0].startswith("prefer element_find")
    assert route["preferred_sequence"][1] == "page_screenshot full_page=false"
    assert guide["vision_interaction"]["coordinate_contract"]["accepted"] == (
        "viewport CSS pixels"
    )
    assert set(guide["vision_interaction"]["profiles"]) == {
        "natural",
        "precise",
        "direct",
    }
    assert prompt_text.index("element_click") < prompt_text.index("page_screenshot")
    assert prompt_text.index("page_screenshot") < prompt_text.index("page_pointer_move")
    assert prompt_text.index("page_pointer_move") < prompt_text.index("page_click_xy")
    assert "page_pointer_drag" in prompt_text
    assert "page_pointer_drag_element" in prompt_text
    assert "viewport_x = image_x * viewport_width / image_width" in prompt_text
    assert "Verify before retrying" in prompt_text
    assert "Do not repeat stale coordinate actions blindly" in prompt_text
