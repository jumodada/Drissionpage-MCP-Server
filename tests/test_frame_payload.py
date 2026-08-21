"""Focused coverage for frame payload helpers."""

from __future__ import annotations

from drissionpage_mcp.browser.frame_payload import (
    _frame_snapshot_payload,
    _frame_summary,
)


class AttrElement:
    def __init__(self, attrs: dict[str, str | None] | None = None) -> None:
        self.attrs = attrs or {}

    def attr(self, name: str):
        return self.attrs.get(name)


class SummaryStates:
    is_alive = True
    is_displayed = True
    is_enabled = True
    is_clickable = True
    is_checked = False
    is_selected = False
    is_in_viewport = True
    is_whole_in_viewport = True
    is_covered = False


class SummaryRect:
    location = (20.0, 40.0)
    size = (300.0, 65.0)
    midpoint = (170.0, 72.5)
    click_point = (170.0, 43.0)
    viewport_location = (20.0, 40.0)
    viewport_midpoint = (170.0, 72.5)
    viewport_click_point = (170.0, 43.0)


class SummaryElement(AttrElement):
    states = SummaryStates()
    rect = SummaryRect()

    def run_js(self, _script: str):
        return {
            "display": "inline",
            "visibility": "visible",
            "opacity": 1.0,
            "pointer_events": "auto",
            "transform": "matrix3d(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)",
            "transform_style": "preserve-3d",
            "perspective": "600px",
            "ancestor_3d": True,
        }


class SummaryFrame:
    frame_ele = SummaryElement({"id": "challenge-frame"})
    title = "Challenge"
    url = "https://frame.example.test/"
    _is_diff_domain = True

    def run_js(self, _script: str):
        return True


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


def test_frame_summary_reports_boundary_access_and_outer_actionability() -> None:
    summary = _frame_summary(SummaryFrame(), 0)

    assert summary["boundary"] == "cross_origin"
    assert summary["document_access"] == "readable"
    assert summary["outer"]["rect"]["viewport_coordinate_space"] == (
        "top_level_viewport"
    )
    assert summary["outer"]["presentation"]["three_dimensional"] is True
    assert summary["outer"]["presentation"]["coordinate_actionability"] == (
        "transformed_3d"
    )


def test_frame_summary_marks_nested_owner_viewport_as_target_document() -> None:
    top_page = object()
    nested_owner = object()
    frame = SummaryFrame()
    frame.frame_ele = SummaryElement({"id": "nested-frame"})
    frame.frame_ele.owner = nested_owner

    summary = _frame_summary(frame, 0, top_page=top_page)

    assert summary["outer"]["rect"]["viewport_coordinate_space"] == (
        "target_document_viewport"
    )
    assert summary["outer"]["presentation"]["coordinate_actionability"] == (
        "transformed_3d"
    )


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
