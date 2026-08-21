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


@pytest.mark.asyncio
async def test_mcp_structured_targets_act_across_oopif_and_closed_shadow() -> None:
    """Unified targets must drive reads/actions without frame/shadow helper calls."""

    server = DrissionPageMCPServer()
    try:
        with local_http_fixture() as base_url:
            await _call(
                server,
                "page_navigate",
                {"url": base_url + "/document-boundaries"},
            )
            frame_target = {
                "kind": "accessibility",
                "role": "textbox",
                "name": "Frame Name",
                "frame_selectors": ["#oopif-frame"],
            }
            typed = await _call(
                server,
                "element_type",
                {"selector": frame_target, "text": "Ada in frame", "timeout": 3},
            )
            assert typed["target_kind"] == "accessibility"
            assert typed["frame_selectors"] == ["#oopif-frame"]
            frame_value = await _call(
                server,
                "element_get_text",
                {
                    "selector": {
                        "kind": "selector",
                        "selector": "#frame-value",
                        "frame_selectors": ["#oopif-frame"],
                    }
                },
            )
            assert frame_value["text"] == "Ada in frame"

            shadow_button = {
                "kind": "accessibility",
                "role": "button",
                "name": "Closed",
                "exact": False,
                "shadow_hosts": ["#closed-shadow-host"],
            }
            await _call(server, "element_click", {"selector": shadow_button, "timeout": 3})
            shadow_status = await _call(
                server,
                "element_get_text",
                {
                    "selector": {
                        "kind": "selector",
                        "selector": "#closed-shadow-status",
                        "shadow_hosts": ["#closed-shadow-host"],
                    }
                },
            )
            assert shadow_status["text"] == "clicked"

            state = await _call(
                server,
                "element_state_get",
                {"selector": shadow_button, "timeout": 3},
            )
            assert state["clickable"] is True
            assert state["alive"] is True
            assert state["rect"]["size"]["width"] > 0
            assert state["rect"]["coordinate_space"] == "target_document"

            accessibility = await _call(
                server,
                "page_accessibility_snapshot",
                {
                    "scope": {
                        "kind": "selector",
                        "selector": "#closed-shadow-host",
                    },
                    "max_nodes": 30,
                },
            )
            assert any(
                node["role"] == "button" and node["name"] == "Closed Action"
                for node in accessibility["nodes"]
            )
            assert accessibility["returned"] <= 30
    finally:
        await server.cleanup()


@pytest.mark.asyncio
async def test_mcp_challenge_surfaces_expose_actionability_and_parent_postcondition() -> None:
    """Cross-origin surfaces retain top-level geometry and explicit risk states."""

    server = DrissionPageMCPServer()
    try:
        with local_http_fixture() as base_url:
            await _call(server, "page_navigate", {"url": base_url + "/challenge-surfaces"})
            await _call(server, "page_resize", {"width": 800, "height": 600})
            await _call(
                server,
                "wait_for_element",
                {"selector": "#delayed-widget", "timeout": 3},
            )

            frames = await _call(server, "frame_list", {"limit": 10})
            by_id = {frame["id"]: frame for frame in frames["frames"]}
            assert {
                "normal-widget",
                "hidden-widget",
                "below-widget",
                "transformed-widget",
                "delayed-widget",
            } <= set(by_id)
            assert by_id["normal-widget"]["boundary"] == "cross_origin"
            assert by_id["normal-widget"]["document_access"] == "readable"
            assert by_id["normal-widget"]["outer"]["presentation"][
                "coordinate_actionability"
            ] == "ready"
            assert by_id["hidden-widget"]["outer"]["presentation"][
                "coordinate_actionability"
            ] == "hidden"
            assert by_id["below-widget"]["outer"]["presentation"][
                "coordinate_actionability"
            ] == "off_viewport"
            assert by_id["transformed-widget"]["outer"]["presentation"][
                "coordinate_actionability"
            ] == "transformed_3d"

            scrolled = await _call(
                server,
                "element_scroll_into_view",
                {"selector": "#below-widget", "center": True, "timeout": 3},
            )
            assert scrolled["after"]["in_viewport"] is True
            assert scrolled["after"]["rect"]["viewport_coordinate_space"] == (
                "top_level_viewport"
            )

            await _call(
                server,
                "element_scroll_into_view",
                {"selector": "#normal-widget", "center": True, "timeout": 3},
            )
            state = await _call(
                server,
                "element_state_get",
                {"selector": "#normal-widget", "timeout": 3},
            )
            location = state["rect"]["viewport_location"]
            await _call(
                server,
                "page_click_xy",
                {
                    "x": location["x"] + 32,
                    "y": location["y"] + 32,
                    "element": "fixture cross-origin challenge control",
                },
            )
            await _call(
                server,
                "wait_until",
                {
                    "condition": "text_contains",
                    "selector": "#challenge-status",
                    "value": "normal:passed",
                    "timeout": 3,
                },
            )
            postcondition = await _call(
                server,
                "element_get_text",
                {"selector": "#challenge-status"},
            )
            assert postcondition["text"] == "normal:passed"

            screenshot = await _call(server, "page_screenshot", {})
            assert screenshot["screenshot"]["mime_type"] == "image/png"
            assert screenshot["screenshot"]["bytes"] > 0
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
