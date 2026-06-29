"""Release metadata and documentation checks for 0.5.0."""

from __future__ import annotations

import re
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback.
    import tomli as tomllib

import drissionpage_mcp


def test_package_version_metadata_is_0_5_0() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["version"] == "0.5.0"
    assert drissionpage_mcp.__version__ == "0.5.0"


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


def test_readmes_end_with_latest_0_5_0_feature_summary() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    readme_cn = Path("README_CN.md").read_text(encoding="utf-8")

    assert "## 🆕 Latest Version: v0.5.0" in readme
    assert "form_inspect" in readme
    assert "error.details.hints" in readme
    assert "page_snapshot" in readme
    assert "element_find_all" in readme
    assert "22 tools" in readme
    assert "drissionpage-mcp doctor --launch-browser" in readme
    assert "MCP_ARGUMENT_INVALID" in readme
    assert "## 🆕 最新版本：v0.5.0" in readme_cn
    assert "form_inspect" in readme_cn
    assert "error.details.hints" in readme_cn
    assert "page_snapshot" in readme_cn
    assert "element_find_all" in readme_cn
    assert "22 个" in readme_cn
    assert "drissionpage-mcp doctor --launch-browser" in readme_cn
    assert "MCP_ARGUMENT_INVALID" in readme_cn


def test_public_guides_do_not_advertise_removed_alias_tools() -> None:
    for path in (
        Path("README.md"),
        Path("README_CN.md"),
        Path("playground/README.md"),
    ):
        text = path.read_text(encoding="utf-8")
        assert "element_input_text" not in text
        assert "wait_sleep" not in text
        assert "19 tools" not in text
        assert "19 powerful tools" not in text
        assert "19 automation tools" not in text
        assert "19 个" not in text


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


def test_public_guides_do_not_point_to_removed_or_stale_setup_paths() -> None:
    """keeps first-run docs aligned after removing examples/ and mcp-config files."""

    public_docs = {
        "README.md": Path("README.md").read_text(encoding="utf-8"),
        "README_CN.md": Path("README_CN.md").read_text(encoding="utf-8"),
        "docs/troubleshooting.md": Path("docs/troubleshooting.md").read_text(
            encoding="utf-8"
        ),
        "playground/README.md": Path("playground/README.md").read_text(
            encoding="utf-8"
        ),
        "playground/run_mcp_lab.py": Path("playground/run_mcp_lab.py").read_text(
            encoding="utf-8"
        ),
    }

    for path, text in public_docs.items():
        assert "mcp-config.json" not in text, path
        assert "examples/" not in text, path
        assert "current 75% floor" not in text, path
        assert "当前 75% 覆盖率底线" not in text, path

    assert "current 95% floor" in public_docs["README.md"]
    assert "当前 95% 覆盖率底线" in public_docs["README_CN.md"]
    assert 'args = ["-m", "drissionpage_mcp.cli"]' in public_docs["README.md"]
    assert 'args = ["-m", "drissionpage_mcp.cli"]' in public_docs["README_CN.md"]
    assert "playground/quick_start.py" not in "\n".join(public_docs.values())
    assert "playground/local_test.py" not in "\n".join(public_docs.values())
    assert "playground/run_mcp_lab.py --case registry" in public_docs["README.md"]
    assert "playground/run_mcp_lab.py --case registry" in public_docs["README_CN.md"]
    assert "DP_HEADLESS" in public_docs["docs/troubleshooting.md"]
    assert "doctor --launch-browser" in public_docs["docs/troubleshooting.md"]


def test_maintenance_docs_do_not_retain_deleted_examples_or_old_versions() -> None:
    security = Path("SECURITY.md").read_text(encoding="utf-8")
    codecov = Path("codecov.yml").read_text(encoding="utf-8")
    release_checklist = Path("docs/release-checklist.md").read_text(encoding="utf-8")

    assert "0.3.2" not in security
    assert "examples/**" not in codecov
    assert 'importlib.metadata.version("drissionpage-mcp")' in release_checklist


def _tool_inventory(contract: str) -> str:
    match = re.search(r"## Tool Inventory(.*?)## Compatibility Notes", contract, re.S)
    assert match, "tool inventory section should exist"
    return match.group(1)
