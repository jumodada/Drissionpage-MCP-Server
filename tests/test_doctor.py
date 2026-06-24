"""Doctor/self-test diagnostics coverage."""

from __future__ import annotations

import json
import re

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
