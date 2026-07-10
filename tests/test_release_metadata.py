"""Release metadata and documentation checks for 0.5.8."""

from __future__ import annotations

import re
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback.
    import tomli as tomllib

import drissionpage_mcp


def test_package_version_metadata_is_0_5_8() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["version"] == "0.5.8"
    assert drissionpage_mcp.__version__ == "0.5.8"


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


def test_readmes_end_with_latest_0_5_8_feature_summary() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    readme_cn = Path("README_CN.md").read_text(encoding="utf-8")
    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")

    assert "## 🆕 Latest Version: v0.5.8" in readme
    assert "Released on 2026-07-10" in readme
    asset_url = "https://raw.githubusercontent.com/jumodada/Drissionpage-MCP-Server/assets/vision-natural-pointer-demo.gif"
    assert asset_url in readme
    assert asset_url in readme_cn
    assert "## 🖱️ Vision-Guided Human–Computer Interaction" in readme
    assert "One MCP call connects visual understanding" in readme
    assert "20–35 cubic Bézier movement steps" in readme
    assert "Security or anti-automation challenge completion" in readme
    assert "## 🖱️ 视觉驱动的人机交互" in readme_cn
    assert "一次 MCP 调用即可连接视觉理解" in readme_cn
    assert "20–35 个三次贝塞尔移动点" in readme_cn
    assert "安全验证或反自动化挑战" in readme_cn
    assert "20–35 cubic Bézier movement steps" in readme
    assert "100–300 ms after arrival" in readme
    assert "50–120 ms" in readme
    assert "20–35 个三次贝塞尔移动点" in readme_cn
    assert "到位后停顿 100–300ms" in readme_cn
    assert "50–120ms" in readme_cn
    assert "workflow-first" in readme
    assert "workflow_routes" in readme
    assert "drissionpage://tools/catalog" in readme
    assert "structuredContent" in readme
    assert "public registry stays at 52 tools" in readme
    assert "tab_list" in readme
    assert "drissionpage://session/history" in readme
    assert "meta.approx_tokens" in readme
    assert "form_inspect" in readme
    assert "error.details.hints" in readme
    assert "page_snapshot" in readme
    assert "element_find_all" in readme
    assert "52 tools" in readme
    assert "page_observe" in readme
    assert "page_console_logs" in readme
    assert "console_errors_added" in readme
    assert "page_evaluate" in readme
    assert "wait_until" in readme
    assert "element_upload_file" in readme
    assert "DP_MCP_UPLOAD_ROOT" in readme
    assert "frame_snapshot" in readme
    assert "shadow_find_all" in readme
    assert "browser_cookies_get" in readme
    assert "storage_set" in readme
    assert "drissionpage://session/state" in readme
    assert "DrissionPage 5.x" in readme
    assert "drissionpage-mcp doctor --launch-browser" in readme
    assert "browser_open_and_snapshot" in readme
    assert "browser_extract_links" in readme
    assert "form_fill_preview" in readme
    assert "network_listen_start" in readme
    assert "network_listen_wait" in readme
    assert "drissionpage://session/config" in readme
    assert "MCP_ARGUMENT_INVALID" in readme
    assert "Chrome sandbox remains enabled by default" in readme
    assert "restricted container/root environments" in readme
    assert "## 🆕 最新版本：v0.5.8" in readme_cn
    assert "发布日期：2026-07-10" in readme_cn
    assert "workflow-first" in readme_cn
    assert "workflow_routes" in readme_cn
    assert "drissionpage://tools/catalog" in readme_cn
    assert "structuredContent" in readme_cn
    assert "公开工具数仍为 52 个" in readme_cn
    assert "tab_list" in readme_cn
    assert "drissionpage://session/history" in readme_cn
    assert "meta.approx_tokens" in readme_cn
    assert "form_inspect" in readme_cn
    assert "error.details.hints" in readme_cn
    assert "page_snapshot" in readme_cn
    assert "element_find_all" in readme_cn
    assert "52 个" in readme_cn
    assert "page_observe" in readme_cn
    assert "page_console_logs" in readme_cn
    assert "console_errors_added" in readme_cn
    assert "page_evaluate" in readme_cn
    assert "wait_until" in readme_cn
    assert "element_upload_file" in readme_cn
    assert "DP_MCP_UPLOAD_ROOT" in readme_cn
    assert "frame_snapshot" in readme_cn
    assert "shadow_find_all" in readme_cn
    assert "browser_cookies_get" in readme_cn
    assert "storage_set" in readme_cn
    assert "drissionpage://session/state" in readme_cn
    assert "DrissionPage 5.x" in readme_cn
    assert "drissionpage-mcp doctor --launch-browser" in readme_cn
    assert "browser_open_and_snapshot" in readme_cn
    assert "browser_extract_links" in readme_cn
    assert "form_fill_preview" in readme_cn
    assert "network_listen_start" in readme_cn
    assert "network_listen_wait" in readme_cn
    assert "drissionpage://session/config" in readme_cn
    assert "MCP_ARGUMENT_INVALID" in readme_cn
    assert "默认保持 Chrome sandbox 开启" in readme_cn
    assert "受限容器/root 环境" in readme_cn
    assert "## [0.5.8] - 2026-07-10" in changelog
    assert (
        "[Unreleased]: https://github.com/jumodada/Drissionpage-MCP-Server/compare/v0.5.8...HEAD"
        in changelog
    )
    assert (
        "[0.5.8]: https://github.com/jumodada/Drissionpage-MCP-Server/compare/v0.5.7...v0.5.8"
        in changelog
    )


