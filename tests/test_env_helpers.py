"""Environment helper coverage."""

from __future__ import annotations

from drissionpage_mcp.env import env_bool, redacted_env_path


def test_env_bool_returns_default_when_missing(monkeypatch) -> None:
    monkeypatch.delenv("DP_TEST_BOOL", raising=False)

    assert env_bool("DP_TEST_BOOL") is False
    assert env_bool("DP_TEST_BOOL", default=True) is True


def test_env_bool_parses_truthy_values(monkeypatch) -> None:
    for value in ("1", "true", "TRUE", " yes ", "y", "on"):
        monkeypatch.setenv("DP_TEST_BOOL", value)
        assert env_bool("DP_TEST_BOOL") is True


def test_env_bool_parses_falsy_values(monkeypatch) -> None:
    for value in ("0", "false", "no", "n", "off", "", "random"):
        monkeypatch.setenv("DP_TEST_BOOL", value)
        assert env_bool("DP_TEST_BOOL", default=True) is False


def test_redacted_env_path_reports_missing_path_exists_false(monkeypatch, tmp_path) -> None:
    missing = tmp_path / "missing-browser"
    monkeypatch.setenv("DP_BROWSER_PATH", str(missing))

    assert redacted_env_path("DP_BROWSER_PATH") == {
        "configured": True,
        "env": "DP_BROWSER_PATH",
        "value": "<redacted>",
        "exists": False,
    }


def test_redacted_env_path_reports_existing_path(monkeypatch, tmp_path) -> None:
    browser = tmp_path / "browser"
    browser.write_text("stub")
    monkeypatch.setenv("DP_BROWSER_PATH", str(browser))

    assert redacted_env_path("DP_BROWSER_PATH") == {
        "configured": True,
        "env": "DP_BROWSER_PATH",
        "value": "<redacted>",
        "exists": True,
    }


def test_redacted_env_path_uses_first_configured_env(monkeypatch, tmp_path) -> None:
    chrome = tmp_path / "chrome"
    chrome.write_text("stub")
    monkeypatch.setenv("CHROME_PATH", str(chrome))
    monkeypatch.setenv("DP_BROWSER_PATH", str(tmp_path / "ignored"))

    assert redacted_env_path("CHROME_PATH", "DP_BROWSER_PATH") == {
        "configured": True,
        "env": "CHROME_PATH",
        "value": "<redacted>",
        "exists": True,
    }


def test_redacted_env_path_reports_unconfigured(monkeypatch) -> None:
    monkeypatch.delenv("CHROME_PATH", raising=False)
    monkeypatch.delenv("DP_BROWSER_PATH", raising=False)

    assert redacted_env_path("CHROME_PATH", "DP_BROWSER_PATH") == {
        "configured": False,
        "env": "",
        "value": "",
        "exists": False,
    }
