"""Doctor/self-test diagnostics coverage."""

from __future__ import annotations

import json
import re
from types import SimpleNamespace

import drissionpage_mcp.doctor as doctor
from drissionpage_mcp.doctor import format_diagnostics, run_diagnostics


def test_doctor_reports_versions_and_skips_browser_launch_by_default() -> None:
    report = run_diagnostics()

    assert report["ok"] is True
    check_names = {item["name"] for item in report["checks"]}
    assert {
        "python",
        "mcp_package",
        "drissionpage_package",
        "browser_launch",
    } <= check_names
    browser_launch = next(
        item for item in report["checks"] if item["name"] == "browser_launch"
    )
    assert browser_launch["ok"] is True
    assert "skipped" in browser_launch["detail"]


def test_format_diagnostics_includes_parseable_json_result() -> None:
    report = run_diagnostics()
    text = format_diagnostics(report)

    assert "DrissionPage MCP doctor" in text
    assert "### JSON_RESULT" in text
    payload = json.loads(re.search(r"```json\n(.*?)\n```", text, re.S).group(1))
    assert payload["version"] == report["version"]
    assert payload["checks"]


def test_package_version_falls_back_to_module_attribute(monkeypatch) -> None:
    def missing_distribution(_name: str) -> str:
        raise doctor.importlib.metadata.PackageNotFoundError

    monkeypatch.setattr(doctor.importlib.metadata, "version", missing_distribution)
    monkeypatch.setattr(
        doctor.importlib,
        "import_module",
        lambda _name: SimpleNamespace(__version__="9.9.9"),
    )

    assert doctor._package_version("example") == "9.9.9"


def test_package_version_reports_unavailable_when_import_fails(monkeypatch) -> None:
    def missing_distribution(_name: str) -> str:
        raise doctor.importlib.metadata.PackageNotFoundError

    def fail_import(_name: str):
        raise RuntimeError("broken import")

    monkeypatch.setattr(doctor.importlib.metadata, "version", missing_distribution)
    monkeypatch.setattr(doctor.importlib, "import_module", fail_import)

    assert doctor._package_version("example").startswith("unavailable: broken import")


def test_find_browser_uses_environment_path_and_reports_none(monkeypatch) -> None:
    monkeypatch.setenv("CHROME_PATH", "/tmp/chrome")
    monkeypatch.setattr(doctor.os.path, "exists", lambda path: path == "/tmp/chrome")

    assert doctor._find_browser() == "/tmp/chrome"

    monkeypatch.delenv("CHROME_PATH", raising=False)
    monkeypatch.delenv("DP_BROWSER_PATH", raising=False)
    monkeypatch.setattr(doctor.shutil, "which", lambda _name: None)
    monkeypatch.setattr(doctor.os.path, "exists", lambda _path: False)
    monkeypatch.setattr(doctor.sys, "platform", "linux")

    assert doctor._find_browser() is None


def test_run_diagnostics_reports_actionable_hints_for_old_python_and_no_browser(
    monkeypatch,
) -> None:
    monkeypatch.setattr(doctor.sys, "version_info", (3, 9, 18))
    monkeypatch.setattr(doctor, "_find_browser", lambda: None)

    report = doctor.run_diagnostics()

    assert report["ok"] is False
    assert "Use Python 3.10 or newer." in report["hints"]
    assert any("Install Chrome/Chromium" in hint for hint in report["hints"])


def test_run_diagnostics_warns_when_chrome_sandbox_is_disabled(monkeypatch) -> None:
    monkeypatch.setenv("DP_NO_SANDBOX", "1")
    monkeypatch.setattr(doctor, "_find_browser", lambda: "/tmp/chrome")

    report = doctor.run_diagnostics()

    assert report["ok"] is True
    assert any("Chrome sandbox is disabled" in hint for hint in report["hints"])


def test_run_diagnostics_launch_browser_success_and_failure(monkeypatch) -> None:
    class FakeCompat:
        def __init__(self, fail: bool = False) -> None:
            self.fail = fail
            self.quit_calls = []

        def create_browser(self):
            if self.fail:
                raise RuntimeError("launch failed")
            return object()

        def quit_browser(self, browser) -> None:
            self.quit_calls.append(browser)

    compat = FakeCompat()
    monkeypatch.setitem(
        __import__("sys").modules,
        "drissionpage_mcp.compat",
        SimpleNamespace(
            create_browser=compat.create_browser,
            quit_browser=compat.quit_browser,
        ),
    )

    success = doctor.run_diagnostics(launch_browser=True)

    assert success["ok"] is True
    launch = next(item for item in success["checks"] if item["name"] == "browser_launch")
    assert launch == {"name": "browser_launch", "ok": True, "detail": "launched successfully"}
    assert compat.quit_calls

    failing_compat = FakeCompat(fail=True)
    monkeypatch.setitem(
        __import__("sys").modules,
        "drissionpage_mcp.compat",
        SimpleNamespace(
            create_browser=failing_compat.create_browser,
            quit_browser=failing_compat.quit_browser,
        ),
    )

    failure = doctor.run_diagnostics(launch_browser=True)

    assert failure["ok"] is False
    launch = next(item for item in failure["checks"] if item["name"] == "browser_launch")
    assert launch["ok"] is False
    assert "RuntimeError: launch failed" in launch["detail"]
    assert any("Browser launch failed" in hint for hint in failure["hints"])


def test_format_diagnostics_includes_hints() -> None:
    text = doctor.format_diagnostics(
        {
            "ok": False,
            "version": "0.test",
            "platform": {},
            "checks": [{"name": "browser", "ok": False, "detail": "missing"}],
            "hints": ["Install Chromium"],
        }
    )

    assert "hints:" in text
    assert "  - Install Chromium" in text
