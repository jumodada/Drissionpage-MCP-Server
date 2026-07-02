"""MCP Resources coverage for 0.4.0 public context surfaces."""

from __future__ import annotations

import json
from typing import Any

import pytest
from mcp.types import ListResourcesRequest, ReadResourceRequest, ReadResourceRequestParams

from drissionpage_mcp.resources import (
    PAGE_HTML_EXCERPT_CHARS,
    PAGE_TEXT_EXCERPT_CHARS,
    RESOURCE_JSON_MAX_CHARS,
    _fit_resource_budget,
    _safe_string_attr,
    _truncate,
)
from drissionpage_mcp.server import DrissionPageMCPServer


RESOURCE_URIS = [
    "drissionpage://session/summary",
    "drissionpage://session/history",
    "drissionpage://page/current",
    "drissionpage://tools/catalog",
    "drissionpage://policy/summary",
]


@pytest.mark.asyncio
async def test_list_resources_is_deterministic_and_json_typed() -> None:
    server = DrissionPageMCPServer()
    handler = server.server.request_handlers[ListResourcesRequest]

    result = await handler(ListResourcesRequest(method="resources/list"))

    resources = result.root.resources
    assert [str(resource.uri) for resource in resources] == RESOURCE_URIS
    assert [resource.mimeType for resource in resources] == ["application/json"] * 5
    assert all(resource.name and resource.description for resource in resources)
    current_page = resources[2]
    assert current_page.name == "page_current"
    assert "redaction" not in current_page.description.lower()


@pytest.mark.asyncio
async def test_read_session_and_policy_resources_do_not_initialize_browser(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DP_MCP_NAV_ALLOWLIST", "example.com,allowed.test")
    monkeypatch.setenv("DP_MCP_BLOCK_PRIVATE_NETWORK", "1")

    server = DrissionPageMCPServer()

    session_payload = await _read_json(server, "drissionpage://session/summary")
    policy_payload = await _read_json(server, "drissionpage://policy/summary")
    history_payload = await _read_json(server, "drissionpage://session/history")

    assert server.context is None
    assert session_payload == {
        "available": True,
        "browser_active": False,
        "tab_count": 0,
        "current_url": "",
        "policy": {
            "profile": "restricted",
            "controls": {
                "navigation_allowlist": True,
                "navigation_blocklist": False,
                "block_private_network": True,
                "screenshot_root": False,
            },
        },
    }
    assert policy_payload["profile"] == "restricted"
    assert policy_payload["controls"]["navigation_allowlist"] == {
        "configured": True,
        "count": 2,
        "values": "<redacted>",
    }
    assert policy_payload["controls"]["block_private_network"] is True
    assert history_payload == {
        "available": True,
        "limit": 100,
        "count": 0,
        "actions": [],
    }


@pytest.mark.asyncio
async def test_read_page_current_without_active_tab_is_unavailable() -> None:
    server = DrissionPageMCPServer()

    payload = await _read_json(server, "drissionpage://page/current")

    assert payload == {
        "available": False,
        "reason": "NO_ACTIVE_TAB",
        "url": "",
        "title": "",
        "text_excerpt": "",
        "html_excerpt": "",
        "truncated": False,
        "limits": {
            "text_chars": PAGE_TEXT_EXCERPT_CHARS,
            "html_chars": PAGE_HTML_EXCERPT_CHARS,
        },
        "meta": {
            "approx_tokens": 0,
            "json_chars": 0,
            "truncated": False,
        },
    }
    assert server.context is None


@pytest.mark.asyncio
async def test_read_page_current_truncates_text_and_html() -> None:
    server = DrissionPageMCPServer()
    server.context = FakeContext(
        FakeTab(
            url="https://example.test/",
            title="Example",
            text="t" * (PAGE_TEXT_EXCERPT_CHARS + 7),
            html="<main>" + ("h" * PAGE_HTML_EXCERPT_CHARS) + "</main>",
        )
    )

    payload = await _read_json(server, "drissionpage://page/current")

    assert payload["available"] is True
    assert payload["url"] == "https://example.test/"
    assert payload["title"] == "Example"
    assert len(payload["text_excerpt"]) <= PAGE_TEXT_EXCERPT_CHARS
    assert len(payload["html_excerpt"]) <= PAGE_HTML_EXCERPT_CHARS
    assert payload["truncated"] is True
    assert payload["meta"]["approx_tokens"] > 0
    assert payload["meta"]["json_chars"] > 0
    assert payload["meta"]["truncated"] is True
    assert payload["text_truncation"] == {
        "truncated": True,
        "original_length": PAGE_TEXT_EXCERPT_CHARS + 7,
        "limit": PAGE_TEXT_EXCERPT_CHARS,
    }
    assert payload["html_truncation"]["original_length"] > PAGE_HTML_EXCERPT_CHARS
    assert len(json.dumps(payload, ensure_ascii=False, separators=(",", ":"))) <= (
        RESOURCE_JSON_MAX_CHARS
    )


@pytest.mark.asyncio
async def test_tools_catalog_matches_public_tools_and_excludes_aliases() -> None:
    server = DrissionPageMCPServer()

    payload = await _read_json(server, "drissionpage://tools/catalog")

    names = [tool["name"] for tool in payload["tools"]]
    assert len(names) == 29
    assert names == list(server.tools.keys())
    assert "page_snapshot" in names
    assert "page_observe" in names
    assert "page_console_logs" in names
    assert "page_evaluate" in names
    assert "element_find_all" in names
    assert "form_inspect" in names
    assert "wait_until" in names
    assert {"tab_list", "tab_switch", "tab_close"} <= set(names)
    assert "element_input_text" not in names
    assert "wait_sleep" not in names
    schema_by_name = {tool["name"]: tool["output_schema"] for tool in payload["tools"]}
    assert schema_by_name["page_snapshot"] == "PageSnapshotData"
    assert schema_by_name["page_observe"] == "PageObservation"
    assert schema_by_name["page_console_logs"] == "ConsoleLogsData"
    assert schema_by_name["page_evaluate"] == "PageEvaluateData"
    assert schema_by_name["element_find_all"] == "ElementFindAllData"
    assert schema_by_name["form_inspect"] == "FormInspectData"
    assert schema_by_name["wait_until"] == "WaitUntilData"
    navigate_tool = payload["tools"][0]
    assert navigate_tool == {
        "name": "page_navigate",
        "title": "Navigate to URL",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "output_schema": "PageNavigateData",
    }


@pytest.mark.asyncio
async def test_read_unknown_resource_reports_value_error() -> None:
    server = DrissionPageMCPServer()
    handler = server.server.request_handlers[ReadResourceRequest]

    with pytest.raises(ValueError, match="Unknown resource URI"):
        await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(uri="drissionpage://unknown"),
            )
        )


