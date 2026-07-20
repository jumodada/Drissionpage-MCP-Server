"""CI workflow structure tests for the approved MCP usability gates."""

from __future__ import annotations

import re
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback.
    import tomli as tomllib

CI_WORKFLOW = Path(".github/workflows/ci.yml")
WORKFLOW_LINT = Path(".github/workflows/workflow-lint.yml")
CODECOV_CONFIG = Path("codecov.yml")
MANIFEST = Path("MANIFEST.in")
PYPROJECT = Path("pyproject.toml")
README_FILES = (Path("README.md"), Path("README_CN.md"))


def test_repository_has_no_unresolved_merge_markers() -> None:
    """prevents conflicted source or workflow files from being committed."""

    markers = ("<<<<<<< ", "=======", ">>>>>>> ")
    paths = [
        *Path(".github").rglob("*.yml"),
        *Path("drissionpage_mcp").rglob("*.py"),
        *Path("tests").rglob("*.py"),
        Path("README.md"),
        Path("README_CN.md"),
        Path(".gitignore"),
    ]
    conflicts = [
        str(path)
        for path in paths
        if path.is_file()
        and any(
            line.startswith(markers)
            for line in path.read_text(encoding="utf-8").splitlines()
        )
    ]

    assert conflicts == []


def test_independent_workflow_lint_catches_invalid_primary_ci() -> None:
    """keeps syntax validation runnable when the primary workflow is invalid."""

    workflow = WORKFLOW_LINT.read_text(encoding="utf-8")

    assert "rhysd/actionlint:1.7.7" in workflow
    assert "git grep -nE" in workflow
    assert "<<<<<<< " in workflow
    assert ".github" in workflow
    assert "pull_request:" in workflow


def test_ci_separates_required_quality_gates() -> None:
    """keeps quality gates separate without running browser integration twice."""

    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    job_names = set(re.findall(r"^  ([a-z0-9_-]+):\n", workflow, re.MULTILINE))

    assert {
        "lint",
        "unit",
        "protocol",
        "evals",
        "benchmark",
        "coverage",
        "package",
    } <= job_names
    assert "browser-integration" not in job_names


def test_ci_enforces_pre_0_8_production_loc_budget() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    lint_job = workflow.split("  lint:\n", maxsplit=1)[1].split(
        "\n  unit:\n", maxsplit=1
    )[0]

    assert "fetch-depth: 0" in lint_job
    assert "BASELINE=e0b8805" in lint_job
    assert "drissionpage_mcp/**/*.py" in lint_job
    assert 'test "$NET_PRODUCTION_LOC" -le 200' in lint_job


def test_ci_coverage_is_the_single_strict_browser_integration_gate() -> None:
    """runs browser integration once while collecting release coverage."""

    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    coverage_job = workflow.split("  coverage:\n", maxsplit=1)[1].split(
        "\n  package:\n", maxsplit=1
    )[0]

    assert "python -m pytest tests/" in coverage_job
    assert "chromium" in coverage_job.lower()
    assert "command -v google-chrome" in coverage_job
    assert "CHROME_PATH=$BROWSER_BIN" in coverage_job
    assert 'DP_HEADLESS: "1"' in coverage_job
    assert 'DP_MCP_REQUIRE_BROWSER: "1"' in coverage_job


def test_ci_browser_gate_starts_shared_drissionpage_test_site_once() -> None:
    """keeps one shared SSR test-site setup in the browser-capable job."""

    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    coverage_job = workflow.split("  coverage:\n", maxsplit=1)[1].split(
        "\n  package:\n", maxsplit=1
    )[0]
    assert coverage_job.count("repository: jumodada/DrissionPage-test-site") == 1
    assert coverage_job.count("npm run build") == 1
    assert coverage_job.count("npm run dev -- --host 127.0.0.1 --port 4321") == 1
    assert "DP_TEST_SITE_URL: http://127.0.0.1:4321" in coverage_job
    assert "api/health.json" in coverage_job
    assert workflow.count("repository: jumodada/DrissionPage-test-site") == 1


def test_ci_private_shared_test_site_uses_secret_only() -> None:
    """keeps deployed shared SSR test-site URLs out of the public workflow."""

    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "DP_PRIVATE_FIXTURE_URL" in workflow
    assert "vars.DP_TEST_SITE_URL" not in workflow
    assert "DP_TEST_SITE_URL: https://" not in workflow

    coverage_job = workflow.split("  coverage:\n", maxsplit=1)[1].split(
        "\n  package:\n", maxsplit=1
    )[0]
    assert "RUN_PRIVATE_TEST_SITE" in coverage_job
    assert "github.event_name != 'pull_request'" in coverage_job
    assert "DP_TEST_SITE_URL: ${{ secrets.DP_PRIVATE_FIXTURE_URL }}" in coverage_job
    assert "::add-mask::" in coverage_job


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
    package_job = workflow.split("  package:\n", maxsplit=1)[1]

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

    assert packages == [
        "drissionpage_mcp",
        "drissionpage_mcp.browser",
        "drissionpage_mcp.tools",
    ]
    assert "src" not in packages
    assert "recursive-include src" not in manifest
    assert not Path("src").exists()


def test_browser_availability_has_one_strict_gate_per_workload() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    benchmark_job = workflow.split("  benchmark:\n", maxsplit=1)[1].split(
        "\n  coverage:\n", maxsplit=1
    )[0]
    coverage_job = workflow.split("  coverage:\n", maxsplit=1)[1].split(
        "\n  package:\n", maxsplit=1
    )[0]

    assert "DrissionPage-test-site" not in benchmark_job
    assert "tests.evals.task_completion_benchmark" in benchmark_job
    assert "command -v google-chrome" in benchmark_job
    assert "TMPDIR: ${{ runner.temp }}" in benchmark_job
    assert 'DP_MCP_REQUIRE_BROWSER: "1"' in benchmark_job
    assert "tests.evals.task_completion_benchmark" not in coverage_job
    assert 'DP_MCP_REQUIRE_BROWSER: "1"' in coverage_job
    assert 'DP_MCP_REQUIRE_BROWSER: "0"' not in workflow


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

    assert version == "0.7.1"
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
    assert "tests.evals.task_completion_benchmark" in workflow
    assert "--iterations 10" in workflow
    benchmark_job = workflow.split("  benchmark:\n", maxsplit=1)[1].split(
        "\n  coverage:\n", maxsplit=1
    )[0]
    benchmark_upload = benchmark_job.split(
        "- name: Upload task-completion benchmark", 1
    )[1]
    assert "if: always()" in benchmark_upload.split("- name:", 1)[0]
    assert "if-no-files-found: warn" in benchmark_upload


def test_security_policy_and_ci_document_0_4_0_controls() -> None:
    security = Path("SECURITY.md").read_text(encoding="utf-8")
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    for name in (
        "DP_MCP_NAV_ALLOWLIST",
        "DP_MCP_NAV_BLOCKLIST",
        "DP_MCP_BLOCK_PRIVATE_NETWORK",
        "DP_MCP_SCREENSHOT_ROOT",
        "DP_MCP_UPLOAD_ROOT",
    ):
        assert name in security
    assert "local stdio" in security.lower()
    assert "runtime request throttling" in security.lower()
    assert "CODECOV_TOKEN" in workflow
    assert "coverage.xml" in workflow
    assert "Check wheel package contents" in workflow
    assert "tests/evals -q" in workflow
