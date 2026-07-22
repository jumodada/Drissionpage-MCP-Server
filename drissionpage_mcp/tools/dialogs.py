"""Capability-probed JavaScript dialog response tool."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from time import monotonic
from typing import TYPE_CHECKING, Annotated, Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, StrictStr, model_validator

from ..browser.dialogs import (
    DialogPreconditionError,
    DialogResponseIndeterminateError,
    DialogUnsupportedError,
)
from ..limits import MAX_WAIT_SECONDS
from ..tool_outputs import ActionReceipt, CapabilityProbe, PageDialogRespondData
from .base import ToolInput, ToolOutcome, ToolType, define_tool

if TYPE_CHECKING:
    from ..context import DrissionPageContext


PromptText = Annotated[StrictStr, Field(max_length=4000)]


class PageDialogRespondInput(ToolInput):
    """Strict response for one currently pending JavaScript dialog."""

    action: Literal["accept", "dismiss"]
    prompt_text: PromptText | None = Field(
        default=None,
        description="Text for an accepted prompt. The value is never returned.",
    )
    timeout: float = Field(
        default=5.0,
        gt=0,
        le=MAX_WAIT_SECONDS,
        description="Maximum seconds to wait for a pending dialog.",
    )

    @model_validator(mode="after")
    def validate_prompt_action(self) -> "PageDialogRespondInput":
        if self.action == "dismiss" and self.prompt_text is not None:
            raise ValueError("prompt_text cannot be used when dismissing a dialog")
        return self


@define_tool(
    name="page_dialog_respond",
    title="Respond To Dialog",
    description="Accept or dismiss one pending alert, confirm, or prompt through a capability-probed native DrissionPage dialog path.",
    input_schema=PageDialogRespondInput,
    tool_type=ToolType.DESTRUCTIVE,
    output_model=PageDialogRespondData,
    failure_message=lambda args, exc: _dialog_failure_message(exc),
)
async def page_dialog_respond(
    context: "DrissionPageContext", args: PageDialogRespondInput
) -> "ToolOutcome":
    """Respond once after capability and pending-dialog preflight."""

    outcome = ToolOutcome()
    deadline = monotonic() + args.timeout
    _validate_dialog_capability(context)
    tab = context.current_tab_or_die()
    try:
        tab.dialogs.probe()
        pending = await tab.dialogs.wait_for_pending(timeout=args.timeout)
    except DialogUnsupportedError as exc:
        if exc.reason_code in _STRUCTURAL_DIALOG_FAILURES:
            context.record_capability_probe(
                _dialog_probe(
                    status="unsupported",
                    evidence_source="runtime_probe",
                    reason_code=exc.reason_code,
                )
            )
        raise

    if args.prompt_text is not None and pending["dialog_type"] != "prompt":
        raise DialogPreconditionError(
            "prompt_text is valid only for a pending prompt dialog"
        )
    response_timeout = deadline - monotonic()
    if response_timeout <= 0:
        raise TimeoutError("Dialog response deadline expired before invocation.")

    action_id = context.new_action_id()
    operation_key = f"dialog-response-{action_id}"
    fingerprint = context.request_fingerprint(
        {
            "tool": "page_dialog_respond",
            "action": args.action,
            "prompt_text": args.prompt_text,
            "timeout": args.timeout,
            "dialog_type": pending["dialog_type"],
            "message": pending["message"],
        }
    )
    claim = context.claim_operation(operation_key, fingerprint)
    started_at = datetime.now(timezone.utc)
    target_fingerprint = context.request_fingerprint(
        {
            "tab_id": tab.mcp_tab_id or "untracked-tab",
            "dialog_type": pending["dialog_type"],
            "message": pending["message"],
        }
    )
    try:
        await asyncio.wait_for(
            tab.dialogs.respond(
                pending=pending,
                action=args.action,
                prompt_text=args.prompt_text,
                timeout=response_timeout,
            ),
            timeout=response_timeout,
        )
    except Exception as exc:
        if (
            isinstance(exc, DialogUnsupportedError)
            and exc.reason_code in _STRUCTURAL_DIALOG_FAILURES
        ):
            context.record_capability_probe(
                _dialog_probe(
                    status="unsupported",
                    evidence_source="runtime_probe",
                    reason_code=exc.reason_code,
                )
            )
        status: Literal["failed", "indeterminate"] = (
            "failed"
            if isinstance(exc, (DialogPreconditionError, DialogUnsupportedError))
            else "indeterminate"
        )
        receipt = _receipt(
            context=context,
            action_id=action_id,
            operation_key=operation_key,
            fingerprint=fingerprint,
            tab_id=tab.mcp_tab_id or "untracked-tab",
            target_fingerprint=target_fingerprint,
            started_at=started_at,
            status=status,
            error_code=(
                "DIALOG_RESPONSE_INDETERMINATE"
                if status == "indeterminate"
                else "DIALOG_RESPONSE_FAILED"
            ),
        )
        context.complete_operation(claim, receipt)
        raise

    context.record_capability_probe(
        _dialog_probe(status="supported", evidence_source="browser_event")
    )
    receipt = _receipt(
        context=context,
        action_id=action_id,
        operation_key=operation_key,
        fingerprint=fingerprint,
        tab_id=tab.mcp_tab_id or "untracked-tab",
        target_fingerprint=target_fingerprint,
        started_at=started_at,
        status="success",
    )
    data = {
        "dialog_type": pending["dialog_type"],
        "action": args.action,
        "handled": True,
        "dialog_message": {
            "present": bool(pending["message"]),
            "length": len(pending["message"]),
            "redacted": True,
        },
        "prompt": {
            "provided": args.prompt_text is not None,
            "length": len(args.prompt_text or ""),
            "redacted": True,
        },
        "final_url": _public_url(tab.url),
        "receipt": receipt.model_dump(mode="json"),
    }
    context.complete_operation(claim, receipt, result=data)
    outcome.set_result(
        f"Handled pending {pending['dialog_type']} dialog with action {args.action}",
        data,
    )
    return outcome


def _receipt(
    *,
    context: "DrissionPageContext",
    action_id: str,
    operation_key: str,
    fingerprint: str,
    tab_id: str,
    target_fingerprint: str,
    started_at: datetime,
    status: Literal["success", "failed", "indeterminate"],
    error_code: str | None = None,
) -> ActionReceipt:
    return ActionReceipt(
        action_id=action_id,
        task_id=context.task_id,
        operation_key=operation_key,
        request_fingerprint=fingerprint,
        kind="page_dialog_respond",
        side_effect="dialog_response",
        status=status,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        tab_id=tab_id,
        target_fingerprint=target_fingerprint,
        error_code=error_code,
        redacted=True,
    )


def _dialog_probe(
    *,
    status: Literal["supported", "unsupported"],
    evidence_source: Literal["runtime_probe", "browser_event"],
    reason_code: str | None = None,
) -> CapabilityProbe:
    return CapabilityProbe(
        name="dialog.respond",
        status=status,
        evidence_source=evidence_source,
        reason_code=reason_code,
        checked_at=datetime.now(timezone.utc),
    )


def _validate_dialog_capability(context: "DrissionPageContext") -> None:
    """Honor recorded negative evidence before touching a tab or dialog."""

    for capability in context.capability_set().capabilities:
        if capability.name == "dialog.respond" and capability.status in {
            "unsupported",
            "degraded",
        }:
            raise DialogUnsupportedError(
                capability.reason_code or "RECORDED_CAPABILITY_UNAVAILABLE"
            )


def _public_url(value: str) -> str:
    parts = urlsplit(value)
    return urlunsplit(
        (parts.scheme, parts.netloc.rsplit("@", 1)[-1], parts.path, "", "")
    )[:500]


_STRUCTURAL_DIALOG_FAILURES = frozenset(
    {
        "HANDLE_ALERT_API_UNAVAILABLE",
        "BOUNDED_HANDLE_ALERT_API_UNAVAILABLE",
        "ALERT_STATE_UNAVAILABLE",
        "ALERT_METADATA_UNAVAILABLE",
    }
)


def _dialog_failure_message(exc: Exception) -> str:
    """Return stable public text without reflecting browser or prompt values."""

    if isinstance(exc, DialogResponseIndeterminateError):
        return "Dialog response outcome is indeterminate after native invocation."
    if isinstance(exc, TimeoutError):
        return "Dialog response deadline expired before a terminal state was confirmed."
    if isinstance(
        exc,
        (
            DialogPreconditionError,
            DialogUnsupportedError,
        ),
    ):
        return str(exc)
    return "Failed to respond to the pending page dialog."
