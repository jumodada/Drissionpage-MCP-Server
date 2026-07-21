"""Release metadata checks for 0.7.2."""

from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback.
    import tomli as tomllib

import drissionpage_mcp


def test_package_version_metadata_is_0_7_2() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["version"] == "0.7.2"
    assert drissionpage_mcp.__version__ == "0.7.2"


def test_changelog_describes_breaking_alias_removal() -> None:
    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")

    assert "## [0.4.1]" in changelog
    assert "## [0.4.0]" in changelog
    assert "element_input_text" in changelog
    assert "wait_sleep" in changelog


def test_readmes_and_changelog_publish_latest_0_7_2_summary() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    readme_cn = Path("README_CN.md").read_text(encoding="utf-8")
    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")

    browser_lab_url = "https://raw.githubusercontent.com/jumodada/Drissionpage-MCP-Server/assets/drissionpage-mcp-browser-lab.gif"
    assert browser_lab_url in readme and browser_lab_url in readme_cn
    assert "vision-natural-pointer-demo.gif" not in readme
    assert "vision-natural-pointer-demo.gif" not in readme_cn
    assert "website/public/og-browser-lab.png" not in readme
    assert "website/public/og-browser-lab.png" not in readme_cn
    assert "Watch the original natural pointer demo" not in readme
    assert "观看原始自然指针演示" not in readme_cn
    assert "## 🆕 Latest Version: v0.7.2" in readme
    assert "Released on 2026-07-21" in readme
    assert "58 Powerful Tools" in readme
    assert "Form Operations" not in readme
    assert "page_dialog_respond" in readme
    assert "element_click_and_download" in readme
    assert "optional Skill" in readme
    assert "### 🌐 Navigation (4 tools)" in readme
    assert "### 🎯 Element Interaction & Extraction (14 tools)" in readme
    assert "### 📸 Page Operations (18 tools)" in readme
    assert "## 🆕 最新版本：v0.7.2" in readme_cn
    assert "发布日期：2026-07-21" in readme_cn
    assert "58 个强大工具" in readme_cn
    assert "表单工具（3 个）" not in readme_cn
    assert "page_dialog_respond" in readme_cn
    assert "element_click_and_download" in readme_cn
    assert "可选 Skill" in readme_cn
    assert "### 🌐 导航工具（4 个）" in readme_cn
    assert "### 🎯 元素交互与提取（14 个）" in readme_cn
    assert "### 📸 页面操作（18 个）" in readme_cn
    assert "## [0.7.2] - 2026-07-21" in changelog
    assert "58 generic tools" in changelog
    assert "No compatibility aliases" in changelog
    assert "ActionReceipt" in changelog
    assert "ArtifactRef" in changelog
    assert "ten-run" in changelog
    assert "## [0.6.2] - 2026-07-15" in changelog
    assert "optional ordered `waypoints`" in changelog
    assert "no new public tool" in changelog
    assert "## [0.6.1] - 2026-07-14" in changelog
    assert "Added `page_pointer_drag_element`" in changelog
    assert "distance-aware timing" in changelog
    assert "layout-drift recovery" in changelog
    assert (
        "[Unreleased]: https://github.com/jumodada/Drissionpage-MCP-Server/compare/v0.7.2...HEAD"
        in changelog
    )
    assert (
        "[0.7.2]: https://github.com/jumodada/Drissionpage-MCP-Server/compare/v0.7.1...v0.7.2"
        in changelog
    )
    assert (
        "[0.7.1]: https://github.com/jumodada/Drissionpage-MCP-Server/compare/v0.7.0...v0.7.1"
        in changelog
    )
    assert (
        "[0.7.0]: https://github.com/jumodada/Drissionpage-MCP-Server/compare/v0.6.2...v0.7.0"
        in changelog
    )
    assert (
        "[0.6.2]: https://github.com/jumodada/Drissionpage-MCP-Server/compare/v0.6.1...v0.6.2"
        in changelog
    )
    assert (
        "[0.6.1]: https://github.com/jumodada/Drissionpage-MCP-Server/compare/v0.6.0...v0.6.1"
        in changelog
    )


def test_public_readmes_advertise_mcp_model_usage_surfaces() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    readme_cn = Path("README_CN.md").read_text(encoding="utf-8")
    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")

    assert "drissionpage://guide/model-usage" in readme
    assert "drissionpage://guide/model-usage" in readme_cn
    assert "drissionpage_mcp_usage_playbook" in readme
    assert "drissionpage_mcp_usage_playbook" in readme_cn
    assert "browser_vision_guided_interaction" in readme
    assert "browser_vision_guided_interaction" in readme_cn
    assert "MCP-exposed model usage guide" in changelog


def test_public_readmes_keep_no_sandbox_out_of_general_setup_examples() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    readme_cn = Path("README_CN.md").read_text(encoding="utf-8")

    assert '# DP_NO_SANDBOX = "1"' not in readme
    assert '# DP_NO_SANDBOX = "1"' not in readme_cn
    assert '"DP_NO_SANDBOX": "1"' not in readme
    assert '"DP_NO_SANDBOX": "1"' not in readme_cn


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


def test_public_readmes_include_codex_mcp_configuration() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    readme_cn = Path("README_CN.md").read_text(encoding="utf-8")
    manifest = Path("MANIFEST.in").read_text(encoding="utf-8")
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    for text in (readme, readme_cn):
        assert "[mcp_servers.drissionpage]" in text
        assert 'command = "drissionpage-mcp"' in text

    assert "Codex CLI/IDE" in readme
    assert "Codex CLI/IDE" in readme_cn
    assert "recursive-include examples" not in manifest
    assert "Codex" in pyproject["project"]["description"]
    assert "codex" in pyproject["project"]["keywords"]


def test_public_readmes_do_not_point_to_removed_or_stale_setup_paths() -> None:
    public_files = {
        "README.md": Path("README.md").read_text(encoding="utf-8"),
        "README_CN.md": Path("README_CN.md").read_text(encoding="utf-8"),
        "playground/README.md": Path("playground/README.md").read_text(
            encoding="utf-8"
        ),
        "playground/run_mcp_lab.py": Path("playground/run_mcp_lab.py").read_text(
            encoding="utf-8"
        ),
    }

    for path, text in public_files.items():
        assert "mcp-config.json" not in text, path
        assert "examples/" not in text, path
        assert "current 75% floor" not in text, path
        assert "当前 75% 覆盖率底线" not in text, path

    assert "current 95% floor" in public_files["README.md"]
    assert "当前 95% 覆盖率底线" in public_files["README_CN.md"]
    assert 'args = ["-m", "drissionpage_mcp.cli"]' in public_files["README.md"]
    assert 'args = ["-m", "drissionpage_mcp.cli"]' in public_files["README_CN.md"]
    assert "playground/quick_start.py" not in "\n".join(public_files.values())
    assert "playground/local_test.py" not in "\n".join(public_files.values())
    assert "playground/run_mcp_lab.py --case registry" in public_files["README.md"]
    assert "playground/run_mcp_lab.py --case registry" in public_files["README_CN.md"]


def test_maintenance_files_do_not_retain_deleted_examples_or_old_versions() -> None:
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
