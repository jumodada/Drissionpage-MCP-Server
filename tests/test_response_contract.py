"""Response contract tests for machine-readable MCP tool results."""

from __future__ import annotations

import base64
import json
import re

import pytest

from drissionpage_mcp.response import (
    ErrorCode,
    ToolResponse,
    ToolResult,
    build_screenshot_metadata,
    classify_error,
)

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


@pytest.mark.parametrize(
    ("exc", "tool_name", "expected"),
    [
        (
            type("PolicyError", (Exception,), {"code": ErrorCode.POLICY_DENIED})(
                "blocked"
            ),
            "",
            ErrorCode.POLICY_DENIED,
        ),
        (ValueError("selector syntax invalid"), "", ErrorCode.SELECTOR_INVALID),
        (RuntimeError("operation timed out"), "", ErrorCode.TIMEOUT),
        (RuntimeError("No active tab"), "", ErrorCode.BROWSER_NOT_INITIALIZED),
        (RuntimeError("failed to navigate to url"), "", ErrorCode.PAGE_NAVIGATION_FAILED),
        (RuntimeError("boom"), "page_navigate", ErrorCode.PAGE_NAVIGATION_FAILED),
        (RuntimeError("screenshot failed"), "", ErrorCode.SCREENSHOT_FAILED),
        (RuntimeError("policy allowlist denied"), "", ErrorCode.POLICY_DENIED),
        (RuntimeError("browser launch failed"), "", ErrorCode.BROWSER_START_FAILED),
    ],
)
def test_classify_error_maps_mcp_recovery_categories(
    exc: Exception, tool_name: str, expected: ErrorCode
) -> None:
    assert classify_error(exc, tool_name) is expected


def test_set_tool_result_controls_error_state_and_default_error_content() -> None:
    response = ToolResponse()
    response.set_tool_result(
        ToolResult.failure(ErrorCode.UNKNOWN_ERROR, "explicit failure")
    )

    content = response.get_content()
    payload = response.get_structured_content()

    assert response.is_error() is True
    assert payload["ok"] is False
    assert payload["error"]["code"] == "UNKNOWN_ERROR"
    assert content[0].text.startswith(JSON_RESULT_SENTINEL)
    assert content[1].text == "### Error\nUnknown error occurred."


def test_add_image_accepts_bytes_and_rejects_invalid_input() -> None:
    response = ToolResponse()
    response.add_image(b"image-bytes", "image/png")

    images = [item for item in response.get_content() if item.type == "image"]

    assert images[0].data == base64.b64encode(b"image-bytes").decode()

    with pytest.raises(ValueError, match="Image data must be string or bytes"):
        response.add_image(object())  # type: ignore[arg-type]


def test_screenshot_metadata_handles_non_inline_and_malformed_images(tmp_path) -> None:
    raw_png = base64.b64decode(ONE_PIXEL_PNG)
    png_path = tmp_path / "screen.png"
    png_path.write_bytes(raw_png)

    assert build_screenshot_metadata(raw_png, full_page=True)["width"] == 1
    assert build_screenshot_metadata(path=str(png_path), inline=False) == {
        "mime_type": "image/png",
        "inline": False,
        "path": str(png_path),
        "bytes": len(raw_png),
        "width": 1,
        "height": 1,
    }

    invalid_base64 = build_screenshot_metadata("not base64", full_page=False)
    assert invalid_base64 == {
        "mime_type": "image/png",
        "inline": True,
        "encoding": "base64",
        "full_page": False,
    }

    missing_file = build_screenshot_metadata(path=str(tmp_path / "missing.png"))
    assert missing_file == {
        "mime_type": "image/png",
        "path": str(tmp_path / "missing.png"),
    }

    assert build_screenshot_metadata(b"short") == {
        "mime_type": "image/png",
        "inline": True,
        "encoding": "base64",
        "bytes": len(b"short"),
    }
    non_png = b"x" * 24
    assert build_screenshot_metadata(non_png)["bytes"] == len(non_png)
    assert "width" not in build_screenshot_metadata(non_png)
