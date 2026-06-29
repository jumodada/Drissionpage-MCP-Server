"""Deterministic read-only evals for 0.4.9 page-understanding tools."""

from __future__ import annotations

import os
from typing import Any

import pytest

from drissionpage_mcp.context import DrissionPageContext
from drissionpage_mcp.response import ToolResponse
from drissionpage_mcp.server import DrissionPageMCPServer
from tests.fixtures.http_fixture import local_http_fixture

_BROWSER_UNAVAILABLE_MARKERS = (
    "browser",
    "chrome",
    "chromium",
    "cannot find",
    "connection refused",
    "failed to initialize",
    "executable",
)


@pytest.mark.asyncio
async def test_eval_page_understanding_read_only_catalog_tasks() -> None:
    server = DrissionPageMCPServer()
    try:
        with local_http_fixture() as base_url:
            navigate = await _call(server, "page_navigate", {"url": base_url + "/catalog"})
            _skip_if_browser_unavailable(navigate["message"])

            snapshot = await _call(
                server,
                "page_snapshot",
                {"max_elements": 30, "max_text_chars": 1200},
            )
            cards = await _call(
                server,
                "element_find_all",
                {"selector": ".product-card", "limit": 10},
            )
            rows = await _call(
                server,
                "element_find_all",
                {"selector": "#people tbody tr", "limit": 10},
            )
            limited_cards = await _call(
                server,
                "element_find_all",
                {"selector": ".product-card", "limit": 2},
            )

            snapshot_data = snapshot["data"]
            cards_data = cards["data"]
            rows_data = rows["data"]
            limited_data = limited_cards["data"]

            # 1. Summarize page identity from bounded snapshot evidence.
            assert snapshot_data["title"] == "Fixture Catalog"
            assert snapshot_data["headings"][0]["text"] == "Automation Catalog"

            # 2. Discover navigation and form controls without full-page HTML.
            assert {link["text"] for link in snapshot_data["links"]} >= {
                "Docs",
                "Pricing",
            }
            assert any(item["selector"] == "#query" for item in snapshot_data["inputs"])
            assert any(item["selector"] == "#filter-form" for item in snapshot_data["forms"])

            # 3. Extract repeated product card names.
            assert [item["text"].split()[0] for item in cards_data["elements"]] == [
                "Alpha",
                "Beta",
                "Gamma",
            ]

            # 4. Extract table rows.
            assert [item["text"] for item in rows_data["elements"]] == [
                "Ada Engineer",
                "Grace Researcher",
                "Katherine Mathematician",
            ]

            # 5. Detect truncation and keep stable selectors for follow-up actions.
            assert limited_data["count"] == 3
            assert limited_data["returned"] == 2
            assert limited_data["truncated"] is True
            assert limited_data["elements"][0]["selector"] == "#alpha"
    finally:
        await server.cleanup()


async def _call(
    server: DrissionPageMCPServer,
    name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    if server.context is None:
        server.context = DrissionPageContext()
    tool = server.tools[name]
    response = ToolResponse()
    await tool.execute(
        server.context,
        tool.input_schema.model_validate(arguments),
        response,
    )
    return response.get_structured_content()


def _skip_if_browser_unavailable(message: str) -> None:
    lowered = message.lower()
    if any(marker in lowered for marker in _BROWSER_UNAVAILABLE_MARKERS):
        if os.environ.get("DP_MCP_REQUIRE_BROWSER", "").lower() in {
            "1",
            "true",
            "yes",
        }:
            pytest.fail(
                "Chrome/Chromium browser is required but unavailable for "
                f"DrissionPage eval: {message[:300]}"
            )
        pytest.skip(
            f"Chrome/Chromium browser unavailable for DrissionPage eval: {message[:300]}"
        )
