"""CI workflow structure tests for the approved MCP usability gates."""

from __future__ import annotations

import re
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback.
    import tomli as tomllib

CI_WORKFLOW = Path(".github/workflows/ci.yml")
PUBLISH_WORKFLOW = Path(".github/workflows/publish-mcp-registry.yml")
WORKFLOW_LINT = Path(".github/workflows/workflow-lint.yml")
CODECOV_CONFIG = Path("codecov.yml")
MANIFEST = Path("MANIFEST.in")
PYPROJECT = Path("pyproject.toml")
README_FILES = (Path("README.md"), Path("README_CN.md"))


def _job(workflow: str, name: str) -> str:
    return re.split(
        r"\n  [a-z0-9_-]+:\n", workflow.split(f"\n  {name}:\n", 1)[1], maxsplit=1
    )[0]


def test_tag_publication_requires_the_complete_reusable_ci() -> None:
    ci = CI_WORKFLOW.read_text(encoding="utf-8")
    publish = PUBLISH_WORKFLOW.read_text(encoding="utf-8")

    assert "  workflow_call:" in ci
    gate = _job(publish, "quality-gates")
    assert "needs: release-metadata" in gate
    assert "uses: ./.github/workflows/ci.yml" in gate
    assert "secrets: inherit" in gate
    verification = _job(publish, "verify-and-build")
    assert "needs: quality-gates" in verification
    assert "python -m build" not in verification
    assert "name: python-distribution" in verification
    assert "needs: verify-and-build" in _job(publish, "publish-pypi")


def test_tag_and_all_package_versions_are_checked_before_release_gates() -> None:
    publish = PUBLISH_WORKFLOW.read_text(encoding="utf-8")
    metadata = _job(publish, "release-metadata")

    assert "github.ref_name" in metadata
    assert 'pyproject["project"]["version"] == version' in metadata
    assert 'server["version"] == version' in metadata
    assert 'package["version"] == version' in metadata
    assert 'for package in server["packages"]' in metadata
    assert "module_version == version" in metadata
    assert 'Path("drissionpage_mcp/__init__.py")' in metadata


def test_release_publishes_the_same_hashed_distributions_as_clean_smoke_tests() -> None:
    ci = CI_WORKFLOW.read_text(encoding="utf-8")
    publish = PUBLISH_WORKFLOW.read_text(encoding="utf-8")
    package = _job(ci, "package")
    wheel = _job(ci, "wheel-smoke")

    assert "needs: package" in wheel
    assert "python -m build" not in wheel
    assert "name: python-distribution" in wheel
    assert package.index("Complete sdist browser flow") < package.index(
        "Upload verified distribution"
    )
    assert "sha256sum -- ./*.whl ./*.tar.gz > SHA256SUMS" in package
    assert "name: python-distribution" in package
    for job in (wheel, _job(publish, "verify-and-build"), _job(publish, "publish-pypi")):
        assert "sha256sum --check SHA256SUMS" in job
    pypi = _job(publish, "publish-pypi")
    assert pypi.index("sha256sum --check SHA256SUMS") < pypi.index(
        "pypa/gh-action-pypi-publish"
    )
    assert "rm SHA256SUMS" in pypi


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
        "browser-boundaries",
        "coverage",
        "wheel-smoke",
        "package",
    } <= job_names
    assert "browser-integration" not in job_names


def test_ci_enforces_current_release_production_loc_budget() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    lint_job = workflow.split("  lint:\n", maxsplit=1)[1].split(
        "\n  unit:\n", maxsplit=1
    )[0]

    assert "fetch-depth: 0" in lint_job
    assert "BASELINE=c1f9dde" in lint_job
    assert "drissionpage_mcp/**/*.py" in lint_job
    assert 'test "$NET_PRODUCTION_LOC" -le 150' in lint_job


def test_ci_runs_mypy_as_a_required_lint_gate() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    lint_job = workflow.split("  lint:\n", maxsplit=1)[1].split(
        "\n  unit:\n", maxsplit=1
    )[0]

    assert "python -m mypy drissionpage_mcp" in lint_job


def test_ci_coverage_is_the_single_strict_browser_integration_gate() -> None:
    """runs the full browser suite once while collecting release coverage."""

    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    coverage_job = workflow.split("  coverage:\n", maxsplit=1)[1].split(
        "\n  wheel-smoke:\n", maxsplit=1
    )[0]

    assert "python -m pytest tests/" in coverage_job
    assert "chromium" in coverage_job.lower()
    assert "command -v google-chrome" in coverage_job
    assert "CHROME_PATH=$BROWSER_BIN" in coverage_job
    assert 'DP_HEADLESS: "1"' in coverage_job
    assert 'DP_MCP_REQUIRE_BROWSER: "1"' in coverage_job


