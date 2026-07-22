"""Unit coverage for opt-in local safety policy controls."""

from __future__ import annotations
import json
from unittest.mock import AsyncMock, Mock
import pytest
from drissionpage_mcp.context import DrissionPageContext
from drissionpage_mcp.policy import SafetyPolicy
from drissionpage_mcp.policy import (
    ENV_DENY_DOWNLOAD,
    ENV_DOWNLOAD_ROOT,
)
from drissionpage_mcp.response_errors import ErrorCode
from drissionpage_mcp.tools.base import ToolOutcome
from drissionpage_mcp.tools.common import ScreenshotSaveInput, screenshot_save
from drissionpage_mcp.tools.files import UploadFileInput, element_upload_file
from drissionpage_mcp.tools.navigate import NavigateInput, navigate


@pytest.mark.parametrize(
    "url", ["https://example.com/path", "http://sub.example.com/path"]
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
    response = ToolOutcome()
    response = await navigate.execute(
        context, NavigateInput(url="https://denied.test/")
    )
    assert response.is_error is True
    payload = response.structured_content()
    assert payload["error"]["code"] == ErrorCode.POLICY_DENIED.value
    context.ensure_tab.assert_not_called()


@pytest.mark.asyncio
async def test_allowed_navigation_still_uses_existing_tab_flow(monkeypatch) -> None:
    _clear_policy_env(monkeypatch)
    monkeypatch.setenv("DP_MCP_NAV_ALLOWLIST", "allowed.test")
    tab = Mock()
    tab.url = "https://allowed.test/"
    tab.mcp_tab_id = "t0"
    tab.navigation = Mock()
    tab.navigation.navigate = AsyncMock()
    context = Mock(spec=DrissionPageContext)
    context.ensure_tab = AsyncMock(return_value=tab)
    response = ToolOutcome()
    response = await navigate.execute(
        context, NavigateInput(url="https://allowed.test/")
    )
    assert response.is_error is False
    context.ensure_tab.assert_awaited_once()
    tab.navigation.navigate.assert_awaited_once_with("https://allowed.test/")


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
    response = ToolOutcome()
    response = await screenshot_save.execute(
        context, ScreenshotSaveInput(path=str(tmp_path / "outside.png"))
    )
    assert response.is_error is True
    assert response.structured_content()["error"]["code"] == "POLICY_DENIED"
    hints = response.structured_content()["error"]["details"]["hints"]
    assert any((hint.get("env") == "DP_MCP_SCREENSHOT_ROOT" for hint in hints))
    context.current_tab_or_die.assert_not_called()


@pytest.mark.asyncio
async def test_screenshot_save_requires_configured_root_before_file_write(
    monkeypatch, tmp_path
) -> None:
    _clear_policy_env(monkeypatch)
    context = Mock(spec=DrissionPageContext)
    context.current_tab_or_die = Mock()
    response = ToolOutcome()
    response = await screenshot_save.execute(
        context, ScreenshotSaveInput(path=str(tmp_path / "screen.png"))
    )
    assert response.is_error is True
    payload = response.structured_content()
    assert payload["error"]["code"] == ErrorCode.POLICY_DENIED.value
    assert "DP_MCP_SCREENSHOT_ROOT" in payload["message"]
    context.current_tab_or_die.assert_not_called()


def test_screenshot_save_root_policy_allows_child_path(monkeypatch, tmp_path) -> None:
    _clear_policy_env(monkeypatch)
    monkeypatch.setenv("DP_MCP_SCREENSHOT_ROOT", str(tmp_path))
    SafetyPolicy.from_env().validate_screenshot_path(str(tmp_path / "screen.png"))


@pytest.mark.asyncio
async def test_upload_requires_configured_root_before_file_access(
    monkeypatch, tmp_path
) -> None:
    _clear_policy_env(monkeypatch)
    candidate = tmp_path / "upload.txt"
    candidate.write_text("ok", encoding="utf-8")
    context = Mock(spec=DrissionPageContext)
    context.current_tab_or_die = Mock()
    response = ToolOutcome()
    response = await element_upload_file.execute(
        context, UploadFileInput(selector="#upload", paths=[str(candidate)])
    )
    assert response.is_error is True
    payload = response.structured_content()
    assert payload["error"]["code"] == ErrorCode.POLICY_DENIED.value
    assert "DP_MCP_UPLOAD_ROOT" in payload["message"]
    context.current_tab_or_die.assert_not_called()


@pytest.mark.asyncio
async def test_upload_root_policy_blocks_outside_path_before_browser_use(
    monkeypatch, tmp_path
) -> None:
    _clear_policy_env(monkeypatch)
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("nope", encoding="utf-8")
    monkeypatch.setenv("DP_MCP_UPLOAD_ROOT", str(allowed))
    context = Mock(spec=DrissionPageContext)
    context.current_tab_or_die = Mock()
    response = ToolOutcome()
    response = await element_upload_file.execute(
        context, UploadFileInput(selector="#upload", paths=[str(outside)])
    )
    assert response.is_error is True
    payload = response.structured_content()
    assert payload["error"]["code"] == "POLICY_DENIED"
    assert str(allowed) not in json.dumps(payload)
    assert str(outside) not in json.dumps(payload)
    context.current_tab_or_die.assert_not_called()


def test_upload_root_policy_allows_existing_child_files(monkeypatch, tmp_path) -> None:
    _clear_policy_env(monkeypatch)
    monkeypatch.setenv("DP_MCP_UPLOAD_ROOT", str(tmp_path))
    candidate = tmp_path / "upload.txt"
    candidate.write_text("ok", encoding="utf-8")
    paths = SafetyPolicy.from_env().validate_upload_paths([str(candidate)])
    assert paths == [candidate.resolve()]


def test_download_policy_summary_redacts_root_and_exposes_deny_flag(
    monkeypatch, tmp_path
) -> None:
    _clear_policy_env(monkeypatch)
    monkeypatch.setenv(ENV_DOWNLOAD_ROOT, str(tmp_path))
    monkeypatch.setenv(ENV_DENY_DOWNLOAD, "1")

    policy = SafetyPolicy.from_env()
    assert policy.validate_download_root() == tmp_path.resolve()
    assert policy.control_flags()["download_root"] is True
    assert policy.control_flags()["deny_download"] is True
    summary = policy.public_summary()
    assert summary["controls"]["download_root"] == {
        "configured": True,
        "value": "<redacted>",
    }
    assert summary["controls"]["deny_download"] is True
    assert str(tmp_path) not in json.dumps(summary, ensure_ascii=False)


def _clear_policy_env(monkeypatch) -> None:
    for name in (
        "DP_MCP_NAV_ALLOWLIST",
        "DP_MCP_NAV_BLOCKLIST",
        "DP_MCP_BLOCK_PRIVATE_NETWORK",
        "DP_MCP_SCREENSHOT_ROOT",
        "DP_MCP_UPLOAD_ROOT",
        "DP_MCP_DOWNLOAD_ROOT",
        "DP_MCP_DENY_DOWNLOAD",
    ):
        monkeypatch.delenv(name, raising=False)
