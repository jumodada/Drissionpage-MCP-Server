"""Real Chromium evidence for opt-in snapshot search and continuation."""

import asyncio
import os

import pytest

from drissionpage_mcp.server import DrissionPageMCPServer
from tests.fixtures.http_fixture import local_http_fixture


async def call(server, name, args):
    result = (await server._call_tool_impl(name, args)).structuredContent
    if result.get("error", {}).get("code") == "BROWSER_START_FAILED" and not os.getenv(
        "DP_MCP_REQUIRE_BROWSER"
    ):
        pytest.skip("Chromium is unavailable")
    assert result["ok"], result
    return result["data"]


@pytest.mark.asyncio
async def test_query_scans_beyond_excerpt_and_replays_an_immutable_page():
    server = DrissionPageMCPServer()
    try:
        with local_http_fixture() as url:
            await call(server, "page_navigate", {"url": url})
            await call(
                server,
                "page_evaluate",
                {
                    "script": """
                document.body.innerHTML = '<p>' + 'ordinary '.repeat(600) + '</p>' +
                  '<p id="first">中文 Needle first</p><button id="second">needle second</button>' +
                  '<p hidden>needle hidden</p><textarea>needle private-value</textarea>' +
                  '<input value="needle private-input"><script>needle private-script<\\/script>';
                return true;
            """
                },
            )
            old = await call(server, "page_snapshot", {"max_text_chars": 100})
            assert "Needle" not in old["text_excerpt"]
            args = {"query": "needle", "max_elements": 1, "max_text_chars": 100}
            first = await call(server, "page_snapshot", args)
            assert first["match_count"] == 2
            assert first["matches"][0]["selector"] == "#first"
            assert first["scan"]["truncated"] is False
            await call(
                server,
                "page_evaluate",
                {
                    "script": "document.querySelector('#second').textContent='changed'; return true;"
                },
            )
            continuation = {**args, "cursor": first["next_cursor"]}
            second = await call(server, "page_snapshot", continuation)
            assert second == await call(server, "page_snapshot", continuation)
            assert second["matches"][0]["text"] == "needle second"
            assert second["has_more"] is False
            assert "private" not in str(first) + str(second)
            fresh = await call(server, "page_snapshot", args)
            assert fresh["match_count"] == 1
            assert fresh["observation_id"] != first["observation_id"]
            await call(server, "page_navigate", {"url": url})
            stale = (
                await server._call_tool_impl("page_snapshot", continuation)
            ).structuredContent
            assert stale["error"]["code"] == "SNAPSHOT_CURSOR_INVALID"
    finally:
        await server.cleanup()


@pytest.mark.asyncio
async def test_query_cursor_cannot_cross_tabs_and_close_discards_cache():
    server = DrissionPageMCPServer()
    try:
        with local_http_fixture() as url:
            first_tab = await call(server, "page_navigate", {"url": url})
            await call(
                server,
                "page_evaluate",
                {
                    "script": "document.body.innerHTML='<p>needle one</p><p>needle two</p>'; return true;"
                },
            )
            args = {"query": "needle", "max_elements": 1, "max_text_chars": 100}
            first = await call(server, "page_snapshot", args)
            second_tab = await call(
                server, "page_navigate", {"url": url, "new_tab": True}
            )
            cross = (
                await server._call_tool_impl(
                    "page_snapshot",
                    {
                        **args,
                        "cursor": first["next_cursor"],
                        "tab_id": second_tab["tab_id"],
                    },
                )
            ).structuredContent
            assert cross["error"]["code"] == "SNAPSHOT_CURSOR_INVALID"
            resumed = await call(
                server,
                "page_snapshot",
                {**args, "cursor": first["next_cursor"], "tab_id": first_tab["tab_id"]},
            )
            assert resumed["matches"][0]["text"] == "needle two"
            await call(server, "tab_close", {"tab_id": first_tab["tab_id"]})
            assert server.context.snapshots.size_bytes == 0
    finally:
        await server.cleanup()


@pytest.mark.asyncio
async def test_navigation_evidence_matches_target_across_thirty_navigations():
    server = DrissionPageMCPServer()
    try:
        with local_http_fixture() as url:
            for index in range(30):
                path = ("/", "/redirect", "/status/404")[index % 3]
                result = await call(
                    server,
                    "page_navigate",
                    {
                        "url": url + path,
                        "timeout": 5,
                        "observe": index == 0,
                    },
                )
                current = await call(
                    server, "page_get_url", {"tab_id": result["tab_id"]}
                )
                assert result["final_url"] == current["url"]
                assert result["ready_state"] in {"interactive", "complete"}
                assert result["settled"] is True
                assert 0 <= result["navigation_ms"] <= result["total_ms"]
                assert 0 <= result["settle_ms"] <= result["total_ms"]
                assert (
                    result["navigation_ms"] + result["settle_ms"] <= result["total_ms"]
                )
    finally:
        await server.cleanup()