def test_resource_helpers_handle_budget_and_attribute_edges() -> None:
    small = {"html_excerpt": "ok", "text_excerpt": "ok", "truncated": False}
    assert _fit_resource_budget(small) is small

    large = {
        "html_excerpt": "h" * PAGE_HTML_EXCERPT_CHARS,
        "text_excerpt": "t" * PAGE_TEXT_EXCERPT_CHARS,
        "truncated": False,
    }
    fitted = _fit_resource_budget(large)
    assert fitted["truncated"] is True
    assert fitted["resource_truncation"] == {
        "truncated": True,
        "original_length": len(
            json.dumps(large, ensure_ascii=False, separators=(",", ":"))
        ),
        "limit": RESOURCE_JSON_MAX_CHARS,
    }
    assert len(json.dumps(fitted, ensure_ascii=False, separators=(",", ":"))) <= (
        RESOURCE_JSON_MAX_CHARS
    )

    value, metadata = _truncate("short", 20)
    assert value == "short"
    assert metadata == {"truncated": False, "original_length": 5, "limit": 20}

    class BrokenPage:
        @property
        def text(self):
            raise RuntimeError("detached")

    assert _safe_string_attr(BrokenPage(), "text") == ""


async def _read_json(server: DrissionPageMCPServer, uri: str) -> dict[str, Any]:
    handler = server.server.request_handlers[ReadResourceRequest]
    result = await handler(
        ReadResourceRequest(
            method="resources/read",
            params=ReadResourceRequestParams(uri=uri),
        )
    )
    contents = result.root.contents
    assert len(contents) == 1
    assert contents[0].mimeType == "application/json"
    return json.loads(contents[0].text)


class FakeContext:
    def __init__(self, tab: FakeTab) -> None:
        self._tab = tab

    def current_tab(self) -> FakeTab:
        return self._tab

    def tabs(self) -> list[FakeTab]:
        return [self._tab]

    def is_active(self) -> bool:
        return True


class FakeTab:
    def __init__(self, *, url: str, title: str, text: str, html: str) -> None:
        self.url = url
        self.page = FakePage(title=title, text=text, html=html)


class FakePage:
    def __init__(self, *, title: str, text: str, html: str) -> None:
        self.title = title
        self.text = text
        self.html = html
