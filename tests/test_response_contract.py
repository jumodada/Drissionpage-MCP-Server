"""Response contract tests for machine-readable MCP tool results."""

from __future__ import annotations
import base64
import json
import re
import pytest
from jsonschema import ValidationError, validate
from drissionpage_mcp.response_errors import ErrorCode, classify_error, recovery_hints
from drissionpage_mcp.response_media import build_screenshot_metadata
from drissionpage_mcp.tools import get_all_tools
from drissionpage_mcp.tools.base import ToolOutcome

JSON_RESULT_SENTINEL = "### JSON_RESULT"


def tool_result_output_schema(tool_name: str) -> dict[str, object]:
    return next(
        tool for tool in get_all_tools() if tool.name == tool_name
    ).output_schema()


class ToolResult:
    """Payload factory used only to validate generated public schemas."""

    @staticmethod
    def success(message: str = "", **data: object):
        class Payload:
            def to_dict(self) -> dict[str, object]:
                return {"ok": True, "message": message, "data": data}

        return Payload()

    @staticmethod
    def failure(code: ErrorCode | str, message: str, **details: object):
        code_value = code.value if isinstance(code, ErrorCode) else str(code)

        class Payload:
            def to_dict(self) -> dict[str, object]:
                return {
                    "ok": False,
                    "message": message,
                    "error": {
                        "code": code_value,
                        "message": message,
                        "details": details,
                    },
                }

        return Payload()


ONE_PIXEL_PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="


def test_result_content_starts_with_json_result_sentinel() -> None:
    """returns the JSON_RESULT sentinel as the first text content item for results."""
    response = ToolOutcome()
    response.add_result('{"ok": true}')
    content = response.content()
    assert content[0].type == "text"
    assert content[0].text.startswith(JSON_RESULT_SENTINEL)


def test_default_success_content_starts_with_json_result_sentinel() -> None:
    """returns the JSON_RESULT sentinel for default successful empty responses."""
    content = ToolOutcome().content()
    assert content[0].type == "text"
    assert content[0].text.startswith(JSON_RESULT_SENTINEL)


def test_error_without_explicit_code_is_classified_from_message() -> None:
    """maps common tool-level failure messages to stable error codes."""
    response = ToolOutcome()
    response.add_error("Failed to find element '#missing': Element not found")
    payload = response.structured_content()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "ELEMENT_NOT_FOUND"


def test_add_error_includes_actionable_recovery_hints() -> None:
    """adds machine-readable next steps without changing the error envelope."""
    response = ToolOutcome()
    response.add_error(
        "Failed to find element '#missing': Element not found",
        ErrorCode.ELEMENT_NOT_FOUND,
        selector="#missing",
    )
    details = response.structured_content()["error"]["details"]
    hints = details["hints"]
    assert details["selector"] == "#missing"
    assert {hint["action"] for hint in hints} >= {
        "inspect_page_snapshot",
        "find_similar_elements",
        "wait_for_element",
        "check_iframe_or_dynamic_content",
    }
    assert {hint.get("tool") for hint in hints} >= {
        "page_snapshot",
        "element_find_all",
        "wait_for_element",
    }


def test_recovery_hints_cover_common_runtime_failures() -> None:
    """keeps recovery hints deterministic for high-frequency failure categories."""
    timeout_hints = recovery_hints(ErrorCode.TIMEOUT, tool_name="wait_for_url")
    browser_hints = recovery_hints(ErrorCode.BROWSER_START_FAILED)
    not_initialized_hints = recovery_hints(ErrorCode.BROWSER_NOT_INITIALIZED)
    argument_hints = recovery_hints(ErrorCode.MCP_ARGUMENT_INVALID)
    not_found_hints = recovery_hints(ErrorCode.TOOL_NOT_FOUND)
    screenshot_policy_hints = recovery_hints(
        ErrorCode.POLICY_DENIED, message="Screenshot path denied by policy"
    )
    unsupported_hints = recovery_hints(
        ErrorCode.UNSUPPORTED_OPERATION,
        tool_name="network_listen_start",
        message="listener unavailable",
    )
    assert {hint["action"] for hint in timeout_hints} >= {
        "increase_timeout",
        "inspect_current_page",
    }
    assert any(
        (
            hint.get("command") == "drissionpage-mcp doctor --launch-browser"
            for hint in browser_hints
        )
    )
    assert not_initialized_hints[0] == {
        "action": "navigate_first",
        "message": "Open a page with the workflow helper when you need immediate page context; use page_navigate only for navigation-only retries.",
        "tool": "browser_open_and_snapshot",
    }
    assert argument_hints[0]["action"] == "check_input_schema"
    catalog_hint = next(
        hint for hint in argument_hints if hint["action"] == "inspect_tools_catalog"
    )
    assert "compact required/default field guidance" in catalog_hint["message"]
    assert "tools/list" in catalog_hint["message"]
    assert "complete JSON Schema" in catalog_hint["message"]
    assert not_found_hints[0]["action"] == "list_available_tools"
    assert any((hint["action"] == "read_model_usage_guide" for hint in not_found_hints))
    assert any(
        (
            hint.get("env") == "DP_MCP_SCREENSHOT_ROOT"
            for hint in screenshot_policy_hints
        )
    )
    assert any((hint["action"] == "verify_listener_api" for hint in unsupported_hints))


