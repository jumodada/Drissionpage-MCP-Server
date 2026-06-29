"""Browser integration tests using the deterministic local HTTP fixture."""

from __future__ import annotations

import base64
import os
from typing import Any, Dict, List, Tuple
from urllib.request import urlopen

import pytest

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


def test_local_http_fixture_serves_required_routes() -> None:
    """serves all deterministic fixture routes without external network access."""

    with local_http_fixture() as base_url:
        assert _read(base_url + "/")[0] == 200
        assert "DrissionMCP Fixture" in _read(base_url + "/")[1]
        assert "fixture-form" in _read(base_url + "/form")[1]
        assert "dynamic-root" in _read(base_url + "/dynamic")[1]
        assert "Automation Catalog" in _read(base_url + "/catalog")[1]
        assert "Link Heavy Page" in _read(base_url + "/link-heavy")[1]
        assert _read(base_url + "/redirect")[0] == 200
        assert _read(base_url + "/status/404")[0] == 404
        assert _read(base_url + "/status/500")[0] == 500
        assert "Iframe Content" in _read(base_url + "/iframe")[1]


@pytest.mark.asyncio
async def test_mcp_browser_tools_can_read_local_fixture_page() -> None:
    """navigates to a local fixture page and reads page text through MCP tools."""

    server = DrissionPageMCPServer()
    try:
        with local_http_fixture() as base_url:
            navigate = await _execute_tool_text(
                server, "page_navigate", {"url": base_url + "/"}
            )
            _skip_if_browser_unavailable(navigate)
            assert "Successfully navigated" in navigate

            text = await _execute_tool_text(
                server, "element_get_text", {"selector": "#app"}
            )
            _skip_if_browser_unavailable(text)
            assert "DrissionMCP Fixture" in text

            frame = await _execute_tool_text(
                server,
                "element_get_attribute",
                {"selector": "#fixture-frame", "attribute": "src"},
            )
            _skip_if_browser_unavailable(frame)
            assert "/iframe" in frame

            form_nav = await _execute_tool_text(
                server, "page_navigate", {"url": base_url + "/form"}
            )
            _skip_if_browser_unavailable(form_nav)
            assert "Successfully navigated" in form_nav

            typed = await _execute_tool_text(
                server,
                "element_type",
                {"selector": "#name", "text": "Ada", "clear": True},
            )
            _skip_if_browser_unavailable(typed)
            assert "Successfully typed" in typed

            value = await _execute_tool_text(
                server,
                "element_get_property",
                {"selector": "#name", "property": "value"},
            )
            _skip_if_browser_unavailable(value)
            assert "Ada" in value

            screenshot, screenshot_payload = await _execute_tool(
                server, "page_screenshot", {}
            )
            text_content = "\n".join(
                item.text for item in screenshot if item.type == "text"
            )
            _skip_if_browser_unavailable(text_content)
            images = [item for item in screenshot if item.type == "image"]
            assert images
            assert base64.b64decode(images[0].data).startswith(b"\x89PNG")
            metadata = screenshot_payload["data"]["screenshot"]
            assert metadata["mime_type"] == "image/png"
            assert metadata["inline"] is True
            assert metadata["encoding"] == "base64"
            assert metadata["full_page"] is False
            assert metadata["bytes"] > 0
            assert metadata["width"] > 0
            assert metadata["height"] > 0

            closed = await _execute_tool_text(server, "page_close", {})
            assert "Successfully closed browser" in closed
    finally:
        await server.cleanup()


@pytest.mark.asyncio
async def test_mcp_form_inspect_extracts_form_controls() -> None:
    """inspects forms with labels and safe default value handling."""

    server = DrissionPageMCPServer()
    try:
        with local_http_fixture() as base_url:
            navigate = await _execute_tool_text(
                server, "page_navigate", {"url": base_url + "/form"}
            )
            _skip_if_browser_unavailable(navigate)
            assert "Successfully navigated" in navigate

            _content, payload = await _execute_tool(server, "form_inspect", {})
            assert payload["ok"] is True
            data = payload["data"]
            assert data["count"] == 1
            assert data["returned"] == 1
            form = data["forms"][0]
            assert form["selector"] == "#fixture-form"
            assert form["method"] == "get"
            assert form["action"].endswith("/form")
            fields = {field["selector"]: field for field in form["fields"]}
            assert fields["#name"]["label"] == "Name"
            assert fields["#name"]["name"] == "name"
            assert fields["#name"]["type"] == "text"
            assert fields["#name"]["value"] is None
            assert fields["#secret"]["label"] == "Secret"
            assert fields["#secret"]["type"] == "password"
            assert fields["#secret"]["value"] is None
            assert fields["#submit"]["tag"] == "button"
            assert fields["#submit"]["type"] == "submit"

            _content, values_payload = await _execute_tool(
                server, "form_inspect", {"selector": "#fixture-form", "include_values": True}
            )
            value_fields = {
                field["selector"]: field
                for field in values_payload["data"]["forms"][0]["fields"]
            }
            assert value_fields["#name"]["value"] == ""
            assert value_fields["#secret"]["value"] is None
            assert "value" not in value_fields["#secret"]["attributes"]
    finally:
        await server.cleanup()


