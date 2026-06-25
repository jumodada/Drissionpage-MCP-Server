"""Unit coverage for opt-in local safety policy controls."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from drissionpage_mcp.context import DrissionPageContext
from drissionpage_mcp.policy import SafetyPolicy
from drissionpage_mcp.response import ErrorCode, ToolResponse
from drissionpage_mcp.tools.common import ScreenshotInput, screenshot
from drissionpage_mcp.tools.navigate import NavigateInput, navigate


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/path",
        "http://sub.example.com/path",
    ],
)
def test_navigation_policy_defaults_allow_http_urls(monkeypatch, url: str) -> None:
    _clear_policy_env(monkeypatch)

    SafetyPolicy.from_env().validate_navigation(url)


def test_navigation_policy_defaults_do_not_block_non_http_urls(monkeypatch) -> None:
    _clear_policy_env(monkeypatch)

    SafetyPolicy.from_env().validate_navigation("about:blank")


def test_navigation_policy_uses_allowlist_first(monkeypatch) -> None:
    _clear_policy_env(monkeypatch)
    monkeypatch.setenv("DP_MCP_NAV_ALLOWLIST", "example.com,https://allowed.test/app")

    SafetyPolicy.from_env().validate_navigation("https://sub.example.com/page")
    SafetyPolicy.from_env().validate_navigation("https://allowed.test/app/1")

    with pytest.raises(Exception, match="allowlist|ALLOWLIST"):
        SafetyPolicy.from_env().validate_navigation("https://blocked.test/")


def test_navigation_policy_blocks_hosts_and_private_networks(monkeypatch) -> None:
    _clear_policy_env(monkeypatch)
    monkeypatch.setenv("DP_MCP_NAV_BLOCKLIST", "blocked.test")
    monkeypatch.setenv("DP_MCP_BLOCK_PRIVATE_NETWORK", "1")

    SafetyPolicy.from_env().validate_navigation("https://public.example/")

    for url in (
        "https://blocked.test/",
        "http://localhost:8000/",
        "http://127.0.0.1:8000/",
        "http://10.0.0.1/",
        "http://192.168.1.1/",
    ):
        with pytest.raises(Exception):
            SafetyPolicy.from_env().validate_navigation(url)


@pytest.mark.asyncio
async def test_denied_navigation_does_not_initialize_browser(monkeypatch) -> None:
    _clear_policy_env(monkeypatch)
    monkeypatch.setenv("DP_MCP_NAV_ALLOWLIST", "allowed.test")
    context = Mock(spec=DrissionPageContext)
    context.ensure_tab = AsyncMock()
    response = ToolResponse()

    await navigate.handler(
        context,
        NavigateInput(url="https://denied.test/"),
        response,
    )

    assert response.is_error() is True
    payload = response.get_structured_content()
    assert payload["error"]["code"] == ErrorCode.POLICY_DENIED.value
    context.ensure_tab.assert_not_called()


@pytest.mark.asyncio
async def test_allowed_navigation_still_uses_existing_tab_flow(monkeypatch) -> None:
    _clear_policy_env(monkeypatch)
    monkeypatch.setenv("DP_MCP_NAV_ALLOWLIST", "allowed.test")
    tab = Mock()
    tab.navigate = AsyncMock()
    context = Mock(spec=DrissionPageContext)
    context.ensure_tab = AsyncMock(return_value=tab)
    response = ToolResponse()

    await navigate.handler(
        context, NavigateInput(url="https://allowed.test/"), response
    )

    assert response.is_error() is False
    context.ensure_tab.assert_awaited_once()
    tab.navigate.assert_awaited_once_with("https://allowed.test/")


@pytest.mark.asyncio
async def test_screenshot_save_root_policy_blocks_path_before_file_write(
    monkeypatch, tmp_path
) -> None:
    _clear_policy_env(monkeypatch)
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    monkeypatch.setenv("DP_MCP_SCREENSHOT_ROOT", str(allowed))
    context = Mock(spec=DrissionPageContext)
    context.current_tab_or_die = Mock()
    response = ToolResponse()

    await screenshot.handler(
        context,
        ScreenshotInput(path=str(tmp_path / "outside.png")),
        response,
    )

    assert response.is_error() is True
    assert response.get_structured_content()["error"]["code"] == "POLICY_DENIED"
    context.current_tab_or_die.assert_not_called()


def test_screenshot_save_root_policy_allows_child_path(monkeypatch, tmp_path) -> None:
    _clear_policy_env(monkeypatch)
    monkeypatch.setenv("DP_MCP_SCREENSHOT_ROOT", str(tmp_path))

    SafetyPolicy.from_env().validate_screenshot_path(str(tmp_path / "screen.png"))


def _clear_policy_env(monkeypatch) -> None:
    for name in (
        "DP_MCP_NAV_ALLOWLIST",
        "DP_MCP_NAV_BLOCKLIST",
        "DP_MCP_BLOCK_PRIVATE_NETWORK",
        "DP_MCP_SCREENSHOT_ROOT",
    ):
        monkeypatch.delenv(name, raising=False)
