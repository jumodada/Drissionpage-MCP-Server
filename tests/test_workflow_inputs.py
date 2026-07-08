"""Workflow input validation guardrails."""

from __future__ import annotations

import pytest
from mcp.types import CallToolRequest, CallToolRequestParams
from pydantic import ValidationError

from drissionpage_mcp.server import DrissionPageMCPServer
from drissionpage_mcp.tools.workflow import FormFillPreviewInput


class GuardContext:
    def __init__(self) -> None:
        self.current_tab_calls = 0
        self.current_tab_or_die_calls = 0

    def current_tab(self):
        self.current_tab_calls += 1
        raise AssertionError("current_tab should not be called for invalid submit=True")

    def current_tab_or_die(self):
        self.current_tab_or_die_calls += 1
        raise AssertionError("current_tab_or_die should not be called for invalid submit=True")

    def is_active(self) -> bool:
        return False


@pytest.mark.parametrize("submit", [True])
def test_form_fill_preview_input_rejects_submit_true(submit: bool) -> None:
    with pytest.raises(ValidationError) as exc_info:
        FormFillPreviewInput(fields={"email": "ada@example.test"}, submit=submit)

    assert "form_fill_preview never submits" in str(exc_info.value)


@pytest.mark.asyncio
async def test_mcp_form_fill_preview_submit_true_rejects_before_tab_lookup() -> None:
    server = DrissionPageMCPServer()
    context = GuardContext()
    server.context = context  # type: ignore[assignment]
    handler = server.server.request_handlers[CallToolRequest]

    result = await handler(
        CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(
                name="form_fill_preview",
                arguments={"fields": {"email": "ada@example.test"}, "submit": True},
            ),
        )
    )

    assert result.root.isError is True
    assert result.root.structuredContent["error"]["code"] == "MCP_ARGUMENT_INVALID"
    assert "Input validation error" in result.root.structuredContent["message"]
    assert context.current_tab_calls == 0
    assert context.current_tab_or_die_calls == 0
