"""Form inspection and non-submitting fill tools for DrissionPage MCP."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Annotated, Literal, cast
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, StrictBool, StrictStr, StringConstraints

from ..limits import MAX_WAIT_SECONDS
from ..metadata import with_response_meta
from ..policy import PolicyDeniedError, validate_external_submission
from ..response_errors import ErrorCode
from ..tool_outputs import (
    ActionReceipt,
    Expectation,
    FormFillData,
    FormInspectData,
    FormSubmitData,
)
from .base import ToolInput, ToolOutcome, ToolType, define_tool

if TYPE_CHECKING:
    from ..context import DrissionPageContext


class FormInspectInput(ToolInput):
    """Input schema for inspecting forms and their controls."""

    selector: str = Field(
        default="",
        description="Optional CSS selector or XPath for a form or container. Empty means all forms on the current page.",
    )
    include_values: bool = Field(
        default=False,
        description="Include current non-password field values. Password values are never returned.",
    )
    max_forms: int = Field(
        default=10, ge=1, le=50, description="Maximum number of forms to return"
    )
    max_fields_per_form: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Maximum number of controls to return per form",
    )


FormFieldKey = Annotated[str, StringConstraints(min_length=1, max_length=500)]
FormFieldValue = StrictStr | StrictBool | Annotated[list[StrictStr], Field(strict=True)]


class FormFillInput(ToolInput):
    """Strict input for filling a form without submitting it."""

    form_selector: str = Field(
        default="form",
        min_length=1,
        description="CSS/XPath/DrissionPage locator for one form or form container.",
    )
    fields: dict[FormFieldKey, FormFieldValue] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Field selectors, ids, names, labels, or placeholders mapped to string, boolean, or string-list values.",
    )
    timeout: float = Field(
        default=10.0,
        gt=0,
        le=MAX_WAIT_SECONDS,
        description="Maximum seconds for resolving and stabilizing the local form mutation.",
    )
    redact_values: bool = Field(
        default=True,
        description="Redact requested and observed values; password values are always redacted.",
    )
    verify: bool = Field(
        default=True,
        description="Read each live control representation after interaction and require it to match.",
    )


OperationKey = Annotated[
    StrictStr,
    StringConstraints(min_length=1, max_length=128, strip_whitespace=True),
]


class FormSubmitInput(ToolInput):
    """Strict input for one live-task external form submission."""

    form_selector: StrictStr = Field(
        default="form",
        min_length=1,
        max_length=500,
        description="CSS/XPath/DrissionPage locator resolving exactly one form.",
    )
    submit_selector: StrictStr = Field(
        default="",
        max_length=500,
        description="Optional locator resolving exactly one enabled submitter inside the form.",
    )
    operation_key: OperationKey | None = Field(
        default=None,
        description="Live-task idempotency key. Reusing it with the same request replays the frozen result without clicking again.",
    )
    expect: Expectation | None = Field(
        default=None,
        description="Bounded success postconditions. Omit only when a submitted_pending result is acceptable.",
    )


@define_tool(
    name="form_inspect",
    title="Inspect Forms",
    description="Inspect forms and controls with labels, selectors, methods, actions, requirements, options, and safe optional values.",
    input_schema=FormInspectInput,
    tool_type=ToolType.READ_ONLY,
    idempotent=True,
    output_model=FormInspectData,
    failure_message=lambda args, exc: (
        lambda e: f"Failed to inspect forms for selector {args.selector!r}: {e}"
    )(exc),
)
async def form_inspect(
    context: "DrissionPageContext", args: FormInspectInput
) -> "ToolOutcome":
    """Inspect forms on the current page."""
    outcome = ToolOutcome()
    tab = context.current_tab_or_die()
    result = await tab.workflows.inspect_forms(
        selector=args.selector,
        include_values=args.include_values,
        max_forms=args.max_forms,
        max_fields_per_form=args.max_fields_per_form,
    )
    outcome.add_code("page.run_js(<bounded form inspection script>)")
    outcome.add_result(
        f"Inspected {result['returned']} of {result['count']} forms",
        **with_response_meta(result),
    )
    return outcome


@define_tool(
    name="form_fill",
    title="Fill Form",
    description="Fill supported native, controlled, contenteditable, multi-select, and ARIA form controls without submitting, then verify live values.",
    input_schema=FormFillInput,
    tool_type=ToolType.DESTRUCTIVE,
    output_model=FormFillData,
    failure_message=lambda args, exc: "Failed to fill form: " + str(exc),
)
async def form_fill(
    context: "DrissionPageContext", args: FormFillInput
) -> "ToolOutcome":
    """Fill supported fields and return a local UI mutation receipt."""

    outcome = ToolOutcome()
    tab = context.current_tab_or_die()
    started_at = datetime.now(timezone.utc)
    action_id = context.new_action_id()
    fingerprint = context.request_fingerprint(
        {
            "tool": "form_fill",
            "form_selector": args.form_selector,
            "fields": args.fields,
            "redact_values": args.redact_values,
            "verify": args.verify,
            "timeout": args.timeout,
        }
    )
    operation_key = f"form-fill-{action_id}"
    claim = context.claim_operation(operation_key, fingerprint)
    try:
        result = await tab.workflows.form_fill(
            form_selector=args.form_selector,
            fields=args.fields,
            redact_values=args.redact_values,
            verify=args.verify,
            timeout=args.timeout,
        )
    except Exception:
        failed_receipt = ActionReceipt(
            action_id=action_id,
            task_id=context.task_id,
            operation_key=operation_key,
            request_fingerprint=fingerprint,
            kind="form_fill",
            side_effect="local_ui_mutation",
            status="failed",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            tab_id=tab.mcp_tab_id or "untracked-tab",
            error_code="INTERACTION_FAILED",
            redacted=True,
        )
        context.complete_operation(claim, failed_receipt)
        raise
    status: Literal["success", "failed"] = (
        "success" if result["failed_count"] == 0 else "failed"
    )
    receipt = ActionReceipt(
        action_id=action_id,
        task_id=context.task_id,
        operation_key=operation_key,
        request_fingerprint=fingerprint,
        kind="form_fill",
        side_effect="local_ui_mutation",
        status=status,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        tab_id=tab.mcp_tab_id or "untracked-tab",
        redacted=True,
    )
    context.complete_operation(claim, receipt)
    result["receipt"] = receipt.model_dump(mode="json")
    outcome.add_code(
        "DrissionPage native form interactions with bounded framework-control JS fallback"
    )
    outcome.add_result(
        f"Filled {result['filled_count']} of {result['requested_count']} requested form fields",
        **result,
    )
    outcome.set_include_snapshot(True)
    return outcome


@define_tool(
    name="form_submit",
    title="Submit Form Once",
    description="Submit one form at most once for an operation key, classify validation or postconditions, and return a typed external-side-effect receipt.",
    input_schema=FormSubmitInput,
    tool_type=ToolType.DESTRUCTIVE,
    idempotent=False,
    output_model=FormSubmitData,
    failure_message=lambda args, exc: "Failed to submit form: " + str(exc),
)
async def form_submit(
    context: "DrissionPageContext", args: FormSubmitInput
) -> "ToolOutcome":
    """Submit once after policy, capability, and target preflight."""

    outcome = ToolOutcome()
    request = {
        "tool": "form_submit",
        "form_selector": args.form_selector,
        "submit_selector": args.submit_selector,
        "expect": args.expect.model_dump(mode="json") if args.expect else None,
    }
    fingerprint = context.request_fingerprint(request)
    operation_key = args.operation_key
    action_id: str | None = None
    if operation_key is None:
        action_id = context.new_action_id()
        operation_key = f"form-submit-{action_id}"

    replay = context.preview_operation(operation_key, fingerprint)
    if replay is not None:
        cached = dict(replay.cached_result or {})
        if not cached or replay.cached_receipt is None:
            raise RuntimeError(
                "completed operation has no replayable form_submit result"
            )
        duplicate = dict(cached["duplicate_prevention"])
        duplicate.update(replayed=True, browser_invoked=False)
        cached["duplicate_prevention"] = duplicate
        cached["receipt"] = replay.cached_receipt.model_dump(mode="json")
        outcome.add_result(
            f"Replayed frozen form submission result for operation key {operation_key}",
            **cached,
        )
        return outcome

    try:
        validate_external_submission()
    except PolicyDeniedError as exc:
        outcome.add_error(
            str(exc), ErrorCode.POLICY_DENIED, rule=exc.rule, value=exc.value
        )
        return outcome

    _validate_submit_capability(context)
    tab = context.current_tab_or_die()
    resolved = tab.workflows.resolve_form_submit(
        form_selector=args.form_selector,
        submit_selector=args.submit_selector,
    )
    claim = context.claim_operation(operation_key, fingerprint)
    if action_id is None:
        action_id = context.new_action_id()
    started_at = datetime.now(timezone.utc)
    target_fingerprint = context.request_fingerprint(
        {
            "form": resolved.get("form"),
            "submitter": resolved.get("submitter"),
            "tab_id": tab.mcp_tab_id or "untracked-tab",
        }
    )
    try:
        result = await tab.workflows.form_submit(
            resolved=resolved,
            expect=args.expect,
        )
    except Exception as exc:
        triggered = bool(getattr(exc, "triggered", True))
        result = {
            "status": "indeterminate",
            "triggered": triggered,
            "current_url": tab.url,
            "title": "",
            "validation_messages": [],
            "preconditions": [],
            "postconditions": [],
            "error_code": "SUBMISSION_WORKFLOW_FAILED",
        }
        failed_receipt = ActionReceipt(
            action_id=action_id,
            task_id=context.task_id,
            operation_key=operation_key,
            request_fingerprint=fingerprint,
            kind="form_submit",
            side_effect="external_submission",
            status="indeterminate",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            tab_id=tab.mcp_tab_id or "untracked-tab",
            target_fingerprint=target_fingerprint,
            error_code="SUBMISSION_WORKFLOW_FAILED",
            redacted=True,
        )
        data = _form_submit_data(
            result=result,
            operation_key=operation_key,
            resolved=resolved,
            receipt=failed_receipt,
            tab=tab,
        )
        context.complete_operation(claim, failed_receipt, result=data)
        outcome.add_result(
            (
                "Form submission outcome is indeterminate; no automatic resubmission was attempted"
                if triggered
                else "Form submission failed before submitter invocation; the reserved operation key remains frozen"
            ),
            **data,
        )
        return outcome

    public_status = str(result["status"])
    receipt_status: Literal[
        "success", "validation_failed", "pending", "indeterminate", "failed"
    ]
    receipt_status = cast(
        Literal["success", "validation_failed", "pending", "indeterminate", "failed"],
        "pending" if public_status == "submitted_pending" else public_status,
    )
    receipt = ActionReceipt(
        action_id=action_id,
        task_id=context.task_id,
        operation_key=operation_key,
        request_fingerprint=fingerprint,
        kind="form_submit",
        side_effect="external_submission",
        status=receipt_status,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        tab_id=tab.mcp_tab_id or "untracked-tab",
        target_fingerprint=target_fingerprint,
        preconditions=tuple(result.get("preconditions") or []),
        postconditions=tuple(result.get("postconditions") or []),
        error_code=str(result.get("error_code") or "") or None,
        redacted=True,
    )
    data = _form_submit_data(
        result=result,
        operation_key=operation_key,
        resolved=resolved,
        receipt=receipt,
        tab=tab,
    )
    context.complete_operation(claim, receipt, result=data)
    outcome.add_code(
        "resolved_submitter.click() once; then bounded read-only postcondition checks"
    )
    outcome.add_result(
        f"Form submission classified as {public_status}",
        **data,
    )
    outcome.set_include_snapshot(True)
    return outcome


def _validate_submit_capability(context: "DrissionPageContext") -> None:
    """Honor explicit negative capability evidence without blocking unprobed use."""

    capability_set = context.capability_set()
    for capability in capability_set.capabilities:
        if capability.name in {"form.submit", "form_submit"} and capability.status in {
            "unsupported",
            "degraded",
        }:
            exc = RuntimeError(
                capability.reason_code
                or "Form submission is unsupported by this runtime"
            )
            exc.code = ErrorCode.UNSUPPORTED_OPERATION  # type: ignore[attr-defined]
            raise exc


def _submission_recovery(status: str) -> str:
    if status == "success":
        return "Use the returned postcondition evidence as the completion receipt."
    if status == "validation_failed":
        return "Correct the reported fields with form_fill, inspect fresh state, then submit with a new operation key."
    if status == "submitted_pending":
        return "Inspect fresh URL, visible state, network, or task evidence before deciding whether a new submission is needed."
    return "Do not resubmit automatically. Inspect fresh URL, visible state, network, and the frozen receipt before using a new operation key."


def _form_submit_data(
    *,
    result: dict[str, object],
    operation_key: str,
    resolved: dict[str, object],
    receipt: ActionReceipt,
    tab: object,
) -> dict[str, object]:
    status = str(result["status"])
    triggered = bool(result.get("triggered"))
    sensitive_values = [
        str(value)
        for value in cast(list[object], result.get("_sensitive_values") or [])
        if str(value)
    ]
    submitter = dict(cast(dict[str, object], resolved["submitter"]))
    submitter["text"] = _redact_sensitive_text(
        str(submitter.get("text") or ""), sensitive_values
    )
    return {
        "status": status,
        "operation_key": operation_key,
        "form_selector": resolved["form_selector"],
        "submitter": submitter,
        "triggered": triggered,
        "current_url": _public_url(
            str(result.get("current_url") or getattr(tab, "url", ""))
        ),
        "title": _redact_sensitive_text(
            str(result.get("title") or ""), sensitive_values
        ),
        "validation_messages": list(
            cast(list[object], result.get("validation_messages") or [])
        ),
        "postconditions": list(cast(list[object], result.get("postconditions") or [])),
        "duplicate_prevention": {
            "scope": "live_server_task",
            "guarantee": "at_most_once_browser_invocation",
            "replayed": False,
            "browser_invoked": triggered,
        },
        "recovery": _submission_recovery(status),
        "receipt": receipt.model_dump(mode="json"),
    }


def _public_url(value: str) -> str:
    """Remove credentials, query, and fragment from a public submission URL."""

    if not value:
        return ""
    try:
        parts = urlsplit(value)
    except ValueError:
        return "<redacted-url>"
    netloc = parts.netloc.rsplit("@", 1)[-1]
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def _redact_sensitive_text(value: str, sensitive_values: list[str]) -> str:
    redacted = value
    for secret in sorted(set(sensitive_values), key=len, reverse=True):
        if secret:
            redacted = redacted.replace(secret, "<redacted>")
    return redacted
