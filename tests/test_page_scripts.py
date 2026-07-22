"""Focused coverage for PageTab JavaScript builders."""

from __future__ import annotations

from pathlib import Path

from drissionpage_mcp.browser.page_state_scripts import _selector_state_script


def test_page_script_builders_are_owned_by_browser_package() -> None:
    package_root = Path(__file__).parents[1] / "drissionpage_mcp"

    assert not (package_root / "browser" / "form_inspection_scripts.py").exists()
    assert not (package_root / "browser" / "form_scripts.py").exists()
    assert not (package_root / "tools" / "forms.py").exists()
    assert not (package_root / "page_scripts.py").exists()


def test_selector_state_script_uses_json_literals_for_css_and_xpath() -> None:
    css_script = _selector_state_script('css:#weird"id')
    xpath_script = _selector_state_script("xpath://button[contains(., 'Save')]")

    assert 'const strategy = "css";' in css_script
    assert 'const raw = "#weird\\"id";' in css_script
    assert "document.querySelector(raw)" in css_script
    assert 'const strategy = "xpath";' in xpath_script
    assert "const raw = \"//button[contains(., 'Save')]\";" in xpath_script
    assert "XPathResult.FIRST_ORDERED_NODE_TYPE" in xpath_script