@pytest.mark.asyncio
async def test_mcp_browser_tools_normalize_llm_friendly_selectors() -> None:
    """treats bare selectors as CSS and preserves explicit DrissionPage locators."""

    server = DrissionPageMCPServer()
    try:
        with local_http_fixture() as base_url:
            navigate = await _execute_tool_text(
                server, "page_navigate", {"url": base_url + "/selectors"}
            )
            _skip_if_browser_unavailable(navigate)
            assert "Successfully navigated" in navigate

            _content, h1_payload = await _execute_tool(
                server, "element_find", {"selector": "h1", "timeout": 2}
            )
            assert h1_payload["ok"] is True
            h1 = h1_payload["data"]["element"]
            assert h1["tag"] == "h1"
            assert h1["locator"] == "css:h1"
            assert h1["selector_strategy"] == "css"
            assert h1["selector_normalized"] is True

            _content, input_payload = await _execute_tool(
                server,
                "element_find",
                {"selector": "input[name='custname']", "timeout": 2},
            )
            assert input_payload["ok"] is True
            input_element = input_payload["data"]["element"]
            assert input_element["tag"] == "input"
            assert input_element["locator"] == "css:input[name='custname']"

            _content, explicit_payload = await _execute_tool(
                server, "element_find", {"selector": "tag:h1", "timeout": 2}
            )
            assert explicit_payload["ok"] is True
            explicit = explicit_payload["data"]["element"]
            assert explicit["tag"] == "h1"
            assert explicit["locator"] == "tag:h1"
            assert explicit["selector_normalized"] is False
    finally:
        await server.cleanup()


@pytest.mark.asyncio
async def test_mcp_browser_tools_complete_form_submission_flow() -> None:
    """fills and submits a local form through public MCP tools."""

    server = DrissionPageMCPServer()
    try:
        with local_http_fixture() as base_url:
            navigate = await _execute_tool_text(
                server, "page_navigate", {"url": base_url + "/form"}
            )
            _skip_if_browser_unavailable(navigate)
            assert "Successfully navigated" in navigate

            _content, field_payload = await _execute_tool(
                server, "element_find", {"selector": "#name", "timeout": 2}
            )
            assert field_payload["ok"] is True
            field = field_payload["data"]["element"]
            assert field["tag"] == "input"
            assert field["locator"] == "css:#name"
            assert field["selector_normalized"] is True

            _content, typed_payload = await _execute_tool(
                server,
                "element_type",
                {
                    "selector": "#name",
                    "text": "Ada Lovelace",
                    "clear": True,
                    "timeout": 2,
                },
            )
            assert typed_payload["ok"] is True
            assert typed_payload["data"]["typed"] is True
            assert typed_payload["data"]["cleared"] is True

            _content, value_payload = await _execute_tool(
                server,
                "element_get_property",
                {"selector": "#name", "property": "value"},
            )
            assert value_payload["ok"] is True
            assert value_payload["data"]["value"] == "Ada Lovelace"

            _content, click_payload = await _execute_tool(
                server, "element_click", {"selector": "#submit", "timeout": 2}
            )
            assert click_payload["ok"] is True
            assert click_payload["data"]["locator"] == "css:#submit"

            _content, url_payload = await _execute_tool(
                server, "wait_for_url", {"url_pattern": "name=Ada", "timeout": 3}
            )
            assert url_payload["ok"] is True
            assert "name=Ada" in url_payload["data"]["url"]

            _content, submitted_payload = await _execute_tool(
                server, "element_get_text", {"selector": "#submitted"}
            )
            assert submitted_payload["ok"] is True
            assert submitted_payload["data"]["text"] == "Ada Lovelace"
    finally:
        await server.cleanup()


