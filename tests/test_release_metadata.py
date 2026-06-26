"""Release metadata and documentation checks for 0.4.0."""

from __future__ import annotations

import re
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback.
    import tomli as tomllib

import drissionpage_mcp


def test_package_version_metadata_is_0_4_0() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["version"] == "0.4.0"
    assert drissionpage_mcp.__version__ == "0.4.0"


def test_docs_describe_0_4_0_breaking_alias_removal() -> None:
    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")
    contract = Path("docs/tool-contract.md").read_text(encoding="utf-8")
    compatibility = Path("docs/compatibility.md").read_text(encoding="utf-8")

    assert "## [0.4.0]" in changelog
    assert "element_input_text" in changelog
    assert "wait_sleep" in changelog
    assert "0.4.0" in compatibility
    assert "element_input_text" not in _tool_inventory(contract)
    assert "wait_sleep" not in _tool_inventory(contract)
    assert "drissionpage://session/summary" in contract
    assert "browser_navigate_and_summarize" in contract


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
        assert "21 个" not in text


def _tool_inventory(contract: str) -> str:
    match = re.search(r"## Tool Inventory(.*?)## Compatibility Notes", contract, re.S)
    assert match, "tool inventory section should exist"
    return match.group(1)
