"""CI workflow structure tests for the approved MCP usability gates."""

from __future__ import annotations

import re
from pathlib import Path

CI_WORKFLOW = Path(".github/workflows/ci.yml")


def test_ci_separates_required_quality_gates() -> None:
    """keeps lint/unit/protocol/package/browser checks as separate jobs."""

    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    job_names = set(re.findall(r"^  ([a-z0-9_-]+):\n", workflow, re.MULTILINE))

    assert {
        "lint",
        "unit",
        "protocol",
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
