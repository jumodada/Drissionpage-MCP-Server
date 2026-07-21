"""Focused coverage for PageTab JavaScript builders."""

from __future__ import annotations

from pathlib import Path

from drissionpage_mcp.browser.form_inspection_scripts import (
    build_form_inspect_script,
)
from drissionpage_mcp.browser.form_scripts import (
    _form_fill_preview_script,
    _form_fill_resolve_script,
)
from drissionpage_mcp.browser.page_state_scripts import (
    _extract_links_script,
    _selector_state_script,
)


def test_page_script_builders_are_owned_by_browser_package() -> None:
    package_root = Path(__file__).parents[1] / "drissionpage_mcp"

    assert not (package_root / "forms.py").exists()
    assert not (package_root / "page_scripts.py").exists()
    assert "querySelectorAll('form')" in build_form_inspect_script(
        selector="css:form",
        include_values=False,
        max_forms=2,
        max_fields_per_form=4,
    )


def test_workflow_scripts_escape_css_literals() -> None:
    """Lock generated JS escaping used by workflow tools before browser execution."""

    escaped_identifier_replacement = r"""replace(/[^a-zA-Z0-9_-]/g, '\\$&')"""
    escaped_attribute_value = r"""split('\\').join('\\\\').replace(/"/g, '\\"')"""

    form_script = _form_fill_preview_script(
        form_locator="css:#workflow-form",
        fields={'#weird"name\\field': 'Ada "Lovelace" \\ secret'},
        redact_values=True,
    )
    links_script = _extract_links_script(
        locator="css:a",
        limit=5,
        include_text=True,
        same_origin_only=False,
        absolute_urls=True,
        base_url="http://127.0.0.1/links",
    )

    assert escaped_identifier_replacement in form_script
    assert escaped_attribute_value in form_script
    assert escaped_identifier_replacement in links_script
    assert escaped_attribute_value in links_script
    assert "replace(/\\/g" not in form_script


def test_shared_css_helpers_keep_form_resolution_fallback_escaped() -> None:
    script = _form_fill_resolve_script(
        form_locator="css:form",
        fields={'field"with\\slashes': "value"},
        redact_values=True,
    )

    assert r"replace(/[^a-zA-Z0-9_-]/g, '\\$&')" in script
    assert r"""split('\\').join('\\\\').replace(/"/g, '\\"')""" in script
    assert script.count("function cssIdent") == 1
    assert script.count("function cssString") == 1


def test_extract_links_script_uses_json_literals_for_flags_and_url() -> None:
    script = _extract_links_script(
        locator='css:a[data-kind="external"]',
        limit=3,
        include_text=False,
        same_origin_only=True,
        absolute_urls=False,
        base_url='https://example.test/path?x="quoted"',
    )

    assert 'const locator = "css:a[data-kind=\\"external\\"]";' in script
    assert "const limit = 3;" in script
    assert "const includeText = false;" in script
    assert "const sameOriginOnly = true;" in script
    assert "const absoluteUrls = false;" in script
    assert 'const baseUrl = "https://example.test/path?x=\\"quoted\\"";' in script


def test_form_fill_preview_script_never_submits_and_can_disable_redaction() -> None:
    script = _form_fill_preview_script(
        form_locator="css:form.login",
        fields={"email": "ada@example.test", "remember": True},
        redact_values=False,
    )

    assert "const redactValues = false;" in script
    assert "requires_confirmation: true" in script
    assert "submitted: false" in script
    assert "form.submit" not in script
    assert "requestSubmit" not in script
    assert "type === 'password') return '<redacted>'" in script


def test_selector_state_script_uses_json_literals_for_css_and_xpath() -> None:
    css_script = _selector_state_script('css:#weird"id')
    xpath_script = _selector_state_script("xpath://button[contains(., 'Save')]")

    assert 'const strategy = "css";' in css_script
    assert 'const raw = "#weird\\"id";' in css_script
    assert "document.querySelector(raw)" in css_script
    assert 'const strategy = "xpath";' in xpath_script
    assert "const raw = \"//button[contains(., 'Save')]\";" in xpath_script
    assert "XPathResult.FIRST_ORDERED_NODE_TYPE" in xpath_script
