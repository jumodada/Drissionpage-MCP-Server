"""Browser integration tests using the deterministic local HTTP fixture."""

from __future__ import annotations

import base64
import json
import os
from typing import Any, Dict, List, Tuple
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import urlopen

import pytest

from drissionpage_mcp.response import ToolResponse
from drissionpage_mcp.server import DrissionPageMCPServer
from tests.fixtures.http_fixture import local_http_fixture

SHARED_TEST_SITE_URL_ENV = "DP_TEST_SITE_URL"


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
        assert "Observable Workflow" in _read(base_url + "/observable")[1]
        assert "New Tab Target" in _read(base_url + "/new-tab")[1]
        assert "Automation Catalog" in _read(base_url + "/catalog")[1]
        assert "Link Heavy Page" in _read(base_url + "/link-heavy")[1]
        assert "Console Workflow" in _read(base_url + "/console")[1]
        assert _read(base_url + "/redirect")[0] == 200
        assert _read(base_url + "/status/404")[0] == 404
        assert _read(base_url + "/status/500")[0] == 500
        assert "Iframe Content" in _read(base_url + "/iframe")[1]
        assert "Upload Workflow" in _read(base_url + "/upload")[1]
        assert "Interaction Workflow" in _read(base_url + "/interactions")[1]
        assert "shadow-host" in _read(base_url + "/shadow")[1]
        assert "Storage Workflow" in _read(base_url + "/storage")[1]


def test_shared_drissionpage_test_site_contract_when_configured() -> None:
    """verifies the external shared SSR test-site contract before MCP smoke."""

    base_url = _shared_test_site_url_or_skip()

    health = _json(_site_url(base_url, "/api/health.json"))
    assert health["ok"] is True
    assert health["service"] == "drissionpage-ssr-test-site"

    manifest = _json(_site_url(base_url, "/api/manifest.json"))
    assert manifest["ok"] is True
    case_ids = {item["id"] for item in manifest["cases"]}
    assert {
        "forms",
        "locators",
        "marketplace-flow",
        "social-notes-mobile",
    } <= case_ids


def test_shared_drissionpage_test_site_url_preserves_private_query() -> None:
    """keeps secret query tokens when building shared fixture case URLs."""

    base_url = "https://fixture.example.test/base?x-vercel-protection-bypass=secret"

    assert _site_url(base_url, "/cases/forms") == (
        "https://fixture.example.test/base/cases/forms"
        "?x-vercel-protection-bypass=secret"
    )


