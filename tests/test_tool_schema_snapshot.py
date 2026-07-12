"""Snapshot coverage for the MCP tool schema exposed to clients."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

from drissionpage_mcp.server import DrissionPageMCPServer

SNAPSHOT_PATH = Path(__file__).parent / "snapshots" / "tools_schema.json"


def test_current_tool_schema_matches_snapshot() -> None:
    """exposes the public tools with stable schemas and annotations."""

    snapshot = _build_tool_schema_snapshot()

    if os.environ.get("UPDATE_SNAPSHOTS") == "1":
        SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT_PATH.write_text(_to_json(snapshot), encoding="utf-8")

    expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    assert snapshot == expected


def _build_tool_schema_snapshot() -> List[Dict[str, Any]]:
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
    assert len(tools) == 54
    assert "element_input_text" not in names
    assert "wait_sleep" not in names
    return tools


def _to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
