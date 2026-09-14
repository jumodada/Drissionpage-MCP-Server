"""Versioned repository Skill catalog and validation contracts."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from urllib.error import URLError

from drissionpage_mcp.resources import SKILL_EXAMPLES
from drissionpage_mcp.tools import get_all_tools
from playground import validate_skills as validator


def test_skill_catalog_matches_repository_sources_and_public_tools() -> None:
    tool_names = {tool.name for tool in get_all_tools()}

    for skill in SKILL_EXAMPLES:
        path = Path(skill["path"])
        content = path.read_bytes()

        assert path.is_file()
        assert path.parent.name == skill["name"]
        assert set(skill["required_tools"]) <= tool_names
        assert skill["source_revision"] == "v0.8.4"
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
    assert report["source_revision"] == "v0.8.4"
    assert report["tool_count"] == 69
    assert {item["name"] for item in report["skills"]} == {
        "cross-origin-iframe-probe",
        "turnstile-testing",
        "xiaohongshu-content-research",
    }
    assert all(item["ok"] for item in report["skills"])


class _RemoteResponse:
    def __init__(self, content: bytes) -> None:
        self._content = content

    def __enter__(self) -> _RemoteResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, amount: int) -> bytes:
        return self._content[:amount]


def test_remote_skill_validation_fetches_pinned_raw_sources(monkeypatch) -> None:
    content_by_url = {
        validator.remote_url(entry): Path(entry["path"]).read_bytes()
        for entry in SKILL_EXAMPLES
    }
    requested: list[tuple[str, float]] = []

    def fake_urlopen(url: str, *, timeout: float) -> _RemoteResponse:
        requested.append((url, timeout))
        return _RemoteResponse(content_by_url[url])

    monkeypatch.setattr(validator, "urlopen", fake_urlopen)

    report = validator.validate_skills(remote=True)

    assert report["ok"] is True
    assert report["remote"] == {
        "enabled": True,
        "source": "github_raw",
        "revision": report["source_revision"],
        "timeout_seconds": validator.REMOTE_TIMEOUT_SECONDS,
        "max_bytes": validator.REMOTE_MAX_BYTES,
    }
    assert requested == [
        (validator.remote_url(entry), validator.REMOTE_TIMEOUT_SECONDS)
        for entry in SKILL_EXAMPLES
    ]
    for item, entry in zip(report["skills"], SKILL_EXAMPLES, strict=True):
        assert item["remote"] == {
            "ok": True,
            "url": validator.remote_url(entry),
            "bytes": len(Path(entry["path"]).read_bytes()),
            "sha256": entry["sha256"],
            "hash_matches": True,
        }


def test_remote_skill_validation_reports_network_failure(monkeypatch) -> None:
    def failing_urlopen(url: str, *, timeout: float) -> _RemoteResponse:
        raise URLError("offline")

    monkeypatch.setattr(validator, "urlopen", failing_urlopen)

    report = validator.validate_skills(remote=True)

    assert report["ok"] is False
    assert all(item["remote"]["ok"] is False for item in report["skills"])
    assert all(
        "remote fetch failed" in item["remote"]["error"]
        for item in report["skills"]
    )


def test_remote_skill_validation_rejects_oversized_content(monkeypatch) -> None:
    content = b"x" * (validator.REMOTE_MAX_BYTES + 1)
    monkeypatch.setattr(
        validator,
        "urlopen",
        lambda url, *, timeout: _RemoteResponse(content),
    )

    report = validator.validate_skills(remote=True)

    assert report["ok"] is False
    assert all(
        item["remote"]["error"] == "remote Skill exceeds size limit"
        for item in report["skills"]
    )


def test_remote_skill_validation_reports_hash_mismatch(monkeypatch) -> None:
    monkeypatch.setattr(
        validator,
        "urlopen",
        lambda url, *, timeout: _RemoteResponse(b"different"),
    )

    report = validator.validate_skills(remote=True)

    assert report["ok"] is False
    assert all(item["remote"]["hash_matches"] is False for item in report["skills"])
    assert all(
        item["remote"]["error"] == "remote SHA-256 does not match catalog"
        for item in report["skills"]
    )
