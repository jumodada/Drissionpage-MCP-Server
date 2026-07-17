"""MCP Resources coverage for 0.4.0 public context surfaces."""

from __future__ import annotations

import json
from typing import Any

import pytest
from mcp.types import (
    ListResourcesRequest,
    ReadResourceRequest,
    ReadResourceRequestParams,
)

from drissionpage_mcp.resources import (
    PAGE_HTML_EXCERPT_CHARS,
    PAGE_TEXT_EXCERPT_CHARS,
    RESOURCE_JSON_MAX_CHARS,
    _fit_resource_budget,
    _safe_string_attr,
    _truncate,
)
from drissionpage_mcp.server import DrissionPageMCPServer


RESOURCE_URIS = [
    "drissionpage://session/summary",
    "drissionpage://session/history",
    "drissionpage://session/state",
    "drissionpage://session/config",
    "drissionpage://guide/model-usage",
    "drissionpage://page/current",
    "drissionpage://tools/catalog",
    "drissionpage://policy/summary",
    "drissionpage://task/current",
    "drissionpage://artifacts/inventory",
    "drissionpage://runtime/capabilities",
]


@pytest.mark.asyncio
async def test_list_resources_is_deterministic_and_json_typed() -> None:
    server = DrissionPageMCPServer()
    handler = server.server.request_handlers[ListResourcesRequest]

    result = await handler(ListResourcesRequest(method="resources/list"))

    resources = result.root.resources
    assert [str(resource.uri) for resource in resources] == RESOURCE_URIS
    assert [resource.mimeType for resource in resources] == ["application/json"] * 11
    assert all(resource.name and resource.description for resource in resources)
    current_page = resources[5]
    assert current_page.name == "page_current"
    assert "redaction" not in current_page.description.lower()


