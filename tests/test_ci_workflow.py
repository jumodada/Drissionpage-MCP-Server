"""CI workflow structure tests for the approved MCP usability gates."""

from __future__ import annotations

import re
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback.
    import tomli as tomllib

CI_WORKFLOW = Path(".github/workflows/ci.yml")
CODECOV_CONFIG = Path("codecov.yml")
MANIFEST = Path("MANIFEST.in")
PYPROJECT = Path("pyproject.toml")
README_FILES = (Path("README.md"), Path("README_CN.md"))


def test_ci_separates_required_quality_gates() -> None:
    """keeps lint/unit/protocol/package/browser checks as separate jobs."""

    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    job_names = set(re.findall(r"^  ([a-z0-9_-]+):\n", workflow, re.MULTILINE))

    assert {
        "lint",
        "unit",
        "protocol",
        "evals",
        "coverage",
        "package",
        "browser-integration",
    } <= job_names


def test_ci_browser_integration_is_not_manual_only() -> None:
    """runs the browser integration job on push/PR with explicit skip handling."""

    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    browser_job = workflow.split("  browser-integration:\n", maxsplit=1)[1]

    assert "github.event_name == 'workflow_dispatch'" not in browser_job
    assert "tests/test_browser_integration.py" in browser_job
    assert "chromium" in browser_job.lower()
    assert "CHROME_PATH=$BROWSER_BIN" in browser_job
    assert 'DP_HEADLESS: "1"' in browser_job


def test_ci_uploads_xml_coverage_to_codecov() -> None:
    """publishes a deterministic XML coverage report through the Codecov action."""

    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    coverage_job = workflow.split("  coverage:\n", maxsplit=1)[1].split(
        "\n  package:\n", maxsplit=1
    )[0]

    assert 'python-version: "3.11"' in coverage_job
    assert "--cov=drissionpage_mcp" in coverage_job
    assert "--cov-report=xml:coverage.xml" in coverage_job
    assert "CHROME_PATH=$BROWSER_BIN" in coverage_job
    assert 'DP_HEADLESS: "1"' in coverage_job
    assert "codecov/codecov-action@v7" in coverage_job
    assert "token: ${{ secrets.CODECOV_TOKEN }}" in coverage_job
    assert "use_oidc:" not in coverage_job
    assert "id-token: write" not in coverage_job


def test_ci_checks_wheel_package_contents() -> None:
    """prevents broad compatibility shim packages from leaking into wheels."""

    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    package_job = workflow.split("  package:\n", maxsplit=1)[1].split(
        "\n  browser-integration:\n", maxsplit=1
    )[0]

    assert "Check wheel package contents" in package_job
    assert 'top_level == ["drissionpage_mcp"]' in package_job
    assert 'name.startswith("src/")' in package_job


def test_readmes_publish_ci_and_codecov_badges() -> None:
    """shows readers the live test and coverage state from the canonical repo."""

    for readme in README_FILES:
        text = readme.read_text(encoding="utf-8")
        assert "actions/workflows/ci.yml/badge.svg?branch=main" in text
        assert "codecov.io/gh/jumodada/Drissionpage-MCP-Server" in text


def test_distribution_does_not_publish_src_compat_shim() -> None:
    """keeps the wheel focused on the canonical drissionpage_mcp package."""

    pyproject = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    packages = pyproject["tool"]["setuptools"]["packages"]
    manifest = MANIFEST.read_text(encoding="utf-8")

    assert packages == ["drissionpage_mcp", "drissionpage_mcp.tools"]
    assert "src" not in packages
    assert "recursive-include src" not in manifest
    assert not Path("src").exists()


def test_browser_jobs_require_browser_after_installing_chromium() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert 'DP_MCP_REQUIRE_BROWSER: "1"' in workflow
    coverage_job = workflow.split("  coverage:\n", maxsplit=1)[1].split(
        "\n  package:\n", maxsplit=1
    )[0]
    browser_job = workflow.split("  browser-integration:\n", maxsplit=1)[1]
    assert 'DP_MCP_REQUIRE_BROWSER: "1"' in browser_job
    assert 'DP_MCP_REQUIRE_BROWSER: "1"' in coverage_job


def test_codecov_policy_matches_current_project_baseline() -> None:
    """keeps Codecov thresholds realistic while the project grows coverage."""

    config = CODECOV_CONFIG.read_text(encoding="utf-8")

    assert "target: auto" in config
    assert "threshold: 2%" in config
    assert "target: 70%" in config
    assert "threshold: 5%" in config


def test_release_versions_are_in_sync() -> None:
    """keeps package metadata, runtime version, and README examples aligned."""

    import drissionpage_mcp

    pyproject = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    version = pyproject["project"]["version"]

    assert version == "0.4.5"
    assert drissionpage_mcp.__version__ == version
    for readme in README_FILES:
        text = readme.read_text(encoding="utf-8")
        assert "0.3.0" not in text
        assert f"drissionpage-mcp {version}" in text


def test_ci_runs_0_4_0_resource_prompt_and_eval_gates() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "tests/test_mcp_resources.py" in workflow
    assert "tests/test_mcp_prompts.py" in workflow
    assert "python -m pytest tests/evals -q" in workflow


def test_security_policy_and_release_checklist_document_0_4_0_controls() -> None:
    security = Path("SECURITY.md").read_text(encoding="utf-8")
    checklist = Path("docs/release-checklist.md").read_text(encoding="utf-8")

    for name in (
        "DP_MCP_NAV_ALLOWLIST",
        "DP_MCP_NAV_BLOCKLIST",
        "DP_MCP_BLOCK_PRIVATE_NETWORK",
        "DP_MCP_SCREENSHOT_ROOT",
    ):
        assert name in security
    assert "local stdio" in security.lower()
    assert "runtime request throttling" in security.lower()
    assert "CODECOV_TOKEN" in checklist
    assert "coverage.xml" in checklist
    assert "Check wheel package contents" in checklist
    assert "Resource and prompt inventories" in checklist
    assert "tests/evals -q" in checklist
