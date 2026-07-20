"""Workflow input validation guardrails."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from mcp.types import CallToolRequest, CallToolRequestParams
from pydantic import ValidationError

from drissionpage_mcp.browser.workflows import WorkflowOperations
from drissionpage_mcp.context import DrissionPageContext
from drissionpage_mcp.policy import ENV_DENY_EXTERNAL_SUBMISSION
from drissionpage_mcp.server import DrissionPageMCPServer
from drissionpage_mcp.tools.forms import (
    FormFillInput,
    FormSubmitInput,
    form_fill,
    form_submit,
)
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
        raise AssertionError(
            "current_tab_or_die should not be called for invalid submit=True"
        )

    def is_active(self) -> bool:
        return False


def test_form_fill_input_accepts_only_strict_supported_value_shapes() -> None:
    value = FormFillInput(
        fields={
            "Full name": "Ada",
            "Receive updates": True,
            "Skills": ["writing", "analysis"],
        }
    )

    assert value.form_selector == "form"
    assert value.timeout == 10
    assert value.redact_values is True
    assert value.verify is True


@pytest.mark.parametrize(
    "invalid_value",
    [1, 1.5, None, {"nested": "value"}, ["valid", 2], [True]],
)
def test_form_fill_input_rejects_coerced_or_nested_values(
    invalid_value: object,
) -> None:
    with pytest.raises(ValidationError):
        FormFillInput(fields={"Field": invalid_value})  # type: ignore[dict-item]


def test_form_fill_input_is_strict_bounded_and_forbids_unknown_arguments() -> None:
    with pytest.raises(ValidationError):
        FormFillInput(fields={})
    with pytest.raises(ValidationError):
        FormFillInput(fields={f"field-{index}": "value" for index in range(101)})
    with pytest.raises(ValidationError):
        FormFillInput(fields={"Field": "value"}, unknown=True)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        FormFillInput(fields={"Field": "value"}, timeout=0)


def test_plain_form_text_uses_one_native_input_payload() -> None:
    assert WorkflowOperations._native_input_value("Ada Controlled", "text") == (
        "Ada Controlled"
    )
    assert WorkflowOperations._native_input_value("2026-07-16", "date") == [
        "2",
        "0",
        "2",
        "6",
        "\ue014",
        "0",
        "7",
        "\ue014",
        "1",
        "6",
    ]


@pytest.mark.parametrize(
    ("reason", "matches", "verify", "expected"),
    [
        ("", True, True, (True, True, "")),
        ("", True, False, (True, True, "")),
        ("", False, True, (False, False, "VERIFICATION_FAILED")),
        ("", False, False, (True, False, "")),
        ("INTERACTION_FAILED", True, True, (False, False, "INTERACTION_FAILED")),
    ],
)
def test_form_field_outcome_distinguishes_success_from_verification(
    reason: str,
    matches: bool,
    verify: bool,
    expected: tuple[bool, bool, str],
) -> None:
    assert (
        WorkflowOperations._classify_form_value(
            reason=reason,
            matches=matches,
            verify=verify,
        )
        == expected
    )


def test_form_submit_input_is_strict_bounded_and_typed() -> None:
    value = FormSubmitInput(
        form_selector="#profile-form",
        operation_key="profile-submit-1",
        expect={
            "mode": "all",
            "conditions": (
                {"kind": "url_changed"},
                {"kind": "selector_visible", "selector": "#submission-status"},
            ),
            "timeout": 3,
        },
    )

    assert value.operation_key == "profile-submit-1"
    assert value.expect is not None
    assert value.expect.mode == "all"
    with pytest.raises(ValidationError):
        FormSubmitInput(operation_key=" ")
    with pytest.raises(ValidationError):
        FormSubmitInput(operation_key="x" * 129)
    with pytest.raises(ValidationError):
        FormSubmitInput(expect={"conditions": [], "timeout": 1})
    with pytest.raises(ValidationError):
        FormSubmitInput(expect={"conditions": [{"kind": "url_changed"}], "timeout": 0})
    with pytest.raises(ValidationError):
        FormSubmitInput(
            expect={"conditions": [{"kind": "url_changed"}], "timeout": 121}
        )
    with pytest.raises(ValidationError):
        FormSubmitInput(expect={"conditions": [{"kind": "unknown"}], "timeout": 1})
    with pytest.raises(ValidationError):
        FormSubmitInput(unknown=True)  # type: ignore[call-arg]


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


@pytest.mark.asyncio
async def test_mcp_form_fill_rejects_unknown_arguments_before_tab_lookup() -> None:
    server = DrissionPageMCPServer()
    context = GuardContext()
    server.context = context  # type: ignore[assignment]
    handler = server.server.request_handlers[CallToolRequest]

    result = await handler(
        CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(
                name="form_fill",
                arguments={"fields": {"Full name": "Ada"}, "submit": True},
            ),
        )
    )

    assert result.root.isError is True
    assert result.root.structuredContent["error"]["code"] == "MCP_ARGUMENT_INVALID"
    assert "submit" in result.root.structuredContent["message"]
    assert context.current_tab_calls == 0
    assert context.current_tab_or_die_calls == 0


@pytest.mark.asyncio
async def test_mcp_form_submit_rejects_invalid_input_before_tab_lookup() -> None:
    server = DrissionPageMCPServer()
    context = GuardContext()
    server.context = context  # type: ignore[assignment]
    handler = server.server.request_handlers[CallToolRequest]

    result = await handler(
        CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(
                name="form_submit",
                arguments={"operation_key": "", "unexpected": True},
            ),
        )
    )

    assert result.root.isError is True
    assert result.root.structuredContent["error"]["code"] == "MCP_ARGUMENT_INVALID"
    assert context.current_tab_calls == 0
    assert context.current_tab_or_die_calls == 0


@pytest.mark.asyncio
async def test_concurrent_form_submit_key_invokes_browser_workflow_once() -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    invocations = 0

    def resolve_form_submit(**_kwargs):
        return {
            "form_selector": {
                "selector": "#form",
                "locator": "css:#form",
                "selector_strategy": "css",
                "selector_normalized": True,
            },
            "form_locator": "css:#form",
            "form": {"selector": "#form"},
            "submitter": {
                "selector": "#submit",
                "id": "submit",
                "name": "",
                "tag": "button",
                "type": "submit",
                "text": "Submit",
                "disabled": False,
            },
        }

    async def invoke_form_submit(**_kwargs):
        nonlocal invocations
        invocations += 1
        started.set()
        await release.wait()
        return {
            "status": "submitted_pending",
            "triggered": True,
            "current_url": "https://example.test/current",
            "title": "Current",
            "validation_messages": [],
            "preconditions": [],
            "postconditions": [],
            "error_code": "",
        }

    context = DrissionPageContext()
    tab = SimpleNamespace(
        url="https://example.test/current",
        title="Current",
        mcp_tab_id="t0",
        workflows=SimpleNamespace(
            resolve_form_submit=resolve_form_submit,
            form_submit=invoke_form_submit,
        ),
    )
    context._current_tab = tab  # type: ignore[assignment]
    args = FormSubmitInput(form_selector="#form", operation_key="submit-once")

    first_task = asyncio.create_task(form_submit.execute(context, args))
    await started.wait()
    duplicate = await form_submit.execute(context, args)
    release.set()
    first = await first_task

    assert first.is_error is False
    assert duplicate.is_error is True
    assert duplicate.structured_content()["error"]["code"] == "OPERATION_IN_FLIGHT"
    assert invocations == 1
    assert context.task_summary().receipt_count == 1


@pytest.mark.asyncio
async def test_cancelled_form_fill_records_terminal_receipt() -> None:
    started = asyncio.Event()

    async def invoke_form_fill(**_kwargs):
        started.set()
        await asyncio.Event().wait()

    context = DrissionPageContext()
    context._current_tab = SimpleNamespace(  # type: ignore[assignment]
        mcp_tab_id="t0",
        workflows=SimpleNamespace(form_fill=invoke_form_fill),
    )
    task = asyncio.create_task(
        form_fill.execute(
            context,
            FormFillInput(form_selector="#form", fields={"Name": "Ada"}),
        )
    )
    await started.wait()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    receipt = context.receipt_inventory()[0]
    assert receipt.status == "indeterminate"
    assert receipt.error_code == "FORM_FILL_INDETERMINATE"
    replay = context.claim_operation(
        receipt.operation_key,
        receipt.request_fingerprint,
    )
    assert replay.should_invoke is False
    assert replay.cached_receipt == receipt


@pytest.mark.asyncio
async def test_cancelled_form_submit_freezes_indeterminate_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()

    def resolve_form_submit(**_kwargs):
        return {
            "form_selector": {
                "selector": "#form",
                "locator": "css:#form",
                "selector_strategy": "css",
                "selector_normalized": True,
            },
            "form_locator": "css:#form",
            "form": {"selector": "#form"},
            "submitter": {
                "selector": "#submit",
                "id": "submit",
                "name": "",
                "tag": "button",
                "type": "submit",
                "text": "Submit",
                "disabled": False,
            },
        }

    async def invoke_form_submit(**_kwargs):
        started.set()
        await asyncio.Event().wait()

    context = DrissionPageContext()
    context._current_tab = SimpleNamespace(  # type: ignore[assignment]
        url="https://example.test/current",
        title="Current",
        mcp_tab_id="t0",
        workflows=SimpleNamespace(
            resolve_form_submit=resolve_form_submit,
            form_submit=invoke_form_submit,
        ),
    )
    args = FormSubmitInput(form_selector="#form", operation_key="cancelled-submit")
    task = asyncio.create_task(form_submit.execute(context, args))
    await started.wait()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    receipt = context.operation_receipt("cancelled-submit")
    assert receipt is not None
    assert receipt.status == "indeterminate"
    assert receipt.error_code == "SUBMISSION_CANCELLED"
    frozen = context.operation_result("cancelled-submit")
    assert frozen is not None
    assert frozen["status"] == "indeterminate"

    monkeypatch.setenv(ENV_DENY_EXTERNAL_SUBMISSION, "1")
    context._current_tab = None
    replay = await form_submit.execute(context, args)
    assert replay.is_error is False
    assert replay.structured_content()["data"]["status"] == "indeterminate"
    assert replay.structured_content()["data"]["duplicate_prevention"] == {
        "scope": "live_server_task",
        "guarantee": "at_most_once_browser_invocation",
        "replayed": True,
        "browser_invoked": False,
    }


@pytest.mark.asyncio
async def test_form_submit_preclick_failure_freezes_nontriggered_receipt() -> None:
    def resolve_form_submit(**_kwargs):
        return {
            "form_selector": {
                "selector": "#form",
                "locator": "css:#form",
                "selector_strategy": "css",
                "selector_normalized": True,
            },
            "form_locator": "css:#form",
            "form": {"selector": "#form"},
            "submitter": {
                "selector": "#submit",
                "id": "submit",
                "name": "",
                "tag": "button",
                "type": "submit",
                "text": "Submit",
                "disabled": False,
            },
        }

    async def invoke_form_submit(**_kwargs):
        from drissionpage_mcp.browser.workflows import FormSubmitExecutionError

        raise FormSubmitExecutionError("precondition failed", triggered=False)

    context = DrissionPageContext()
    context._current_tab = SimpleNamespace(  # type: ignore[assignment]
        url="https://example.test/current",
        title="Current",
        mcp_tab_id="t0",
        workflows=SimpleNamespace(
            resolve_form_submit=resolve_form_submit,
            form_submit=invoke_form_submit,
        ),
    )
    args = FormSubmitInput(form_selector="#form", operation_key="submit-preclick")

    outcome = await form_submit.execute(context, args)

    assert outcome.is_error is False
    data = outcome.structured_content()["data"]
    assert data["status"] == "indeterminate"
    assert data["triggered"] is False
    assert data["duplicate_prevention"]["browser_invoked"] is False
    assert data["receipt"]["status"] == "indeterminate"
    assert context.task_summary().receipt_count == 1


@pytest.mark.asyncio
async def test_form_submit_cached_replay_precedes_policy_and_tab_access(
    monkeypatch,
) -> None:
    context = DrissionPageContext()
    tab = SimpleNamespace(
        url="https://example.test/done?secret=hidden",
        title="Done",
        mcp_tab_id="t0",
        workflows=SimpleNamespace(
            resolve_form_submit=lambda **_kwargs: {
                "form_selector": {
                    "selector": "#form",
                    "locator": "css:#form",
                    "selector_strategy": "css",
                    "selector_normalized": True,
                },
                "form_locator": "css:#form",
                "form": {"selector": "#form"},
                "submitter": {
                    "selector": "#submit",
                    "id": "submit",
                    "name": "",
                    "tag": "button",
                    "type": "submit",
                    "text": "Submit",
                    "disabled": False,
                },
            },
            form_submit=lambda **_kwargs: None,
        ),
    )

    async def invoke_form_submit(**_kwargs):
        return {
            "status": "submitted_pending",
            "triggered": True,
            "current_url": tab.url,
            "title": tab.title,
            "validation_messages": [],
            "preconditions": [],
            "postconditions": [],
            "error_code": "",
        }

    tab.workflows.form_submit = invoke_form_submit
    context._current_tab = tab  # type: ignore[assignment]
    args = FormSubmitInput(form_selector="#form", operation_key="cached-submit")
    first = await form_submit.execute(context, args)
    assert first.is_error is False

    context._current_tab = None
    monkeypatch.setenv(ENV_DENY_EXTERNAL_SUBMISSION, "1")
    replay = await form_submit.execute(context, args)

    assert replay.is_error is False
    data = replay.structured_content()["data"]
    assert data["duplicate_prevention"]["replayed"] is True
    assert data["duplicate_prevention"]["browser_invoked"] is False
    assert data["current_url"] == "https://example.test/done"