def test_ci_runs_focused_browser_boundaries_across_supported_runner_os() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    boundary_job = workflow.split("  browser-boundaries:\n", maxsplit=1)[1].split(
        "\n  coverage:\n", maxsplit=1
    )[0]

    assert "ubuntu-latest" in boundary_job
    assert "macos-latest" in boundary_job
    assert "windows-latest" in boundary_job
    assert "tests/test_browser_capability_boundaries.py" in boundary_job
    assert "tests/test_observation_browser.py" in boundary_job
    assert "Locate Chrome or Chromium (Linux)" in boundary_job
    assert "if: runner.os == 'Linux'" in boundary_job
    assert "command -v google-chrome" in boundary_job
    assert "CHROME_PATH=$BROWSER_BIN" in boundary_job
    assert "drissionpage-mcp doctor --launch-browser" in boundary_job
    assert 'DP_HEADLESS: "1"' in boundary_job
    assert 'DP_MCP_REQUIRE_BROWSER: "1"' in boundary_job
    assert 'no_sandbox: "1"' in boundary_job
    assert 'no_sandbox: "0"' in boundary_job


def test_ci_browser_gate_starts_shared_drissionpage_test_site_once() -> None:
    """keeps one shared SSR test-site setup in the browser-capable job."""

    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    coverage_job = workflow.split("  coverage:\n", maxsplit=1)[1].split(
        "\n  wheel-smoke:\n", maxsplit=1
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
        "\n  wheel-smoke:\n", maxsplit=1
    )[0]
    assert "RUN_PRIVATE_TEST_SITE" in coverage_job
    assert "github.event_name != 'pull_request'" in coverage_job
    assert "DP_TEST_SITE_URL: ${{ secrets.DP_PRIVATE_FIXTURE_URL }}" in coverage_job
    assert "::add-mask::" in coverage_job