def test_screenshot_result_includes_image_content_and_json_metadata() -> None:
    """emits PNG image content plus parseable screenshot metadata."""
    response = ToolOutcome()
    response.add_screenshot(ONE_PIXEL_PNG, {"full_page": False})
    content = response.content()
    payload = response.structured_content()
    screenshot = payload["data"]["screenshot"]
    assert any((item.type == "image" for item in content))
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
        re.search("```json\\n(.*?)\\n```", content[0].text, re.S).group(1)
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
        (
            RuntimeError("failed to navigate to url"),
            "",
            ErrorCode.PAGE_NAVIGATION_FAILED,
        ),
        (RuntimeError("boom"), "page_navigate", ErrorCode.PAGE_NAVIGATION_FAILED),
        (RuntimeError("screenshot failed"), "", ErrorCode.SCREENSHOT_FAILED),
        (RuntimeError("policy allowlist denied"), "", ErrorCode.POLICY_DENIED),
        (RuntimeError("browser launch failed"), "", ErrorCode.BROWSER_START_FAILED),
        (RuntimeError("listener unsupported"), "", ErrorCode.UNSUPPORTED_OPERATION),
    ],
)
def test_classify_error_maps_mcp_recovery_categories(
    exc: Exception, tool_name: str, expected: ErrorCode
) -> None:
    assert classify_error(exc, tool_name) is expected


def test_failure_outcome_controls_error_state_and_default_error_content() -> None:
    response = ToolOutcome()
    response.add_error("explicit failure", ErrorCode.UNKNOWN_ERROR)
    content = response.content()
    payload = response.structured_content()
    assert response.is_error is True
    assert payload["ok"] is False
    assert payload["error"]["code"] == ErrorCode.UNKNOWN_ERROR.value
    assert "explicit failure" in content[1].text


def test_tool_result_output_schema_validates_real_payloads() -> None:
    schema = tool_result_output_schema("page_close")
    validate(
        ToolResult.success("Successfully closed browser", closed=True).to_dict(), schema
    )
    validate(
        ToolResult.failure(
            ErrorCode.MCP_ARGUMENT_INVALID,
            "Input validation error",
            tool_name="page_close",
        ).to_dict(),
        schema,
    )
    with pytest.raises(ValidationError):
        validate(
            {
                "ok": True,
                "message": "Successfully closed browser",
                "data": {"closed": True},
                "unexpected": True,
            },
            schema,
        )


def test_page_understanding_output_schemas_validate_success_payloads() -> None:
    snapshot_payload = ToolResult.success(
        "Captured page snapshot",
        url="https://example.test/catalog",
        title="Catalog",
        text_excerpt="Alpha Beta",
        headings=[],
        links=[],
        buttons=[],
        inputs=[],
        forms=[],
        counts={"headings": 0},
        truncated={"text": False, "elements": False, "returned_elements": 0},
        limits={"max_elements": 50, "max_text_chars": 4000},
        meta={"approx_tokens": 10, "json_chars": 35, "truncated": False},
    ).to_dict()
    find_all_payload = ToolResult.success(
        "Found 1 of 1 elements: .card",
        selector=".card",
        locator="css:.card",
        selector_strategy="css",
        selector_normalized=True,
        count=1,
        returned=1,
        limit=20,
        truncated=False,
        elements=[
            {
                "index": 0,
                "tag": "article",
                "text": "Alpha",
                "selector": "#alpha",
                "attributes": {"id": "alpha"},
            }
        ],
        meta={"approx_tokens": 10, "json_chars": 35, "truncated": False},
    ).to_dict()
    validate(snapshot_payload, tool_result_output_schema("page_snapshot"))
    validate(find_all_payload, tool_result_output_schema("element_find_all"))