@pytest.mark.asyncio
async def test_mcp_browser_tools_wait_for_dynamic_dom_content() -> None:
    """waits for deterministic JavaScript-rendered content before reading it."""

    server = DrissionPageMCPServer()
    try:
        with local_http_fixture() as base_url:
            navigate = await _execute_tool_text(
                server, "page_navigate", {"url": base_url + "/dynamic"}
            )
            _skip_if_browser_unavailable(navigate)
            assert "Successfully navigated" in navigate

            _content, wait_payload = await _execute_tool(
                server, "wait_for_element", {"selector": "#dynamic-ready", "timeout": 3}
            )
            assert wait_payload["ok"] is True
            assert wait_payload["data"] == {
                "selector": "#dynamic-ready",
                "locator": "css:#dynamic-ready",
                "selector_strategy": "css",
                "selector_normalized": True,
                "found": True,
                "timeout": 3,
            }

            _content, text_payload = await _execute_tool(
                server, "element_get_text", {"selector": "#dynamic-ready"}
            )
            assert text_payload["ok"] is True
            assert text_payload["data"]["text"] == "dynamic content ready"
    finally:
        await server.cleanup()


@pytest.mark.asyncio
async def test_mcp_page_understanding_tools_extract_catalog_outline() -> None:
    """uses 0.4.9 preview tools to inspect repeated cards and page controls."""

    server = DrissionPageMCPServer()
    try:
        with local_http_fixture() as base_url:
            navigate = await _execute_tool_text(
                server, "page_navigate", {"url": base_url + "/catalog"}
            )
            _skip_if_browser_unavailable(navigate)
            assert "Successfully navigated" in navigate

            _content, snapshot_payload = await _execute_tool(
                server,
                "page_snapshot",
                {"max_elements": 30, "max_text_chars": 1000},
            )
            assert snapshot_payload["ok"] is True
            snapshot = snapshot_payload["data"]
            assert snapshot["title"] == "Fixture Catalog"
            assert "Automation Catalog" in snapshot["text_excerpt"]
            assert snapshot["headings"][0]["selector"] == "#catalog-title"
            assert {link["text"] for link in snapshot["links"]} >= {
                "Docs",
                "Pricing",
            }
            assert any(button["text"] == "Choose Alpha" for button in snapshot["buttons"])
            assert any(input_["selector"] == "#query" for input_ in snapshot["inputs"])
            assert snapshot["limits"] == {"max_elements": 30, "max_text_chars": 1000}

            _content, cards_payload = await _execute_tool(
                server,
                "element_find_all",
                {"selector": ".product-card", "limit": 2, "include_html": True},
            )
            assert cards_payload["ok"] is True
            cards = cards_payload["data"]
            assert cards["locator"] == "css:.product-card"
            assert cards["count"] == 3
            assert cards["returned"] == 2
            assert cards["truncated"] is True
            assert [card["text"].split()[0] for card in cards["elements"]] == [
                "Alpha",
                "Beta",
            ]
            assert cards["elements"][0]["selector"] == "#alpha"
            assert "html" in cards["elements"][0]

            _content, rows_payload = await _execute_tool(
                server,
                "element_find_all",
                {"selector": "#people tbody tr", "limit": 5},
            )
            assert rows_payload["ok"] is True
            rows = rows_payload["data"]["elements"]
            assert [row["text"] for row in rows] == [
                "Ada Engineer",
                "Grace Researcher",
                "Katherine Mathematician",
            ]
    finally:
        await server.cleanup()


@pytest.mark.asyncio
async def test_mcp_page_snapshot_balances_link_heavy_pages() -> None:
    """keeps high-value controls visible when a page has many links."""

    server = DrissionPageMCPServer()
    try:
        with local_http_fixture() as base_url:
            navigate = await _execute_tool_text(
                server, "page_navigate", {"url": base_url + "/link-heavy"}
            )
            _skip_if_browser_unavailable(navigate)
            assert "Successfully navigated" in navigate

            _content, snapshot_payload = await _execute_tool(
                server,
                "page_snapshot",
                {"max_elements": 20, "max_text_chars": 1000},
            )
            assert snapshot_payload["ok"] is True
            snapshot = snapshot_payload["data"]
            returned = sum(
                len(snapshot[name])
                for name in ("headings", "links", "buttons", "inputs", "forms")
            )

            assert snapshot["counts"]["links"] == 75
            assert snapshot["counts"]["inputs"] == 1
            assert snapshot["counts"]["forms"] == 1
            assert snapshot["limits"]["max_elements"] == 20
            assert snapshot["truncated"]["elements"] is True
            assert snapshot["truncated"]["returned_elements"] == returned <= 20
            assert len(snapshot["links"]) < 20
            assert any(button["selector"] == "#search-button" for button in snapshot["buttons"])
            assert any(input_["selector"] == "#search-input" for input_ in snapshot["inputs"])
            assert any(form["selector"] == "#search-form" for form in snapshot["forms"])
    finally:
        await server.cleanup()


