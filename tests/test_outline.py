"""Unit tests for page-understanding outline helpers."""

from __future__ import annotations

from drissionpage_mcp.outline import (
    build_page_snapshot_script,
    recommend_selector,
    summarize_elements,
)


class FakeElement:
    def __init__(self, *, tag: str, text: str, html: str, attrs: dict[str, str]):
        self.tag = tag
        self.text = text
        self.html = html
        self.attrs = attrs

    def attr(self, name: str):
        return self.attrs.get(name)


def test_recommend_selector_prefers_stable_attributes() -> None:
    assert recommend_selector("button", {"id": "save"}) == "#save"
    assert (
        recommend_selector("button", {"data-testid": "save button"})
        == '[data-testid="save button"]'
    )
    assert recommend_selector("input", {"name": "email"}) == 'input[name="email"]'
    assert (
        recommend_selector("button", {"aria-label": "Save"})
        == 'button[aria-label="Save"]'
    )
    assert recommend_selector("article", {"class": "card featured"}) == "article.card"
    assert recommend_selector("li", {}, index=2) == "li:nth-of-type(3)"


def test_summarize_elements_bounds_output_and_html() -> None:
    long_text = "x" * 600
    elements = [
        FakeElement(
            tag="article",
            text=long_text,
            html="<article>" + ("y" * 1200) + "</article>",
            attrs={"id": "alpha", "class": "card"},
        ),
        FakeElement(
            tag="article",
            text="Beta",
            html="<article>Beta</article>",
            attrs={"id": "beta"},
        ),
    ]

    summaries, truncated = summarize_elements(elements, limit=1, include_html=True)

    assert truncated is True
    assert summaries == [
        {
            "index": 0,
            "tag": "article",
            "text": "x" * 500,
            "selector": "#alpha",
            "attributes": {"id": "alpha", "class": "card"},
            "html": "<article>" + ("y" * 991),
        }
    ]


def test_build_page_snapshot_script_embeds_bounded_literals() -> None:
    script = build_page_snapshot_script(
        include_html=True,
        max_elements=7,
        max_text_chars=123,
    )

    assert "const includeHtml = true;" in script
    assert "const maxElements = 7;" in script
    assert "const maxTextChars = 123;" in script
    assert "document.querySelectorAll" in script