def test_0_5_5_output_schemas_validate_new_capability_payloads() -> None:
    upload_payload = ToolResult.success(
        "Uploaded 1 file",
        selector="#upload",
        locator="css:#upload",
        selector_strategy="css",
        selector_normalized=True,
        uploaded=True,
        file_count=1,
        filenames=["fixture.txt"],
    ).to_dict()
    frame_payload = ToolResult.success(
        "Captured frame snapshot",
        frame={
            "index": 0,
            "selector": "#fixture-frame",
            "id": "fixture-frame",
            "name": "fixture-frame",
            "title": "Frame",
            "url": "https://example.test/frame",
        },
        url="https://example.test/frame",
        title="Frame",
        text_excerpt="Frame text",
        headings=[],
        links=[],
        buttons=[],
        inputs=[],
        forms=[],
        counts={},
        truncated={"text": False, "elements": False, "returned_elements": 0},
        limits={"max_elements": 20, "max_text_chars": 1000},
        meta={"approx_tokens": 10, "json_chars": 35, "truncated": False},
    ).to_dict()
    storage_payload = ToolResult.success(
        "Read local storage",
        area="local",
        key="",
        include_values=True,
        count=1,
        items={"mode": "dark"},
    ).to_dict()
    validate(upload_payload, tool_result_output_schema("element_upload_file"))
    validate(frame_payload, tool_result_output_schema("frame_snapshot"))
    validate(storage_payload, tool_result_output_schema("storage_get"))


def test_form_inspect_output_schema_validates_success_payload() -> None:
    payload = ToolResult.success(
        "Inspected 1 of 1 forms",
        selector="",
        include_values=False,
        count=1,
        returned=1,
        limits={"max_forms": 10, "max_fields_per_form": 50},
        truncated={"forms": False, "fields": False},
        meta={"approx_tokens": 10, "json_chars": 35, "truncated": False},
        forms=[
            {
                "index": 0,
                "selector": "#fixture-form",
                "id": "fixture-form",
                "name": "",
                "method": "get",
                "action": "https://example.test/form",
                "text": "Name Submit",
                "fields": [
                    {
                        "index": 0,
                        "tag": "input",
                        "type": "text",
                        "name": "name",
                        "label": "Name",
                        "selector": "#name",
                        "placeholder": "",
                        "required": False,
                        "disabled": False,
                        "readonly": False,
                        "checked": False,
                        "value": None,
                        "attributes": {"id": "name", "name": "name"},
                        "options": [],
                    }
                ],
            }
        ],
    ).to_dict()
    validate(payload, tool_result_output_schema("form_inspect"))


def test_observable_action_output_schemas_validate_success_payloads() -> None:
    changes = {
        "url_before": "https://example.test/start",
        "url_after": "https://example.test/done",
        "url_changed": True,
        "title_before": "Start",
        "title_after": "Done",
        "title_changed": True,
        "ready_state": "complete",
        "counts_before": {"buttons": 1},
        "counts_after": {"buttons": 2},
        "counts_delta": {"buttons": 1},
        "appeared_texts": ["Saved"],
        "removed_texts": ["Loading"],
        "active_element": None,
        "console_errors_added": 1,
        "console_warnings_added": 0,
        "new_console_messages": [
            {
                "index": 2,
                "level": "error",
                "text": "save failed",
                "url": "https://example.test/done",
                "line": 12,
                "column": 4,
                "source": "console-api",
            }
        ],
    }
    observe_payload = ToolResult.success(
        "Observed page state",
        url="https://example.test",
        title="Observable",
        ready_state="complete",
        counts={"buttons": 1, "inputs": 1},
        text_samples=["Ready"],
        active_element=None,
        console={
            "available": True,
            "listening": True,
            "count": 1,
            "total": 1,
            "next_cursor": 0,
            "error_count": 0,
            "warning_count": 0,
            "recent": [
                {
                    "index": 0,
                    "level": "log",
                    "text": "ready",
                    "url": "https://example.test",
                    "line": 1,
                    "column": 1,
                    "source": "console-api",
                }
            ],
        },
        limits={"max_texts": 20, "max_text_chars": 160},
    ).to_dict()
    console_payload = ToolResult.success(
        "Read 1 console log",
        available=True,
        listening=True,
        count=1,
        total=1,
        next_cursor=0,
        logs=[
            {
                "index": 0,
                "level": "log",
                "text": "ready",
                "url": "https://example.test",
                "line": 1,
                "column": 1,
                "source": "console-api",
            }
        ],
    ).to_dict()
    evaluate_payload = ToolResult.success(
        "Evaluated JavaScript",
        result={"status": "ready"},
        result_type="object",
        truncated=False,
        original_json_chars=18,
        max_chars=4000,
    ).to_dict()
    navigate_payload = ToolResult.success(
        "Successfully navigated",
        url="https://example.test/start",
        final_url="https://example.test/done",
        new_tab=False,
        tab_id="t0",
        changes=changes,
    ).to_dict()
    click_payload = ToolResult.success(
        "Successfully clicked element",
        selector="#save",
        locator="css:#save",
        selector_strategy="css",
        selector_normalized=True,
        url="https://example.test/done",
        changes=changes,
    ).to_dict()
    type_payload = ToolResult.success(
        "Successfully typed text",
        selector="#name",
        locator="css:#name",
        selector_strategy="css",
        selector_normalized=True,
        typed=True,
        cleared=True,
        changes=changes,
    ).to_dict()
    wait_payload = ToolResult.success(
        "Condition matched",
        condition="clickable",
        selector="#save",
        value="",
        name="",
        matched=True,
        timeout=2.0,
        elapsed_ms=100,
        state={"visible": True, "disabled": False},
    ).to_dict()
    validate(observe_payload, tool_result_output_schema("page_observe"))
    validate(console_payload, tool_result_output_schema("page_console_logs"))
    validate(evaluate_payload, tool_result_output_schema("page_evaluate"))
    validate(navigate_payload, tool_result_output_schema("page_navigate"))
    validate(click_payload, tool_result_output_schema("element_click"))
    validate(type_payload, tool_result_output_schema("element_type"))
    validate(wait_payload, tool_result_output_schema("wait_until"))