@pytest.mark.asyncio
async def test_navigation_reports_a_delayed_client_redirect_from_its_target_tab():
    server = DrissionPageMCPServer()
    try:
        with local_http_fixture() as url:
            result = await call(
                server,
                "page_navigate",
                {"url": url + "/client-redirect", "timeout": 5},
            )
            await call(
                server,
                "wait_until",
                {
                    "condition": "url_contains",
                    "value": "/redirect-target",
                    "tab_id": result["tab_id"],
                    "timeout": 2,
                },
            )
            current = await call(
                server, "page_get_url", {"tab_id": result["tab_id"]}
            )
            assert current["url"].endswith("/redirect-target")
            assert result["final_url"].endswith("/redirect-target")
    finally:
        await server.cleanup()


@pytest.mark.asyncio
async def test_delayed_new_tab_does_not_replace_navigation_target():
    server = DrissionPageMCPServer()
    try:
        with local_http_fixture() as url:
            result = await call(
                server,
                "page_navigate",
                {"url": url + "/delayed-new-tab", "timeout": 5},
            )
            await call(
                server,
                "wait_until",
                {
                    "condition": "present",
                    "selector": "#opener",
                    "tab_id": result["tab_id"],
                    "timeout": 2,
                },
            )
            for _ in range(20):
                tabs = await call(server, "tab_list", {})
                if any(tab["url"].endswith("/new-tab") for tab in tabs["tabs"]):
                    break
                await asyncio.sleep(0.05)
            else:
                pytest.fail("delayed new tab was not discovered")
            current = await call(
                server, "page_get_url", {"tab_id": result["tab_id"]}
            )
            assert current["url"].endswith("/delayed-new-tab")
    finally:
        await server.cleanup()


@pytest.mark.asyncio
async def test_dynamic_wait_timeout_does_not_block_another_tab_and_can_recover():
    server = DrissionPageMCPServer()
    try:
        with local_http_fixture() as url:
            first = await call(server, "page_navigate", {"url": url})
            second = await call(server, "page_navigate", {"url": url, "new_tab": True})
            tab_id = first["tab_id"]
            await call(
                server,
                "page_evaluate",
                {
                    "tab_id": tab_id,
                    "script": """
                document.body.innerHTML='<div id="moving">Moving</div>';
                document.querySelector('#moving').animate([
                    {transform:'translateX(0px)'}, {transform:'translateX(200px)'}
                ], {duration:1000, iterations:Infinity, direction:'alternate'});
                setTimeout(() => {
                    const p = document.createElement('p'); p.id='later';
                    p.textContent='Ready'; document.body.appendChild(p);
                }, 50);
                return true;
            """,
                },
            )
            present = await call(
                server,
                "wait_until",
                {
                    "condition": "present",
                    "selector": "#later",
                    "timeout": 2,
                    "tab_id": tab_id,
                },
            )
            assert present["matched"] is True
            pending = asyncio.create_task(
                server._call_tool_impl(
                    "wait_until",
                    {
                        "condition": "stable",
                        "selector": "#moving",
                        "stable_ms": 300,
                        "timeout": 0.4,
                        "tab_id": tab_id,
                    },
                )
            )
            await asyncio.sleep(0.03)
            other = await asyncio.wait_for(
                server._call_tool_impl(
                    "page_get_url",
                    {
                        "tab_id": second["tab_id"],
                    },
                ),
                timeout=0.3,
            )
            assert other.structuredContent["ok"] is True
            result = (await pending).structuredContent
            assert result["error"]["code"] == "TIMEOUT"
            await call(
                server,
                "page_evaluate",
                {
                    "tab_id": tab_id,
                    "script": """
                document.getAnimations().forEach(animation => animation.cancel());
                document.querySelector('#later').remove(); return true;
            """,
                },
            )
            for condition, selector in [("stable", "#moving"), ("detached", "#later")]:
                result = await call(
                    server,
                    "wait_until",
                    {
                        "condition": condition,
                        "selector": selector,
                        "tab_id": tab_id,
                        "timeout": 2,
                        "stable_ms": 100,
                    },
                )
                assert result["matched"] is True
    finally:
        await server.cleanup()


@pytest.mark.asyncio
async def test_cancelled_wait_releases_its_tab_for_close_without_blocking_another_tab():
    server = DrissionPageMCPServer()
    try:
        with local_http_fixture() as url:
            first = await call(server, "page_navigate", {"url": url})
            second = await call(server, "page_navigate", {"url": url, "new_tab": True})
            waiting = asyncio.create_task(
                server._call_tool_impl(
                    "wait_until",
                    {
                        "condition": "url_contains",
                        "value": "/never-arrives",
                        "tab_id": first["tab_id"],
                        "timeout": 5,
                    },
                )
            )
            await asyncio.sleep(0.05)
            closing = asyncio.create_task(
                server._call_tool_impl("tab_close", {"tab_id": first["tab_id"]})
            )
            await asyncio.sleep(0.02)
            assert not closing.done()
            waiting.cancel()
            with pytest.raises(asyncio.CancelledError):
                await waiting
            closed = await asyncio.wait_for(closing, timeout=2)
            assert closed.structuredContent["ok"] is True
            other = await call(server, "page_get_url", {"tab_id": second["tab_id"]})
            assert other["url"].endswith("/")
    finally:
        await server.cleanup()
