"""Live-process task runtime state without browser ownership."""

from __future__ import annotations

import hashlib
import json
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from secrets import token_hex
from threading import Lock
from typing import Any, Deque, Mapping, Sequence

from .observation import safe_int
from .response_errors import ErrorCode
from .tool_outputs import (
    ActionReceipt,
    ArtifactRef,
    CapabilityProbe,
    CapabilitySet,
    PolicyControl,
    TaskContext,
    sanitize_public_url,
)

DEFAULT_OPERATION_LIMIT = 80
DEFAULT_ARTIFACT_LIMIT = 80
DEFAULT_RETRY_LIMIT = 3


class OperationKeyConflictError(ValueError):
    """Raised when an operation key is reused for a different request."""

    code = ErrorCode.OPERATION_KEY_CONFLICT


class TaskLedgerFullError(RuntimeError):
    """Raised before a side effect when the live task ledger is full."""

    code = ErrorCode.TASK_LEDGER_FULL


class OperationInFlightError(RuntimeError):
    """Raised when a duplicate operation is already executing."""

    code = ErrorCode.OPERATION_IN_FLIGHT


class OperationClaim:
    """Immutable claim result used to guard one consequential invocation."""

    __slots__ = (
        "operation_key",
        "request_fingerprint",
        "cached_receipt",
        "cached_result",
    )

    def __init__(
        self,
        operation_key: str,
        request_fingerprint: str,
        cached_receipt: ActionReceipt | None = None,
        cached_result: Mapping[str, Any] | None = None,
    ) -> None:
        self.operation_key = operation_key
        self.request_fingerprint = request_fingerprint
        self.cached_receipt = cached_receipt
        self.cached_result = deepcopy(dict(cached_result)) if cached_result else None

    @property
    def should_invoke(self) -> bool:
        return self.cached_receipt is None


SENSITIVE_HISTORY_KEYS = {
    "password",
    "passwd",
    "pwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "cookies",
    "text",
    "prompt_text",
    "value",
    "values",
    "fields",
    "body",
    "headers",
    "request_headers",
    "response_headers",
    "request_body",
    "response_body",
    "post_data",
    "postdata",
    "set-cookie",
    "proxy-authorization",
}


