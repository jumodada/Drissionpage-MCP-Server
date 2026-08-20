"""Versioned repository Skill catalog and validation contracts."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from drissionpage_mcp.resources import SKILL_EXAMPLES
from drissionpage_mcp.tools import get_all_tools


def test_skill_catalog_matches_repository_sources_and_public_tools() -> None:
    tool_names = {tool.name for tool in get_all_tools()}

    for skill in SKILL_EXAMPLES:
        path = Path(skill["path"])
        content = path.read_bytes()

        assert path.is_file()
        assert path.parent.name == skill["name"]
        assert set(skill["required_tools"]) <= tool_names
        assert skill["source_revision"] == "v0.8.3"
        assert f"/tree/{skill['source_revision']}/" in skill["source_url"]
        assert skill["source_url"].endswith(path.parent.as_posix())
        assert skill["sha256"] == hashlib.sha256(content).hexdigest()


def test_skill_frontmatter_stays_cross_host_compatible() -> None:
    for path in Path("skills").glob("*/SKILL.md"):
        lines = path.read_text(encoding="utf-8").splitlines()
        closing = lines.index("---", 1)
        keys = {
            line.split(":", 1)[0]
            for line in lines[1:closing]
            if line.strip() and not line.startswith((" ", "\t"))
        }

        assert keys == {"name", "description"}
        assert len(lines) < 500


def test_skill_validator_cli_reports_versioned_catalog() -> None:
    completed = subprocess.run(
        [sys.executable, "playground/validate_skills.py", "--json"],
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(completed.stdout)

    assert report["ok"] is True
    assert report["source_revision"] == "v0.8.3"
    assert report["tool_count"] == 69
    assert {item["name"] for item in report["skills"]} == {
        "cross-origin-iframe-probe",
        "turnstile-testing",
        "xiaohongshu-content-research",
    }
    assert all(item["ok"] for item in report["skills"])
