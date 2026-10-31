"""Unit coverage for opt-in local safety policy controls."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, Mock

import pytest

from drissionpage_mcp.context import DrissionPageContext
from drissionpage_mcp.policy import (
    ENV_ARTIFACT_ROOT,
    ENV_DENY_DOWNLOAD,
    ENV_DOWNLOAD_ROOT,
    PolicyDeniedError,
    SafetyPolicy,
    validate_artifact_root,
    validate_download_root,
    validate_external_download,
    validate_navigation,
    validate_screenshot_path,
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
    with pytest.raises(PolicyDeniedError, match="allowlist|ALLOWLIST"):
        SafetyPolicy.from_env().validate_navigation("https://blocked.test/")


@pytest.mark.parametrize(
    ("target", "allowed"),
    [
        ("https://allowed.test/app", True),
        ("https://allowed.test/app/child", True),
        ("https://allowed.test/app?x=1", True),
        ("https://allowed.test/app/my page", True),
        ("https://allowed.test/app/my%20page", True),
        ("https://allowed.test/app/café", True),
        ("https://allowed.test/app/caf%C3%A9", True),
        ("https://allowed.test/app/%70rivate", True),
        ("https://allowed.test/app/%2fprivate", True),
        ("https://allowed.test/application", False),
        ("https://allowed.test.attacker.test/app", False),
        ("https://allowed.test@attacker.test/app", False),
        ("http://allowed.test/app", False),
        ("https://allowed.test:444/app", False),
        ("https://ALLOWED.TEST:443/app", True),
        ("https://allowed.test./app", True),
        ("https://allowed.test/App", False),
        ("https://allowed.test/app/../private", False),
        ("https://allowed.test/app/%2e%2e/private", False),
        ("https://allowed.test/app%2f..%2fprivate", False),
        ("https://allowed.test/app/private page", True),
        ("https://allowed.test/app/private%20page", True),
        ("https://allowed.test:invalid/app", False),
        ("https://attacker.test\\@allowed.test/app", False),
        ("https://allowed.test/app/\\../private", False),
        ("https://[invalid/app", False),
        ("https://allowed.test:0/app", False),
        ("https://%61llowed.test/app", False),
        ("https://allowed%2etest/app", False),
        ("https://allowed．test/app", False),
        ("https://allowed.test/app;outside", False),
        ("https://allowed.test/app//../outside", True),
        ("http://127.1/app", False),
        ("http://2130706433/app", False),
        ("http://0x7f000001/app", False),
        ("http://0177.0.0.1/app", False),
        ("http://example.123/app", False),
    ],
)
def test_navigation_url_allowlist_uses_structured_origin_and_path_boundaries(
    monkeypatch, target: str, allowed: bool
) -> None:
    _clear_policy_env(monkeypatch)
    monkeypatch.setenv("DP_MCP_NAV_ALLOWLIST", "https://allowed.test/app")
    validator = SafetyPolicy.from_env().validate_navigation
    if allowed:
        validator(target)
    else:
        with pytest.raises(PolicyDeniedError):
            validator(target)


@pytest.mark.parametrize(
    "target",
    [
        "https://blocked.test.attacker.test/",
        "https://blocked.test@attacker.test/",
        "https://blocked.test:444/",
    ],
)
def test_navigation_url_blocklist_does_not_match_lookalike_origin(
    monkeypatch, target: str
) -> None:
    _clear_policy_env(monkeypatch)
    monkeypatch.setenv("DP_MCP_NAV_BLOCKLIST", "https://blocked.test/")
    SafetyPolicy.from_env().validate_navigation(target)


@pytest.mark.parametrize(
    ("pattern", "target", "allowed"),
    [
        ("https://allowed.test", "https://allowed.test.attacker.test/", False),
        ("https://allowed.test", "https://allowed.test@attacker.test/", False),
        ("https://allowed.test", "https://allowed.test:444/", False),
        ("HTTPS://ALLOWED.TEST/App", "https://allowed.test/App", True),
        ("https://allowed.test:443/", "https://allowed.test/", True),
        ("http://allowed.test:80/", "http://allowed.test/", True),
        ("https://[2001:db8::1]/app", "https://[2001:db8::1]:443/app", True),
        ("https://[2001:db8::1]/app", "https://[2001:db8::2]/app", False),
        (
            "https://[2001:db8::1]/app",
            "https://[2001:0db8:0:0:0:0:0:1]/app",
            True,
        ),
        ("https://allowed.test/app/", "https://allowed.test/app/child", True),
        ("https://allowed.test/app/", "https://allowed.test/application", False),
        ("https://allowed.test/app", "https://allowed.test/app;outside", False),
        ("https://allowed.test/app", "https://allowed.test/app//../outside", True),
        ("https://allowed.test/app//../outside", "https://allowed.test/app/outside", True),
        ("https://allowed.test/app//../outside", "https://allowed.test/outside", False),
        ("https://allowed.test/app//", "https://allowed.test/app/child", False),
        ("https://allowed.test/app/", "https://allowed.test/app/.", True),
        ("https://allowed.test/app/", "https://allowed.test/app/child/..", True),
        ("https://allowed.test/app%2ename", "https://allowed.test/app.name", True),
    ],
)
def test_navigation_url_allowlist_preserves_url_component_semantics(
    pattern: str, target: str, allowed: bool
) -> None:
    policy = SafetyPolicy(navigation_allowlist=(pattern,))
    if allowed:
        policy.validate_navigation(target)
    else:
        with pytest.raises(PolicyDeniedError):
            policy.validate_navigation(target)


@pytest.mark.parametrize(
    "target",
    ["https://blocked.test:443/app", "https://blocked.test/public/../app"],
)
def test_navigation_url_blocklist_matches_normalized_origin_and_path(target: str) -> None:
    policy = SafetyPolicy(navigation_blocklist=("https://blocked.test/app",))
    with pytest.raises(PolicyDeniedError):
        policy.validate_navigation(target)


@pytest.mark.parametrize(
    ("pattern", "target"),
    [
        ("private page", "private page"),
        ("private page", "private%20page"),
        ("private", "%70rivate"),
        ("pRIVATE", "%70RIVATE"),
        ("café", "café"),
        ("café", "caf%C3%A9"),
    ],
)
def test_navigation_url_blocklist_matches_browser_serialized_paths(
    pattern: str, target: str
) -> None:
    policy = SafetyPolicy(
        navigation_blocklist=(f"https://blocked.test/{pattern}",)
    )
    with pytest.raises(PolicyDeniedError):
        policy.validate_navigation(f"https://blocked.test/{target}")


@pytest.mark.parametrize(
    "target",
    [
        "https://%62locked.test/",
        "https://blocked．test/",
        "https://blocked。test/",
        "https://%6cocalhost/",
        "https://ｌｏｃａｌｈｏｓｔ/",
    ],
)
@pytest.mark.parametrize("mode", ["url_blocklist", "host_blocklist", "private"])
def test_active_navigation_policy_rejects_noncanonical_host_spellings(
    target: str, mode: str
) -> None:
    policy = SafetyPolicy(
        navigation_blocklist=("https://blocked.test/",) if mode == "url_blocklist" else
        ("blocked.test",) if mode == "host_blocklist" else (),
        block_private_network=mode == "private",
    )
    with pytest.raises(PolicyDeniedError):
        policy.validate_navigation(target)


@pytest.mark.parametrize("host", ["127.1", "2130706433", "0x7f000001", "0177.0.0.1"])
@pytest.mark.parametrize("mode", ["private", "host_blocklist", "url_blocklist", "allowlist"])
def test_active_policy_rejects_noncanonical_numeric_ipv4(host: str, mode: str) -> None:
    policy = SafetyPolicy(
        block_private_network=mode == "private",
        navigation_blocklist=("127.0.0.1",) if mode == "host_blocklist" else
        ("https://127.0.0.1/",) if mode == "url_blocklist" else (),
        navigation_allowlist=(host,) if mode == "allowlist" else (),
    )
    with pytest.raises(PolicyDeniedError):
        policy.validate_navigation(f"https://{host}/")


@pytest.mark.parametrize(
    ("pattern", "target", "blocked"),
    [
        ("https://blocked.test/app", "https://blocked.test/app//../outside", True),
        ("https://blocked.test/app//../outside", "https://blocked.test/app/outside", True),
        ("https://blocked.test/app//../outside", "https://blocked.test/outside", False),
        ("https://blocked.test/app//", "https://blocked.test/app/child", False),
        ("https://blocked.test/app", "https://blocked.test/app;outside", False),
        ("https://blocked.test/app;outside", "https://blocked.test/app;outside", True),
    ],
)
def test_navigation_url_blocklist_preserves_complete_paths_and_empty_segments(
    pattern: str, target: str, blocked: bool
) -> None:
    policy = SafetyPolicy(navigation_blocklist=(pattern,))
    if blocked:
        with pytest.raises(PolicyDeniedError):
            policy.validate_navigation(target)
    else:
        policy.validate_navigation(target)


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
        "http://127.1/",
        "http://2130706433/",
        "http://0x7f000001/",
        "http://0177.0.0.1/",
    ):
        with pytest.raises(PolicyDeniedError):
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
async def test_denied_navigation_redacts_policy_detail_value(monkeypatch) -> None:
    _clear_policy_env(monkeypatch)
    monkeypatch.setenv("DP_MCP_NAV_ALLOWLIST", "allowed.test")
    context = Mock(spec=DrissionPageContext)
    context.ensure_tab = AsyncMock()
    secret_url = (
        "https://user:password@denied.test/private?token=secret-token#fragment"
    )

    response = await navigate.execute(context, NavigateInput(url=secret_url))

    payload = response.structured_content()
    encoded = json.dumps(payload, ensure_ascii=False)
    assert payload["error"]["details"]["value"] == "<redacted>"
    assert "denied.test" not in encoded
    assert "password" not in encoded
    assert "secret-token" not in encoded
    assert "denied.test/private" not in encoded
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
async def test_navigation_failure_does_not_reflect_private_destination(
    monkeypatch,
) -> None:
    _clear_policy_env(monkeypatch)
    secret_url = "https://private.test/report?token=secret-token#section"
    tab = Mock()
    tab.navigation = Mock()
    tab.navigation.navigate = AsyncMock(
        side_effect=RuntimeError("CDP objectId=private-runtime-object")
    )
    context = Mock(spec=DrissionPageContext)
    context.ensure_tab = AsyncMock(return_value=tab)

    response = await navigate.execute(context, NavigateInput(url=secret_url))

    encoded = json.dumps(response.structured_content(), ensure_ascii=False)
    assert "private.test" not in encoded
    assert "secret-token" not in encoded
    assert "objectId" not in encoded
    assert response.structured_content()["error"]["code"] == "PAGE_NAVIGATION_FAILED"


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
    payload = response.structured_content()
    assert payload["error"]["code"] == "POLICY_DENIED"
    assert payload["error"]["details"]["value"] == "<redacted>"
    assert str(tmp_path / "outside.png") not in json.dumps(payload)
    hints = payload["error"]["details"]["hints"]
    assert any(hint.get("env") == "DP_MCP_SCREENSHOT_ROOT" for hint in hints)
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


def test_screenshot_save_resolves_relative_paths_under_configured_root(
    monkeypatch, tmp_path
) -> None:
    _clear_policy_env(monkeypatch)
    root = tmp_path / "screenshots"
    root.mkdir()
    monkeypatch.setenv("DP_MCP_SCREENSHOT_ROOT", str(root))

    resolved = SafetyPolicy.from_env().validate_screenshot_path("nested/screen.png")

    assert resolved == (root / "nested" / "screen.png").resolve()


@pytest.mark.parametrize("path", ["../escape.png", "nested/../../escape.png"])
def test_screenshot_save_rejects_relative_traversal(monkeypatch, tmp_path, path) -> None:
    _clear_policy_env(monkeypatch)
    root = tmp_path / "screenshots"
    root.mkdir()
    monkeypatch.setenv("DP_MCP_SCREENSHOT_ROOT", str(root))

    with pytest.raises(PolicyDeniedError, match="DP_MCP_SCREENSHOT_ROOT"):
        SafetyPolicy.from_env().validate_screenshot_path(path)


def test_screenshot_save_rejects_symlink_escape(monkeypatch, tmp_path) -> None:
    _clear_policy_env(monkeypatch)
    root = tmp_path / "screenshots"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "linked").symlink_to(outside, target_is_directory=True)
    monkeypatch.setenv("DP_MCP_SCREENSHOT_ROOT", str(root))

    with pytest.raises(PolicyDeniedError, match="DP_MCP_SCREENSHOT_ROOT"):
        SafetyPolicy.from_env().validate_screenshot_path("linked/escape.png")


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


def test_artifact_root_policy_requires_safe_directory(monkeypatch, tmp_path) -> None:
    _clear_policy_env(monkeypatch)
    policy = SafetyPolicy.from_env()
    with pytest.raises(PolicyDeniedError, match="DP_MCP_ARTIFACT_ROOT"):
        policy.validate_artifact_root()

    root = tmp_path / "artifacts"
    monkeypatch.setenv(ENV_ARTIFACT_ROOT, str(root))
    policy = SafetyPolicy.from_env()
    assert policy.validate_artifact_root() == root.resolve()
    assert policy.control_flags()["artifact_root"] is True
    summary = policy.public_summary()
    assert summary["controls"]["artifact_root"] == {
        "configured": True,
        "value": "<redacted>",
    }
    assert str(root) not in json.dumps(summary)


def test_artifact_root_policy_rejects_symlink_and_file(monkeypatch, tmp_path) -> None:
    _clear_policy_env(monkeypatch)
    file_root = tmp_path / "artifact-file"
    file_root.write_text("not a directory", encoding="utf-8")
    monkeypatch.setenv(ENV_ARTIFACT_ROOT, str(file_root))
    with pytest.raises(PolicyDeniedError, match="directory"):
        validate_artifact_root()

    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "artifact-link"
    link.symlink_to(target, target_is_directory=True)
    monkeypatch.setenv(ENV_ARTIFACT_ROOT, str(link))
    with pytest.raises(PolicyDeniedError, match="symlink"):
        validate_artifact_root()


def test_restricted_policy_rejects_invalid_url_and_empty_file_inputs(tmp_path) -> None:
    policy = SafetyPolicy(
        navigation_allowlist=("example.test",),
        screenshot_root=tmp_path,
        upload_root=tmp_path,
    )

    with pytest.raises(PolicyDeniedError, match="absolute http"):
        policy.validate_navigation("about:blank")
    with pytest.raises(PolicyDeniedError, match="non-empty path"):
        policy.validate_screenshot_path("")
    with pytest.raises(PolicyDeniedError, match="at least one path"):
        policy.validate_upload_paths([""])
    with pytest.raises(PolicyDeniedError, match="exist and be a file"):
        policy.validate_upload_paths([str(tmp_path / "missing.txt")])


def test_environment_policy_wrappers_enforce_configured_boundaries(
    monkeypatch, tmp_path
) -> None:
    _clear_policy_env(monkeypatch)
    monkeypatch.setenv("DP_MCP_NAV_ALLOWLIST", "example.test")
    monkeypatch.setenv("DP_MCP_SCREENSHOT_ROOT", str(tmp_path))
    monkeypatch.setenv(ENV_DOWNLOAD_ROOT, str(tmp_path))
    monkeypatch.setenv(ENV_ARTIFACT_ROOT, str(tmp_path))

    validate_navigation("https://example.test/path")
    assert validate_screenshot_path(str(tmp_path / "screen.png")) == (
        tmp_path / "screen.png"
    ).resolve()
    assert validate_download_root() == tmp_path.resolve()
    assert validate_artifact_root() == tmp_path.resolve()

    monkeypatch.setenv(ENV_DENY_DOWNLOAD, "1")
    with pytest.raises(PolicyDeniedError, match="disabled"):
        validate_external_download()


def test_policy_summary_redacts_configured_navigation_patterns() -> None:
    summary = SafetyPolicy(
        navigation_allowlist=("example.test",),
        navigation_blocklist=("blocked.test",),
    ).public_summary()

    assert summary["controls"]["navigation_allowlist"] == {
        "configured": True,
        "count": 1,
        "values": "<redacted>",
    }
    assert "example.test" not in json.dumps(summary)


def test_navigation_pattern_matching_ignores_empty_entries() -> None:
    policy = SafetyPolicy(navigation_allowlist=("", "example.test"))

    policy.validate_navigation("https://example.test/path")


def _clear_policy_env(monkeypatch) -> None:
    for name in (
        "DP_MCP_NAV_ALLOWLIST",
        "DP_MCP_NAV_BLOCKLIST",
        "DP_MCP_BLOCK_PRIVATE_NETWORK",
        "DP_MCP_SCREENSHOT_ROOT",
        "DP_MCP_UPLOAD_ROOT",
        "DP_MCP_DOWNLOAD_ROOT",
        "DP_MCP_ARTIFACT_ROOT",
        "DP_MCP_DENY_DOWNLOAD",
    ):
        monkeypatch.delenv(name, raising=False)
