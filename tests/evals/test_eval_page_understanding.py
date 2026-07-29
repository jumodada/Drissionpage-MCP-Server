"""Deterministic read-only evals for 0.4.9 page-understanding tools."""

from __future__ import annotations

import os
from typing import Any

import pytest

from drissionpage_mcp.context import DrissionPageContext
from drissionpage_mcp.response_errors import ErrorCode
from drissionpage_mcp.server import DrissionPageMCPServer
from drissionpage_mcp.tools.base import ToolOutcome
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
            navigate = await _call(
                server, "page_navigate", {"url": base_url + "/catalog"}
            )
            _success_data(navigate)
            snapshot = await _call(
                server, "page_snapshot", {"max_elements": 30, "max_text_chars": 1200}
            )
            cards = await _call(
                server, "element_find_all", {"selector": ".product-card", "limit": 10}
            )
            rows = await _call(
                server,
                "element_find_all",
                {"selector": "#people tbody tr", "limit": 10},
            )
            limited_cards = await _call(
                server, "element_find_all", {"selector": ".product-card", "limit": 2}
            )
            snapshot_data = _success_data(snapshot)
            cards_data = _success_data(cards)
            rows_data = _success_data(rows)
            limited_data = _success_data(limited_cards)
            assert snapshot_data["title"] == "Fixture Catalog"
            assert snapshot_data["headings"][0]["text"] == "Automation Catalog"
            assert {link["text"] for link in snapshot_data["links"]} >= {
                "Docs",
                "Pricing",
            }
            assert any(item["selector"] == "#query" for item in snapshot_data["inputs"])
            assert any(
                item["selector"] == "#filter-form" for item in snapshot_data["forms"]
            )
            assert [item["text"].split()[0] for item in cards_data["elements"]] == [
                "Alpha",
                "Beta",
                "Gamma",
            ]
            assert [item["text"] for item in rows_data["elements"]] == [
                "Ada Engineer",
                "Grace Researcher",
                "Katherine Mathematician",
            ]
            assert limited_data["count"] == 3
            assert limited_data["returned"] == 2
            assert limited_data["truncated"] is True
            assert limited_data["elements"][0]["selector"] == "#alpha"
    finally:
        await server.cleanup()


async def _call(
    server: DrissionPageMCPServer, name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    if server.context is None:
        server.context = DrissionPageContext()
    tool = server.tools[name]
    response = ToolOutcome()
    response = await tool.execute(
        server.context, tool.input_schema.model_validate(arguments)
    )
    return response.structured_content()


def _success_data(payload: dict[str, Any]) -> dict[str, Any]:
    _skip_if_browser_unavailable(payload)
    assert payload.get("ok") is True, payload
    data = payload.get("data")
    assert isinstance(data, dict), payload
    return data


def _skip_if_browser_unavailable(payload: dict[str, Any]) -> None:
    message = str(payload.get("message", ""))
    error = payload.get("error")
    code = str(error.get("code", "")) if isinstance(error, dict) else ""
    lowered = message.lower()
    if code == ErrorCode.BROWSER_START_FAILED.value or any(
        marker in lowered for marker in _BROWSER_UNAVAILABLE_MARKERS
    ):
        if os.environ.get("DP_MCP_REQUIRE_BROWSER", "").lower() in {"1", "true", "yes"}:
            pytest.fail(
                f"Chrome/Chromium browser is required but unavailable for DrissionPage eval: {message[:300]}"
            )
        pytest.skip(
            f"Chrome/Chromium browser unavailable for DrissionPage eval: {message[:300]}"
        )


def test_eval_browser_unavailable_helper_uses_error_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DP_MCP_REQUIRE_BROWSER", raising=False)
    payload = {
        "ok": False,
        "message": "Page navigation failed.",
        "error": {"code": ErrorCode.BROWSER_START_FAILED.value},
    }

    with pytest.raises(pytest.skip.Exception):
        _skip_if_browser_unavailable(payload)


def test_eval_browser_unavailable_helper_fails_when_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DP_MCP_REQUIRE_BROWSER", "1")
    payload = {
        "ok": False,
        "message": "Page navigation failed.",
        "error": {"code": ErrorCode.BROWSER_START_FAILED.value},
    }

    with pytest.raises(pytest.fail.Exception):
        _skip_if_browser_unavailable(payload)
