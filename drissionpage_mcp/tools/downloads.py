"""Atomic browser click/download workflow with typed artifact receipts."""

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING, Annotated, Any, Literal

from pydantic import Field, StrictStr, StringConstraints, model_validator

from ..browser.downloads import (
    DownloadFailedError,
    DownloadIndeterminateError,
    DownloadUnsupportedError,
    DownloadValidationError,
)
from ..limits import MAX_WAIT_SECONDS
from ..policy import PolicyDeniedError, SafetyPolicy
from ..response_errors import ErrorCode
from ..selector import normalize_selector
from ..tool_outputs import (
    ActionReceipt,
    ArtifactRef,
    CapabilityProbe,
    ElementClickAndDownloadData,
)
from .base import ToolInput, ToolOutcome, ToolType, define_tool

if TYPE_CHECKING:
    from ..context import DrissionPageContext


OperationKey = Annotated[
    StrictStr,
    StringConstraints(min_length=1, max_length=128, strip_whitespace=True),
]
Filename = Annotated[
    StrictStr,
    StringConstraints(min_length=1, max_length=255, strip_whitespace=True),
]
MimeType = Annotated[
    StrictStr,
    StringConstraints(min_length=1, max_length=200, strip_whitespace=True),
]


class ElementClickAndDownloadInput(ToolInput):
    """Strict request for one native click and one correlated download."""

    selector: StrictStr = Field(
        ...,
        min_length=1,
        max_length=500,
        description="CSS/XPath/DrissionPage selector for the download control.",
    )
    operation_key: OperationKey | None = Field(
        default=None,
        description="Optional live-task key. Reusing the same key replays the frozen artifact result without clicking again.",
    )
    timeout: float = Field(
        default=30.0,
        gt=0,
        le=MAX_WAIT_SECONDS,
        description="Shared maximum seconds for target resolution, click, and download completion.",
    )
    expected_filename: Filename | None = Field(
        default=None,
        description="Optional exact basename constraint for the downloaded artifact.",
    )
    expected_mime_type: MimeType | None = Field(
        default=None,
        description="Optional MIME constraint inferred from the completed filename.",
    )

    @model_validator(mode="after")
    def validate_filename(self) -> "ElementClickAndDownloadInput":
        if self.expected_filename is not None and (
            self.expected_filename in {".", ".."}
            or "/" in self.expected_filename
            or "\\" in self.expected_filename
        ):
            raise ValueError("expected_filename must be a basename")
        return self