@pytest.mark.asyncio
async def test_mcp_browser_tools_use_shared_drissionpage_test_site() -> None:
    """runs MCP browser tools against the shared Astro SSR test-site."""

    base_url = _shared_test_site_url_or_skip()
    server = DrissionPageMCPServer()
    try:
        navigate = await _execute_tool_text(
            server, "page_navigate", {"url": _site_url(base_url, "/cases/forms")}
        )
        _skip_if_browser_unavailable(navigate)
        assert "Successfully navigated" in navigate

        _content, forms_payload = await _execute_tool(
            server,
            "form_inspect",
            {"selector": "#profile-form", "include_values": True},
        )
        assert forms_payload["ok"] is True
        assert forms_payload["data"]["count"] == 1
        form = forms_payload["data"]["forms"][0]
        assert form["selector"] == "#profile-form"
        assert form["method"] == "post"
        assert form["action"].endswith("/api/echo.json")
        fields = {field["selector"]: field for field in form["fields"]}
        assert fields["#name"]["value"] == "initial"
        assert fields["#mode"]["tag"] == "select"
        assert fields["#agree"]["type"] == "checkbox"

        navigate = await _execute_tool_text(
            server, "page_navigate", {"url": _site_url(base_url, "/cases/locators")}
        )
        _skip_if_browser_unavailable(navigate)
        _content, target_payload = await _execute_tool(
            server, "element_find", {"selector": "#target", "timeout": 3}
        )
        assert target_payload["ok"] is True
        target = target_payload["data"]["element"]
        assert target["text"] == "target div"
        assert 'data-testid="xpath-target"' in target["html"]

        navigate = await _execute_tool_text(
            server,
            "page_navigate",
            {"url": _site_url(base_url, "/scenarios/marketplace")},
        )
        _skip_if_browser_unavailable(navigate)
        _content, snapshot_payload = await _execute_tool(
            server, "page_snapshot", {"max_elements": 40, "max_text_chars": 1500}
        )
        assert snapshot_payload["ok"] is True
        snapshot = snapshot_payload["data"]
        assert snapshot["title"] == "Marketplace full flow"
        assert "橙市集" in snapshot["text_excerpt"]

        _content, cards_payload = await _execute_tool(
            server,
            "element_find_all",
            {"selector": '[data-testid="marketplace-home-card"]', "limit": 3},
        )
        assert cards_payload["ok"] is True
        assert cards_payload["data"]["count"] >= 12
        assert cards_payload["data"]["returned"] == 3
    finally:
        await server.cleanup()


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
async def test_mcp_tab_tools_discover_target_blank_tabs() -> None:
    """discovers, switches, and closes a tab opened by target=_blank."""

    server = DrissionPageMCPServer()
    try:
        with local_http_fixture() as base_url:
            navigate = await _execute_tool_text(
                server, "page_navigate", {"url": base_url + "/"}
            )
            _skip_if_browser_unavailable(navigate)
            assert "Successfully navigated" in navigate

            _content, initial_tabs = await _execute_tool(server, "tab_list", {})
            assert initial_tabs["ok"] is True
            initial_count = initial_tabs["data"]["count"]
            active_id = initial_tabs["data"]["active_tab_id"]

            _content, click_payload = await _execute_tool(
                server, "element_click", {"selector": "#new-tab-link", "timeout": 2}
            )
            assert click_payload["ok"] is True

            _content, tabs_payload = await _execute_tool(server, "tab_list", {})
            assert tabs_payload["ok"] is True
            tabs_data = tabs_payload["data"]
            assert tabs_data["count"] >= initial_count + 1
            target_tabs = [
                tab for tab in tabs_data["tabs"] if tab["url"].endswith("/new-tab")
            ]
            assert target_tabs
            new_tab_id = target_tabs[0]["id"]

            _content, switch_payload = await _execute_tool(
                server, "tab_switch", {"tab_id": new_tab_id}
            )
            assert switch_payload["ok"] is True

            _content, url_payload = await _execute_tool(server, "page_get_url", {})
            assert url_payload["data"]["url"].endswith("/new-tab")

            _content, close_payload = await _execute_tool(
                server, "tab_close", {"tab_id": new_tab_id}
            )
            assert close_payload["ok"] is True

            _content, switch_back = await _execute_tool(
                server, "tab_switch", {"tab_id": active_id}
            )
            assert switch_back["ok"] is True
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
async def test_mcp_observable_actions_cover_dynamic_business_flow() -> None:
    """uses observable tools to wait for and verify a delayed UI action."""

    server = DrissionPageMCPServer()
    try:
        with local_http_fixture() as base_url:
            navigate = await _execute_tool_text(
                server, "page_navigate", {"url": base_url + "/observable"}
            )
            _skip_if_browser_unavailable(navigate)
            assert "Successfully navigated" in navigate

            _content, clickable_payload = await _execute_tool(
                server,
                "wait_until",
                {"condition": "clickable", "selector": "#delayed", "timeout": 3},
            )
            assert clickable_payload["ok"] is True
            assert clickable_payload["data"]["state"]["disabled"] is False

            _content, hidden_payload = await _execute_tool(
                server,
                "wait_until",
                {"condition": "hidden", "selector": "#spinner", "timeout": 3},
            )
            assert hidden_payload["ok"] is True

            _content, observe_payload = await _execute_tool(
                server, "page_observe", {"max_texts": 5}
            )
            assert observe_payload["ok"] is True
            assert "ready" in observe_payload["data"]["text_samples"]

            _content, evaluate_payload = await _execute_tool(
                server,
                "page_evaluate",
                {"script": "return document.querySelector('#status').textContent;"},
            )
            assert evaluate_payload["ok"] is True
            assert evaluate_payload["data"]["result"] == "ready"

            _content, click_payload = await _execute_tool(
                server,
                "element_click",
                {"selector": "#delayed", "timeout": 2, "observe": True},
            )
            assert click_payload["ok"] is True
            changes = click_payload["data"]["changes"]
            assert changes["url_changed"] is True
            assert "saved=1" in changes["url_after"]
            assert "Saved successfully" in changes["appeared_texts"]
    finally:
        await server.cleanup()


