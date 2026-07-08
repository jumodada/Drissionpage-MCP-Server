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
