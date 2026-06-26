"""Selector normalization contract tests."""

from __future__ import annotations

import pytest

from drissionpage_mcp.selector import normalize_selector


@pytest.mark.parametrize(
    ("selector", "locator", "strategy", "normalized"),
    [
        ("", "", "page", False),
        ("h1", "css:h1", "css", True),
        ("#app", "css:#app", "css", True),
        ("input[name='custname']", "css:input[name='custname']", "css", True),
        ("css:h1", "css:h1", "css", False),
        ("css=h1", "css=h1", "css", False),
        ("tag:h1", "tag:h1", "tag", False),
        ("tag=h1", "tag=h1", "tag", False),
        ("text:Title", "text:Title", "text", False),
        ("text=Title", "text=Title", "text", False),
        ("xpath://h1", "xpath://h1", "xpath", False),
        ("x://h1", "x://h1", "xpath", False),
        ("//h1", "xpath://h1", "xpath", True),
        (".//input", "xpath:.//input", "xpath", True),
        ("@name=custname", "@name=custname", "drissionpage", False),
    ],
)
def test_normalize_selector_contract(
    selector: str, locator: str, strategy: str, normalized: bool
) -> None:
    plan = normalize_selector(selector)

    assert plan.original == selector
    assert plan.locator == locator
    assert plan.strategy == strategy
    assert plan.normalized is normalized


def test_normalize_selector_rejects_blank_whitespace() -> None:
    with pytest.raises(ValueError, match="blank selector"):
        normalize_selector("   ")
