"""Regression checks for the MCP Lab playground."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from urllib.request import urlopen

from playground.mcp_lab.server import local_lab_server


def test_playground_is_rebuilt_as_mcp_lab() -> None:
    """keeps playground focused on the real MCP lab instead of stale demos."""

    readme = Path("playground/README.md").read_text(encoding="utf-8")

    assert Path("playground/run_mcp_lab.py").is_file()
    assert Path("playground/mcp_lab/server.py").is_file()
    assert Path("playground/mcp_lab/runner.py").is_file()
    assert not Path("playground/quick_start.py").exists()
    assert not Path("playground/local_test.py").exists()
    assert not Path("playground/test_scenarios").exists()
    assert "MCP Lab" in readme
    assert "atomic element" in readme
    assert "commerce" in readme
    assert "social-notes" in readme
    assert "timeline" in readme


def test_mcp_lab_site_routes_are_deterministic() -> None:
    """serves local business fixtures without third-party network access."""

    with local_lab_server() as base_url:
        manifest = _json(base_url + "/api/manifest.json")

        assert manifest["name"] == "DrissionPage MCP Lab"
        assert set(manifest["scenarios"]) >= {
            "forms",
            "commerce",
            "social-notes",
            "timeline",
        }
        assert 'data-testid="commerce-search-form"' in _text(
            base_url + "/scenarios/commerce"
        )
        assert 'data-testid="note-card-note-002"' in _text(
            base_url + "/scenarios/social-notes"
        )
        assert 'data-testid="timeline-composer"' in _text(
            base_url + "/scenarios/timeline"
        )
        assert 'type="password"' in _text(base_url + "/cases/forms")


def test_mcp_lab_site_case_cli_returns_json_report() -> None:
    """runs the no-browser site smoke through the public playground CLI."""

    report = _run_lab("--case", "site", "--json")

    assert report["ok"] is True
    assert report["summary"]["passed"] >= 1
    assert report["summary"]["failed"] == 0
    assert report["cases"][0]["name"] == "site"


def test_mcp_lab_registry_case_cli_returns_json_report() -> None:
    """smokes the real stdio MCP registry path without opening a browser."""

    report = _run_lab("--case", "registry", "--json")

    assert report["ok"] is True
    assert report["summary"]["failed"] == 0
    assert report["cases"][0]["name"] == "registry"
    assert "element_type" in report["cases"][0]["details"]["tools"]


def _run_lab(*args: str) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, "playground/run_mcp_lab.py", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def _json(url: str) -> dict[str, object]:
    return json.loads(_text(url))


def _text(url: str) -> str:
    with urlopen(url, timeout=10) as response:
        return response.read().decode("utf-8")
