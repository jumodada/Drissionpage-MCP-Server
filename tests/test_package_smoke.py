"""Contracts for the clean-install package browser smoke script."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from playground import package_smoke


@dataclass
class _Result:
    structuredContent: dict[str, Any]
    isError: bool = False


class _Session:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> _Result:
        self.calls.append((name, arguments))
        if name == "page_navigate":
            return _ok({"tab_id": "tab-1", "final_url": arguments["url"]})
        if name == "page_snapshot" and "cursor" not in arguments:
            return _ok(
                {
                    "matches": [{"text": "First NEEDLE", "tag": "p"}],
                    "match_count": 2,
                    "has_more": True,
                    "next_cursor": "next-1",
                    "observation_id": "obs-1",
                    "url": "http://127.0.0.1/",
                    "title": "Package smoke",
                    "meta": {},
                }
            )
        if name == "page_snapshot":
            return _ok(
                {
                    "matches": [{"text": "Second needle", "tag": "button"}],
                    "match_count": 2,
                    "has_more": False,
                    "next_cursor": None,
                    "observation_id": "obs-1",
                    "url": "http://127.0.0.1/",
                    "title": "Package smoke",
                    "meta": {},
                }
            )
        if name == "wait_until":
            return _ok({"matched": True, "condition": "ready_state"})
        if name == "tab_close":
            return _ok({"closed": True})
        if name == "page_close":
            return _ok({"closed": True})
        raise AssertionError(name)


def _ok(data: dict[str, Any]) -> _Result:
    return _Result({"ok": True, "data": data})


@pytest.mark.asyncio
async def test_browser_flow_queries_continues_replays_and_closes() -> None:
    session = _Session()

    evidence = await package_smoke.run_browser_flow(
        session, "http://127.0.0.1:1234/"
    )

    assert evidence["match_count"] == 2
    assert evidence["matched_tags"] == ["p", "button"]
    assert session.calls == [
        ("page_navigate", {"url": "http://127.0.0.1:1234/"}),
        ("page_snapshot", {"query": "needle", "max_elements": 1}),
        (
            "page_snapshot",
            {"query": "needle", "max_elements": 1, "cursor": "next-1"},
        ),
        (
            "page_snapshot",
            {"query": "needle", "max_elements": 1, "cursor": "next-1"},
        ),
        (
            "wait_until",
            {"condition": "ready_state", "value": "complete"},
        ),
        ("tab_close", {"tab_id": "tab-1"}),
        ("page_close", {}),
    ]


def test_fixture_contains_two_distinct_needle_text_nodes() -> None:
    assert "<p>First NEEDLE</p>" in package_smoke.FIXTURE_HTML
    assert "<button type=\"button\">Second needle</button>" in package_smoke.FIXTURE_HTML


def test_protocol_surface_uses_initialize_for_absent_prompts_capability() -> None:
    initialized = SimpleNamespace(
        capabilities=SimpleNamespace(
            tools=SimpleNamespace(),
            resources=SimpleNamespace(),
            prompts=None,
        )
    )
    tools = SimpleNamespace(tools=[object()] * package_smoke.EXPECTED_TOOL_COUNT)
    resources = SimpleNamespace(
        resources=[object()] * package_smoke.EXPECTED_RESOURCE_COUNT
    )

    assert package_smoke.verify_protocol_surface(initialized, tools, resources) == {
        "tools": 69,
        "prompts": 0,
        "resources": 1,
    }


def test_protocol_surface_rejects_advertised_prompts_handler() -> None:
    initialized = SimpleNamespace(
        capabilities=SimpleNamespace(
            tools=SimpleNamespace(),
            resources=SimpleNamespace(),
            prompts=SimpleNamespace(),
        )
    )

    with pytest.raises(AssertionError, match="unexpectedly advertised prompts"):
        package_smoke.verify_protocol_surface(
            initialized,
            SimpleNamespace(tools=[object()] * package_smoke.EXPECTED_TOOL_COUNT),
            SimpleNamespace(
                resources=[object()] * package_smoke.EXPECTED_RESOURCE_COUNT
            ),
        )
