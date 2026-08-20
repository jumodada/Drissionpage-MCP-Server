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

    assert len(tool_names) == 69
    assert {
        "page_navigate",
        "page_snapshot",
        "element_find_all",
        "element_type",
        "browser_cookies_set",
        "browser_cookies_delete",
        "browser_cookies_clear",
        "browser_headers_set",
        "browser_user_agent_set",
        "browser_cache_clear",
        "network_blocked_urls_set",
        "browser_permission_get",
        "browser_permission_set",
        "browser_permissions_reset",
        "page_export_artifact",
        "element_click_and_upload",
        "page_navigate_with_http_auth",
    } <= tool_names
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
    assert catalog["status"] == "repository_examples"
    assert catalog["schema_version"] == "2"
    assert catalog["source_revision"] == "v0.8.3"
    assert catalog["repository_url"].endswith("/skills-manager")
    assert {skill["name"] for skill in catalog["skills"]} >= {
        "cross-origin-iframe-probe",
        "turnstile-testing",
        "xiaohongshu-content-research",
    }
    for skill in catalog["skills"]:
        assert skill["skill_version"] == "0.1.0"
        assert skill["mcp_compatibility"] == ">=0.8.2,<0.9.0"
        assert skill["required_tools"]
        assert skill["source_revision"] == catalog["source_revision"]
        assert skill["source_url"].startswith(catalog["repository_url"])
        assert skill["source_revision"] in skill["source_url"]
        assert len(skill["sha256"]) == 64
        assert skill["verification_status"] in {
            "fixture_verified",
            "field_evaluated",
        }
    assert server.context is None