@pytest.mark.asyncio
async def test_mcp_browser_tools_return_structured_errors_for_bad_page_actions() -> None:
    """returns machine-readable errors for common LLM recovery paths."""

    server = DrissionPageMCPServer()
    try:
        with local_http_fixture() as base_url:
            navigate = await _execute_tool_text(
                server, "page_navigate", {"url": base_url + "/"}
            )
            _skip_if_browser_unavailable(navigate)
            assert "Successfully navigated" in navigate

            missing_content, missing_payload = await _execute_tool(
                server,
                "element_find",
                {"selector": "#never-appears", "timeout": 1},
            )
            assert missing_payload["ok"] is False
            assert missing_payload["error"]["code"] == "ELEMENT_NOT_FOUND"
            assert missing_payload["message"].startswith("Failed to find element")
            missing_hints = missing_payload["error"]["details"]["hints"]
            assert {hint.get("tool") for hint in missing_hints} >= {
                "page_snapshot",
                "element_find_all",
                "wait_for_element",
            }
            assert missing_content[0].text.startswith("### JSON_RESULT")

            _content, wait_payload = await _execute_tool(
                server,
                "wait_for_url",
                {"url_pattern": "not-in-current-url", "timeout": 0},
            )
            assert wait_payload["ok"] is False
            assert wait_payload["error"]["code"] == "TIMEOUT"
            wait_hints = wait_payload["error"]["details"]["hints"]
            assert any(hint["action"] == "increase_timeout" for hint in wait_hints)
    finally:
        await server.cleanup()


async def _execute_tool_text(
    server: DrissionPageMCPServer, name: str, arguments: Dict[str, Any]
) -> str:
    content = await _execute_tool_content(server, name, arguments)
    return "\n".join(item.text for item in content if item.type == "text")


async def _execute_tool_content(
    server: DrissionPageMCPServer, name: str, arguments: Dict[str, Any]
) -> List[Any]:
    content, _payload = await _execute_tool(server, name, arguments)
    return content


async def _execute_tool(
    server: DrissionPageMCPServer, name: str, arguments: Dict[str, Any]
) -> Tuple[List[Any], Dict[str, Any]]:
    tool = server.tools[name]
    if server.context is None:
        from drissionpage_mcp.context import DrissionPageContext

        server.context = DrissionPageContext()
    response = ToolResponse()
    validated = tool.input_schema.model_validate(arguments)
    await tool.execute(server.context, validated, response)
    return list(response.get_content()), response.get_structured_content()


def _read(url: str) -> Tuple[int, str]:
    try:
        response = urlopen(url, timeout=5)  # noqa: S310 - local fixture URL only
        return response.status, response.read().decode("utf-8")
    except Exception as exc:
        status = getattr(getattr(exc, "fp", None), "status", None) or getattr(
            exc, "code", None
        )
        body = ""
        if getattr(exc, "fp", None) is not None:
            body = exc.fp.read().decode("utf-8")
        if status is not None:
            return int(status), body
        raise


def test_browser_unavailable_helper_skips_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DP_MCP_REQUIRE_BROWSER", raising=False)

    with pytest.raises(pytest.skip.Exception):
        _skip_if_browser_unavailable("### Error\nChrome failed to initialize")


def test_browser_unavailable_helper_fails_when_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DP_MCP_REQUIRE_BROWSER", "1")

    with pytest.raises(pytest.fail.Exception):
        _skip_if_browser_unavailable("### Error\nChrome failed to initialize")


def _skip_if_browser_unavailable(text: str) -> None:
    lowered = text.lower()
    if "### Error" in text and any(
        marker in lowered for marker in _BROWSER_UNAVAILABLE_MARKERS
    ):
        if os.environ.get("DP_MCP_REQUIRE_BROWSER", "").lower() in {
            "1",
            "true",
            "yes",
        }:
            pytest.fail(
                "Chrome/Chromium browser is required but unavailable for "
                "DrissionPage integration: {0}".format(text[:300])
            )
        pytest.skip(
            "Chrome/Chromium browser unavailable for DrissionPage integration: {0}".format(
                text[:300]
            )
        )