@pytest.mark.asyncio
async def test_read_session_and_policy_resources_do_not_initialize_browser(
    monkeypatch,
) -> None:
    monkeypatch.delenv("DP_MCP_DENY_EXTERNAL_SUBMISSION", raising=False)
    monkeypatch.delenv("DP_MCP_DENY_DOWNLOAD", raising=False)
    monkeypatch.delenv("DP_MCP_DOWNLOAD_ROOT", raising=False)
    monkeypatch.delenv("CHROME_PATH", raising=False)
    monkeypatch.delenv("DP_BROWSER_PATH", raising=False)
    monkeypatch.delenv("DP_USER_DATA_PATH", raising=False)
    monkeypatch.setenv("DP_MCP_NAV_ALLOWLIST", "example.com,allowed.test")
    monkeypatch.setenv("DP_MCP_BLOCK_PRIVATE_NETWORK", "1")
    monkeypatch.setenv("DP_MCP_DENY_EXTERNAL_SUBMISSION", "1")

    server = DrissionPageMCPServer()

    session_payload = await _read_json(server, "drissionpage://session/summary")
    state_payload = await _read_json(server, "drissionpage://session/state")
    policy_payload = await _read_json(server, "drissionpage://policy/summary")
    config_payload = await _read_json(server, "drissionpage://session/config")
    guide_payload = await _read_json(server, "drissionpage://guide/model-usage")
    history_payload = await _read_json(server, "drissionpage://session/history")
    task_payload = await _read_json(server, "drissionpage://task/current")
    artifacts_payload = await _read_json(server, "drissionpage://artifacts/inventory")
    capabilities_payload = await _read_json(
        server, "drissionpage://runtime/capabilities"
    )

    assert server.context is None
    assert session_payload == {
        "available": True,
        "browser_active": False,
        "tab_count": 0,
        "current_url": "",
        "policy": {
            "profile": "restricted",
            "controls": {
                "navigation_allowlist": True,
                "navigation_blocklist": False,
                "block_private_network": True,
                "screenshot_root": False,
                "upload_root": False,
                "download_root": False,
                "deny_external_submission": True,
                "deny_download": False,
            },
        },
    }
    assert state_payload == {
        "available": False,
        "reason": "NO_ACTIVE_TAB",
        "browser_active": False,
        "current_url": "",
        "cookies": {"count": 0, "names": []},
        "storage": {
            "local": {"count": 0, "keys": []},
            "session": {"count": 0, "keys": []},
        },
    }
    assert config_payload["available"] is True
    assert config_payload["browser_active"] is False
    assert config_payload["environment"]["user_data_path"]["configured"] is False
    assert config_payload["environment"]["browser_path"]["value"] == ""
    assert config_payload["policy"]["profile"] == "restricted"
    assert guide_payload["available"] is True
    assert guide_payload["version"] == "0.6.2"
    assert "DrissionPage>=4.1.1.4,<5" in guide_payload["instructions"]
    assert "form_fill_preview" in guide_payload["instructions"]
    assert "network_listen_start" in guide_payload["instructions"]
    assert "page_click_xy" in guide_payload["instructions"]
    assert "page_pointer_drag_element" in guide_payload["instructions"]
    assert "track_ratio" in guide_payload["instructions"]
    assert "page_detect_challenges" in guide_payload["instructions"]
    assert "page_click_xy_batch" in guide_payload["instructions"]
    assert "page_wait_challenge_result" in guide_payload["instructions"]
    assert (
        "fully autonomous" not in guide_payload["instructions"].lower()
        or "autonomous" in guide_payload["instructions"].lower()
    )
    assert "viewport CSS coordinates" in guide_payload["instructions"]
    assert "full_page=false" in guide_payload["instructions"]
    assert "precise" in guide_payload["instructions"]
    assert "stale coordinate actions" in guide_payload["instructions"]
    assert "observation only" in guide_payload["network"]["boundary"]
    assert guide_payload["tested"]["browser_backed"] is True
    assert "element_input_text" not in json.dumps(guide_payload)
    assert policy_payload["profile"] == "restricted"
    assert policy_payload["controls"]["navigation_allowlist"] == {
        "configured": True,
        "count": 2,
        "values": "<redacted>",
    }
    assert policy_payload["controls"]["block_private_network"] is True
    assert policy_payload["controls"]["deny_external_submission"] is True
    assert policy_payload["controls"]["download_root"] == {"configured": False}
    assert policy_payload["controls"]["deny_download"] is False
    assert config_payload["policy"]["controls"]["deny_external_submission"] is True
    assert config_payload["policy"]["controls"]["download_root"] == {
        "configured": False
    }
    assert config_payload["policy"]["controls"]["deny_download"] is False
    assert history_payload == {
        "available": True,
        "limit": 100,
        "count": 0,
        "actions": [],
    }
    assert task_payload == {
        "available": False,
        "reason": "NO_ACTIVE_TASK",
        "task": None,
    }
    assert artifacts_payload == {
        "available": False,
        "reason": "NO_ACTIVE_TASK",
        "count": 0,
        "returned": 0,
        "artifacts": [],
        "truncated": False,
    }
    assert capabilities_payload == {
        "available": True,
        "capabilities": {
            "schema_version": "1",
            "overall_status": "unprobed",
            "drissionpage_version": "",
            "browser_product": "",
            "browser_version": "",
            "capabilities": [],
        },
    }


@pytest.mark.asyncio
async def test_new_runtime_resources_are_bounded_without_browser_side_effects() -> None:
    from datetime import datetime, timezone

    from drissionpage_mcp.context import DrissionPageContext
    from drissionpage_mcp.tool_outputs import ArtifactRef

    server = DrissionPageMCPServer()
    server.context = DrissionPageContext(artifact_limit=80)
    for index in range(80):
        server.context.record_artifact(
            ArtifactRef(
                artifact_id=f"artifact-{index:06d}",
                task_id=server.context.task_id,
                producing_action_id="action-000001",
                kind="download",
                filename=f"report-{index}.csv",
                mime_type="text/csv",
                size_bytes=index,
                sha256=f"{index:064x}",
                safe_relative_path=(
                    f"{server.context.task_id}/reports/report-{index}.csv"
                ),
                source_url="https://example.test/report?token=secret",
                created_at=datetime.now(timezone.utc),
            )
        )

    task_payload = await _read_json(server, "drissionpage://task/current")
    artifacts_payload = await _read_json(server, "drissionpage://artifacts/inventory")
    capabilities_payload = await _read_json(
        server, "drissionpage://runtime/capabilities"
    )

    assert server.context.is_active() is False
    assert task_payload["available"] is True
    assert "receipts" not in task_payload["task"]
    assert "operation_keys" not in task_payload["task"]
    assert artifacts_payload["count"] == 80
    assert artifacts_payload["truncated"] is True
    assert artifacts_payload["returned"] < artifacts_payload["count"]
    assert capabilities_payload["capabilities"]["overall_status"] == "unprobed"
    for payload in (task_payload, artifacts_payload, capabilities_payload):
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        assert len(encoded) <= RESOURCE_JSON_MAX_CHARS
        assert "token=secret" not in encoded
        assert "/Users/" not in encoded


