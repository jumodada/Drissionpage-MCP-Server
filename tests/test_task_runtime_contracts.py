"""Core 0.7.2 contracts and live-process ledger behavior."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from drissionpage_mcp.context import (
    DrissionPageContext,
    OperationClaim,
    OperationInFlightError,
    OperationKeyConflictError,
    TaskLedgerFullError,
)
from drissionpage_mcp.tool_outputs import (
    ActionReceipt,
    ArtifactRef,
    CapabilityProbe,
    CapabilitySet,
    ElementClickAndDownloadData,
    TaskContext,
)


def test_context_uses_drissionpage_free_task_runtime_boundary() -> None:
    from drissionpage_mcp.runtime import TaskRuntime

    assert issubclass(DrissionPageContext, TaskRuntime)

    runtime_path = Path(__file__).parents[1] / "drissionpage_mcp" / "runtime.py"
    tree = ast.parse(runtime_path.read_text(encoding="utf-8"))
    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert not any(
        name == "DrissionPage" or name.startswith("DrissionPage.")
        for name in imported_modules
    )


def _dialog_receipt(
    context: DrissionPageContext,
    operation_key: str,
    fingerprint: str,
    *,
    status: str = "success",
) -> ActionReceipt:
    now = datetime.now(timezone.utc)
    return ActionReceipt(
        action_id=context.new_action_id(),
        task_id=context.task_id,
        operation_key=operation_key,
        request_fingerprint=fingerprint,
        kind="page_dialog_respond",
        side_effect="dialog_response",
        status=status,
        started_at=now,
        finished_at=now,
        tab_id="t0",
    )


def _artifact(context: DrissionPageContext, artifact_id: str) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=artifact_id,
        task_id=context.task_id,
        producing_action_id="action-000001",
        kind="download",
        filename="report.csv",
        mime_type="text/csv",
        size_bytes=10,
        sha256="a" * 64,
        safe_relative_path=f"{context.task_id}/report.csv",
        source_url="https://user:pass@example.test/report?token=secret#part",
        created_at=datetime.now(timezone.utc),
    )


def _download_receipt(
    context: DrissionPageContext,
    operation_key: str,
    fingerprint: str,
    artifact_id: str,
) -> ActionReceipt:
    now = datetime.now(timezone.utc)
    return ActionReceipt(
        action_id="action-000001",
        task_id=context.task_id,
        operation_key=operation_key,
        request_fingerprint=fingerprint,
        kind="element_click_and_download",
        side_effect="external_download",
        status="success",
        started_at=now,
        finished_at=now,
        tab_id="t0",
        artifact_ids=(artifact_id,),
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"operation_limit": 0},
        {"artifact_limit": 0},
        {"retry_limit": -1},
    ],
)
def test_task_context_rejects_invalid_ledger_limits(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        DrissionPageContext(**kwargs)


def test_shared_contracts_are_strict_frozen_and_bounded() -> None:
    task = DrissionPageContext().task_summary()

    assert task.lifetime == "server_process"
    with pytest.raises(ValidationError):
        TaskContext.model_validate({**task.model_dump(), "unexpected": True})
    with pytest.raises(ValidationError):
        task.action_count = 1  # type: ignore[misc]

    receipt_payload = _dialog_receipt(
        DrissionPageContext(), "dialog-1", "a" * 64
    ).model_dump()
    receipt_payload["finished_at"] = receipt_payload["started_at"] - timedelta(
        seconds=1
    )
    with pytest.raises(ValidationError, match="must not precede"):
        ActionReceipt.model_validate(receipt_payload)


def test_capability_support_requires_behavioral_probe_evidence() -> None:
    checked_at = datetime.now(timezone.utc)
    supported = CapabilityProbe(
        name="dialog.respond",
        status="supported",
        evidence_source="integration_probe",
        checked_at=checked_at,
    )
    capabilities = CapabilitySet(
        overall_status="supported",
        capabilities=(supported,),
    )

    assert capabilities.capabilities[0].status == "supported"
    with pytest.raises(ValidationError):
        CapabilityProbe(
            name="dialog.respond",
            status="supported",
            evidence_source="runtime_probe",
            checked_at=checked_at,
        )
    with pytest.raises(ValidationError, match="require evidence_source"):
        CapabilityProbe(
            name="dialog.respond",
            status="unsupported",
        )
    with pytest.raises(ValidationError):
        CapabilityProbe(
            name="dialog.respond",
            status="unprobed",
            evidence_source="runtime_probe",
            checked_at=checked_at,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("filename", "../secret.csv"),
        ("filename", "nested/report.csv"),
        ("safe_relative_path", "/tmp/report.csv"),
        ("safe_relative_path", "task/../report.csv"),
        ("safe_relative_path", "C:/tmp/report.csv"),
        ("safe_relative_path", "task\\report.csv"),
        ("sha256", "invalid"),
    ],
)
def test_artifact_ref_rejects_unsafe_metadata(field: str, value: str) -> None:
    context = DrissionPageContext()
    payload = _artifact(context, "artifact-000001").model_dump()
    payload[field] = value

    with pytest.raises(ValidationError):
        ArtifactRef.model_validate(payload)


@pytest.mark.parametrize(
    ("source_url", "expected"),
    [
        (
            "https://user:pass@example.test/report?token=secret#part",
            "https://example.test/report",
        ),
        (
            "http://user:pass@example.test:8080/report?token=secret#part",
            "http://example.test:8080/report",
        ),
    ],
)
def test_artifact_source_url_is_sanitized(source_url: str, expected: str) -> None:
    context = DrissionPageContext()
    payload = _artifact(context, "artifact-000001").model_dump()
    payload["source_url"] = source_url

    artifact = ArtifactRef.model_validate(payload)

    assert artifact.source_url == expected


@pytest.mark.parametrize(
    "source_url",
    [
        "file:///Users/example/secret.txt",
        "data:text/plain,secret",
        "javascript:alert(1)",
        "not a URL",
        "https://",
        "https://[malformed",
        "http://.",
        "https://bad_host.example/report.csv",
        "https://-bad.example/report.csv",
        "https://bad-.example/report.csv",
        "https://example..test/report.csv",
        "https://example.test/report with space.csv",
        "https://example.test/report\\secret.csv",
        "https://example.test/report%zz.csv",
        "https://example.test/" + "a" * 500,
    ],
)
def test_artifact_source_url_redacts_unsafe_or_malformed_urls(
    source_url: str,
) -> None:
    context = DrissionPageContext()
    payload = _artifact(context, "artifact-000001").model_dump()
    payload["source_url"] = source_url

    artifact = ArtifactRef.model_validate(payload)

    assert artifact.source_url == ""


def _download_data_payload(
    *,
    status: str = "success",
) -> dict[str, object]:
    now = datetime.now(timezone.utc)
    artifact_id = "artifact-000001"
    task_id = "task-000001"
    action_id = "action-000001"
    operation_key = "download-report-1"
    receipt = ActionReceipt(
        action_id=action_id,
        task_id=task_id,
        operation_key=operation_key,
        request_fingerprint="a" * 64,
        kind="element_click_and_download",
        side_effect="external_download",
        status=status,
        started_at=now,
        finished_at=now,
        tab_id="t0",
        artifact_ids=(artifact_id,) if status == "success" else (),
    ).model_dump(mode="json")
    artifact = ArtifactRef(
        artifact_id=artifact_id,
        task_id=task_id,
        producing_action_id=action_id,
        kind="download",
        filename="report.csv",
        mime_type="text/csv",
        size_bytes=10,
        sha256="b" * 64,
        safe_relative_path=f"{task_id}/{action_id}/report.csv",
        source_url="https://example.test/report.csv",
        created_at=now,
    ).model_dump(mode="json")
    return {
        "status": status,
        "operation_key": operation_key,
        "selector": "#download",
        "locator": "css:#download",
        "selector_strategy": "css",
        "selector_normalized": True,
        "artifact": artifact if status == "success" else None,
        "receipt": receipt,
    }


def test_click_and_download_contract_accepts_correlated_success_and_failures() -> None:
    success = ElementClickAndDownloadData.model_validate(_download_data_payload())
    failure = ElementClickAndDownloadData.model_validate(
        _download_data_payload(status="failed")
    )

    assert success.model_dump(mode="json")["artifact"] is not None
    assert failure.model_dump(mode="json")["artifact"] is None


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("artifact",), None),
        (("receipt", "status"), "failed"),
        (("receipt", "kind"), "page_dialog_respond"),
        (("receipt", "side_effect"), "dialog_response"),
        (("receipt", "operation_key"), "other-operation"),
        (("artifact", "task_id"), "task-other"),
        (("artifact", "producing_action_id"), "action-other"),
        (("receipt", "artifact_ids"), []),
        (("receipt", "artifact_ids"), ["artifact-other"]),
    ],
)
def test_click_and_download_contract_rejects_uncorrelated_success(
    path: tuple[str, ...], value: object
) -> None:
    payload = _download_data_payload()
    target = payload
    for key in path[:-1]:
        nested = target[key]
        assert isinstance(nested, dict)
        target = nested
    target[path[-1]] = value

    with pytest.raises(ValidationError):
        ElementClickAndDownloadData.model_validate(payload)


@pytest.mark.parametrize("status", ["failed", "validation_failed", "indeterminate"])
def test_click_and_download_contract_rejects_invalid_failure_shapes(
    status: str,
) -> None:
    payload = _download_data_payload(status=status)
    valid_artifact = _download_data_payload()["artifact"]

    mismatched_receipt = _download_data_payload(status=status)
    receipt = mismatched_receipt["receipt"]
    assert isinstance(receipt, dict)
    receipt["status"] = "success"
    with pytest.raises(ValidationError):
        ElementClickAndDownloadData.model_validate(mismatched_receipt)

    mismatched_operation = _download_data_payload(status=status)
    receipt = mismatched_operation["receipt"]
    assert isinstance(receipt, dict)
    receipt["operation_key"] = "other-operation"
    with pytest.raises(ValidationError):
        ElementClickAndDownloadData.model_validate(mismatched_operation)

    payload["artifact"] = valid_artifact
    with pytest.raises(ValidationError):
        ElementClickAndDownloadData.model_validate(payload)

    payload = _download_data_payload(status=status)
    receipt = payload["receipt"]
    assert isinstance(receipt, dict)
    receipt["artifact_ids"] = ["artifact-000001"]
    with pytest.raises(ValidationError):
        ElementClickAndDownloadData.model_validate(payload)


def test_request_fingerprint_is_canonical_and_sensitive_to_request_changes() -> None:
    first = DrissionPageContext.request_fingerprint(
        {"tool": "page_dialog_respond", "accept": True, "prompt_text": ""}
    )
    reordered = DrissionPageContext.request_fingerprint(
        {"prompt_text": "", "accept": True, "tool": "page_dialog_respond"}
    )
    changed = DrissionPageContext.request_fingerprint(
        {"tool": "page_dialog_respond", "accept": False, "prompt_text": ""}
    )

    assert first == reordered
    assert first != changed
    assert len(first) == 64


@pytest.mark.parametrize("method_name", ["claim_operation", "preview_operation"])
@pytest.mark.parametrize(
    ("operation_key", "fingerprint"),
    [
        ("", "a" * 64),
        ("x" * 129, "a" * 64),
        ("dialog-1", "short"),
    ],
)
def test_operation_claim_inputs_are_strict(
    method_name: str, operation_key: str, fingerprint: str
) -> None:
    context = DrissionPageContext()
    method = getattr(context, method_name)

    with pytest.raises(ValueError):
        method(operation_key, fingerprint)


@pytest.mark.parametrize("method_name", ["claim_operation", "preview_operation"])
def test_operation_claim_inputs_normalize_uppercase_fingerprints(
    method_name: str,
) -> None:
    context = DrissionPageContext()
    method = getattr(context, method_name)

    result = method("dialog-1", "A" * 64)

    if result is not None:
        assert result.request_fingerprint == "a" * 64


def test_atomic_claim_allows_only_one_concurrent_invocation() -> None:
    context = DrissionPageContext(operation_limit=2)
    fingerprint = "a" * 64

    def claim() -> str:
        try:
            return (
                "invoke"
                if context.claim_operation("dialog-1", fingerprint).should_invoke
                else "cached"
            )
        except OperationInFlightError:
            return "in-flight"

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: claim(), range(8)))

    assert results.count("invoke") == 1
    assert results.count("in-flight") == 7


def test_completed_operation_replays_receipt_and_rejects_changed_request() -> None:
    context = DrissionPageContext(operation_limit=2)
    fingerprint = "a" * 64
    claim = context.claim_operation("dialog-1", fingerprint)
    receipt = context.complete_operation(
        claim, _dialog_receipt(context, "dialog-1", fingerprint)
    )

    replay = context.claim_operation("dialog-1", fingerprint)

    assert replay.should_invoke is False
    assert replay.cached_receipt == receipt
    with pytest.raises(OperationKeyConflictError):
        context.claim_operation("dialog-1", "b" * 64)


def test_complete_operation_rejects_mismatched_or_inactive_claims() -> None:
    context = DrissionPageContext()
    fingerprint = "a" * 64
    claim = context.claim_operation("dialog-1", fingerprint)
    receipt = _dialog_receipt(context, "dialog-1", fingerprint)

    with pytest.raises(OperationKeyConflictError, match="operation_key"):
        context.complete_operation(
            claim, receipt.model_copy(update={"operation_key": "dialog-other"})
        )
    with pytest.raises(OperationKeyConflictError, match="request_fingerprint"):
        context.complete_operation(
            claim, receipt.model_copy(update={"request_fingerprint": "b" * 64})
        )
    with pytest.raises(OperationKeyConflictError, match="task_id"):
        context.complete_operation(
            claim, receipt.model_copy(update={"task_id": "task-other"})
        )

    retried_receipt = receipt.model_copy(update={"retry_of": "action-000000"})
    completed = context.complete_operation(
        claim, retried_receipt, result={"nested": {"x": 1}}
    )
    assert context.complete_operation(claim, retried_receipt) is completed
    assert context.task_summary().retry_count == 1
    cached = context.operation_result("dialog-1")
    assert cached == {"nested": {"x": 1}}
    assert cached is not None
    cached["nested"]["x"] = 2
    assert context.operation_result("dialog-1") == {"nested": {"x": 1}}

    inactive = OperationClaim("never-claimed", claim.request_fingerprint)
    inactive_receipt = receipt.model_copy(update={"operation_key": "never-claimed"})
    with pytest.raises(OperationKeyConflictError, match="not active"):
        context.complete_operation(inactive, inactive_receipt)


def test_artifact_guards_and_atomic_completion_contract() -> None:
    context = DrissionPageContext(artifact_limit=2)
    artifact = _artifact(context, "artifact-000001")

    with pytest.raises(OperationKeyConflictError, match="task_id"):
        context.record_artifact(artifact.model_copy(update={"task_id": "task-other"}))
    recorded = context.record_artifact(artifact)
    assert context.record_artifact(artifact) is recorded
    with pytest.raises(OperationKeyConflictError, match="different metadata"):
        context.record_artifact(artifact.model_copy(update={"sha256": "b" * 64}))

    context.reserve_artifact_slot("artifact-000002")
    with pytest.raises(OperationKeyConflictError, match="already reserved"):
        context.reserve_artifact_slot("artifact-000002")
    context.release_artifact_slot("artifact-000002")

    operation_context = DrissionPageContext()
    fingerprint = "a" * 64
    claim = operation_context.claim_operation("download-1", fingerprint)
    download_artifact = _artifact(operation_context, "artifact-000001")
    receipt = _download_receipt(
        operation_context, "download-1", fingerprint, download_artifact.artifact_id
    ).model_copy(update={"retry_of": "action-000000"})
    operation_context.reserve_artifact_slot(download_artifact.artifact_id)

    mismatch_cases = [
        (receipt.model_copy(update={"operation_key": "other"}), download_artifact),
        (
            receipt.model_copy(update={"request_fingerprint": "b" * 64}),
            download_artifact,
        ),
        (receipt.model_copy(update={"task_id": "task-other"}), download_artifact),
        (
            receipt,
            download_artifact.model_copy(
                update={"producing_action_id": "action-other"}
            ),
        ),
        (
            receipt.model_copy(update={"artifact_ids": ("artifact-other",)}),
            download_artifact,
        ),
    ]
    for invalid_receipt, invalid_artifact in mismatch_cases:
        with pytest.raises(OperationKeyConflictError):
            operation_context.complete_artifact_operation(
                claim,
                invalid_receipt,
                invalid_artifact,
                result={"status": "success"},
            )

    completed = operation_context.complete_artifact_operation(
        claim, receipt, download_artifact, result={"status": "success"}
    )
    assert (
        operation_context.complete_artifact_operation(
            claim, receipt, download_artifact, result={"status": "success"}
        )
        is completed
    )
    assert operation_context.task_summary().retry_count == 1

    inactive_context = DrissionPageContext()
    inactive_artifact = _artifact(inactive_context, "artifact-000002")
    inactive_claim = OperationClaim("download-2", fingerprint)
    inactive_receipt = _download_receipt(
        inactive_context,
        inactive_claim.operation_key,
        fingerprint,
        inactive_artifact.artifact_id,
    )
    with pytest.raises(OperationKeyConflictError, match="not active"):
        inactive_context.complete_artifact_operation(
            inactive_claim,
            inactive_receipt,
            inactive_artifact,
            result={"status": "success"},
        )


def test_capability_probe_aggregation_covers_all_public_states() -> None:
    context = DrissionPageContext()
    now = datetime.now(timezone.utc)

    unprobed = CapabilityProbe(
        name="dialog.respond",
        status="unprobed",
    )
    supported = CapabilityProbe(
        name="dialog.respond",
        status="supported",
        evidence_source="integration_probe",
        checked_at=now,
    )
    unsupported = CapabilityProbe(
        name="download.click_and_wait",
        status="unsupported",
        evidence_source="runtime_probe",
        reason_code="DOWNLOAD_MANAGER_UNAVAILABLE",
        checked_at=now,
    )

    assert context.record_capability_probe(unprobed).overall_status == "unprobed"
    assert context.record_capability_probe(supported).overall_status == "supported"
    assert context.record_capability_probe(unsupported).overall_status == "degraded"
    context.set_capability_set(CapabilitySet())
    assert context.record_capability_probe(unsupported).overall_status == "unsupported"


def test_preview_operation_replays_without_reserving_new_key() -> None:
    context = DrissionPageContext()
    fingerprint = "a" * 64
    assert context.preview_operation("dialog-1", fingerprint) is None
    assert context.task_summary().operation_count == 0
    claim = context.claim_operation("dialog-1", fingerprint)
    receipt = context.complete_operation(
        claim,
        _dialog_receipt(context, "dialog-1", fingerprint),
        result={"status": "success", "operation_key": "dialog-1"},
    )

    replay = context.preview_operation("dialog-1", fingerprint)

    assert replay is not None
    assert replay.cached_receipt == receipt
    assert replay.cached_result == {"status": "success", "operation_key": "dialog-1"}
    with pytest.raises(OperationKeyConflictError):
        context.preview_operation("dialog-1", "b" * 64)


def test_in_flight_claim_remains_reserved_and_prevents_blind_retry() -> None:
    context = DrissionPageContext()
    context.claim_operation("dialog-1", "a" * 64)

    with pytest.raises(OperationInFlightError):
        context.claim_operation("dialog-1", "a" * 64)
    with pytest.raises(OperationInFlightError):
        context.preview_operation("dialog-1", "a" * 64)
    assert context.operation_receipt("dialog-1") is None


def test_operation_and_artifact_caps_never_evict_dedupe_evidence() -> None:
    context = DrissionPageContext(operation_limit=1, artifact_limit=1)
    fingerprint = "a" * 64
    claim = context.claim_operation("dialog-1", fingerprint)
    receipt = context.complete_operation(
        claim, _dialog_receipt(context, "dialog-1", fingerprint)
    )
    context.record_artifact(_artifact(context, "artifact-000001"))

    with pytest.raises(TaskLedgerFullError):
        context.claim_operation("dialog-2", "b" * 64)
    with pytest.raises(TaskLedgerFullError):
        context.record_artifact(_artifact(context, "artifact-000002"))

    assert context.claim_operation("dialog-1", fingerprint).cached_receipt == receipt
    assert len(context.artifact_inventory()) == 1


def test_consequential_receipts_share_one_bounded_inventory() -> None:
    context = DrissionPageContext(operation_limit=2)
    first_fingerprint = context.request_fingerprint(
        {"tool": "page_dialog_respond", "accept": True}
    )
    first_claim = context.claim_operation("dialog-1", first_fingerprint)
    first = context.complete_operation(
        first_claim, _dialog_receipt(context, "dialog-1", first_fingerprint)
    )
    after_first = context.task_summary()

    assert after_first.operation_count == 1
    assert after_first.receipt_count == 1
    assert after_first.action_count == 1
    assert context.receipt_inventory() == [first]

    second_fingerprint = context.request_fingerprint(
        {"tool": "page_dialog_respond", "accept": False}
    )
    second_claim = context.claim_operation("dialog-2", second_fingerprint)
    second = context.complete_operation(
        second_claim, _dialog_receipt(context, "dialog-2", second_fingerprint)
    )
    full = context.task_summary()

    assert full.operation_count == 2
    assert full.receipt_count == 2
    assert full.action_count == 2
    assert context.receipt_inventory() == [first, second]
    assert (
        context.claim_operation("dialog-2", second_fingerprint).cached_receipt
        == second
    )
    with pytest.raises(TaskLedgerFullError):
        context.claim_operation("dialog-3", "b" * 64)
    assert context.receipt_inventory() == [first, second]


def test_preflight_denial_by_convention_creates_no_claim_or_receipt() -> None:
    context = DrissionPageContext()

    # Policy/capability adapters must run before claim_operation. G001 proves
    # that untouched runtime state has no implicit receipt or dedupe entry.
    summary = context.task_summary()

    assert summary.operation_count == 0
    assert summary.receipt_count == 0
    assert context.receipt_inventory() == []