@pytest.mark.asyncio
async def test_mcp_console_logs_and_observe_changes_cover_action_errors() -> None:
    """reads console output and reports new action-time console errors."""

    server = DrissionPageMCPServer()
    try:
        with local_http_fixture() as base_url:
            navigate = await _execute_tool_text(
                server, "page_navigate", {"url": base_url + "/console"}
            )
            _skip_if_browser_unavailable(navigate)
            assert "Successfully navigated" in navigate

            _content, logs_payload = await _execute_tool(
                server,
                "page_console_logs",
                {"level": "all", "limit": 20},
            )
            assert logs_payload["ok"] is True
            logs = logs_payload["data"]["logs"]
            assert {"log", "warning", "error"} <= {item["level"] for item in logs}
            assert any(item["text"] == "fixture console error" for item in logs)

            _content, error_payload = await _execute_tool(
                server,
                "page_console_logs",
                {"level": "error", "limit": 20},
            )
            assert error_payload["ok"] is True
            assert error_payload["data"]["logs"]
            assert {item["level"] for item in error_payload["data"]["logs"]} == {"error"}

            cursor = logs_payload["data"]["next_cursor"]
            _content, click_payload = await _execute_tool(
                server,
                "element_click",
                {"selector": "#console-action", "timeout": 2, "observe": True},
            )
            assert click_payload["ok"] is True
            changes = click_payload["data"]["changes"]
            assert changes["console_errors_added"] >= 1
            assert any(
                item["text"] == "fixture action failed"
                for item in changes["new_console_messages"]
            )

            _content, since_payload = await _execute_tool(
                server,
                "page_console_logs",
                {"level": "all", "since": cursor, "limit": 10},
            )
            assert since_payload["ok"] is True
            assert [item["text"] for item in since_payload["data"]["logs"]] == [
                "fixture action failed"
            ]
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


@pytest.mark.asyncio
async def test_mcp_0_5_5_interaction_and_upload_tools_use_local_fixture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """exercises 0.5.5 interaction and upload tools in a real browser."""

    upload_root = tmp_path / "uploads"
    upload_root.mkdir()
    upload_file = upload_root / "fixture-upload.txt"
    upload_file.write_text("fixture upload", encoding="utf-8")
    monkeypatch.setenv("DP_MCP_UPLOAD_ROOT", str(upload_root))

    server = DrissionPageMCPServer()
    try:
        with local_http_fixture() as base_url:
            navigate = await _execute_tool_text(
                server, "page_navigate", {"url": base_url + "/upload"}
            )
            _skip_if_browser_unavailable(navigate)

            _content, upload_payload = await _execute_tool(
                server,
                "element_upload_file",
                {"selector": "#upload", "paths": [str(upload_file)], "timeout": 2},
            )
            assert upload_payload["ok"] is True
            assert upload_payload["data"]["filenames"] == ["fixture-upload.txt"]
            assert str(upload_file) not in json.dumps(upload_payload["data"])

            _content, upload_state = await _execute_tool(
                server,
                "page_evaluate",
                {
                    "script": "return document.querySelector('#upload').files[0].name;",
                },
            )
            assert upload_state["data"]["result"] == "fixture-upload.txt"

            navigate = await _execute_tool_text(
                server, "page_navigate", {"url": base_url + "/interactions"}
            )
            _skip_if_browser_unavailable(navigate)

            _content, scroll_payload = await _execute_tool(
                server, "page_scroll", {"direction": "bottom"}
            )
            assert scroll_payload["ok"] is True

            _content, into_view_payload = await _execute_tool(
                server,
                "element_scroll_into_view",
                {"selector": "#deep-target", "center": True, "timeout": 2},
            )
            assert into_view_payload["ok"] is True

            _content, hover_payload = await _execute_tool(
                server,
                "element_hover",
                {"selector": "#hover-target", "timeout": 2},
            )
            assert hover_payload["ok"] is True

            _content, select_payload = await _execute_tool(
                server,
                "element_select",
                {"selector": "#mode", "value": "advanced", "by": "value"},
            )
            assert select_payload["data"]["selected"] is True

            _content, check_payload = await _execute_tool(
                server,
                "element_check",
                {"selector": "#agree", "checked": True, "by_js": True},
            )
            assert check_payload["data"]["checked"] is True

            _content, click_payload = await _execute_tool(
                server, "element_click", {"selector": "#keyboard-input", "timeout": 2}
            )
            assert click_payload["ok"] is True

            _content, key_payload = await _execute_tool(
                server, "keyboard_press", {"keys": "XYZ", "interval": 0}
            )
            assert key_payload["ok"] is True

            _content, state_payload = await _execute_tool(
                server,
                "page_evaluate",
                {
                    "script": (
                        "return {"
                        "mode: document.querySelector('#mode').value,"
                        "checked: document.querySelector('#agree').checked,"
                        "keys: document.querySelector('#keyboard-input').value,"
                        "hovered: document.querySelector('#hover-status').textContent"
                        "};"
                    )
                },
            )
            state = state_payload["data"]["result"]
            assert state["mode"] == "advanced"
            assert state["checked"] is True
            assert state["keys"].endswith("XYZ")
            assert state["hovered"] == "hovered"
    finally:
        await server.cleanup()