@pytest.mark.asyncio
async def test_artifact_inventory_preserves_safe_receipt_correlation_without_paths() -> (
    None
):
    from datetime import datetime, timezone

    from drissionpage_mcp.context import DrissionPageContext
    from drissionpage_mcp.tool_outputs import ArtifactRef

    server = DrissionPageMCPServer()
    server.context = DrissionPageContext()
    server.context.record_artifact(
        ArtifactRef(
            artifact_id="artifact-000001",
            task_id=server.context.task_id,
            producing_action_id="action-000001",
            kind="download",
            filename="fixture-report.csv",
            mime_type="text/csv",
            size_bytes=55,
            sha256="a" * 64,
            safe_relative_path=(
                f"{server.context.task_id}/action-000001/fixture-report.csv"
            ),
            source_url="https://user:pass@example.test/report.csv?token=secret",
            created_at=datetime.now(timezone.utc),
        )
    )

    payload = await _read_json(server, "drissionpage://artifacts/inventory")

    assert payload["available"] is True
    assert payload["count"] == 1
    artifact = payload["artifacts"][0]
    assert artifact["artifact_id"] == "artifact-000001"
    assert artifact["producing_action_id"] == "action-000001"
    assert artifact["safe_relative_path"].startswith(server.context.task_id)
    encoded = json.dumps(payload, ensure_ascii=False)
    assert "/Users/" not in encoded
    assert "token=secret" not in encoded
    assert "user:pass" not in encoded


@pytest.mark.asyncio
async def test_read_page_current_without_active_tab_is_unavailable() -> None:
    server = DrissionPageMCPServer()

    payload = await _read_json(server, "drissionpage://page/current")

    assert payload == {
        "available": False,
        "reason": "NO_ACTIVE_TAB",
        "url": "",
        "title": "",
        "text_excerpt": "",
        "html_excerpt": "",
        "truncated": False,
        "limits": {
            "text_chars": PAGE_TEXT_EXCERPT_CHARS,
            "html_chars": PAGE_HTML_EXCERPT_CHARS,
        },
        "meta": {
            "approx_tokens": 0,
            "json_chars": 0,
            "truncated": False,
        },
    }
    assert server.context is None


@pytest.mark.asyncio
async def test_read_page_current_truncates_text_and_html() -> None:
    server = DrissionPageMCPServer()
    server.context = FakeContext(
        FakeTab(
            url="https://example.test/",
            title="Example",
            text="t" * (PAGE_TEXT_EXCERPT_CHARS + 7),
            html="<main>" + ("h" * PAGE_HTML_EXCERPT_CHARS) + "</main>",
        )
    )

    payload = await _read_json(server, "drissionpage://page/current")

    assert payload["available"] is True
    assert payload["url"] == "https://example.test/"
    assert payload["title"] == "Example"
    assert len(payload["text_excerpt"]) <= PAGE_TEXT_EXCERPT_CHARS
    assert len(payload["html_excerpt"]) <= PAGE_HTML_EXCERPT_CHARS
    assert payload["truncated"] is True
    assert payload["meta"]["approx_tokens"] > 0
    assert payload["meta"]["json_chars"] > 0
    assert payload["meta"]["truncated"] is True
    assert payload["text_truncation"] == {
        "truncated": True,
        "original_length": PAGE_TEXT_EXCERPT_CHARS + 7,
        "limit": PAGE_TEXT_EXCERPT_CHARS,
    }
    assert payload["html_truncation"]["original_length"] > PAGE_HTML_EXCERPT_CHARS
    assert len(json.dumps(payload, ensure_ascii=False, separators=(",", ":"))) <= (
        RESOURCE_JSON_MAX_CHARS
    )


