"""Browser-backed evidence for input and document-boundary capabilities."""

from __future__ import annotations

import os
from typing import Any

import pytest

from drissionpage_mcp.server import DrissionPageMCPServer
from tests.fixtures.http_fixture import local_http_fixture


@pytest.mark.asyncio
async def test_mcp_repeated_native_input_replaces_values_for_ten_cycles() -> None:
    """Repeated clear-plus-native-input calls must never concatenate old values."""

    server = DrissionPageMCPServer()
    try:
        with local_http_fixture() as base_url:
            await _call(server, "page_navigate", {"url": base_url + "/form-controlled"})
            for iteration in range(1, 11):
                for value in (
                    f"Ada Initial {iteration:02d}",
                    f"Ada Controlled {iteration:02d}",
                ):
                    await _type_and_assert(server, "#controlled-name", value)
                    rendered = await _call(
                        server,
                        "element_get_text",
                        {"selector": "#controlled-rendered"},
                    )
                    assert rendered["text"].startswith(f"{value}; input=")

            await _call(server, "page_navigate", {"url": base_url + "/form-validation"})
            for iteration in range(1, 11):
                await _type_and_assert(server, "#employee-code", f"bad-{iteration:02d}")
                await _type_and_assert(server, "#employee-code", f"DP-{iteration:03d}")
    finally:
        await server.cleanup()


@pytest.mark.asyncio
async def test_mcp_frame_and_shadow_tools_cross_document_boundaries() -> None:
    """Prove OOPIF and closed-shadow access through the existing public tools."""

    server = DrissionPageMCPServer()
    try:
        with local_http_fixture() as base_url:
            await _call(
                server,
                "page_navigate",
                {"url": base_url + "/document-boundaries"},
            )
            browser_boundary = await _call(
                server,
                "page_evaluate",
                {
                    "script": "const frame=document.querySelector('#oopif-frame'); const host=document.querySelector('#closed-shadow-host'); return {frameContentDocumentVisible: !!frame.contentDocument, closedShadowVisible: !!host.shadowRoot};"
                },
            )
            assert browser_boundary["result"] == {
                "frameContentDocumentVisible": False,
                "closedShadowVisible": False,
            }

            frames = await _call(server, "frame_list", {"limit": 10})
            oopif_candidates = [
                frame
                for frame in frames["frames"]
                if frame["selector"] == "#oopif-frame"
            ]
            assert len(oopif_candidates) == 1, (
                "document-boundary fixture did not expose its cross-origin frame: "
                + repr(frames)
            )
            oopif = oopif_candidates[0]
            assert oopif["url"].startswith("http://localhost:")

            target_infos = _target_infos(server)
            oopif_candidates = [
                target for target in target_infos if target.get("url") == oopif["url"]
            ]
            assert oopif_candidates, (
                "OOPIF capability unavailable or fixture target missing: "
                + repr(target_infos)
            )
            oopif_target = oopif_candidates[0]
            assert oopif_target["type"] == "iframe", oopif_target
            assert oopif_target["attached"] is True, oopif_target
            assert oopif_target.get("parentId"), oopif_target

            frame_element = await _call(
                server,
                "frame_find",
                {
                    "frame_selector": "#oopif-frame",
                    "selector": "#frame-text",
                    "timeout": 3,
                },
            )
            assert frame_element["element"]["text"] == "frame ready"
            frame_snapshot = await _call(
                server,
                "frame_snapshot",
                {
                    "frame_selector": "#oopif-frame",
                    "max_elements": 10,
                    "max_text_chars": 500,
                    "timeout": 3,
                },
            )
            assert frame_snapshot["title"] == "Fixture Iframe"
            assert "Iframe Content" in frame_snapshot["text_excerpt"]

            shadow_element = await _call(
                server,
                "shadow_find",
                {
                    "host_selector": "#closed-shadow-host",
                    "selector": "#closed-shadow-button",
                    "timeout": 3,
                },
            )
            assert shadow_element["element"]["text"] == "Closed Action"
            shadow_elements = await _call(
                server,
                "shadow_find_all",
                {
                    "host_selector": "#closed-shadow-host",
                    "selector": ".closed-shadow-item",
                    "limit": 10,
                },
            )
            assert [item["text"] for item in shadow_elements["elements"]] == [
                "Closed Alpha",
                "Closed Beta",
            ]
    finally:
        await server.cleanup()


async def _type_and_assert(
    server: DrissionPageMCPServer, selector: str, value: str
) -> None:
    await _call(
        server,
        "element_type",
        {"selector": selector, "text": value, "clear": True, "timeout": 3},
    )
    observed = await _call(
        server,
        "element_get_property",
        {"selector": selector, "property": "value"},
    )
    assert observed["value"] == value


async def _call(
    server: DrissionPageMCPServer, name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    result = await server._call_tool_impl(name, arguments)
    payload = result.structuredContent
    assert payload is not None
    if not payload["ok"] and payload["error"]["code"] == "BROWSER_START_FAILED":
        if os.environ.get("DP_MCP_REQUIRE_BROWSER", "").lower() in {
            "1",
            "true",
            "yes",
        }:
            pytest.fail(f"browser capability evidence requires Chromium: {payload}")
        pytest.skip("browser capability evidence requires Chromium")
    assert payload["ok"] is True, payload
    return payload["data"]


def _target_infos(server: DrissionPageMCPServer) -> list[dict[str, Any]]:
    assert server.context is not None
    page = server.context.current_tab_or_die().page
    response = page.run_cdp("Target.getTargets")
    targets = response.get("targetInfos")
    assert isinstance(targets, list), response
    return targets
