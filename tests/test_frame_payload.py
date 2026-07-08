"""Focused coverage for frame payload helpers."""

from __future__ import annotations

from drissionpage_mcp.frame_payload import _frame_snapshot_payload, _frame_summary


class AttrElement:
    def __init__(self, attrs: dict[str, str | None] | None = None) -> None:
        self.attrs = attrs or {}

    def attr(self, name: str):
        return self.attrs.get(name)


class TextElement:
    text = "Body fallback text"


class LookupFailFrame:
    text = ""
    url = "https://example.test/frame"
    title = "Frame Title"

    def ele(self, locator: str, **kwargs):
        assert locator == "tag:body"
        return TextElement()

    def eles(self, _locator: str, **_kwargs):
        raise RuntimeError("lookup failed")


class BodyFailFrame(LookupFailFrame):
    title = None
    url = None

    def ele(self, _locator: str, **_kwargs):
        raise RuntimeError("body failed")


def test_frame_summary_selector_fallbacks() -> None:
    assert _frame_summary(type("Frame", (), {"frame_ele": AttrElement({"id": "login-frame"})})(), 0)[
        "selector"
    ] == "#login-frame"
    assert _frame_summary(type("Frame", (), {"frame_ele": AttrElement({"name": "checkout"})})(), 1)[
        "selector"
    ] == 'iframe[name="checkout"]'
    assert _frame_summary(AttrElement(), 2)["selector"] == "iframe:nth-of-type(3)"
    assert _frame_summary(AttrElement({"id": "ignored"}), 3, "css:iframe.special")[
        "selector"
    ] == "css:iframe.special"


def test_frame_snapshot_lookup_failure_returns_empty_groups_and_body_fallback() -> None:
    payload = _frame_snapshot_payload(
        LookupFailFrame(),
        include_html=True,
        max_elements=5,
        max_text_chars=4,
    )

    assert payload["url"] == "https://example.test/frame"
    assert payload["title"] == "Frame Title"
    assert payload["text_excerpt"] == "Body"
    assert payload["headings"] == []
    assert payload["links"] == []
    assert payload["buttons"] == []
    assert payload["inputs"] == []
    assert payload["forms"] == []
    assert payload["counts"] == {
        "headings": 0,
        "links": 0,
        "buttons": 0,
        "inputs": 0,
        "forms": 0,
    }
    assert payload["truncated"] == {
        "text": True,
        "elements": False,
        "returned_elements": 0,
    }


def test_frame_snapshot_body_lookup_failure_uses_empty_text() -> None:
    payload = _frame_snapshot_payload(BodyFailFrame(), max_elements=0, max_text_chars=10)

    assert payload["url"] == ""
    assert payload["title"] == ""
    assert payload["text_excerpt"] == ""
    assert payload["truncated"]["text"] is False