@pytest.mark.asyncio
async def test_tools_catalog_matches_public_tools_and_excludes_aliases() -> None:
    server = DrissionPageMCPServer()

    payload = await _read_json(server, "drissionpage://tools/catalog")

    assert "tools/list" in payload["schema_source"]
    names = [tool["name"] for tool in payload["tools"]]
    assert len(names) == 62
    assert names == list(server.tools.keys())
    assert "page_snapshot" in names
    assert "page_observe" in names
    assert "page_console_logs" in names
    assert "page_evaluate" in names
    assert "page_screenshot_save" in names
    assert "element_find_all" in names
    assert "form_inspect" in names
    assert "wait_until" in names
    assert "element_upload_file" in names
    assert "page_scroll" in names
    assert "frame_list" in names
    assert "shadow_find" in names
    assert "storage_get" in names
    assert "browser_open_and_snapshot" in names
    assert "browser_extract_links" in names
    assert "form_fill_preview" in names
    assert "form_fill" in names
    assert "form_submit" in names
    assert "page_dialog_respond" in names
    assert "element_click_and_download" in names
    assert "network_listen_start" in names
    assert "network_listen_wait" in names
    assert "network_listen_stop" in names
    assert {"tab_list", "tab_switch", "tab_close"} <= set(names)
    assert "element_input_text" not in names
    assert "wait_sleep" not in names
    schema_by_name = {tool["name"]: tool["output_schema"] for tool in payload["tools"]}
    assert schema_by_name["page_snapshot"] == "PageSnapshotData"
    assert schema_by_name["page_observe"] == "PageObservation"
    assert schema_by_name["page_console_logs"] == "ConsoleLogsData"
    assert schema_by_name["page_evaluate"] == "PageEvaluateData"
    assert schema_by_name["element_find_all"] == "ElementFindAllData"
    assert schema_by_name["form_inspect"] == "FormInspectData"
    assert schema_by_name["wait_until"] == "WaitUntilData"
    assert schema_by_name["element_upload_file"] == "ElementUploadFileData"
    assert schema_by_name["frame_snapshot"] == "FrameSnapshotData"
    assert schema_by_name["storage_get"] == "StorageGetData"
    assert schema_by_name["browser_open_and_snapshot"] == "BrowserOpenAndSnapshotData"
    assert schema_by_name["browser_extract_links"] == "BrowserExtractLinksData"
    assert schema_by_name["form_fill_preview"] == "FormFillPreviewData"
    assert schema_by_name["form_fill"] == "FormFillData"
    assert schema_by_name["form_submit"] == "FormSubmitData"
    assert schema_by_name["page_dialog_respond"] == "PageDialogRespondData"
    assert schema_by_name["element_click_and_download"] == (
        "ElementClickAndDownloadData"
    )
    assert schema_by_name["network_listen_wait"] == "NetworkListenWaitData"
    assert schema_by_name["page_pointer_move"] == "PagePointerMoveData"
    assert schema_by_name["page_pointer_drag"] == "PagePointerDragData"
    assert schema_by_name["page_pointer_drag_element"] == "PagePointerDragElementData"
    assert schema_by_name["page_detect_challenges"] == "DetectChallengesData"
    assert schema_by_name["page_click_xy_batch"] == "BatchClickData"
    assert schema_by_name["page_wait_challenge_result"] == "WaitChallengeData"
    assert schema_by_name["page_click_xy"] == "PageClickXYData"
    navigate_tool = payload["tools"][0]
    assert (
        navigate_tool.items()
        >= {
            "name": "page_navigate",
            "title": "Navigate to URL",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "output_schema": "PageNavigateData",
        }.items()
    )
    assert navigate_tool["description"] == "Navigate to a specific URL in the browser"


