#!/usr/bin/env python3
"""Exercise a clean-installed DrissionPage MCP package through real stdio."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version as distribution_version
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import drissionpage_mcp

EXPECTED_TOOL_COUNT = 69
EXPECTED_PROMPT_COUNT = 0
EXPECTED_RESOURCE_COUNT = 1
FIXTURE_HTML = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Package smoke</title></head>
<body><p>First NEEDLE</p><button type="button">Second needle</button></body>
</html>
"""


class _FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        content = FIXTURE_HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def local_fixture() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        yield f"http://{host}:{port}/"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _tool_data(result: Any, name: str) -> dict[str, Any]:
    content = result.structuredContent or {}
    if result.isError or not content.get("ok", False):
        raise AssertionError(f"{name} failed: {json.dumps(content, ensure_ascii=False)}")
    data = content.get("data")
    if not isinstance(data, dict):
        raise AssertionError(f"{name} returned no structured data")
    return data


def _assert_snapshot_page(data: dict[str, Any], *, has_more: bool) -> list[dict[str, Any]]:
    required = {
        "matches",
        "match_count",
        "has_more",
        "next_cursor",
        "observation_id",
        "url",
        "title",
        "meta",
    }
    missing = sorted(required - data.keys())
    if missing:
        raise AssertionError(f"page_snapshot omitted fields: {missing}")
    matches = data["matches"]
    if not isinstance(matches, list) or len(matches) != 1:
        raise AssertionError("page_snapshot must return exactly one bounded match")
    if data["has_more"] is not has_more:
        raise AssertionError("page_snapshot continuation state is incorrect")
    if has_more and not data["next_cursor"]:
        raise AssertionError("page_snapshot did not provide a continuation cursor")
    return matches


async def run_browser_flow(session: ClientSession, fixture_url: str) -> dict[str, Any]:
    """Run the browser-backed part of the package acceptance scenario."""

    tab_id = ""
    try:
        navigate = _tool_data(
            await session.call_tool("page_navigate", {"url": fixture_url}),
            "page_navigate",
        )
        tab_id = str(navigate["tab_id"])

        first = _tool_data(
            await session.call_tool(
                "page_snapshot", {"query": "needle", "max_elements": 1}
            ),
            "page_snapshot",
        )
        first_matches = _assert_snapshot_page(first, has_more=True)
        if first["match_count"] != 2:
            raise AssertionError("case-insensitive literal query did not find both nodes")

        continuation_args = {
            "query": "needle",
            "max_elements": 1,
            "cursor": str(first["next_cursor"]),
        }
        second = _tool_data(
            await session.call_tool("page_snapshot", continuation_args),
            "page_snapshot",
        )
        second_matches = _assert_snapshot_page(second, has_more=False)
        replay = _tool_data(
            await session.call_tool("page_snapshot", continuation_args),
            "page_snapshot",
        )
        if replay != second:
            raise AssertionError("repeating a continuation request changed its result")

        wait = _tool_data(
            await session.call_tool(
                "wait_until", {"condition": "ready_state", "value": "complete"}
            ),
            "wait_until",
        )
        if wait.get("matched") is not True:
            raise AssertionError("ready_state did not reach complete")

        matches = first_matches + second_matches
        return {
            "match_count": first["match_count"],
            "matched_tags": [str(item.get("tag", "")) for item in matches],
            "observation_id": first["observation_id"],
        }
    finally:
        try:
            if tab_id:
                _tool_data(
                    await session.call_tool("tab_close", {"tab_id": tab_id}),
                    "tab_close",
                )
        finally:
            _tool_data(await session.call_tool("page_close", {}), "page_close")


def verify_installed_package(expected_version: str) -> dict[str, str]:
    package_path = Path(drissionpage_mcp.__file__).resolve()
    if "site-packages" not in package_path.parts:
        raise AssertionError(f"package was not imported from site-packages: {package_path}")
    metadata_version = distribution_version("drissionpage-mcp")
    versions = {metadata_version, drissionpage_mcp.__version__}
    if versions != {expected_version}:
        raise AssertionError(
            f"expected version {expected_version}, got package={metadata_version}, "
            f"module={drissionpage_mcp.__version__}"
        )
    return {"module_path": str(package_path), "version": metadata_version}


def verify_protocol_surface(
    initialized: Any,
    tools: Any,
    resources: Any,
) -> dict[str, int]:
    """Verify advertised handlers before relying on their list operations."""

    capabilities = initialized.capabilities
    if capabilities.tools is None:
        raise AssertionError("stdio server did not advertise tools capability")
    if capabilities.resources is None:
        raise AssertionError("stdio server did not advertise resources capability")
    if capabilities.prompts is not None:
        raise AssertionError("stdio server unexpectedly advertised prompts capability")

    counts = (len(tools.tools), len(resources.resources))
    expected_counts = (EXPECTED_TOOL_COUNT, EXPECTED_RESOURCE_COUNT)
    if counts != expected_counts:
        raise AssertionError(
            f"unexpected MCP surface counts: {counts} != {expected_counts}"
        )
    return {
        "tools": counts[0],
        "prompts": EXPECTED_PROMPT_COUNT,
        "resources": counts[1],
    }


async def run_smoke(expected_version: str) -> dict[str, Any]:
    package = verify_installed_package(expected_version)
    with tempfile.TemporaryDirectory(prefix="drissionpage-mcp-smoke-") as temp_dir:
        child_env = os.environ.copy()
        child_env["DP_USER_DATA_PATH"] = str(Path(temp_dir) / "browser-profile")
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "drissionpage_mcp.cli", "--log-level", "ERROR"],
            env=child_env,
            cwd=temp_dir,
        )
        with local_fixture() as fixture_url:
            async with stdio_client(params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    initialized = await session.initialize()
                    if initialized.serverInfo.version != expected_version:
                        raise AssertionError("stdio server reported an unexpected version")
                    tools = await session.list_tools()
                    resources = await session.list_resources()
                    protocol = verify_protocol_surface(initialized, tools, resources)
                    browser = await run_browser_flow(session, fixture_url)
    return {
        "ok": True,
        "package": package,
        "protocol": protocol,
        "browser": browser,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-version", default="0.8.9")
    args = parser.parse_args(argv)
    report = asyncio.run(run_smoke(args.expected_version))
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
