"""Unit coverage for compact page observation helpers."""

from __future__ import annotations

from drissionpage_mcp.metadata import response_meta, with_response_meta
from drissionpage_mcp.observation import (
    bounded_json_value,
    diff_observations,
    result_type,
)


def test_diff_observations_reports_url_title_counts_and_text_changes() -> None:
    before = {
        "url": "https://example.test/start",
        "title": "Start",
        "counts": {"buttons": "1", "inputs": object()},
        "text_samples": ["Loading", "Save"],
    }
    after = {
        "url": "https://example.test/done",
        "title": "Done",
        "ready_state": "complete",
        "counts": {"buttons": 2, "links": 1},
        "text_samples": ["Save", "Saved"],
        "active_element": {"tag": "button"},
    }

    diff = diff_observations(before, after)

    assert diff["url_changed"] is True
    assert diff["title_changed"] is True
    assert diff["counts_before"] == {"buttons": 1, "inputs": 0}
    assert diff["counts_delta"] == {"buttons": 1, "inputs": 0, "links": 1}
    assert diff["appeared_texts"] == ["Saved"]
    assert diff["removed_texts"] == ["Loading"]
    assert diff["active_element"] == {"tag": "button"}


def test_bounded_json_value_and_result_type_cover_json_edges() -> None:
    short, truncated, original = bounded_json_value({"ok": True}, max_chars=20)
    long_object, object_truncated, object_original = bounded_json_value(
        {"items": list(range(20))},
        max_chars=12,
    )
    long_string, string_truncated, string_original = bounded_json_value(
        "abcdef",
        max_chars=3,
    )

    assert short == {"ok": True}
    assert truncated is False
    assert original > 0
    assert long_object == {"preview": '{"items":[0,', "truncated_json": True}
    assert object_truncated is True
    assert object_original > 12
    assert long_string == "abc"
    assert string_truncated is True
    assert string_original == 8
    assert [result_type(value) for value in (None, True, 1, "x", [], {}, object())] == [
        "null",
        "boolean",
        "number",
        "string",
        "array",
        "object",
        "object",
    ]


def test_response_metadata_detects_nested_truncation() -> None:
    payload = {"items": [{"truncated": {"text": False, "html": True}}]}

    meta = response_meta(payload)
    enriched = with_response_meta({"items": [1]}, truncated=False)

    assert meta["truncated"] is True
    assert meta["json_chars"] > 0
    assert enriched["meta"]["truncated"] is False
