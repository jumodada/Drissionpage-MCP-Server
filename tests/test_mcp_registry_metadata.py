"""Contracts for publishing the PyPI package to the official MCP Registry."""

from __future__ import annotations

import json
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback.
    import tomli as tomllib


SERVER_JSON = Path("server.json")
PUBLISH_WORKFLOW = Path(".github/workflows/publish-mcp-registry.yml")
SERVER_NAME = "io.github.jumodada/drissionpage-mcp"


def test_registry_metadata_matches_the_current_pypi_release() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    server = json.loads(SERVER_JSON.read_text(encoding="utf-8"))
    packages = server["packages"]

    assert "mcp-name: io.github.jumodada/drissionpage-mcp" in Path(
        "README.md"
    ).read_text(encoding="utf-8")
    assert server["$schema"] == (
        "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json"
    )
    assert server["name"] == SERVER_NAME
    assert server["title"] == "DrissionPage MCP"
    assert server["repository"] == {
        "url": "https://github.com/jumodada/Drissionpage-MCP-Server",
        "source": "github",
    }
    assert server["version"] == pyproject["project"]["version"]
    assert packages == [
        {
            "registryType": "pypi",
            "identifier": "drissionpage-mcp",
            "version": pyproject["project"]["version"],
            "transport": {"type": "stdio"},
        }
    ]


def test_registry_release_workflow_uses_trusted_pypi_and_github_oidc() -> None:
    workflow = PUBLISH_WORKFLOW.read_text(encoding="utf-8")

    assert 'tags: ["v*"]' in workflow
    assert "pypa/gh-action-pypi-publish@release/v1" in workflow
    assert "name: pypi" in workflow
    assert "id-token: write" in workflow
    assert "mcp-publisher login github-oidc" in workflow
    assert "./mcp-publisher publish" in workflow
    assert "https://pypi.org/pypi/drissionpage-mcp/${VERSION}/json" in workflow