def test_ci_uploads_xml_coverage_to_codecov() -> None:
    """publishes a deterministic XML coverage report through the Codecov action."""

    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    coverage_job = workflow.split("  coverage:\n", maxsplit=1)[1].split(
        "\n  wheel-smoke:\n", maxsplit=1
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
    """prevents private guidance, Skills, and deleted modules from shipping."""

    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    package_job = workflow.split("  package:\n", maxsplit=1)[1]

    assert "Check wheel package contents" in package_job
    assert 'top_level == ["drissionpage_mcp"]' in package_job
    assert 'name.startswith("src/")' in package_job
    assert "tarfile.open" in package_job
    assert "/AGENTS.md" in package_job
    assert "/SKILL.md" in package_job
    assert "/docs/core-and-skills-strategy.md" in package_job
    assert "/docs/0.7.3-to-0.8.0-capability-plan.md" in package_job
    assert "/docs/0.9.0-field-evaluation-and-roadmap.md" in package_job
    assert "/docs/skills.md" in package_job
    assert '"/skills/" in ("/" + name)' in package_job
    assert '"/.omx/" in ("/" + name)' in package_job
    assert "/drissionpage_mcp/prompts.py" in package_job
    assert "/drissionpage_mcp/browser/vision.py" in package_job
    assert "/drissionpage_mcp/tools/workflow.py" in package_job
    assert "Install sdist in a clean virtual environment" in package_job
    assert "--no-cache-dir dist/*.tar.gz" in package_job
    assert "source_tree=no" in package_job
    assert "playground/validate_skills.py --json --remote" not in package_job
    assert "Complete sdist browser flow through real stdio" in package_job
    assert 'cd "$RUNNER_TEMP"' in package_job
    assert '"$SDIST_SMOKE_PYTHON"' in package_job
    assert '"$GITHUB_WORKSPACE/playground/package_smoke.py"' in package_job
    assert "--expected-version 0.9.0" in package_job
    assert 'DP_MCP_REQUIRE_BROWSER: "1"' in package_job


def test_ci_installs_built_wheel_without_cache_and_handshakes() -> None:
    """catches resolver and stdio wiring failures that editable tests can miss."""

    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    wheel_job = workflow.split("  wheel-smoke:\n", maxsplit=1)[1].split(
        "\n  package:\n", maxsplit=1
    )[0]

    assert 'PIP_NO_CACHE_DIR: "1"' in wheel_job
    assert "Download verified package artifacts" in wheel_job
    assert "python -m venv" in wheel_job
    assert "--no-cache-dir dist/*.whl" in wheel_job
    assert "mcp_server_wiring" in wheel_job
    assert "package_metadata" in wheel_job
    assert "source_tree=no" in wheel_job
    assert "public_surface" in wheel_job
    assert "Complete wheel browser flow through real stdio" in wheel_job
    assert 'cd "$RUNNER_TEMP"' in wheel_job
    assert '"$WHEEL_SMOKE_PYTHON"' in wheel_job
    assert '"$GITHUB_WORKSPACE/playground/package_smoke.py"' in wheel_job
    assert "--expected-version 0.9.0" in wheel_job
    assert 'DP_MCP_REQUIRE_BROWSER: "1"' in wheel_job


def test_ci_keeps_remote_skill_validation_out_of_normal_ci() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    before_package = workflow.split("\n  package:\n", maxsplit=1)[0]
    package_job = workflow.split("\n  package:\n", maxsplit=1)[1]
    unit_job = workflow.split("\n  unit:\n", maxsplit=1)[1].split(
        "\n  protocol:\n", maxsplit=1
    )[0]

    assert "validate_skills.py --json --remote" not in before_package
    assert "validate_skills.py --json --remote" not in package_job
    assert "validate_skills.py --json --remote" in PUBLISH_WORKFLOW.read_text(
        encoding="utf-8"
    )
    assert "tests/test_package_smoke.py" in unit_job
    for path in (
        "tests/test_navigation_budget.py",
        "tests/test_snapshot_search.py",
        "tests/test_wait_budget.py",
    ):
        assert path in unit_job


def test_readmes_publish_ci_and_codecov_badges() -> None:
    """shows readers the live test and coverage state from the canonical repo."""

    for readme in README_FILES:
        text = readme.read_text(encoding="utf-8")
        assert "actions/workflows/ci.yml/badge.svg?branch=main" in text
        assert "codecov.io/gh/jumodada/Drissionpage-MCP-Server" in text


def test_readme_architecture_matches_runtime_browser_tool_boundaries() -> None:
    for readme in README_FILES:
        text = readme.read_text(encoding="utf-8")
        architecture = (
            text.split("Architecture", maxsplit=1)[-1]
            if readme.name == "README.md"
            else text.split("架构", maxsplit=1)[-1]
        )

        assert "runtime.py" in architecture
        assert "browser/" in architecture
        assert "tools/" in architecture
        assert "response.py" not in architecture


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
        "\n  browser-boundaries:\n", maxsplit=1
    )[0]
    coverage_job = workflow.split("  coverage:\n", maxsplit=1)[1].split(
        "\n  wheel-smoke:\n", maxsplit=1
    )[0]

    assert "DrissionPage-test-site" not in benchmark_job
    assert "tests.evals.task_completion_benchmark" in benchmark_job
    assert "command -v google-chrome" in benchmark_job
    assert "TMPDIR: ${{ runner.temp }}" in benchmark_job
    assert 'DP_MCP_REQUIRE_BROWSER: "1"' in benchmark_job
    assert "--output benchmark-results/0.9.0-task-completion.json" in benchmark_job
    assert "tests.evals.challenge_surface_benchmark" in benchmark_job
    assert "--output benchmark-results/0.9.0-challenge-surfaces.json" in benchmark_job
    assert "name: 0.9.0-browser-benchmarks" in benchmark_job
    assert "path: benchmark-results/0.9.0-*.json" in benchmark_job
    assert "0.7.2-task-completion" not in benchmark_job
    assert "tests.evals.task_completion_benchmark" not in coverage_job
    assert 'DP_MCP_REQUIRE_BROWSER: "1"' in coverage_job
    assert 'DP_MCP_REQUIRE_BROWSER: "0"' not in workflow


def test_ci_compares_local_baseline_and_candidate_snapshot_search_wheels() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    benchmark_job = workflow.split("  benchmark:\n", maxsplit=1)[1].split(
        "\n  browser-boundaries:\n", maxsplit=1
    )[0]

    assert "git worktree add --detach" in benchmark_job
    assert "30e8adf" in benchmark_job
    assert "fetch-depth: 0" in benchmark_job
    assert "baseline-dist" in benchmark_job
    assert "candidate-dist" in benchmark_job
    assert "baseline-benchmark" in benchmark_job
    assert "candidate-benchmark" in benchmark_job
    assert "tests.evals.snapshot_search_comparison" in benchmark_job
    assert "--iterations 20" in benchmark_job
    assert "pip install" in benchmark_job
    assert "pypi" not in benchmark_job.lower()


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

    assert version == "0.9.0"
    assert drissionpage_mcp.__version__ == version
    for readme in README_FILES:
        text = readme.read_text(encoding="utf-8")
        assert "0.3.0" not in text
        assert f"DrissionPage MCP {version}" in text


def test_ci_runs_resource_and_eval_gates() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "tests/test_mcp_resources.py" in workflow
    assert "tests/test_skill_catalog.py" in workflow
    assert "playground/validate_skills.py --json" in workflow
    assert "tests/test_mcp_prompts.py" not in workflow
    assert "python -m pytest tests/evals -q" in workflow
    assert "tests.evals.task_completion_benchmark" in workflow
    assert "--iterations 10" in workflow
    benchmark_job = workflow.split("  benchmark:\n", maxsplit=1)[1].split(
        "\n  browser-boundaries:\n", maxsplit=1
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
