"""Release metadata and documentation checks for 0.4.1."""

from __future__ import annotations

import re
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback.
    import tomli as tomllib

import drissionpage_mcp


def test_package_version_metadata_is_0_4_1() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["version"] == "0.4.1"
    assert drissionpage_mcp.__version__ == "0.4.1"


def test_docs_describe_breaking_alias_removal() -> None:
    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")
    contract = Path("docs/tool-contract.md").read_text(encoding="utf-8")
    compatibility = Path("docs/compatibility.md").read_text(encoding="utf-8")

    assert "## [0.4.1]" in changelog
    assert "## [0.4.0]" in changelog
    assert "element_input_text" in changelog
    assert "wait_sleep" in changelog
    assert "0.4.1" in compatibility
    assert "property_name" in compatibility
    assert "text:..." in compatibility
    assert "element_input_text" not in _tool_inventory(contract)
    assert "wait_sleep" not in _tool_inventory(contract)
    assert "drissionpage://session/summary" in contract
    assert "browser_navigate_and_summarize" in contract


def test_readmes_end_with_latest_0_4_1_fix_summary() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    readme_cn = Path("README_CN.md").read_text(encoding="utf-8")

    assert "## 🆕 Latest Version: v0.4.1" in readme
    assert "selector normalization" in readme
    assert "serverInfo.version" in readme
    assert "property_name" in readme
    assert "## 🆕 最新版本：v0.4.1" in readme_cn
    assert "选择器归一化" in readme_cn
    assert "serverInfo.version" in readme_cn
    assert "property_name" in readme_cn


def test_public_guides_do_not_advertise_removed_alias_tools() -> None:
    for path in (
        Path("README.md"),
        Path("README_CN.md"),
        Path("playground/README.md"),
    ):
        text = path.read_text(encoding="utf-8")
        assert "element_input_text" not in text
        assert "wait_sleep" not in text
        assert "21 tools" not in text
        assert "21 powerful tools" not in text
        assert "21 automation tools" not in text
        assert "21 个" not in text


def test_public_guides_include_codex_mcp_configuration() -> None:
    """documents Codex's TOML MCP setup alongside JSON MCP clients."""

    readme = Path("README.md").read_text(encoding="utf-8")
    readme_cn = Path("README_CN.md").read_text(encoding="utf-8")
    contract = Path("docs/tool-contract.md").read_text(encoding="utf-8")
    troubleshooting = Path("docs/troubleshooting.md").read_text(encoding="utf-8")
    manifest = Path("MANIFEST.in").read_text(encoding="utf-8")
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    for text in (readme, readme_cn, contract, troubleshooting):
        assert "[mcp_servers.drissionpage]" in text
        assert 'command = "drissionpage-mcp"' in text

    assert "Codex CLI/IDE" in readme
    assert "Codex CLI/IDE" in readme_cn
    assert "codex mcp list" in troubleshooting
    assert "recursive-include examples" not in manifest
    assert "Codex" in pyproject["project"]["description"]
    assert "codex" in pyproject["project"]["keywords"]
    assert 'command = "python"' in contract
    assert 'args = ["-m", "drissionpage_mcp.cli"]' in contract


def _tool_inventory(contract: str) -> str:
    match = re.search(r"## Tool Inventory(.*?)## Compatibility Notes", contract, re.S)
    assert match, "tool inventory section should exist"
    return match.group(1)