@define_tool(
    name="element_click_and_download",
    title="Click And Download",
    description="Perform one native element click, await one completed download, and return an integrity-checked safe artifact receipt.",
    input_schema=ElementClickAndDownloadInput,
    tool_type=ToolType.DESTRUCTIVE,
    output_model=ElementClickAndDownloadData,
    failure_message=lambda args, exc: _download_failure_message(exc),
)
async def element_click_and_download(
    context: "DrissionPageContext", args: ElementClickAndDownloadInput
) -> "ToolOutcome":
    """Execute one download boundary after all non-side-effect preconditions."""

    outcome = ToolOutcome()
    action_id: str | None = None
    operation_key = args.operation_key
    if operation_key is None:
        action_id = context.new_action_id()
        operation_key = f"download-{action_id}"
    fingerprint = context.request_fingerprint(
        {
            "tool": "element_click_and_download",
            "selector": args.selector,
            "operation_key": operation_key,
            "timeout": args.timeout,
            "expected_filename": args.expected_filename,
            "expected_mime_type": args.expected_mime_type,
        }
    )
    replay = context.preview_operation(operation_key, fingerprint)
    if replay is not None:
        if replay.cached_result is None:
            raise RuntimeError("Cached download operation has no frozen result.")
        if replay.cached_result.get("status") == "success":
            outcome.add_code("# replay cached element_click_and_download result")
            outcome.set_result(
                f"Replayed completed download for operation key {operation_key}",
                replay.cached_result,
            )
            return outcome
        return _failure_outcome(
            replay.cached_result,
            _download_error_from_status(str(replay.cached_result.get("status"))),
        )

    policy = SafetyPolicy.from_env()
    try:
        policy.validate_external_download()
        root = policy.validate_download_root()
    except PolicyDeniedError as exc:
        outcome.add_error(
            str(exc), ErrorCode.POLICY_DENIED, rule=exc.rule, value=exc.value
        )
        return outcome

    _validate_download_capability(context)
    tab = context.current_tab_or_die()
    deadline = monotonic() + args.timeout
    plan = normalize_selector(args.selector)
    target_timeout = max(0, math.ceil(deadline - monotonic()))
    element = await tab._element_by_plan(plan, timeout=target_timeout)
    try:
        tab.downloads.probe(element)
    except DownloadUnsupportedError as exc:
        context.record_capability_probe(_download_probe("unsupported", exc.reason_code))
        raise
    _validate_task_download_directory(root, context.task_id)

    if action_id is None:
        action_id = context.new_action_id()
    artifact_id = context.new_artifact_id()
    reserved = False
    download_dir: Path | None = None
    try:
        context.reserve_artifact_slot(artifact_id)
        reserved = True
        download_dir = _allocate_download_dir(root, context.task_id, action_id)
        claim = context.claim_operation(operation_key, fingerprint)
    except Exception:
        if reserved:
            context.release_artifact_slot(artifact_id)
            reserved = False
        rollback_cancellation: asyncio.CancelledError | None = None
        if download_dir is not None:
            cleanup = asyncio.create_task(tab.downloads.cleanup(download_dir))
            rollback_cancellation = await _drain_cleanup(cleanup)
        if rollback_cancellation is not None:
            raise rollback_cancellation
        raise
    started_at = datetime.now(timezone.utc)
    target_fingerprint = context.request_fingerprint(
        {
            "tab_id": tab.mcp_tab_id or "untracked-tab",
            "selector": plan.locator,
            "url": tab.url,
        }
    )
    committed = False
    try:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError("Download deadline expired before native invocation.")
        result = await tab.downloads.click_and_wait(
            element,
            download_dir=download_dir,
            timeout=remaining,
        )
        if (
            args.expected_filename is not None
            and result["filename"] != args.expected_filename
        ):
            raise DownloadValidationError(
                "Downloaded filename did not match the requested constraint."
            )
        if (
            args.expected_mime_type is not None
            and result["mime_type"] != args.expected_mime_type
        ):
            raise DownloadValidationError(
                "Downloaded MIME type did not match the requested constraint."
            )

        safe_relative_path = result["path"].relative_to(root.resolve()).as_posix()
        artifact = ArtifactRef(
            artifact_id=artifact_id,
            task_id=context.task_id,
            producing_action_id=action_id,
            kind="download",
            filename=result["filename"],
            mime_type=result["mime_type"],
            size_bytes=result["size_bytes"],
            sha256=result["sha256"],
            safe_relative_path=safe_relative_path,
            source_url=result["source_url"],
            created_at=datetime.now(timezone.utc),
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
            artifact_ids=(artifact_id,),
        )
        data = {
            "status": "success",
            "operation_key": operation_key,
            **plan.metadata(),
            "artifact": artifact.model_dump(mode="json"),
            "receipt": receipt.model_dump(mode="json"),
        }
        data = ElementClickAndDownloadData.model_validate(data).model_dump(mode="json")
        context.complete_artifact_operation(
            claim,
            receipt,
            artifact,
            result=data,
        )
        reserved = False
        committed = True
        try:
            context.record_capability_probe(_download_probe("supported"))
        except Exception:
            pass
        outcome.add_code(
            f"page.ele({plan.locator!r}).click.to_download(save_path='<approved-root>')"
        )
        outcome.set_result("Downloaded one integrity-checked artifact", data)
        outcome.set_include_snapshot(True)
        return outcome
    except asyncio.CancelledError:
        if reserved:
            context.release_artifact_slot(artifact_id)
            reserved = False
        if download_dir is not None:
            cleanup = asyncio.create_task(tab.downloads.cleanup(download_dir))
            await _drain_cleanup(cleanup)
        receipt = _receipt(
            context=context,
            action_id=action_id,
            operation_key=operation_key,
            fingerprint=fingerprint,
            tab_id=tab.mcp_tab_id or "untracked-tab",
            target_fingerprint=target_fingerprint,
            started_at=started_at,
            status="indeterminate",
            error_code="DOWNLOAD_INDETERMINATE",
        )
        failure_data = {
            "status": "indeterminate",
            "operation_key": operation_key,
            **plan.metadata(),
            "artifact": None,
            "receipt": receipt.model_dump(mode="json"),
        }
        failure_data = ElementClickAndDownloadData.model_validate(
            failure_data
        ).model_dump(mode="json")
        context.complete_operation(claim, receipt, result=failure_data)
        raise
    except Exception as exc:
        if committed:
            raise
        if reserved:
            context.release_artifact_slot(artifact_id)
            reserved = False
        failure_cancellation: asyncio.CancelledError | None = None
        if download_dir is not None:
            cleanup = asyncio.create_task(tab.downloads.cleanup(download_dir))
            failure_cancellation = await _drain_cleanup(cleanup)
        status: Literal["failed", "validation_failed", "indeterminate"]
        if failure_cancellation is not None:
            status = "indeterminate"
        elif isinstance(exc, DownloadValidationError):
            status = "validation_failed"
        elif isinstance(exc, (DownloadIndeterminateError, TimeoutError)):
            status = "indeterminate"
        elif isinstance(exc, (DownloadFailedError, DownloadUnsupportedError)):
            status = "failed"
        else:
            status = "indeterminate"
        receipt = _receipt(
            context=context,
            action_id=action_id,
            operation_key=operation_key,
            fingerprint=fingerprint,
            tab_id=tab.mcp_tab_id or "untracked-tab",
            target_fingerprint=target_fingerprint,
            started_at=started_at,
            status=status,
            error_code=f"DOWNLOAD_{status.upper()}",
        )
        failure_data = {
            "status": status,
            "operation_key": operation_key,
            **plan.metadata(),
            "artifact": None,
            "receipt": receipt.model_dump(mode="json"),
        }
        failure_data = ElementClickAndDownloadData.model_validate(
            failure_data
        ).model_dump(mode="json")
        context.complete_operation(claim, receipt, result=failure_data)
        if failure_cancellation is not None:
            raise failure_cancellation
        return _failure_outcome(failure_data, exc)