def test_public_guides_advertise_mcp_model_usage_surfaces() -> None:
    """keeps model guidance discoverable through MCP surfaces, not long docs."""

    readme = Path("README.md").read_text(encoding="utf-8")
    readme_cn = Path("README_CN.md").read_text(encoding="utf-8")
    contract = Path("docs/tool-contract.md").read_text(encoding="utf-8")
    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")

    assert "drissionpage://guide/model-usage" in readme
    assert "drissionpage://guide/model-usage" in readme_cn
    assert "drissionpage://guide/model-usage" in contract
    assert "drissionpage_mcp_usage_playbook" in readme
    assert "drissionpage_mcp_usage_playbook" in readme_cn
    assert "drissionpage_mcp_usage_playbook" in contract
    assert "browser_vision_guided_interaction" in readme
    assert "browser_vision_guided_interaction" in readme_cn
    assert "browser_vision_guided_interaction" in contract
    assert "MCP-exposed model usage guide" in changelog
    assert not Path("docs/model-usage-skill.md").exists()
    assert not Path("docs/skills").exists()


def test_public_guides_keep_no_sandbox_out_of_general_setup_examples() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    readme_cn = Path("README_CN.md").read_text(encoding="utf-8")
    troubleshooting = Path("docs/troubleshooting.md").read_text(encoding="utf-8")

    assert '# DP_NO_SANDBOX = "1"' not in readme
    assert '# DP_NO_SANDBOX = "1"' not in readme_cn
    assert '"DP_NO_SANDBOX": "1"' not in readme
    assert '"DP_NO_SANDBOX": "1"' not in readme_cn
    assert "DP_NO_SANDBOX=1" in troubleshooting
    assert "restricted container" in troubleshooting


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
    readme = Path("README.md").read_text(encoding="utf-8")
    readme_cn = Path("README_CN.md").read_text(encoding="utf-8")

    assert "0.3.2" not in security
    assert "Chrome sandboxing enabled" in security
    assert "DP_NO_SANDBOX=1" in security
    assert "examples/**" not in codecov
    assert "docs/release-checklist.md" not in readme
    assert "docs/release-checklist.md" not in readme_cn


def _tool_inventory(contract: str) -> str:
    match = re.search(r"## Tool Inventory(.*?)## Compatibility Notes", contract, re.S)
    assert match, "tool inventory section should exist"
    return match.group(1)
