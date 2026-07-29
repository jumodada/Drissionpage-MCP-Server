"""Snapshot coverage for the MCP tool schema exposed to clients."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from drissionpage_mcp.server import DrissionPageMCPServer

SNAPSHOT_PATH = Path(__file__).parent / "snapshots" / "tools_schema.json"
TOOL_CONTRACT_PATH = Path(__file__).parents[1] / "docs" / "tool-contract.md"
PARAMETER_TABLE_START = "<!-- GENERATED:TOOL-PARAMETERS:START -->"
PARAMETER_TABLE_END = "<!-- GENERATED:TOOL-PARAMETERS:END -->"


def test_current_tool_schema_matches_snapshot() -> None:
    """exposes the public tools with stable schemas and annotations."""

    snapshot = _build_tool_schema_snapshot()

    if os.environ.get("UPDATE_SNAPSHOTS") == "1":
        SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT_PATH.write_text(_to_json(snapshot), encoding="utf-8")

    expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    assert snapshot == expected


def test_every_public_timeout_uses_json_number_schema() -> None:
    snapshot = _build_tool_schema_snapshot()
    timeout_fields = []

    for tool in snapshot:
        properties = tool["inputSchema"].get("properties", {})
        if "timeout" not in properties:
            continue
        timeout_fields.append(tool["name"])
        assert properties["timeout"].get("type") == "number", tool["name"]

    assert len(timeout_fields) >= 18


def test_pointer_drag_element_schema_prefers_symmetric_source_and_delta_names() -> None:
    tool = next(
        item
        for item in _build_tool_schema_snapshot()
        if item["name"] == "page_pointer_drag_element"
    )
    schema = tool["inputSchema"]
    source = schema["properties"]["source"]
    offset_properties = schema["$defs"]["OffsetDestinationInput"]["properties"]
    encoded = json.dumps(source)

    assert "ElementSourceInput" in encoded
    assert {"kind", "dx", "dy"} == set(offset_properties)
    assert "x" not in offset_properties
    assert "y" not in offset_properties


def test_schema_derived_tool_parameter_reference_is_current() -> None:
    snapshot = _build_tool_schema_snapshot()
    rendered = _render_tool_parameter_reference(snapshot)
    document = TOOL_CONTRACT_PATH.read_text(encoding="utf-8")

    if os.environ.get("UPDATE_TOOL_CONTRACT") == "1":
        document = _replace_generated_parameter_reference(document, rendered)
        TOOL_CONTRACT_PATH.write_text(document, encoding="utf-8")

    assert _generated_parameter_reference(document) == rendered
    assert sum(1 for line in rendered.splitlines() if line.startswith("| `")) == 69


def _build_tool_schema_snapshot() -> list[dict[str, Any]]:
    mcp_server = DrissionPageMCPServer()
    tools = []
    for tool in mcp_server.tools.values():
        tools.append(
            mcp_server._tool_to_mcp_tool(tool).model_dump(
                by_alias=True,
                exclude_none=True,
            )
        )

    names = [tool["name"] for tool in tools]
    assert len(tools) == 69
    assert {
        "form_inspect",
        "form_fill",
        "form_submit",
        "form_fill_preview",
        "page_detect_challenges",
        "page_click_xy_batch",
        "page_wait_challenge_result",
        "browser_open_and_snapshot",
        "browser_extract_links",
    }.isdisjoint(names)
    assert names.count("page_dialog_respond") == 1
    assert names.count("element_click_and_download") == 1
    assert names.count("browser_cookies_set") == 1
    assert names.count("browser_cookies_delete") == 1
    assert names.count("browser_cookies_clear") == 1
    assert names.count("browser_headers_set") == 1
    assert names.count("browser_user_agent_set") == 1
    assert names.count("browser_cache_clear") == 1
    assert names.count("network_blocked_urls_set") == 1
    assert names.count("page_accessibility_snapshot") == 1
    assert names.count("page_dialog_observe") == 1
    assert names.count("element_state_get") == 1
    assert names.count("browser_permission_get") == 1
    assert names.count("browser_permission_set") == 1
    assert names.count("browser_permissions_reset") == 1
    assert names.count("page_export_artifact") == 1
    assert names.count("element_click_and_upload") == 1
    assert names.count("page_navigate_with_http_auth") == 1
    assert "element_input_text" not in names
    assert "wait_sleep" not in names
    return tools


def _to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _render_tool_parameter_reference(tools: list[dict[str, Any]]) -> str:
    lines = [
        PARAMETER_TABLE_START,
        "## Schema-derived Tool Parameters",
        "",
        "This table is generated from the strict Pydantic input schemas exposed by `tools/list`. Do not edit rows manually; run `UPDATE_TOOL_CONTRACT=1 python -m pytest tests/test_tool_schema_snapshot.py -q` after an intentional schema change.",
        "",
        "| Tool | Required parameters | Optional parameters |",
        "| --- | --- | --- |",
    ]
    for tool in tools:
        schema = tool["inputSchema"]
        required_names = set(schema.get("required", []))
        properties = schema.get("properties", {})
        required = [
            _format_parameter(name, definition, required=True)
            for name, definition in properties.items()
            if name in required_names
        ]
        optional = [
            _format_parameter(name, definition, required=False)
            for name, definition in properties.items()
            if name not in required_names
        ]
        lines.append(
            f"| `{tool['name']}` | {'<br>'.join(required) or '—'} | "
            f"{'<br>'.join(optional) or '—'} |"
        )
    lines.extend((PARAMETER_TABLE_END, ""))
    return "\n".join(lines)


def _format_parameter(
    name: str, definition: dict[str, Any], *, required: bool
) -> str:
    value = f"{name}: {_schema_type(definition)}"
    if not required and "default" in definition:
        value += f" = {json.dumps(definition['default'], ensure_ascii=False)}"
    return f"`{value}`"


def _schema_type(definition: dict[str, Any]) -> str:
    if "$ref" in definition:
        return str(definition["$ref"]).rsplit("/", 1)[-1]
    if "type" in definition:
        return str(definition["type"])
    variants = definition.get("anyOf") or definition.get("oneOf") or []
    if variants:
        return " / ".join(_schema_type(item) for item in variants)
    return "value"


def _generated_parameter_reference(document: str) -> str:
    start = document.index(PARAMETER_TABLE_START)
    end = document.index(PARAMETER_TABLE_END, start) + len(PARAMETER_TABLE_END)
    return document[start:end] + "\n"


def _replace_generated_parameter_reference(document: str, rendered: str) -> str:
    if PARAMETER_TABLE_START not in document:
        marker = "\n## Tool Inventory\n"
        return document.replace(marker, f"\n{rendered}\n## Tool Inventory\n", 1)
    start = document.index(PARAMETER_TABLE_START)
    end = document.index(PARAMETER_TABLE_END, start) + len(PARAMETER_TABLE_END)
    return document[:start] + rendered.rstrip("\n") + document[end:]