class TaskRuntime:
    """Own bounded task history, operation receipts, artifacts, and capabilities."""

    def __init__(
        self,
        *,
        history_limit: int = 100,
        operation_limit: int = DEFAULT_OPERATION_LIMIT,
        artifact_limit: int = DEFAULT_ARTIFACT_LIMIT,
        retry_limit: int = DEFAULT_RETRY_LIMIT,
    ) -> None:
        if operation_limit < 1:
            raise ValueError("operation_limit must be at least 1")
        if artifact_limit < 1:
            raise ValueError("artifact_limit must be at least 1")
        if retry_limit < 0:
            raise ValueError("retry_limit must be non-negative")

        self._history_limit = history_limit
        self._action_history: Deque[dict[str, Any]] = deque(maxlen=history_limit)
        self._task_id = f"task-{token_hex(8)}"
        self._task_created_at = datetime.now(timezone.utc)
        self._operation_limit = operation_limit
        self._artifact_limit = artifact_limit
        self._retry_limit = retry_limit
        self._task_lock = Lock()
        self._operation_fingerprints: dict[str, str] = {}
        self._in_flight_operations: set[str] = set()
        self._operation_receipts: dict[str, ActionReceipt] = {}
        self._operation_results: dict[str, dict[str, Any]] = {}
        self._artifacts: dict[str, ArtifactRef] = {}
        self._artifact_reservations: set[str] = set()
        self._action_count = 0
        self._retry_count = 0
        self._last_action_id: str | None = None
        self._last_verified_action_id: str | None = None
        self._next_action_index = 1
        self._next_artifact_index = 1
        self._capability_set = CapabilitySet()

    def record_action(
        self,
        tool: str,
        args: Mapping[str, Any],
        result: Mapping[str, Any],
        *,
        url_before: str = "",
        url_after: str = "",
        tab_id: str = "",
    ) -> None:
        """Append a redacted tool action to the session history."""

        self._action_history.append(
            {
                "time": datetime.now(timezone.utc).isoformat(),
                "tool": tool,
                "args": _redact_history_value(dict(args)),
                "result": _summarize_result(result),
                "url_before": _redact_history_url(url_before),
                "url_after": _redact_history_url(url_after),
                "tab_id": tab_id,
            }
        )

    def action_history(self) -> dict[str, Any]:
        """Return bounded action history for the MCP resource surface."""

        return {
            "available": True,
            "limit": self._history_limit,
            "count": len(self._action_history),
            "actions": list(self._action_history),
        }

    def claim_operation(
        self, operation_key: str, request_fingerprint: str
    ) -> OperationClaim:
        """Atomically claim or replay one live-process consequential operation."""

        key, fingerprint = _operation_identity(operation_key, request_fingerprint)
        with self._task_lock:
            existing = self._existing_operation_locked(key, fingerprint)
            if existing is not None:
                return existing
            self._ensure_operation_capacity_locked(key)
            self._operation_fingerprints[key] = fingerprint
            self._in_flight_operations.add(key)
            return OperationClaim(key, fingerprint)

    def preview_operation(
        self, operation_key: str, request_fingerprint: str
    ) -> OperationClaim | None:
        """Read an existing operation state without reserving a new key."""

        key, fingerprint = _operation_identity(operation_key, request_fingerprint)
        with self._task_lock:
            if key not in self._operation_fingerprints:
                return None
            return self._existing_operation_locked(key, fingerprint)

    def _existing_operation_locked(
        self, key: str, fingerprint: str
    ) -> OperationClaim | None:
        existing_fingerprint = self._operation_fingerprints.get(key)
        if existing_fingerprint is None:
            return None
        if existing_fingerprint != fingerprint:
            raise OperationKeyConflictError(
                "operation_key is already bound to a different request"
            )
        cached = self._operation_receipts.get(key)
        if cached is None:
            raise OperationInFlightError(
                "operation_key is already executing in this live task"
            )
        return OperationClaim(
            key,
            fingerprint,
            cached,
            self._operation_results.get(key),
        )

    def _ensure_operation_capacity_locked(self, key: str) -> None:
        if (
            key not in self._operation_fingerprints
            and self._operation_count_locked() >= self._operation_limit
        ):
            raise TaskLedgerFullError(
                "operation ledger limit reached; start a new server task"
            )

    def _operation_count_locked(self) -> int:
        return len(
            set(self._operation_fingerprints)
            | self._in_flight_operations
            | set(self._operation_receipts)
        )

    @staticmethod
    def request_fingerprint(request: Mapping[str, Any]) -> str:
        """Return a deterministic SHA-256 for one validated consequential input."""

        encoded = json.dumps(
            request,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def new_action_id(self) -> str:
        """Allocate a deterministic context-local action identifier."""

        with self._task_lock:
            value = f"action-{self._next_action_index:06d}"
            self._next_action_index += 1
            return value

    def new_artifact_id(self) -> str:
        """Allocate a deterministic context-local artifact identifier."""

        with self._task_lock:
            value = f"artifact-{self._next_artifact_index:06d}"
            self._next_artifact_index += 1
            return value

    def complete_operation(
        self,
        claim: OperationClaim,
        receipt: ActionReceipt,
        *,
        result: Mapping[str, Any] | None = None,
    ) -> ActionReceipt:
        """Atomically bind a frozen receipt to its matching operation claim."""

        self._validate_receipt_claim(claim, receipt)
        with self._task_lock:
            existing = self._operation_receipts.get(claim.operation_key)
            if existing is not None:
                return existing
            self._ensure_active_claim_locked(claim)
            self._operation_receipts[claim.operation_key] = receipt
            if result is not None:
                self._operation_results[claim.operation_key] = deepcopy(dict(result))
            self._in_flight_operations.remove(claim.operation_key)
            self._advance_receipt_state(receipt)
            return receipt

    def operation_result(self, operation_key: str) -> dict[str, Any] | None:
        """Return a defensive copy of a cached operation result."""

        with self._task_lock:
            result = self._operation_results.get(operation_key)
            return deepcopy(result) if result is not None else None

    def operation_receipt(self, operation_key: str) -> ActionReceipt | None:
        """Return the frozen receipt for an operation key, when completed."""

        with self._task_lock:
            return self._operation_receipts.get(operation_key)

    def record_local_receipt(self, receipt: ActionReceipt) -> ActionReceipt:
        """Atomically record or replay one local UI mutation receipt."""

        if receipt.task_id != self._task_id:
            raise OperationKeyConflictError("receipt task_id does not match context")
        if receipt.side_effect != "local_ui_mutation":
            raise OperationKeyConflictError(
                "local receipt side_effect must be local_ui_mutation"
            )

        key = receipt.operation_key
        fingerprint = receipt.request_fingerprint
        with self._task_lock:
            existing_fingerprint = self._operation_fingerprints.get(key)
            if existing_fingerprint is not None and existing_fingerprint != fingerprint:
                raise OperationKeyConflictError(
                    "operation_key is already bound to a different request"
                )
            existing = self._operation_receipts.get(key)
            if existing is not None:
                if existing.request_fingerprint != fingerprint:
                    raise OperationKeyConflictError(
                        "operation_key is already bound to a different request"
                    )
                return existing
            if key in self._in_flight_operations:
                raise OperationInFlightError(
                    "operation_key is already executing in this live task"
                )
            self._ensure_operation_capacity_locked(key)
            self._operation_fingerprints[key] = fingerprint
            self._operation_receipts[key] = receipt
            self._advance_receipt_state(receipt)
            return receipt

    def record_artifact(self, artifact: ArtifactRef) -> ArtifactRef:
        """Record one complete artifact without evicting prior task evidence."""

        if artifact.task_id != self._task_id:
            raise OperationKeyConflictError("artifact task_id does not match context")
        with self._task_lock:
            existing = self._artifacts.get(artifact.artifact_id)
            if existing is not None:
                if existing != artifact:
                    raise OperationKeyConflictError(
                        "artifact_id is already bound to different metadata"
                    )
                return existing
            self._ensure_artifact_capacity_locked(artifact.artifact_id)
            self._artifact_reservations.discard(artifact.artifact_id)
            self._artifacts[artifact.artifact_id] = artifact
            return artifact

    def complete_artifact_operation(
        self,
        claim: OperationClaim,
        receipt: ActionReceipt,
        artifact: ArtifactRef,
        *,
        result: Mapping[str, Any],
    ) -> ActionReceipt:
        """Atomically commit one completed artifact with its operation receipt."""

        self._validate_receipt_claim(claim, receipt)
        if artifact.task_id != self._task_id:
            raise OperationKeyConflictError("artifact operation task_id mismatch")
        if artifact.producing_action_id != receipt.action_id:
            raise OperationKeyConflictError(
                "artifact producing_action_id does not match receipt action_id"
            )
        if artifact.artifact_id not in receipt.artifact_ids:
            raise OperationKeyConflictError(
                "receipt does not reference the completed artifact"
            )

        with self._task_lock:
            existing_receipt = self._operation_receipts.get(claim.operation_key)
            if existing_receipt is not None:
                return existing_receipt
            self._ensure_active_claim_locked(claim)
            existing_artifact = self._artifacts.get(artifact.artifact_id)
            if existing_artifact is not None and existing_artifact != artifact:
                raise OperationKeyConflictError(
                    "artifact_id is already bound to different metadata"
                )
            self._ensure_artifact_capacity_locked(artifact.artifact_id)
            self._artifacts[artifact.artifact_id] = artifact
            self._artifact_reservations.discard(artifact.artifact_id)
            self._operation_receipts[claim.operation_key] = receipt
            self._operation_results[claim.operation_key] = deepcopy(dict(result))
            self._in_flight_operations.remove(claim.operation_key)
            self._advance_receipt_state(receipt)
            return receipt

    def _validate_receipt_claim(
        self, claim: OperationClaim, receipt: ActionReceipt
    ) -> None:
        if receipt.operation_key != claim.operation_key:
            raise OperationKeyConflictError(
                "receipt operation_key does not match the operation claim"
            )
        if receipt.request_fingerprint != claim.request_fingerprint:
            raise OperationKeyConflictError(
                "receipt request_fingerprint does not match the operation claim"
            )
        if receipt.task_id != self._task_id:
            raise OperationKeyConflictError("receipt task_id does not match context")

    def _ensure_active_claim_locked(self, claim: OperationClaim) -> None:
        if claim.operation_key not in self._in_flight_operations:
            raise OperationKeyConflictError("operation claim is not active")

    def _advance_receipt_state(self, receipt: ActionReceipt) -> None:
        self._action_count += 1
        if receipt.retry_of is not None:
            self._retry_count += 1
        self._last_action_id = receipt.action_id
        if receipt.status == "success":
            self._last_verified_action_id = receipt.action_id

    def reserve_artifact_slot(self, artifact_id: str) -> None:
        """Reserve one named artifact slot before a browser download starts."""

        with self._task_lock:
            if (
                artifact_id in self._artifacts
                or artifact_id in self._artifact_reservations
            ):
                raise OperationKeyConflictError(
                    "artifact_id is already reserved in this live task"
                )
            self._ensure_artifact_capacity_locked(artifact_id)
            self._artifact_reservations.add(artifact_id)

    def release_artifact_slot(self, artifact_id: str) -> None:
        """Release a named artifact slot after a failed download."""

        with self._task_lock:
            self._artifact_reservations.discard(artifact_id)

    def _ensure_artifact_capacity_locked(self, artifact_id: str) -> None:
        if artifact_id in self._artifacts or artifact_id in self._artifact_reservations:
            return
        if (
            len(self._artifacts) + len(self._artifact_reservations)
            >= self._artifact_limit
        ):
            raise TaskLedgerFullError(
                "artifact ledger limit reached; start a new server task"
            )

    def runtime_summary(
        self,
        *,
        active_tab_ids: Sequence[str] = (),
        current_tab_id: str = "",
    ) -> TaskContext:
        """Return an immutable public summary without browser ownership."""

        policy = _task_policy_snapshot()
        with self._task_lock:
            return TaskContext(
                task_id=self._task_id,
                created_at=self._task_created_at,
                policy_profile=policy["profile"],
                policy_controls=tuple(
                    PolicyControl(name=name, enabled=enabled)
                    for name, enabled in sorted(policy["controls"].items())
                ),
                active_tab_ids=tuple(active_tab_ids),
                current_tab_id=current_tab_id,
                action_count=self._action_count,
                retry_count=self._retry_count,
                operation_count=self._operation_count_locked(),
                receipt_count=len(self._operation_receipts),
                artifact_count=len(self._artifacts),
                operation_limit=self._operation_limit,
                artifact_limit=self._artifact_limit,
                retry_limit=self._retry_limit,
                last_action_id=self._last_action_id,
                last_verified_action_id=self._last_verified_action_id,
            )

    def receipt_inventory(self) -> list[ActionReceipt]:
        """Return receipts in stable insertion order for resource serialization."""

        with self._task_lock:
            return list(self._operation_receipts.values())

    def artifact_inventory(self) -> list[ArtifactRef]:
        """Return artifacts in stable insertion order for resource serialization."""

        with self._task_lock:
            return list(self._artifacts.values())

    def capability_set(self) -> CapabilitySet:
        """Return the latest explicit capability snapshot without probing."""

        with self._task_lock:
            return self._capability_set

    def set_capability_set(self, capability_set: CapabilitySet) -> None:
        """Store explicit probe evidence produced by a capability adapter."""

        with self._task_lock:
            self._capability_set = capability_set

    def record_capability_probe(self, probe: CapabilityProbe) -> CapabilitySet:
        """Replace one named probe while preserving other runtime evidence."""

        with self._task_lock:
            probes = [
                item
                for item in self._capability_set.capabilities
                if item.name != probe.name
            ]
            probes.append(probe)
            statuses = {item.status for item in probes if item.status != "unprobed"}
            if not statuses:
                overall_status = "unprobed"
            elif statuses == {"supported"}:
                overall_status = "supported"
            elif statuses == {"unsupported"}:
                overall_status = "unsupported"
            else:
                overall_status = "degraded"
            self._capability_set = self._capability_set.model_copy(
                update={
                    "overall_status": overall_status,
                    "capabilities": tuple(probes[-24:]),
                }
            )
            return self._capability_set

    @property
    def task_id(self) -> str:
        return self._task_id


def _operation_identity(
    operation_key: str, request_fingerprint: str
) -> tuple[str, str]:
    key = str(operation_key).strip()
    fingerprint = str(request_fingerprint).strip().lower()
    if not key:
        raise ValueError("operation_key is required")
    if len(key) > 128:
        raise ValueError("operation_key must be at most 128 characters")
    if len(fingerprint) != 64 or any(
        char not in "0123456789abcdef" for char in fingerprint
    ):
        raise ValueError("request_fingerprint must be a lowercase SHA-256")
    return key, fingerprint


def _redact_history_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        redacted = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if key_text in SENSITIVE_HISTORY_KEYS or any(
                marker in key_text
                for marker in (
                    "password",
                    "secret",
                    "token",
                    "cookie",
                    "api_key",
                    "authorization",
                    "body",
                    "header",
                    "field",
                    "value",
                )
            ):
                redacted[key] = "<redacted>"
            elif key_text == "url" or key_text.endswith("_url"):
                redacted[key] = _redact_history_url(item)
            else:
                redacted[key] = _redact_history_value(item)
        return redacted
    if isinstance(value, list):
        return [_redact_history_value(item) for item in value]
    if isinstance(value, tuple):
        return [_redact_history_value(item) for item in value]
    return value


def _summarize_result(result: Mapping[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": bool(result.get("ok"))}
    if result.get("message"):
        payload["message"] = str(result["message"])[:300]
    error = result.get("error")
    if isinstance(error, Mapping):
        payload["error_code"] = error.get("code")
    data = result.get("data")
    if isinstance(data, Mapping):
        for key in ("url", "final_url", "tab_id", "active_tab_id"):
            if key in data:
                payload[key] = (
                    _redact_history_url(data[key])
                    if key in {"url", "final_url"}
                    else data[key]
                )
        changes = data.get("changes")
        if isinstance(changes, Mapping):
            payload["changes"] = {
                "url_changed": bool(changes.get("url_changed")),
                "title_changed": bool(changes.get("title_changed")),
                "appeared_texts": list(changes.get("appeared_texts") or [])[:3],
                "removed_texts": list(changes.get("removed_texts") or [])[:3],
                "console_errors_added": safe_int(
                    changes.get("console_errors_added"), 0
                ),
                "console_warnings_added": safe_int(
                    changes.get("console_warnings_added"), 0
                ),
                "new_console_messages": [
                    _summarize_console_message(item)
                    for item in list(changes.get("new_console_messages") or [])[:3]
                    if isinstance(item, Mapping)
                ],
            }
    return payload


def _summarize_console_message(message: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "level": str(message.get("level") or ""),
        "text": str(message.get("text") or "")[:200],
    }


def _redact_history_url(value: Any) -> str:
    return sanitize_public_url(value)


def _task_policy_snapshot() -> dict[str, Any]:
    from .policy import SafetyPolicy

    policy = SafetyPolicy.from_env()
    controls = policy.control_flags()
    return {
        "profile": policy.profile(),
        "controls": {str(key): bool(value) for key, value in controls.items()},
    }


__all__ = [
    "DEFAULT_ARTIFACT_LIMIT",
    "DEFAULT_OPERATION_LIMIT",
    "DEFAULT_RETRY_LIMIT",
    "OperationClaim",
    "OperationInFlightError",
    "OperationKeyConflictError",
    "TaskLedgerFullError",
    "TaskRuntime",
]
