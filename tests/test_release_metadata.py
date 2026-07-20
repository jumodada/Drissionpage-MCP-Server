"""Release metadata and essential README checks for 0.7.1."""

from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback.
    import tomli as tomllib

import drissionpage_mcp


def test_package_version_metadata_is_0_7_1() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["version"] == "0.7.1"
    assert drissionpage_mcp.__version__ == "0.7.1"


def test_readmes_publish_current_release_and_tool_surface() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    readme_cn = Path("README_CN.md").read_text(encoding="utf-8")

    assert "## 🆕 Latest Version: v0.7.1" in readme
    assert "Released on 2026-07-20" in readme
    assert "public registry remains at 62 tools" in readme
    assert "### 🌐 Navigation (4 tools)" in readme
    assert "### 🎯 Element Interaction & Extraction (14 tools)" in readme
    assert "### 🧾 Form Operations (3 tools)" in readme
    assert "### 📸 Page Operations (18 tools)" in readme

    assert "## 🆕 最新版本：v0.7.1" in readme_cn
    assert "发布日期：2026-07-20" in readme_cn
    assert "公开工具数保持 62 个" in readme_cn
    assert "### 🌐 导航工具（4 个）" in readme_cn
    assert "### 🎯 元素交互与提取（14 个）" in readme_cn
    assert "### 🧾 表单工具（3 个）" in readme_cn
    assert "### 📸 页面操作（18 个）" in readme_cn

    for text in (readme, readme_cn):
        for tool_name in (
            "form_fill",
            "form_submit",
            "page_dialog_respond",
            "element_click_and_download",
        ):
            assert tool_name in text


def test_readmes_include_supported_install_and_codex_configuration() -> None:
    for path in (Path("README.md"), Path("README_CN.md")):
        text = path.read_text(encoding="utf-8")

        assert "python -m pip install -U drissionpage-mcp" in text
        assert "drissionpage-mcp 0.7.1" in text
        assert "[mcp_servers.drissionpage]" in text
        assert 'command = "drissionpage-mcp"' in text
        assert 'args = ["-m", "drissionpage_mcp.cli"]' in text