@pytest.mark.asyncio
async def test_model_usage_guide_exposes_workflow_first_routes() -> None:
    server = DrissionPageMCPServer()

    payload = await _read_json(server, "drissionpage://guide/model-usage")

    routes = {route["task"]: route for route in payload["workflow_routes"]}
    assert routes["summarize_or_inspect"]["preferred_sequence"][:2] == [
        "browser_open_and_snapshot",
        "page_snapshot",
    ]
    assert routes["link_discovery"]["preferred_sequence"] == ["browser_extract_links"]
    assert routes["safe_form_fill"]["preferred_sequence"][:2] == [
        "form_inspect",
        "form_fill_preview",
    ]
    assert routes["vision_guided_interaction"]["preferred_sequence"] == [
        "prefer element_find/element_click when reliable",
        "page_screenshot full_page=false",
        "identify and map viewport CSS coordinates",
        "page_pointer_drag_element for stable selector paths, otherwise page_pointer_move, page_click_xy, or page_pointer_drag by interaction intent",
        "bounded state verification",
    ]
    assert "canvas" in routes["vision_guided_interaction"]["use_when"]
    vision = payload["vision_interaction"]
    assert vision["coordinate_contract"]["accepted"] == "viewport CSS pixels"
    assert (
        "full-page document coordinates"
        in vision["coordinate_contract"]["not_accepted_directly"]
    )
    assert "window.innerWidth" in vision["coordinate_contract"]["mapping_hint"]
    assert set(vision["profiles"]) == {"natural", "precise", "direct"}
    assert "must be supplied together" in vision["start_coordinate_rule"]
    assert any("do not repeat" in rule for rule in vision["decision_rules"])
    assert any("stale coordinates" in rule for rule in vision["recovery"])
    assert "security or anti-automation" in vision["boundary"]
    assert payload["discovery"]["workflow_guide"] == (
        "drissionpage://guide/model-usage"
    )
    assert payload["discovery"]["compact_tool_contracts"] == (
        "drissionpage://tools/catalog"
    )
    assert payload["discovery"]["complete_tool_schemas"] == "tools/list"
    assert payload["recovery_loop"] == [
        "Inspect structuredContent.error.",
        "Follow the first actionable error.details.hints entry.",
        "Retry only after corrected input or changed page evidence.",
        "Stop and report the blocker when the same failure repeats.",
    ]
    assert routes["network_observation"]["preferred_sequence"] == [
        "network_listen_start",
        "trigger action",
        "network_listen_wait",
        "network_listen_stop",
    ]


@pytest.mark.asyncio
async def test_tools_catalog_exposes_descriptions_for_ai_tool_choice() -> None:
    server = DrissionPageMCPServer()

    payload = await _read_json(server, "drissionpage://tools/catalog")

    by_name = {tool["name"]: tool for tool in payload["tools"]}
    assert "Open a URL" in by_name["browser_open_and_snapshot"]["description"]
    assert "bounded snapshot" in by_name["browser_open_and_snapshot"]["description"]
    assert (
        "Extract bounded link data" in by_name["browser_extract_links"]["description"]
    )
    assert "without submitting" in by_name["form_fill_preview"]["description"]
    assert "without submitting" in by_name["form_fill"]["description"]
    assert "verify live values" in by_name["form_fill"]["description"]
    assert "at most once" in by_name["form_submit"]["description"]
    assert "dialog" in by_name["page_dialog_respond"]["description"].lower()
    assert "download" in by_name["element_click_and_download"]["description"].lower()
    assert "without clicking" in by_name["page_pointer_move"]["description"]
    assert "drag" in by_name["page_pointer_drag"]["description"].lower()
    assert "immediately before" in by_name["page_pointer_drag_element"]["description"]
    assert "cubic Bézier path" in by_name["page_click_xy"]["description"]
    assert "reaction delay" in by_name["page_click_xy"]["description"]
    assert "network observation" in by_name["network_listen_start"]["description"]
    assert "does not intercept" in by_name["network_listen_start"]["description"]

    click = by_name["page_click_xy"]
    assert click["required_input"] == ["x", "y"]
    assert {"start_x", "start_y", "profile", "button", "element"} <= set(
        click["optional_input"]
    )
    assert click["input_fields"]["profile"]["default"] == "natural"
    assert click["input_fields"]["profile"]["enum"] == [
        "natural",
        "precise",
        "direct",
    ]
    assert "viewport" in click["input_fields"]["x"]["description"].lower()

    assert by_name["browser_open_and_snapshot"]["required_input"] == ["url"]
    assert by_name["form_fill_preview"]["required_input"] == ["fields"]
    assert by_name["form_fill"]["required_input"] == ["fields"]
    assert {
        "form_selector",
        "timeout",
        "redact_values",
        "verify",
    } <= set(by_name["form_fill"]["optional_input"])
    assert by_name["form_submit"]["required_input"] == []
    assert {"form_selector", "submit_selector", "operation_key", "expect"} <= set(
        by_name["form_submit"]["optional_input"]
    )
    assert by_name["page_dialog_respond"]["required_input"] == ["action"]
    assert {"prompt_text", "timeout"} <= set(
        by_name["page_dialog_respond"]["optional_input"]
    )
    assert {"button", "click_count"} <= set(by_name["element_click"]["optional_input"])
    assert by_name["element_click"]["input_fields"]["button"]["default"] == "left"
    assert by_name["element_click"]["input_fields"]["click_count"]["default"] == 1
    assert by_name["element_click_and_download"]["required_input"] == ["selector"]
    assert {
        "operation_key",
        "timeout",
        "expected_filename",
        "expected_mime_type",
    } <= set(by_name["element_click_and_download"]["optional_input"])
    assert by_name["network_listen_start"]["required_input"] == []


