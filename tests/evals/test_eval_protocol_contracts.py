"""Deterministic protocol checks for atomic-core discovery."""

from __future__ import annotations

import json

import pytest
from mcp.types import (
    GetPromptRequest,
    ListPromptsRequest,
    ListResourcesRequest,
    ListToolsRequest,
    ReadResourceRequest,
    ReadResourceRequestParams,
)

from drissionpage_mcp.resources import SKILLS_CATALOG_URI
from drissionpage_mcp.server import DrissionPageMCPServer


@pytest.mark.asyncio
async def test_eval_agent_discovers_atomic_tools_and_optional_skills() -> None:
    server = DrissionPageMCPServer()
    tools_result = await server.server.request_handlers[ListToolsRequest](
        ListToolsRequest(method="tools/list")
    )
    resources_result = await server.server.request_handlers[ListResourcesRequest](
        ListResourcesRequest(method="resources/list")
    )

    tool_names = {tool.name for tool in tools_result.root.tools}
    resource_uris = {str(resource.uri) for resource in resources_result.root.resources}

    assert len(tool_names) == 53
    assert {"page_navigate", "page_snapshot", "element_find_all", "element_type"} <= (
        tool_names
    )
    assert resource_uris == {SKILLS_CATALOG_URI}
    assert ListPromptsRequest not in server.server.request_handlers
    assert GetPromptRequest not in server.server.request_handlers


@pytest.mark.asyncio
async def test_eval_skills_catalog_is_optional_and_static() -> None:
    server = DrissionPageMCPServer()
    result = await server.server.request_handlers[ReadResourceRequest](
        ReadResourceRequest(
            method="resources/read",
            params=ReadResourceRequestParams(uri=SKILLS_CATALOG_URI),
        )
    )

    catalog = json.loads(result.root.contents[0].text)
    assert catalog["optional"] is True
    assert catalog["catalog_path"] == "skills/"
    assert catalog["skill_entrypoint"] == "skills/<skill-name>/SKILL.md"
    assert catalog["status"] == "unpublished"
    assert catalog["skills"] == []
    assert server.context is None
