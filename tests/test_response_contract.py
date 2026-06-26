"""Response contract tests for machine-readable MCP tool results."""

from __future__ import annotations

import base64
import json
import re

from drissionpage_mcp.response import ToolResponse

JSON_RESULT_SENTINEL = "### JSON_RESULT"
ONE_PIXEL_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwAD"
    "hgGAWjR9awAAAABJRU5ErkJggg=="
)


def test_result_content_starts_with_json_result_sentinel() -> None:
    """returns the JSON_RESULT sentinel as the first text content item for results."""

    response = ToolResponse()
    response.add_result('{"ok": true}')

    content = response.get_content()

    assert content[0].type == "text"
    assert content[0].text.startswith(JSON_RESULT_SENTINEL)


def test_default_success_content_starts_with_json_result_sentinel() -> None:
    """returns the JSON_RESULT sentinel for default successful empty responses."""

    content = ToolResponse().get_content()

    assert content[0].type == "text"
    assert content[0].text.startswith(JSON_RESULT_SENTINEL)


def test_error_without_explicit_code_is_classified_from_message() -> None:
    """maps common tool-level failure messages to stable error codes."""

    response = ToolResponse()
    response.add_error("Failed to find element '#missing': Element not found")

    payload = response.get_structured_content()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "ELEMENT_NOT_FOUND"


def test_screenshot_result_includes_image_content_and_json_metadata() -> None:
    """emits PNG image content plus parseable screenshot metadata."""

    response = ToolResponse()
    response.add_screenshot(ONE_PIXEL_PNG, {"full_page": False})

    content = response.get_content()
    payload = response.get_structured_content()
    screenshot = payload["data"]["screenshot"]

    assert any(item.type == "image" for item in content)
    assert screenshot == {
        "mime_type": "image/png",
        "inline": True,
        "encoding": "base64",
        "full_page": False,
        "bytes": len(base64.b64decode(ONE_PIXEL_PNG)),
        "width": 1,
        "height": 1,
    }

    text_mirror_payload = json.loads(
        re.search(r"```json\n(.*?)\n```", content[0].text, re.S).group(1)
    )
    assert text_mirror_payload["data"]["screenshot"] == screenshot


def test_errors_module_reexports_stable_error_api() -> None:
    """keeps the public error helper module from becoming dead re-export slop."""

    from drissionpage_mcp.errors import ErrorCode, ToolError, classify_error

    assert ErrorCode.TIMEOUT.value == "TIMEOUT"
    assert ToolError(code="X", message="m").to_dict() == {"code": "X", "message": "m"}
    assert classify_error(TimeoutError("timed out")) is ErrorCode.TIMEOUT