@pytest.mark.asyncio
async def test_read_unknown_resource_reports_value_error() -> None:
    server = DrissionPageMCPServer()
    handler = server.server.request_handlers[ReadResourceRequest]

    with pytest.raises(ValueError, match="Unknown resource URI"):
        await handler(
            ReadResourceRequest(
                method="resources/read",
                params=ReadResourceRequestParams(uri="drissionpage://unknown"),
            )
        )


def test_resource_helpers_handle_budget_and_attribute_edges() -> None:
    small = {"html_excerpt": "ok", "text_excerpt": "ok", "truncated": False}
    assert _fit_resource_budget(small) is small

    large = {
        "html_excerpt": "h" * PAGE_HTML_EXCERPT_CHARS,
        "text_excerpt": "t" * PAGE_TEXT_EXCERPT_CHARS,
        "truncated": False,
    }
    fitted = _fit_resource_budget(large)
    assert fitted["truncated"] is True
    assert fitted["resource_truncation"] == {
        "truncated": True,
        "original_length": len(
            json.dumps(large, ensure_ascii=False, separators=(",", ":"))
        ),
        "limit": RESOURCE_JSON_MAX_CHARS,
    }
    assert len(json.dumps(fitted, ensure_ascii=False, separators=(",", ":"))) <= (
        RESOURCE_JSON_MAX_CHARS
    )

    value, metadata = _truncate("short", 20)
    assert value == "short"
    assert metadata == {"truncated": False, "original_length": 5, "limit": 20}

    class BrokenPage:
        @property
        def text(self):
            raise RuntimeError("detached")

    assert _safe_string_attr(BrokenPage(), "text") == ""


async def _read_json(server: DrissionPageMCPServer, uri: str) -> dict[str, Any]:
    handler = server.server.request_handlers[ReadResourceRequest]
    result = await handler(
        ReadResourceRequest(
            method="resources/read",
            params=ReadResourceRequestParams(uri=uri),
        )
    )
    contents = result.root.contents
    assert len(contents) == 1
    assert contents[0].mimeType == "application/json"
    return json.loads(contents[0].text)


class FakeContext:
    def __init__(self, tab: FakeTab) -> None:
        self._tab = tab

    def current_tab(self) -> FakeTab:
        return self._tab

    def tabs(self) -> list[FakeTab]:
        return [self._tab]

    def is_active(self) -> bool:
        return True


class FakeTab:
    def __init__(self, *, url: str, title: str, text: str, html: str) -> None:
        self.url = url
        self.page = FakePage(title=title, text=text, html=html)


class FakePage:
    def __init__(self, *, title: str, text: str, html: str) -> None:
        self.title = title
        self.text = text
        self.html = html
