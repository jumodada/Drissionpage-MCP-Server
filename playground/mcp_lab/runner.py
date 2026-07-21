"""Scenario runner for the DrissionPage MCP Lab playground."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable
from urllib.request import urlopen

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .server import local_lab_server

CaseFunc = Callable[["LabContext"], Awaitable[dict[str, Any]]]

_BROWSER_UNAVAILABLE_MARKERS = (
    "browser",
    "chrome",
    "chromium",
    "cannot find",
    "connection refused",
    "failed to initialize",
    "浏览器连接失败",
)


@dataclass
class LabContext:
    """Runtime options shared by MCP Lab cases."""

    command: str = sys.executable
    args: list[str] = field(
        default_factory=lambda: ["-m", "drissionpage_mcp.cli", "--log-level", "ERROR"]
    )
    skip_browser_if_unavailable: bool = False


@dataclass
class CaseResult:
    """Single scenario result."""

    name: str
    ok: bool
    status: str
    duration_ms: int
    details: dict[str, Any] = field(default_factory=dict)
    error: str = ""


def run_lab(
    *,
    case: str = "all",
    command: str | None = None,
    args: list[str] | None = None,
    skip_browser_if_unavailable: bool = False,
) -> dict[str, Any]:
    """Run one or more MCP Lab cases and return a JSON-serializable report."""

    context = LabContext(skip_browser_if_unavailable=skip_browser_if_unavailable)
    if command:
        context.command = command
    if args is not None:
        context.args = args

    return asyncio.run(_run_lab_async(case, context))


async def _run_lab_async(case: str, context: LabContext) -> dict[str, Any]:
    selected = _select_cases(case)
    results: list[CaseResult] = []
    started = time.perf_counter()

    for name, case_func in selected:
        case_started = time.perf_counter()
        try:
            details = await case_func(context)
            results.append(
                CaseResult(
                    name=name,
                    ok=True,
                    status="passed",
                    duration_ms=_elapsed_ms(case_started),
                    details=details,
                )
            )
        except BrowserUnavailableError as exc:
            if not context.skip_browser_if_unavailable:
                results.append(
                    CaseResult(
                        name=name,
                        ok=False,
                        status="failed",
                        duration_ms=_elapsed_ms(case_started),
                        error=str(exc),
                    )
                )
                continue
            results.append(
                CaseResult(
                    name=name,
                    ok=True,
                    status="skipped",
                    duration_ms=_elapsed_ms(case_started),
                    details={"reason": str(exc)},
                )
            )
        except Exception as exc:  # noqa: BLE001 - report every scenario failure.
            results.append(
                CaseResult(
                    name=name,
                    ok=False,
                    status="failed",
                    duration_ms=_elapsed_ms(case_started),
                    error=f"{type(exc).__name__}: {exc}",
                )
            )

    passed = sum(1 for result in results if result.status == "passed")
    skipped = sum(1 for result in results if result.status == "skipped")
    failed = sum(1 for result in results if result.status == "failed")
    return {
        "ok": failed == 0,
        "summary": {
            "passed": passed,
            "skipped": skipped,
            "failed": failed,
            "duration_ms": _elapsed_ms(started),
        },
        "cases": [result.__dict__ for result in results],
    }


async def _case_site(_context: LabContext) -> dict[str, Any]:
    with local_lab_server() as base_url:
        manifest = _read_json(base_url + "/api/manifest.json")
        routes = manifest["routes"]
        required = ["forms", "commerce", "social-notes", "timeline"]
        pages = {name: _read_text(base_url + routes[name]) for name in required}
        _assert_contains(pages["forms"], 'type="password"')
        _assert_contains(pages["commerce"], 'data-testid="commerce-search-form"')
        _assert_contains(pages["social-notes"], 'data-testid="note-card-note-002"')
        _assert_contains(pages["timeline"], 'data-testid="timeline-composer"')
        return {"base_url": base_url, "scenarios": manifest["scenarios"]}


async def _case_registry(context: LabContext) -> dict[str, Any]:
    async with _mcp_session(context) as session:
        init = await session.initialize()
        tools = await session.list_tools()
        names = sorted(tool.name for tool in tools.tools)
        required = {"page_snapshot", "element_find_all", "element_type", "wait_time"}
        missing = required - set(names)
        if missing:
            raise AssertionError(f"missing tools: {sorted(missing)}")
        wait = await session.call_tool("wait_time", {"seconds": 0})
        _assert_tool_ok(wait.structuredContent)
        return {
            "server": init.serverInfo.name,
            "version": init.serverInfo.version,
            "tool_count": len(names),
            "tools": names,
        }


async def _case_commerce(context: LabContext) -> dict[str, Any]:
    async with _mcp_session(context) as session:
        await session.initialize()
        with local_lab_server() as base_url:
            await _navigate_or_raise(session, base_url + "/scenarios/commerce")
            snapshot = await session.call_tool(
                "page_snapshot", {"max_elements": 40, "max_text_chars": 1500}
            )
            snapshot_data = _assert_tool_ok(snapshot.structuredContent)
            assert snapshot_data["title"] == "MockMall Commerce"
            assert any(
                form["selector"] == "#commerce-search-form"
                for form in snapshot_data["forms"]
            )
            cards = await session.call_tool(
                "element_find_all", {"selector": ".product-card", "limit": 10}
            )
            cards_data = _assert_tool_ok(cards.structuredContent)
            assert cards_data["count"] == 3
            names = [item["text"].split("¥")[0].strip() for item in cards_data["elements"]]
            await _close_page(session)
            return {"base_url": base_url, "products": names}


async def _case_social_notes(context: LabContext) -> dict[str, Any]:
    async with _mcp_session(context) as session:
        await session.initialize()
        with local_lab_server() as base_url:
            await _navigate_or_raise(session, base_url + "/scenarios/social-notes")
            cards = await session.call_tool(
                "element_find_all", {"selector": ".note-card", "limit": 10}
            )
            data = _assert_tool_ok(cards.structuredContent)
            assert data["count"] == 3
            assert any("Weekend market guide" in item["text"] for item in data["elements"])
            form = await session.call_tool(
                "element_find", {"selector": "#notes-search-form"}
            )
            form_data = _assert_tool_ok(form.structuredContent)
            assert form_data["element"]["tag"] == "form"
            await _close_page(session)
            return {"base_url": base_url, "notes": data["count"]}


async def _case_timeline(context: LabContext) -> dict[str, Any]:
    async with _mcp_session(context) as session:
        await session.initialize()
        with local_lab_server() as base_url:
            await _navigate_or_raise(session, base_url + "/scenarios/timeline")
            composer = await session.call_tool(
                "element_get_property",
                {"selector": "#post-text", "property": "value"},
            )
            composer_data = _assert_tool_ok(composer.structuredContent)
            assert composer_data["value"] == "Shipping MCP Lab today"
            clicked = await session.call_tool("element_click", {"selector": "#load-more-posts"})
            _assert_tool_ok(clicked.structuredContent)
            loaded = await session.call_tool("wait_for_element", {"selector": "#post-003"})
            _assert_tool_ok(loaded.structuredContent)
            posts = await session.call_tool(
                "element_find_all", {"selector": ".post", "limit": 10}
            )
            posts_data = _assert_tool_ok(posts.structuredContent)
            assert posts_data["count"] == 3
            await _close_page(session)
            return {"base_url": base_url, "posts": posts_data["count"]}


_CASES: dict[str, CaseFunc] = {
    "site": _case_site,
    "registry": _case_registry,
    "commerce": _case_commerce,
    "social-notes": _case_social_notes,
    "timeline": _case_timeline,
}


def _select_cases(case: str) -> list[tuple[str, CaseFunc]]:
    if case == "all":
        return [(name, _CASES[name]) for name in _CASES]
    if case not in _CASES:
        raise ValueError(f"unknown case {case!r}; expected one of {sorted(_CASES)} or 'all'")
    return [(case, _CASES[case])]


class BrowserUnavailableError(RuntimeError):
    """Browser-backed case could not start a local Chromium instance."""


class _mcp_session:
    def __init__(self, context: LabContext) -> None:
        self._params = StdioServerParameters(command=context.command, args=context.args)
        self._stdio_cm: Any = None
        self._session_cm: Any = None
        self._session: ClientSession | None = None

    async def __aenter__(self) -> ClientSession:
        self._stdio_cm = stdio_client(self._params)
        read_stream, write_stream = await self._stdio_cm.__aenter__()
        self._session_cm = ClientSession(read_stream, write_stream)
        self._session = await self._session_cm.__aenter__()
        return self._session

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._session_cm is not None:
            await self._session_cm.__aexit__(exc_type, exc, tb)
        if self._stdio_cm is not None:
            await self._stdio_cm.__aexit__(exc_type, exc, tb)


async def _navigate_or_raise(session: ClientSession, url: str) -> None:
    result = await session.call_tool("page_navigate", {"url": url})
    content = result.structuredContent
    if result.isError or not content.get("ok", False):
        message = json.dumps(content, ensure_ascii=False)
        if _looks_browser_unavailable(message):
            raise BrowserUnavailableError(message[:500])
        raise AssertionError(message)


def _assert_tool_ok(content: dict[str, Any]) -> dict[str, Any]:
    if not content.get("ok", False):
        message = json.dumps(content, ensure_ascii=False)
        if _looks_browser_unavailable(message):
            raise BrowserUnavailableError(message[:500])
        raise AssertionError(message)
    return content["data"]


async def _close_page(session: ClientSession) -> None:
    result = await session.call_tool("page_close", {})
    if result.structuredContent and not result.structuredContent.get("ok", False):
        raise AssertionError(result.structuredContent)


def _looks_browser_unavailable(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in _BROWSER_UNAVAILABLE_MARKERS)


def _read_json(url: str) -> dict[str, Any]:
    return json.loads(_read_text(url))


def _read_text(url: str) -> str:
    with urlopen(url, timeout=10) as response:
        return response.read().decode("utf-8")


def _assert_contains(text: str, expected: str) -> None:
    if expected not in text:
        raise AssertionError(f"expected {expected!r} in page")


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run DrissionPage MCP Lab scenarios")
    parser.add_argument("--case", default="all", choices=["all", *_CASES])
    parser.add_argument("--all", action="store_true", help="Run every MCP Lab case")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    parser.add_argument(
        "--skip-browser-if-unavailable",
        action="store_true",
        help="Treat browser startup failures as skipped browser cases",
    )
    parser.add_argument(
        "--command",
        default=None,
        help="Override MCP server command; defaults to the current Python checkout",
    )
    parser.add_argument(
        "--args",
        nargs=argparse.REMAINDER,
        help="Override MCP server args after --args",
    )
    ns = parser.parse_args(argv)

    selected_case = "all" if ns.all else ns.case
    report = run_lab(
        case=selected_case,
        command=ns.command,
        args=ns.args,
        skip_browser_if_unavailable=ns.skip_browser_if_unavailable,
    )
    if ns.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_human_report(report)
    return 0 if report["ok"] else 1


def _print_human_report(report: dict[str, Any]) -> None:
    summary = report["summary"]
    print(
        "MCP Lab: "
        f"{summary['passed']} passed, {summary['skipped']} skipped, "
        f"{summary['failed']} failed in {summary['duration_ms']}ms"
    )
    for case in report["cases"]:
        marker = "✅" if case["status"] == "passed" else "⏭️" if case["status"] == "skipped" else "❌"
        print(f"{marker} {case['name']} ({case['duration_ms']}ms)")
        if case.get("error"):
            print(f"   {case['error']}")


if __name__ == "__main__":
    raise SystemExit(main())
