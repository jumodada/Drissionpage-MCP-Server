"""Core 0.7.0 contracts and live-process ledger behavior."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from drissionpage_mcp.context import (
    DrissionPageContext,
    OperationInFlightError,
    OperationKeyConflictError,
    TaskLedgerFullError,
)
from drissionpage_mcp.tool_outputs import (
    ActionReceipt,
    ArtifactRef,
    CapabilityProbe,
    CapabilitySet,
    Expectation,
    TaskContext,
)


def _receipt(
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
        kind="form_submit",
        side_effect="external_submission",
        status=status,
        started_at=now,
        finished_at=now,
        tab_id="t0",
    )


def _local_receipt(
    context: DrissionPageContext,
    operation_key: str,
    *,
    status: str = "success",
) -> ActionReceipt:
    now = datetime.now(timezone.utc)
    return ActionReceipt(
        action_id=context.new_action_id(),
        task_id=context.task_id,
        operation_key=operation_key,
        request_fingerprint=context.request_fingerprint(
            {"tool": "form_fill", "operation_key": operation_key}
        ),
        kind="form_fill",
        side_effect="local_ui_mutation",
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


def test_shared_contracts_are_strict_frozen_and_bounded() -> None:
    expectation = Expectation(
        mode="all",
        conditions=(
            {"kind": "url_changed"},
            {"kind": "selector_visible", "selector": "[role=status]"},
        ),
        timeout=2,
    )
    task = DrissionPageContext().task_summary()

    assert expectation.model_dump(mode="json")["mode"] == "all"
    assert task.lifetime == "server_process"
    with pytest.raises(ValidationError):
        Expectation(conditions=(), timeout=1)
    with pytest.raises(ValidationError):
        Expectation(
            conditions=tuple({"kind": "url_changed"} for _ in range(9)),
            timeout=1,
        )
    with pytest.raises(ValidationError):
        Expectation(conditions=({"kind": "url_changed"},), timeout=0)
    with pytest.raises(ValidationError):
        TaskContext.model_validate({**task.model_dump(), "unexpected": True})
    with pytest.raises(ValidationError):
        task.action_count = 1  # type: ignore[misc]


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


def test_artifact_source_url_is_sanitized() -> None:
    artifact = _artifact(DrissionPageContext(), "artifact-000001")

    assert artifact.source_url == "https://example.test/report"


def test_request_fingerprint_is_canonical_and_sensitive_to_request_changes() -> None:
    first = DrissionPageContext.request_fingerprint(
        {"tool": "form_submit", "target": "#form", "expect": {"timeout": 2}}
    )
    reordered = DrissionPageContext.request_fingerprint(
        {"expect": {"timeout": 2}, "target": "#form", "tool": "form_submit"}
    )
    changed = DrissionPageContext.request_fingerprint(
        {"tool": "form_submit", "target": "#other", "expect": {"timeout": 2}}
    )

    assert first == reordered
    assert first != changed
    assert len(first) == 64


def test_atomic_claim_allows_only_one_concurrent_invocation() -> None:
    context = DrissionPageContext(operation_limit=2)
    fingerprint = "a" * 64

    def claim() -> str:
        try:
            return (
                "invoke"
                if context.claim_operation("submit-1", fingerprint).should_invoke
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
    claim = context.claim_operation("submit-1", fingerprint)
    receipt = context.complete_operation(
        claim, _receipt(context, "submit-1", fingerprint)
    )

    replay = context.claim_operation("submit-1", fingerprint)

    assert replay.should_invoke is False
    assert replay.cached_receipt == receipt
    with pytest.raises(OperationKeyConflictError):
        context.claim_operation("submit-1", "b" * 64)


def test_preview_operation_replays_without_reserving_new_key() -> None:
    context = DrissionPageContext()
    fingerprint = "a" * 64
    assert context.preview_operation("submit-1", fingerprint) is None
    assert context.task_summary().operation_count == 0
    claim = context.claim_operation("submit-1", fingerprint)
    receipt = context.complete_operation(
        claim,
        _receipt(context, "submit-1", fingerprint),
        result={"status": "success", "operation_key": "submit-1"},
    )

    replay = context.preview_operation("submit-1", fingerprint)

    assert replay is not None
    assert replay.cached_receipt == receipt
    assert replay.cached_result == {"status": "success", "operation_key": "submit-1"}
    with pytest.raises(OperationKeyConflictError):
        context.preview_operation("submit-1", "b" * 64)


def test_in_flight_claim_remains_reserved_and_prevents_blind_retry() -> None:
    context = DrissionPageContext()
    context.claim_operation("submit-1", "a" * 64)

    with pytest.raises(OperationInFlightError):
        context.claim_operation("submit-1", "a" * 64)
    with pytest.raises(OperationInFlightError):
        context.preview_operation("submit-1", "a" * 64)
    assert context.operation_receipt("submit-1") is None


def test_operation_and_artifact_caps_never_evict_dedupe_evidence() -> None:
    context = DrissionPageContext(operation_limit=1, artifact_limit=1)
    fingerprint = "a" * 64
    claim = context.claim_operation("submit-1", fingerprint)
    receipt = context.complete_operation(
        claim, _receipt(context, "submit-1", fingerprint)
    )
    context.record_artifact(_artifact(context, "artifact-000001"))

    with pytest.raises(TaskLedgerFullError):
        context.claim_operation("submit-2", "b" * 64)
    with pytest.raises(TaskLedgerFullError):
        context.record_artifact(_artifact(context, "artifact-000002"))

    assert context.claim_operation("submit-1", fingerprint).cached_receipt == receipt
    assert len(context.artifact_inventory()) == 1


def test_local_and_consequential_receipts_share_one_bounded_inventory() -> None:
    context = DrissionPageContext(operation_limit=2)
    local_receipt = _local_receipt(context, "local-fill-1")
    local_claim = context.claim_operation(
        local_receipt.operation_key, local_receipt.request_fingerprint
    )
    local = context.complete_operation(local_claim, local_receipt)
    after_local = context.task_summary()

    assert after_local.operation_count == 1
    assert after_local.receipt_count == 1
    assert after_local.action_count == 1
    assert context.receipt_inventory() == [local]

    fingerprint = context.request_fingerprint({"tool": "form_submit", "form": "#f"})
    claim = context.claim_operation("submit-1", fingerprint)
    external = context.complete_operation(
        claim, _receipt(context, "submit-1", fingerprint)
    )
    full = context.task_summary()

    assert full.operation_count == 2
    assert full.receipt_count == 2
    assert full.action_count == 2
    assert context.receipt_inventory() == [local, external]
    assert context.claim_operation("submit-1", fingerprint).cached_receipt == external
    with pytest.raises(TaskLedgerFullError):
        context.claim_operation("submit-2", "b" * 64)
    assert context.receipt_inventory() == [local, external]


def test_preflight_denial_by_convention_creates_no_claim_or_receipt() -> None:
    context = DrissionPageContext()

    # Policy/capability adapters must run before claim_operation. G001 proves
    # that untouched runtime state has no implicit receipt or dedupe entry.
    summary = context.task_summary()

    assert summary.operation_count == 0
    assert summary.receipt_count == 0
    assert context.receipt_inventory() == []