async def _drain_cleanup(
    task: "asyncio.Task[Any]",
) -> asyncio.CancelledError | None:
    cancellation: asyncio.CancelledError | None = None
    while True:
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError as exc:
            cancellation = exc
            if task.done():
                break
            continue
        break
    try:
        task.result()
    except asyncio.CancelledError as exc:
        cancellation = exc
    except Exception:
        pass
    return cancellation


def _allocate_download_dir(root: Path, task_id: str, action_id: str) -> Path:
    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink() or not root.is_dir():
        raise PolicyDeniedError(
            "DP_MCP_DOWNLOAD_ROOT must identify a directory.",
            rule="DP_MCP_DOWNLOAD_ROOT",
            value="<redacted>",
        )
    task_dir = root / task_id
    if task_dir.exists() and task_dir.is_symlink():
        raise PolicyDeniedError(
            "The task download directory is a symlink.",
            rule="DP_MCP_DOWNLOAD_ROOT",
            value="<redacted>",
        )
    task_dir.mkdir(exist_ok=True)
    action_dir = task_dir / action_id
    action_dir.mkdir(exist_ok=False)
    resolved = action_dir.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PolicyDeniedError(
            "The allocated download directory escaped DP_MCP_DOWNLOAD_ROOT.",
            rule="DP_MCP_DOWNLOAD_ROOT",
            value="<redacted>",
        ) from exc
    return resolved