@pytest.mark.asyncio
async def test_mcp_0_5_5_frame_shadow_and_storage_tools_use_local_fixture() -> None:
    """exercises iframe, shadow DOM, cookies, and storage in a real browser."""

    server = DrissionPageMCPServer()
    try:
        with local_http_fixture() as base_url:
            navigate = await _execute_tool_text(
                server, "page_navigate", {"url": base_url + "/"}
            )
            _skip_if_browser_unavailable(navigate)

            _content, frames_payload = await _execute_tool(server, "frame_list", {})
            assert frames_payload["ok"] is True
            assert frames_payload["data"]["count"] >= 1

            _content, frame_find_payload = await _execute_tool(
                server,
                "frame_find",
                {"frame_selector": "#fixture-frame", "selector": "#frame-text"},
            )
            assert frame_find_payload["data"]["element"]["text"] == "frame ready"

            _content, frame_snapshot_payload = await _execute_tool(
                server,
                "frame_snapshot",
                {"frame_selector": "#fixture-frame", "max_elements": 10},
            )
            assert "Iframe Content" in frame_snapshot_payload["data"]["text_excerpt"]

            navigate = await _execute_tool_text(
                server, "page_navigate", {"url": base_url + "/shadow"}
            )
            _skip_if_browser_unavailable(navigate)

            _content, shadow_payload = await _execute_tool(
                server,
                "shadow_find",
                {"host_selector": "#shadow-host", "selector": "#shadow-button"},
            )
            assert shadow_payload["data"]["element"]["text"] == "Shadow Action"

            _content, shadow_all_payload = await _execute_tool(
                server,
                "shadow_find_all",
                {"host_selector": "#shadow-host", "selector": ".shadow-item"},
            )
            assert shadow_all_payload["data"]["count"] == 2

            navigate = await _execute_tool_text(
                server, "page_navigate", {"url": base_url + "/storage"}
            )
            _skip_if_browser_unavailable(navigate)

            _content, cookies_payload = await _execute_tool(
                server, "browser_cookies_get", {"include_values": False}
            )
            assert cookies_payload["ok"] is True
            assert any(
                item["name"] == "fixture_cookie"
                for item in cookies_payload["data"]["cookies"]
            )
            assert all(
                item["value"] in {"", "<redacted>"}
                for item in cookies_payload["data"]["cookies"]
            )

            _content, set_payload = await _execute_tool(
                server,
                "storage_set",
                {"area": "local", "key": "mcp-mode", "value": "green"},
            )
            assert set_payload["data"] == {
                "area": "local",
                "key": "mcp-mode",
                "set": True,
            }

            _content, get_payload = await _execute_tool(
                server,
                "storage_get",
                {"area": "local", "key": "mcp-mode", "include_values": True},
            )
            assert get_payload["data"]["items"] == {"mcp-mode": "green"}

            _content, clear_payload = await _execute_tool(
                server, "storage_clear", {"area": "local", "key": "mcp-mode"}
            )
            assert clear_payload["data"]["cleared"] is True

            _content, state_payload = await _execute_tool(
                server, "storage_get", {"area": "local", "key": "mcp-mode"}
            )
            assert state_payload["data"]["items"] == {}
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


def _shared_test_site_url_or_skip() -> str:
    base_url = (os.environ.get(SHARED_TEST_SITE_URL_ENV) or "").strip()
    if base_url:
        return base_url
    pytest.skip(f"shared DrissionPage test-site requires {SHARED_TEST_SITE_URL_ENV}")


def _site_url(base_url: str, path: str = "") -> str:
    if not path:
        return base_url
    parsed = urlsplit(base_url)
    base_path = parsed.path.rstrip("/") + "/"
    base_without_query = urlunsplit(
        (parsed.scheme, parsed.netloc, base_path, "", "")
    )
    target = urljoin(base_without_query, path.lstrip("/"))
    return _merge_base_query(target, parsed.query)


def _merge_base_query(url: str, base_query: str) -> str:
    if not base_query:
        return url
    parsed = urlsplit(url)
    query = parse_qsl(parsed.query, keep_blank_values=True)
    query.extend(parse_qsl(base_query, keep_blank_values=True))
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urlencode(query),
            parsed.fragment,
        )
    )


def _json(url: str) -> Dict[str, Any]:
    return json.loads(_read(url)[1])


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