def test_0_5_6_workflow_and_network_schemas_validate_success_payloads() -> None:
    open_payload = ToolResult.success(
        "Opened page",
        url="https://example.test/workflow",
        final_url="https://example.test/workflow",
        title="Workflow",
        wait={
            "condition": "visible",
            "selector": "#app",
            "value": "",
            "matched": True,
            "timeout": 5.0,
        },
        snapshot={"title": "Workflow", "links": []},
        meta={"approx_tokens": 10, "json_chars": 35, "truncated": False},
    ).to_dict()
    links_payload = ToolResult.success(
        "Extracted links",
        selector="a",
        locator="css:a",
        selector_strategy="css",
        selector_normalized=True,
        include_text=True,
        same_origin_only=False,
        absolute_urls=True,
        count=1,
        returned=1,
        limit=50,
        truncated=False,
        links=[
            {
                "index": 0,
                "text": "Docs",
                "href": "/docs",
                "url": "https://example.test/docs",
                "selector": "#docs-link",
                "rel": "",
                "target": "",
            }
        ],
        meta={"approx_tokens": 10, "json_chars": 35, "truncated": False},
    ).to_dict()
    fill_payload = ToolResult.success(
        "Prepared fields",
        form_selector={
            "selector": "#profile",
            "locator": "css:#profile",
            "selector_strategy": "css",
            "selector_normalized": True,
        },
        form_found=True,
        form={
            "selector": "#profile",
            "id": "profile",
            "name": "",
            "method": "post",
            "action": "/api/echo.json",
        },
        field_count=2,
        filled_count=1,
        skipped_count=0,
        filled=[
            {
                "key": "name",
                "selector": "#name",
                "matched_by": "name",
                "tag": "input",
                "type": "text",
                "value": "<redacted>",
            }
        ],
        skipped=[],
        requires_confirmation=True,
        submitted=False,
        redacted=True,
    ).to_dict()
    start_payload = ToolResult.success(
        "Started network listener",
        listening=True,
        filters={
            "targets": ["/api"],
            "is_regex": False,
            "method": "",
            "resource_type": "",
        },
        started_at="2026-07-07T00:00:00+00:00",
        tab_id="t0",
        cleared=True,
    ).to_dict()
    wait_payload = ToolResult.success(
        "Captured 1 network packet",
        listening=True,
        timed_out=False,
        count=1,
        limit=10,
        packets=[
            {
                "index": 0,
                "url": "https://example.test/api/data.json",
                "method": "GET",
                "resource_type": "Fetch",
                "status": 200,
                "mime_type": "application/json",
                "failed": False,
                "fail_error": "",
                "request_headers": {"authorization": "<redacted>"},
                "response_headers": {"content-type": "application/json"},
                "body_excerpt": '{"ok":true}',
                "body_truncated": False,
                "body_type": "json",
            }
        ],
        meta={"approx_tokens": 10, "json_chars": 35, "truncated": False},
    ).to_dict()
    stop_payload = ToolResult.success(
        "Stopped network listener", listening=False, was_listening=True, cleared=True
    ).to_dict()
    validate(open_payload, tool_result_output_schema("browser_open_and_snapshot"))
    validate(links_payload, tool_result_output_schema("browser_extract_links"))
    validate(fill_payload, tool_result_output_schema("form_fill_preview"))
    validate(start_payload, tool_result_output_schema("network_listen_start"))
    validate(wait_payload, tool_result_output_schema("network_listen_wait"))
    validate(stop_payload, tool_result_output_schema("network_listen_stop"))


def test_add_image_accepts_bytes_and_rejects_invalid_input() -> None:
    response = ToolOutcome()
    response.add_image(b"image-bytes", "image/png")
    images = [item for item in response.content() if item.type == "image"]
    assert images[0].data == base64.b64encode(b"image-bytes").decode()
    with pytest.raises(ValueError, match="Image data must be string or bytes"):
        response.add_image(object())


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