def _validate_task_download_directory(root: Path, task_id: str) -> None:
    task_dir = root.expanduser().resolve() / task_id
    if task_dir.is_symlink():
        raise PolicyDeniedError(
            "The task download directory is a symlink.",
            rule="DP_MCP_DOWNLOAD_ROOT",
            value="<redacted>",
        )
    if task_dir.exists() and not task_dir.is_dir():
        raise PolicyDeniedError(
            "The task download directory must be a directory.",
            rule="DP_MCP_DOWNLOAD_ROOT",
            value="<redacted>",
        )


def _validate_download_capability(context: "DrissionPageContext") -> None:
    for capability in context.capability_set().capabilities:
        if capability.name == "download.click_and_wait" and capability.status in {
            "unsupported",
            "degraded",
        }:
            raise DownloadUnsupportedError(
                capability.reason_code or "RECORDED_CAPABILITY_UNAVAILABLE"
            )


def _download_probe(
    status: Literal["supported", "unsupported"], reason: str | None = None
) -> CapabilityProbe:
    return CapabilityProbe(
        name="download.click_and_wait",
        status=status,
        evidence_source="runtime_probe"
        if status == "unsupported"
        else "integration_probe",
        reason_code=reason,
        checked_at=datetime.now(timezone.utc),
    )


def _receipt(
    *,
    context: "DrissionPageContext",
    action_id: str,
    operation_key: str,
    fingerprint: str,
    tab_id: str,
    target_fingerprint: str,
    started_at: datetime,
    status: Literal["success", "failed", "validation_failed", "indeterminate"],
    artifact_ids: tuple[str, ...] = (),
    error_code: str | None = None,
) -> ActionReceipt:
    return ActionReceipt(
        action_id=action_id,
        task_id=context.task_id,
        operation_key=operation_key,
        request_fingerprint=fingerprint,
        kind="element_click_and_download",
        side_effect="external_download",
        status=status,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        tab_id=tab_id,
        target_fingerprint=target_fingerprint,
        artifact_ids=artifact_ids,
        error_code=(
            error_code
            if error_code is not None
            else (None if status == "success" else f"DOWNLOAD_{status.upper()}")
        ),
        redacted=True,
    )


def _download_failure_message(exc: Exception) -> str:
    if isinstance(exc, DownloadUnsupportedError):
        return str(exc)
    if isinstance(exc, DownloadValidationError):
        return "Download artifact validation failed; no artifact was published."
    if isinstance(exc, DownloadFailedError):
        return "The browser download failed before producing an artifact."
    if isinstance(exc, (DownloadIndeterminateError, TimeoutError)):
        return "The browser download outcome is indeterminate; inspect the artifact inventory before retrying."
    if isinstance(exc, PolicyDeniedError):
        return str(exc)
    return (
        "The browser download outcome is indeterminate; diagnostic text was redacted."
    )


def _download_error_from_status(status: str) -> Exception:
    if status == "validation_failed":
        return DownloadValidationError(
            "The previous download failed artifact validation; no retry was performed."
        )
    if status == "failed":
        return DownloadFailedError(
            "The previous browser download failed; no retry was performed."
        )
    return DownloadIndeterminateError(
        "The previous browser download outcome is indeterminate; no retry was performed."
    )


def _failure_outcome(data: dict[str, object], exc: Exception) -> ToolOutcome:
    outcome = ToolOutcome()
    status = str(data.get("status") or "indeterminate")
    if status == "validation_failed":
        code = ErrorCode.PRECONDITION_FAILED
    elif status == "indeterminate":
        code = ErrorCode.TIMEOUT
    else:
        code = ErrorCode.UNKNOWN_ERROR
    outcome.add_error(
        _download_failure_message(exc),
        code,
        tool_name="element_click_and_download",
    )
    outcome._data = data
    return outcome
