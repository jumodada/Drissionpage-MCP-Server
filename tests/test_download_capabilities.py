"""Contracts for one-click downloads and safe artifact delivery."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import threading
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from drissionpage_mcp.browser.downloads import (
    DownloadFailedError,
    DownloadIndeterminateError,
    DownloadOperations,
    DownloadUnsupportedError,
    DownloadValidationError,
)
from drissionpage_mcp.context import DrissionPageContext
from drissionpage_mcp.tool_outputs import ArtifactRef, CapabilityProbe, CapabilitySet
from drissionpage_mcp.tools.downloads import (
    ElementClickAndDownloadInput,
    element_click_and_download,
)

DOWNLOAD_BYTES = b"employee_id,name,department\n0701,Ada Lovelace,Research\n"
DOWNLOAD_SHA256 = hashlib.sha256(DOWNLOAD_BYTES).hexdigest()


def test_click_and_download_input_is_strict_bounded_and_path_safe() -> None:
    value = ElementClickAndDownloadInput(
        selector="#download",
        operation_key="download-report-1",
        expected_filename="report.csv",
        expected_mime_type="text/csv",
    )

    assert value.timeout == 30
    structured = ElementClickAndDownloadInput(
        selector={
            "kind": "accessibility",
            "role": "button",
            "name": "Download",
            "frame_selectors": ["#report-frame"],
        }
    )
    assert structured.selector.kind == "accessibility"
    coordinate = ElementClickAndDownloadInput(
        selector={
            "kind": "coordinate",
            "x": 125.5,
            "y": 80,
            "profile": "natural",
            "delay_before_press_ms": 25,
        }
    )
    assert coordinate.selector.kind == "coordinate"
    keyboard = ElementClickAndDownloadInput(
        selector={"kind": "keyboard", "keys": "\ue007", "interval": 0.1}
    )
    assert keyboard.selector.kind == "keyboard"
    with pytest.raises(ValidationError):
        ElementClickAndDownloadInput(selector="")
    with pytest.raises(ValidationError):
        ElementClickAndDownloadInput(selector="x" * 501)
    with pytest.raises(ValidationError):
        ElementClickAndDownloadInput(selector="#download", operation_key=" ")
    with pytest.raises(ValidationError):
        ElementClickAndDownloadInput(selector="#download", operation_key="x" * 129)
    for filename in ("../report.csv", "reports/report.csv", "..", "."):
        with pytest.raises(ValidationError):
            ElementClickAndDownloadInput(
                selector="#download", expected_filename=filename
            )
    for timeout in (0, 121):
        with pytest.raises(ValidationError):
            ElementClickAndDownloadInput(selector="#download", timeout=timeout)
    for trigger in (
        {"kind": "coordinate", "x": -1, "y": 0},
        {"kind": "coordinate", "x": 0, "y": 100001},
        {"kind": "coordinate", "x": 0, "y": 0, "profile": "curved"},
        {"kind": "coordinate", "x": 0, "y": 0, "delay_before_press_ms": 10001},
        {"kind": "keyboard", "keys": ""},
        {"kind": "keyboard", "keys": "x" * 257},
        {"kind": "keyboard", "keys": "x", "interval": -0.1},
        {"kind": "keyboard", "keys": "x", "interval": 2.1},
        {"kind": "keyboard", "keys": "x", "unexpected": True},
    ):
        with pytest.raises(ValidationError):
            ElementClickAndDownloadInput(selector=trigger)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        ElementClickAndDownloadInput(  # type: ignore[call-arg]
            selector="#download", unexpected=True
        )


class _FakeDownloads:
    def __init__(
        self,
        *,
        content: bytes = DOWNLOAD_BYTES,
        filename: str = "fixture-report.csv",
        mime_type: str = "text/csv",
        source_url: str = "https://user:pass@example.test/report.csv?token=secret#part",
        fail: Exception | None = None,
        barrier: asyncio.Event | None = None,
        started: list[str] | None = None,
    ) -> None:
        self.content = content
        self.filename = filename
        self.mime_type = mime_type
        self.source_url = source_url
        self.fail = fail
        self.barrier = barrier
        self.started = started
        self.probed: list[object] = []
        self.clicked: list[object] = []
        self.generic_triggers = 0
        self.cleanup_dirs: list[Path] = []

    def probe(self, element: object) -> None:
        self.probed.append(element)

    def probe_trigger(self) -> None:
        self.probed.append("trigger")

    async def click_and_wait(
        self,
        element: object,
        *,
        download_dir: Path,
        timeout: float,
    ) -> dict[str, object]:
        self.clicked.append(element)
        if self.started is not None:
            self.started.append(download_dir.name)
        if self.barrier is not None:
            await self.barrier.wait()
        path = download_dir / self.filename
        path.write_bytes(self.content)
        if self.fail is not None:
            raise self.fail
        return {
            "path": path.resolve(),
            "filename": self.filename,
            "mime_type": self.mime_type,
            "size_bytes": len(self.content),
            "sha256": hashlib.sha256(self.content).hexdigest(),
            "source_url": self.source_url,
        }

    async def trigger_and_wait(
        self,
        trigger: Callable[[], Awaitable[object]],
        *,
        download_dir: Path,
        timeout: float,
    ) -> dict[str, object]:
        self.generic_triggers += 1
        await trigger()
        if self.started is not None:
            self.started.append(download_dir.name)
        if self.barrier is not None:
            await self.barrier.wait()
        path = download_dir / self.filename
        path.write_bytes(self.content)
        if self.fail is not None:
            raise self.fail
        return {
            "path": path.resolve(),
            "filename": self.filename,
            "mime_type": self.mime_type,
            "size_bytes": len(self.content),
            "sha256": hashlib.sha256(self.content).hexdigest(),
            "source_url": self.source_url,
        }

    async def cleanup(self, download_dir: Path) -> None:
        self.cleanup_dirs.append(download_dir)
        shutil.rmtree(download_dir, ignore_errors=True)


class _FakePointer:
    def __init__(self) -> None:
        self.clicks: list[dict[str, object]] = []

    async def click_at(
        self,
        x: float,
        y: float,
        *,
        profile: str,
        button: str,
        delay_before_press_ms: int,
    ) -> object:
        self.clicks.append(
            {
                "x": x,
                "y": y,
                "profile": profile,
                "button": button,
                "delay_before_press_ms": delay_before_press_ms,
            }
        )
        return object()


class _FakeInteraction:
    def __init__(self) -> None:
        self.key_presses: list[dict[str, object]] = []

    async def keyboard_press(self, keys: str, *, interval: float) -> object:
        self.key_presses.append({"keys": keys, "interval": interval})
        return object()


class _FakeTab:
    def __init__(self, downloads: _FakeDownloads, *, element: object | None = None):
        self.url = "https://example.test/download?private=secret"
        self.mcp_tab_id = "t0"
        self.downloads = downloads
        self.pointer = _FakePointer()
        self.interaction = _FakeInteraction()
        self.element = element if element is not None else object()
        self.element_lookups = 0

    async def _element_by_plan(self, plan: object, *, timeout: int) -> object:
        self.element_lookups += 1
        return self.element


def _context_with_downloads(
    downloads: _FakeDownloads,
) -> tuple[DrissionPageContext, _FakeTab]:
    context = DrissionPageContext()
    tab = _FakeTab(downloads)
    context._current_tab = tab  # type: ignore[assignment]
    return context, tab


def _artifact(context: DrissionPageContext, artifact_id: str) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=artifact_id,
        task_id=context.task_id,
        producing_action_id="action-000000",
        kind="download",
        filename="existing.csv",
        mime_type="text/csv",
        size_bytes=1,
        sha256="a" * 64,
        safe_relative_path=f"{context.task_id}/action-000000/existing.csv",
        source_url="https://example.test/existing.csv",
        created_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("trigger_kind", ["coordinate", "keyboard"])
async def test_coordinate_and_keyboard_downloads_trigger_once_and_replay_redacted(
    monkeypatch, tmp_path: Path, trigger_kind: str
) -> None:
    root = tmp_path / "downloads"
    monkeypatch.setenv("DP_MCP_DOWNLOAD_ROOT", str(root))
    downloads = _FakeDownloads()
    context, tab = _context_with_downloads(downloads)
    secret_keys = "secret-enter-\ue007"
    trigger: dict[str, object]
    if trigger_kind == "coordinate":
        trigger = {
            "kind": "coordinate",
            "x": 125.5,
            "y": 80,
            "profile": "natural",
            "delay_before_press_ms": 25,
        }
    else:
        trigger = {"kind": "keyboard", "keys": secret_keys, "interval": 0.1}
    args = ElementClickAndDownloadInput(
        selector=trigger,  # type: ignore[arg-type]
        operation_key=f"{trigger_kind}-download",
        timeout=2,
    )

    outcome = await element_click_and_download.execute(context, args)

    assert outcome.is_error is False
    data = outcome.structured_content()["data"]
    assert data["status"] == "success"
    assert "selector" not in data
    assert "locator" not in data
    assert data["trigger"]["kind"] == trigger_kind
    assert downloads.probed == ["trigger"]
    assert downloads.generic_triggers == 1
    if trigger_kind == "coordinate":
        assert tab.pointer.clicks == [
            {
                "x": 125.5,
                "y": 80.0,
                "profile": "natural",
                "button": "left",
                "delay_before_press_ms": 25,
            }
        ]
        changed = {**trigger, "x": 126}
    else:
        assert tab.interaction.key_presses == [
            {"keys": secret_keys, "interval": 0.1}
        ]
        assert data["trigger"]["keys"] == {
            "provided": True,
            "length": len(secret_keys),
            "redacted": True,
        }
        assert secret_keys not in json.dumps(data, ensure_ascii=False)
        changed = {**trigger, "keys": "different-secret"}

    replay = await element_click_and_download.execute(context, args)
    assert replay.is_error is False
    assert replay.structured_content()["data"] == data
    assert downloads.generic_triggers == 1

    conflict = await element_click_and_download.execute(
        context,
        ElementClickAndDownloadInput(
            selector=changed,  # type: ignore[arg-type]
            operation_key=args.operation_key,
            timeout=args.timeout,
        ),
    )
    assert conflict.is_error is True
    assert conflict.structured_content()["error"]["code"] == "OPERATION_KEY_CONFLICT"
    assert downloads.generic_triggers == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("trigger_kind", ["coordinate", "keyboard"])
@pytest.mark.parametrize(
    "failure",
    [
        DownloadFailedError("browser canceled"),
        DownloadIndeterminateError("mission timed out"),
    ],
    ids=["terminal-failure", "timeout"],
)
async def test_coordinate_and_keyboard_download_failures_clean_and_do_not_retrigger(
    monkeypatch,
    tmp_path: Path,
    trigger_kind: str,
    failure: Exception,
) -> None:
    root = tmp_path / "downloads"
    monkeypatch.setenv("DP_MCP_DOWNLOAD_ROOT", str(root))
    downloads = _FakeDownloads(fail=failure)
    context, _tab = _context_with_downloads(downloads)
    trigger = (
        {"kind": "coordinate", "x": 10, "y": 20}
        if trigger_kind == "coordinate"
        else {"kind": "keyboard", "keys": "\ue007"}
    )
    args = ElementClickAndDownloadInput(
        selector=trigger,  # type: ignore[arg-type]
        operation_key=f"{trigger_kind}-failure",
        timeout=1,
    )

    first = await element_click_and_download.execute(context, args)
    replay = await element_click_and_download.execute(context, args)

    assert first.is_error is True
    assert replay.is_error is True
    assert replay.structured_content()["data"] == first.structured_content()["data"]
    assert downloads.generic_triggers == 1
    assert not [path for path in root.rglob("*") if path.is_file()]
    assert list(context._artifacts.values()) == []


def test_artifact_reservations_are_bound_to_their_artifact_ids() -> None:
    context = DrissionPageContext(artifact_limit=2)
    context.reserve_artifact_slot("artifact-000001")
    context.reserve_artifact_slot("artifact-000002")

    second = _artifact(context, "artifact-000002")
    context.record_artifact(second)
    # Completing B must leave A reserved rather than consuming an arbitrary slot.
    with pytest.raises(Exception, match="artifact ledger limit"):
        context.reserve_artifact_slot("artifact-000003")
    context.release_artifact_slot("artifact-000001")
    context.reserve_artifact_slot("artifact-000003")

    assert list(context._artifacts.values()) == [second]
    with pytest.raises(Exception, match="artifact ledger limit"):
        context.reserve_artifact_slot("artifact-000004")


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["missing", "file", "deny", "symlink"])
async def test_download_policy_denies_before_claim_tab_or_click(
    monkeypatch, tmp_path: Path, mode: str
) -> None:
    monkeypatch.delenv("DP_MCP_DOWNLOAD_ROOT", raising=False)
    monkeypatch.delenv("DP_MCP_DENY_DOWNLOAD", raising=False)
    if mode == "file":
        invalid = tmp_path / "not-a-directory"
        invalid.write_text("not a root", encoding="utf-8")
        monkeypatch.setenv("DP_MCP_DOWNLOAD_ROOT", str(invalid))
    elif mode == "deny":
        monkeypatch.setenv("DP_MCP_DOWNLOAD_ROOT", str(tmp_path / "downloads"))
        monkeypatch.setenv("DP_MCP_DENY_DOWNLOAD", "1")
    elif mode == "symlink":
        target = tmp_path / "real-root"
        target.mkdir()
        link = tmp_path / "linked-root"
        link.symlink_to(target, target_is_directory=True)
        monkeypatch.setenv("DP_MCP_DOWNLOAD_ROOT", str(link))

    context = DrissionPageContext()
    outcome = await element_click_and_download.execute(
        context,
        ElementClickAndDownloadInput(
            selector="#download", operation_key=f"policy-{mode}", timeout=1
        ),
    )

    assert outcome.is_error is True
    assert outcome.structured_content()["error"]["code"] == "POLICY_DENIED"
    assert len(context._operation_fingerprints) == 0
    assert len(context._operation_receipts) == 0
    assert list(context._artifacts.values()) == []


@pytest.mark.asyncio
async def test_task_directory_symlink_denies_before_claim_or_click(
    monkeypatch, tmp_path: Path
) -> None:
    root = tmp_path / "downloads"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    monkeypatch.setenv("DP_MCP_DOWNLOAD_ROOT", str(root))
    context, tab = _context_with_downloads(_FakeDownloads())
    (root / context.task_id).symlink_to(outside, target_is_directory=True)

    outcome = await element_click_and_download.execute(
        context,
        ElementClickAndDownloadInput(
            selector="#download", operation_key="task-symlink", timeout=1
        ),
    )

    assert outcome.is_error is True
    assert outcome.structured_content()["error"]["code"] == "POLICY_DENIED"
    assert tab.downloads.clicked == []
    assert len(context._operation_fingerprints) == 0
    assert len(context._operation_receipts) == 0
    assert list(context._artifacts.values()) == []


@pytest.mark.asyncio
async def test_recorded_unsupported_download_denies_before_tab_or_click(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DP_MCP_DOWNLOAD_ROOT", str(tmp_path / "downloads"))
    context = DrissionPageContext()
    context.set_capability_set(
        CapabilitySet(
            overall_status="unsupported",
            capabilities=(
                CapabilityProbe(
                    name="download.click_and_wait",
                    status="unsupported",
                    evidence_source="runtime_probe",
                    reason_code="DOWNLOAD_MANAGER_UNAVAILABLE",
                    checked_at=datetime.now(timezone.utc),
                ),
            ),
        )
    )

    outcome = await element_click_and_download.execute(
        context,
        ElementClickAndDownloadInput(
            selector="#download", operation_key="unsupported-download", timeout=1
        ),
    )

    assert outcome.is_error is True
    assert outcome.structured_content()["error"]["code"] == "UNSUPPORTED_OPERATION"
    assert len(context._operation_fingerprints) == 0
    assert len(context._operation_receipts) == 0


@pytest.mark.asyncio
async def test_recorded_selector_download_failure_does_not_block_generic_trigger(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DP_MCP_DOWNLOAD_ROOT", str(tmp_path / "downloads"))
    downloads = _FakeDownloads()
    context, _tab = _context_with_downloads(downloads)
    context.set_capability_set(
        CapabilitySet(
            overall_status="unsupported",
            capabilities=(
                CapabilityProbe(
                    name="download.click_and_wait",
                    status="unsupported",
                    evidence_source="runtime_probe",
                    reason_code="CLICK_TO_DOWNLOAD_API_UNAVAILABLE",
                    checked_at=datetime.now(timezone.utc),
                ),
            ),
        )
    )

    outcome = await element_click_and_download.execute(
        context,
        ElementClickAndDownloadInput(
            selector={"kind": "coordinate", "x": 10, "y": 20},
            operation_key="generic-after-selector-probe",
            timeout=1,
        ),
    )

    assert outcome.is_error is False
    assert downloads.probed == ["trigger"]
    assert downloads.generic_triggers == 1
    probes = {probe.name: probe for probe in context.capability_set().capabilities}
    assert probes["download.click_and_wait"].status == "unsupported"
    assert probes["download.trigger_and_wait"].status == "supported"


@pytest.mark.asyncio
async def test_artifact_ledger_full_denies_before_claim_click_or_receipt(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DP_MCP_DOWNLOAD_ROOT", str(tmp_path / "downloads"))
    downloads = _FakeDownloads()
    context = DrissionPageContext(artifact_limit=1)
    context.record_artifact(_artifact(context, "artifact-000000"))
    tab = _FakeTab(downloads)
    context._current_tab = tab  # type: ignore[assignment]

    outcome = await element_click_and_download.execute(
        context,
        ElementClickAndDownloadInput(
            selector="#download", operation_key="ledger-full", timeout=1
        ),
    )

    assert outcome.is_error is True
    assert outcome.structured_content()["error"]["code"] == "TASK_LEDGER_FULL"
    assert downloads.clicked == []
    assert len(context._operation_fingerprints) == 0
    assert len(context._operation_receipts) == 0
    assert len(list(context._artifacts.values())) == 1


@pytest.mark.asyncio
async def test_download_success_uses_preflight_element_and_returns_safe_artifact(
    monkeypatch, tmp_path: Path
) -> None:
    root = tmp_path / "approved-downloads"
    monkeypatch.setenv("DP_MCP_DOWNLOAD_ROOT", str(root))
    downloads = _FakeDownloads()
    context, tab = _context_with_downloads(downloads)
    args = ElementClickAndDownloadInput(
        selector="#download",
        operation_key="download-success",
        timeout=2,
        expected_filename="fixture-report.csv",
        expected_mime_type="text/csv",
    )

    outcome = await element_click_and_download.execute(context, args)

    assert outcome.is_error is False
    data = outcome.structured_content()["data"]
    assert data["status"] == "success"
    assert data["operation_key"] == "download-success"
    assert data["target_kind"] == "selector"
    assert data["frame_selectors"] == []
    assert data["shadow_hosts"] == []
    assert data["role"] is None
    assert data["name"] is None
    assert data["exact"] is None
    assert "trigger" not in data
    artifact = data["artifact"]
    assert artifact["filename"] == "fixture-report.csv"
    assert artifact["mime_type"] == "text/csv"
    assert artifact["size_bytes"] == len(DOWNLOAD_BYTES)
    assert artifact["sha256"] == DOWNLOAD_SHA256
    assert artifact["status"] == "complete"
    assert artifact["source_url"] == "https://example.test/report.csv"
    assert not Path(artifact["safe_relative_path"]).is_absolute()
    assert ".." not in Path(artifact["safe_relative_path"]).parts
    assert str(root) not in json.dumps(data, ensure_ascii=False)
    stored = root / artifact["safe_relative_path"]
    assert stored.read_bytes() == DOWNLOAD_BYTES
    receipt = data["receipt"]
    assert receipt["kind"] == "element_click_and_download"
    assert receipt["side_effect"] == "external_download"
    assert receipt["status"] == "success"
    assert receipt["artifact_ids"] == [artifact["artifact_id"]]
    assert artifact["producing_action_id"] == receipt["action_id"]
    assert list(context._artifacts.values())[0].model_dump(mode="json") == artifact
    assert downloads.probed == [tab.element]
    assert downloads.clicked == [tab.element]
    assert tab.element_lookups == 1

    monkeypatch.delenv("DP_MCP_DOWNLOAD_ROOT")
    monkeypatch.setenv("DP_MCP_DENY_DOWNLOAD", "1")
    context._current_tab = None
    replay = await element_click_and_download.execute(context, args)
    assert replay.is_error is False
    assert replay.structured_content()["data"] == data
    assert downloads.clicked == [tab.element]

    conflict = await element_click_and_download.execute(
        context,
        args.model_copy(update={"expected_filename": "other.csv"}),
    )
    assert conflict.is_error is True
    assert conflict.structured_content()["error"]["code"] == ("OPERATION_KEY_CONFLICT")
    assert downloads.clicked == [tab.element]


@pytest.mark.asyncio
async def test_capability_bookkeeping_failure_cannot_leave_dangling_artifact(
    monkeypatch, tmp_path: Path
) -> None:
    root = tmp_path / "downloads"
    monkeypatch.setenv("DP_MCP_DOWNLOAD_ROOT", str(root))
    downloads = _FakeDownloads()
    context, _tab = _context_with_downloads(downloads)

    def fail_capability(_probe: CapabilityProbe) -> CapabilitySet:
        raise RuntimeError("capability bookkeeping failed")

    context.record_capability_probe = fail_capability  # type: ignore[method-assign]
    outcome = await element_click_and_download.execute(
        context,
        ElementClickAndDownloadInput(
            selector="#download", operation_key="capability-after-commit", timeout=1
        ),
    )

    inventory = list(context._artifacts.values())
    if inventory:
        assert outcome.is_error is False
        artifact_path = root / inventory[0].safe_relative_path
        assert artifact_path.read_bytes() == DOWNLOAD_BYTES
        receipt = list(context._operation_receipts.values())[0]
        assert receipt.status == "success"
        assert receipt.artifact_ids == (inventory[0].artifact_id,)
    else:
        assert outcome.is_error is True
        assert list(context._operation_receipts.values())[0].status != "success"
        assert not [path for path in root.rglob("*") if path.is_file()]


@pytest.mark.asyncio
async def test_concurrent_same_key_clicks_once_and_reports_in_flight(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DP_MCP_DOWNLOAD_ROOT", str(tmp_path / "downloads"))
    barrier = asyncio.Event()
    downloads = _FakeDownloads(barrier=barrier)
    context, tab = _context_with_downloads(downloads)
    args = ElementClickAndDownloadInput(
        selector="#download", operation_key="download-in-flight", timeout=2
    )

    first_task = asyncio.create_task(element_click_and_download.execute(context, args))
    while not downloads.clicked:
        await asyncio.sleep(0)
    duplicate = await element_click_and_download.execute(context, args)
    barrier.set()
    first = await first_task

    assert first.is_error is False
    assert duplicate.is_error is True
    assert duplicate.structured_content()["error"]["code"] == "OPERATION_IN_FLIGHT"
    assert downloads.clicked == [tab.element]
    assert len(context._operation_receipts) == 1
    assert len(list(context._artifacts.values())) == 1


@pytest.mark.asyncio
async def test_two_concurrent_downloads_keep_distinct_artifact_reservations(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DP_MCP_DOWNLOAD_ROOT", str(tmp_path / "downloads"))
    barrier = asyncio.Event()
    started: list[str] = []
    downloads = _FakeDownloads(barrier=barrier, started=started)
    context, _tab = _context_with_downloads(downloads)
    first = asyncio.create_task(
        element_click_and_download.execute(
            context,
            ElementClickAndDownloadInput(
                selector="#download", operation_key="concurrent-1", timeout=2
            ),
        )
    )
    second = asyncio.create_task(
        element_click_and_download.execute(
            context,
            ElementClickAndDownloadInput(
                selector="#download", operation_key="concurrent-2", timeout=2
            ),
        )
    )
    while len(started) < 2:
        await asyncio.sleep(0)
    barrier.set()
    outcomes = await asyncio.gather(first, second)

    assert all(outcome.is_error is False for outcome in outcomes)
    artifacts = list(context._artifacts.values())
    assert len(artifacts) == 2
    assert len({artifact.artifact_id for artifact in artifacts}) == 2
    assert len({artifact.producing_action_id for artifact in artifacts}) == 2
    assert len({artifact.safe_relative_path for artifact in artifacts}) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "expected_status"),
    [
        (DownloadIndeterminateError("partial secret"), "indeterminate"),
    ],
)
async def test_failed_download_has_no_artifact_cleans_partial_and_replays_failure(
    monkeypatch, tmp_path: Path, failure: Exception, expected_status: str
) -> None:
    root = tmp_path / "downloads"
    monkeypatch.setenv("DP_MCP_DOWNLOAD_ROOT", str(root))
    downloads = _FakeDownloads(fail=failure)
    context, _tab = _context_with_downloads(downloads)
    args = ElementClickAndDownloadInput(
        selector="#download", operation_key="failed-download", timeout=1
    )

    first = await element_click_and_download.execute(context, args)

    assert first.is_error is True
    assert first.structured_content()["error"]["code"] != "SUCCESS"
    assert list(context._artifacts.values()) == []
    receipt = list(context._operation_receipts.values())[0]
    assert receipt.status == expected_status
    assert receipt.artifact_ids == ()
    assert not [path for path in root.rglob("*") if path.is_file()]

    monkeypatch.delenv("DP_MCP_DOWNLOAD_ROOT")
    monkeypatch.setenv("DP_MCP_DENY_DOWNLOAD", "1")
    context._current_tab = None
    replay = await element_click_and_download.execute(context, args)
    assert replay.is_error is True
    assert replay.structured_content() == first.structured_content()
    assert len(downloads.clicked) == 1
    assert list(context._artifacts.values()) == []


@pytest.mark.asyncio
async def test_cancellation_drains_native_work_freezes_failure_and_replays(
    monkeypatch, tmp_path: Path
) -> None:
    root = tmp_path / "downloads"
    monkeypatch.setenv("DP_MCP_DOWNLOAD_ROOT", str(root))
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    click_calls = 0
    manager = SimpleNamespace(missions={})

    class Mission:
        state = "completed"
        is_done = True
        url = "https://example.test/report.csv"

        def __init__(self, path: Path) -> None:
            self.final_path = str(path)
            self.name = path.name

    class Clicker:
        def to_download(self, *, save_path: str, timeout: float) -> Mission:
            nonlocal click_calls
            click_calls += 1
            started.set()
            release.wait(timeout=1)
            path = Path(save_path) / "cancelled.csv"
            path.write_bytes(DOWNLOAD_BYTES)
            finished.set()
            return Mission(path)

    element = SimpleNamespace(click=Clicker())

    class NativeTab:
        url = "https://example.test/download"
        mcp_tab_id = "t0"

        def __init__(self) -> None:
            self.page = SimpleNamespace(browser=SimpleNamespace(_dl_mgr=manager))
            self.downloads = DownloadOperations(self)  # type: ignore[arg-type]
            self.element_lookups = 0

        async def _element_by_plan(self, plan: object, *, timeout: int) -> object:
            self.element_lookups += 1
            return element

    context = DrissionPageContext(artifact_limit=1)
    tab = NativeTab()
    context._current_tab = tab  # type: ignore[assignment]
    args = ElementClickAndDownloadInput(
        selector="#download", operation_key="cancelled-download", timeout=2
    )
    task = asyncio.create_task(element_click_and_download.execute(context, args))
    while not started.is_set():
        await asyncio.sleep(0)

    task.cancel()
    done, _pending = await asyncio.wait({task}, timeout=0.02)
    assert done == set()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert finished.is_set()
    assert click_calls == 1
    receipt = context.operation_receipt("cancelled-download")
    assert receipt is not None
    assert receipt.status == "indeterminate"
    assert receipt.error_code == "DOWNLOAD_INDETERMINATE"
    assert receipt.artifact_ids == ()
    frozen = context.operation_result("cancelled-download")
    assert frozen is not None
    assert frozen["status"] == "indeterminate"
    assert frozen["artifact"] is None
    assert frozen["receipt"] == receipt.model_dump(mode="json")
    assert len(context._operation_fingerprints) == 1
    assert len(context._operation_receipts) == 1
    assert list(context._artifacts.values()) == []
    assert not [path for path in root.rglob("*") if path.is_file()]
    context.reserve_artifact_slot("reservation-probe")
    context.release_artifact_slot("reservation-probe")

    monkeypatch.delenv("DP_MCP_DOWNLOAD_ROOT")
    monkeypatch.setenv("DP_MCP_DENY_DOWNLOAD", "1")
    context._current_tab = None
    replay = await element_click_and_download.execute(context, args)
    assert replay.is_error is True
    assert replay.structured_content()["data"] == frozen
    assert click_calls == 1
    assert tab.element_lookups == 1


@pytest.mark.asyncio
async def test_cancellation_during_failure_cleanup_still_freezes_indeterminate(
    monkeypatch, tmp_path: Path
) -> None:
    root = tmp_path / "downloads"
    monkeypatch.setenv("DP_MCP_DOWNLOAD_ROOT", str(root))
    cleanup_started = asyncio.Event()
    cleanup_release = asyncio.Event()

    class BlockingCleanupDownloads(_FakeDownloads):
        async def cleanup(self, download_dir: Path) -> None:
            cleanup_started.set()
            await cleanup_release.wait()
            await super().cleanup(download_dir)

    downloads = BlockingCleanupDownloads(
        fail=DownloadValidationError("invalid completed artifact")
    )
    context, tab = _context_with_downloads(downloads)
    args = ElementClickAndDownloadInput(
        selector="#download", operation_key="cancelled-cleanup", timeout=1
    )
    task = asyncio.create_task(element_click_and_download.execute(context, args))
    await cleanup_started.wait()

    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    done, _pending = await asyncio.wait({task}, timeout=0.02)
    assert done == set()
    cleanup_release.set()
    with pytest.raises(asyncio.CancelledError):
        await task

    receipt = context.operation_receipt("cancelled-cleanup")
    assert receipt is not None
    assert receipt.status == "indeterminate"
    assert receipt.error_code == "DOWNLOAD_INDETERMINATE"
    frozen = context.operation_result("cancelled-cleanup")
    assert frozen is not None
    assert frozen["status"] == "indeterminate"
    assert frozen["artifact"] is None
    assert list(context._artifacts.values()) == []
    assert not [path for path in root.rglob("*") if path.is_file()]

    monkeypatch.delenv("DP_MCP_DOWNLOAD_ROOT")
    monkeypatch.setenv("DP_MCP_DENY_DOWNLOAD", "1")
    context._current_tab = None
    replay = await element_click_and_download.execute(context, args)
    assert replay.is_error is True
    assert replay.structured_content()["data"] == frozen
    assert downloads.clicked == [tab.element]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "constraint",
    [
        {"expected_filename": "expected.csv"},
        {"expected_mime_type": "application/pdf"},
    ],
)
async def test_expected_artifact_mismatch_has_no_artifact_and_replays_failure(
    monkeypatch, tmp_path: Path, constraint: dict[str, str]
) -> None:
    root = tmp_path / "downloads"
    monkeypatch.setenv("DP_MCP_DOWNLOAD_ROOT", str(root))
    downloads = _FakeDownloads()
    context, _tab = _context_with_downloads(downloads)

    outcome = await element_click_and_download.execute(
        context,
        ElementClickAndDownloadInput(
            selector="#download",
            operation_key="artifact-mismatch",
            timeout=1,
            **constraint,
        ),
    )

    assert outcome.is_error is True
    assert outcome.structured_content()["error"]["code"] == "PRECONDITION_FAILED"
    assert list(context._artifacts.values()) == []
    receipt = list(context._operation_receipts.values())[0]
    assert receipt.status == "validation_failed"
    assert receipt.artifact_ids == ()
    assert not [path for path in root.rglob("*") if path.is_file()]

    args = ElementClickAndDownloadInput(
        selector="#download",
        operation_key="artifact-mismatch",
        timeout=1,
        **constraint,
    )
    monkeypatch.delenv("DP_MCP_DOWNLOAD_ROOT")
    monkeypatch.setenv("DP_MCP_DENY_DOWNLOAD", "1")
    context._current_tab = None
    replay = await element_click_and_download.execute(context, args)
    assert replay.is_error is True
    assert replay.structured_content() == outcome.structured_content()
    assert len(downloads.clicked) == 1


@pytest.mark.asyncio
async def test_same_tab_native_download_calls_are_serialized(tmp_path: Path) -> None:
    state_lock = threading.Lock()
    state = {"active": 0, "max_active": 0}
    manager = SimpleNamespace(missions={})

    class Mission:
        state = "completed"
        is_done = True
        url = "https://example.test/report.csv"

        def __init__(self, path: Path) -> None:
            self.final_path = str(path)
            self.name = path.name

    class Clicker:
        def __init__(self, filename: str) -> None:
            self.filename = filename

        def to_download(self, *, save_path: str, timeout: float) -> Mission:
            with state_lock:
                state["active"] += 1
                state["max_active"] = max(state["max_active"], state["active"])
            try:
                time.sleep(0.05)
                path = Path(save_path) / self.filename
                path.write_bytes(DOWNLOAD_BYTES)
                return Mission(path)
            finally:
                with state_lock:
                    state["active"] -= 1

    page = SimpleNamespace(browser=SimpleNamespace(_dl_mgr=manager))
    tab = SimpleNamespace(page=page)
    downloads = DownloadOperations(tab)  # type: ignore[arg-type]
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first = SimpleNamespace(click=Clicker("first.csv"))
    second = SimpleNamespace(click=Clicker("second.csv"))

    first_result, second_result = await asyncio.gather(
        downloads.click_and_wait(first, download_dir=first_dir, timeout=1),
        downloads.click_and_wait(second, download_dir=second_dir, timeout=1),
    )

    assert state["max_active"] == 1
    assert first_result["path"] == (first_dir / "first.csv").resolve()
    assert second_result["path"] == (second_dir / "second.csv").resolve()


@pytest.mark.asyncio
async def test_cancellation_keeps_tab_lock_until_native_work_finishes(
    tmp_path: Path,
) -> None:
    state_lock = threading.Lock()
    first_started = threading.Event()
    release_first = threading.Event()
    state = {"active": 0, "max_active": 0}
    manager = SimpleNamespace(missions={})

    class Mission:
        state = "completed"
        is_done = True
        url = "https://example.test/report.csv"

        def __init__(self, path: Path) -> None:
            self.final_path = str(path)
            self.name = path.name

    class Clicker:
        def __init__(self, filename: str, *, blocked: bool = False) -> None:
            self.filename = filename
            self.blocked = blocked

        def to_download(self, *, save_path: str, timeout: float) -> Mission:
            with state_lock:
                state["active"] += 1
                state["max_active"] = max(state["max_active"], state["active"])
            try:
                if self.blocked:
                    first_started.set()
                    release_first.wait(timeout=1)
                path = Path(save_path) / self.filename
                path.write_bytes(DOWNLOAD_BYTES)
                return Mission(path)
            finally:
                with state_lock:
                    state["active"] -= 1

    downloads = DownloadOperations(
        SimpleNamespace(page=SimpleNamespace(browser=SimpleNamespace(_dl_mgr=manager)))
    )  # type: ignore[arg-type]
    first_dir = tmp_path / "cancel-lock-first"
    second_dir = tmp_path / "cancel-lock-second"
    first_dir.mkdir()
    second_dir.mkdir()
    first = asyncio.create_task(
        downloads.click_and_wait(
            SimpleNamespace(click=Clicker("first.csv", blocked=True)),
            download_dir=first_dir,
            timeout=1,
        )
    )
    while not first_started.is_set():
        await asyncio.sleep(0)
    first.cancel()
    second = asyncio.create_task(
        downloads.click_and_wait(
            SimpleNamespace(click=Clicker("second.csv")),
            download_dir=second_dir,
            timeout=1,
        )
    )

    done, _pending = await asyncio.wait({first, second}, timeout=0.02)
    assert done == set()
    assert state["max_active"] == 1
    release_first.set()
    with pytest.raises(asyncio.CancelledError):
        await first
    second_result = await second

    assert state["max_active"] == 1
    assert second_result["path"] == (second_dir / "second.csv").resolve()


@pytest.mark.asyncio
async def test_timeout_cancels_only_the_returned_download_mission(
    tmp_path: Path,
) -> None:
    class Mission:
        state = "running"
        is_done = False
        final_path = None
        name = "pending.csv"
        url = "https://example.test/pending.csv"

        def __init__(self) -> None:
            self.cancel_calls = 0

        def cancel(self) -> None:
            self.cancel_calls += 1

    unrelated = Mission()
    current = Mission()
    manager = SimpleNamespace(missions={"unrelated": unrelated})

    class Clicker:
        def to_download(self, *, save_path: str, timeout: float) -> Mission:
            manager.missions["current"] = current
            return current

    page = SimpleNamespace(browser=SimpleNamespace(_dl_mgr=manager))
    downloads = DownloadOperations(SimpleNamespace(page=page))  # type: ignore[arg-type]
    element = SimpleNamespace(click=Clicker())

    with pytest.raises(DownloadIndeterminateError):
        await downloads.click_and_wait(element, download_dir=tmp_path, timeout=0.01)

    assert current.cancel_calls == 1
    assert unrelated.cancel_calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("unsafe_path", ["outside", "leaf_symlink"])
async def test_native_artifact_path_escape_or_symlink_never_records_success(
    monkeypatch, tmp_path: Path, unsafe_path: str
) -> None:
    root = tmp_path / "downloads"
    monkeypatch.setenv("DP_MCP_DOWNLOAD_ROOT", str(root))
    manager = SimpleNamespace(missions={})

    class Mission:
        state = "completed"
        is_done = True
        url = "https://example.test/report.csv"

        def __init__(self, path: Path) -> None:
            self.final_path = str(path)
            self.name = path.name

    class Clicker:
        def to_download(self, *, save_path: str, timeout: float) -> Mission:
            action_dir = Path(save_path)
            if unsafe_path == "outside":
                path = tmp_path / "escaped.csv"
                path.write_bytes(DOWNLOAD_BYTES)
            else:
                real = action_dir / "real.csv"
                real.write_bytes(DOWNLOAD_BYTES)
                path = action_dir / "linked.csv"
                path.symlink_to(real)
            return Mission(path)

    element = SimpleNamespace(click=Clicker())

    class NativeTab:
        url = "https://example.test/download"
        mcp_tab_id = "t0"

        def __init__(self) -> None:
            self.page = SimpleNamespace(browser=SimpleNamespace(_dl_mgr=manager))
            self.downloads = DownloadOperations(self)  # type: ignore[arg-type]

        async def _element_by_plan(self, plan: object, *, timeout: int) -> object:
            return element

    context = DrissionPageContext()
    context._current_tab = NativeTab()  # type: ignore[assignment]

    outcome = await element_click_and_download.execute(
        context,
        ElementClickAndDownloadInput(
            selector="#download",
            operation_key=f"unsafe-{unsafe_path}",
            timeout=1,
        ),
    )

    assert outcome.is_error is True
    assert outcome.structured_content()["error"]["code"] == "PRECONDITION_FAILED"
    assert list(context._artifacts.values()) == []
    receipt = list(context._operation_receipts.values())[0]
    assert receipt.status == "validation_failed"
    assert receipt.artifact_ids == ()


@pytest.mark.asyncio
@pytest.mark.skipif(not getattr(os, "O_NOFOLLOW", 0), reason="O_NOFOLLOW unavailable")
@pytest.mark.parametrize("swap_timing", ["before_open", "after_open"])
async def test_artifact_leaf_swap_never_hashes_symlink_target(
    monkeypatch, tmp_path: Path, swap_timing: str
) -> None:
    root = tmp_path / "downloads"
    outside = tmp_path / "outside-secret.txt"
    outside.write_bytes(b"outside secret must never be hashed")
    monkeypatch.setenv("DP_MCP_DOWNLOAD_ROOT", str(root))
    manager = SimpleNamespace(missions={})
    target_path: Path | None = None
    opened_flags: list[int] = []
    captured_descriptors: list[int] = []
    real_open = os.open

    class Mission:
        state = "completed"
        is_done = True
        url = "https://example.test/report.csv"

        def __init__(self, path: Path) -> None:
            self.final_path = str(path)
            self.name = path.name

    class Clicker:
        def to_download(self, *, save_path: str, timeout: float) -> Mission:
            nonlocal target_path
            target_path = Path(save_path) / "report.csv"
            target_path.write_bytes(DOWNLOAD_BYTES)
            return Mission(target_path)

    def swapping_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        candidate = Path(path) if isinstance(path, (str, os.PathLike)) else None
        if target_path is None or candidate != target_path:
            return real_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]
        opened_flags.append(flags)
        if swap_timing == "before_open":
            target_path.unlink()
            target_path.symlink_to(outside)
            return real_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]
        descriptor = real_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]
        captured_descriptors.append(descriptor)
        target_path.rename(target_path.with_suffix(".original"))
        target_path.symlink_to(outside)
        return descriptor

    monkeypatch.setattr(os, "open", swapping_open)
    element = SimpleNamespace(click=Clicker())

    class NativeTab:
        url = "https://example.test/download"
        mcp_tab_id = "t0"

        def __init__(self) -> None:
            self.page = SimpleNamespace(browser=SimpleNamespace(_dl_mgr=manager))
            self.downloads = DownloadOperations(self)  # type: ignore[arg-type]

        async def _element_by_plan(self, plan: object, *, timeout: int) -> object:
            return element

    context = DrissionPageContext()
    context._current_tab = NativeTab()  # type: ignore[assignment]
    outcome = await element_click_and_download.execute(
        context,
        ElementClickAndDownloadInput(
            selector="#download", operation_key=f"leaf-swap-{swap_timing}", timeout=1
        ),
    )

    assert outcome.is_error is True
    assert outcome.structured_content()["error"]["code"] == "PRECONDITION_FAILED"
    assert list(context._artifacts.values()) == []
    receipt = list(context._operation_receipts.values())[0]
    assert receipt.status == "validation_failed"
    assert receipt.artifact_ids == ()
    assert outside.read_bytes() == b"outside secret must never be hashed"
    assert opened_flags and all(flags & os.O_NOFOLLOW for flags in opened_flags)
    assert not [path for path in root.rglob("*") if path.is_file()]
    for descriptor in captured_descriptors:
        with pytest.raises(OSError):
            os.fstat(descriptor)


@pytest.mark.asyncio
async def test_tab_lock_wait_consumes_deadline_without_second_native_click(
    tmp_path: Path,
) -> None:
    first_started = threading.Event()
    release_first = threading.Event()
    manager = SimpleNamespace(missions={})

    class Mission:
        state = "completed"
        is_done = True
        url = "https://example.test/report.csv"

        def __init__(self, path: Path) -> None:
            self.final_path = str(path)
            self.name = path.name

    class FirstClicker:
        calls = 0

        def to_download(self, *, save_path: str, timeout: float) -> Mission:
            self.calls += 1
            first_started.set()
            release_first.wait(timeout=1)
            path = Path(save_path) / "first.csv"
            path.write_bytes(DOWNLOAD_BYTES)
            return Mission(path)

    class SecondClicker:
        calls = 0

        def to_download(self, *, save_path: str, timeout: float) -> Mission:
            self.calls += 1
            raise AssertionError("expired request must not invoke native click")

    downloads = DownloadOperations(
        SimpleNamespace(page=SimpleNamespace(browser=SimpleNamespace(_dl_mgr=manager)))
    )  # type: ignore[arg-type]
    first_dir = tmp_path / "first-lock"
    second_dir = tmp_path / "second-lock"
    first_dir.mkdir()
    second_dir.mkdir()
    first_clicker = FirstClicker()
    second_clicker = SecondClicker()
    first_task = asyncio.create_task(
        downloads.click_and_wait(
            SimpleNamespace(click=first_clicker),
            download_dir=first_dir,
            timeout=1,
        )
    )
    while not first_started.is_set():
        await asyncio.sleep(0)
    second_task = asyncio.create_task(
        downloads.click_and_wait(
            SimpleNamespace(click=second_clicker),
            download_dir=second_dir,
            timeout=0.01,
        )
    )
    await asyncio.sleep(0.02)
    release_first.set()

    await first_task
    with pytest.raises(DownloadIndeterminateError):
        await second_task
    assert first_clicker.calls == 1
    assert second_clicker.calls == 0


@pytest.mark.asyncio
async def test_browser_probe_unsupported_api_records_probe_without_click(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DP_MCP_DOWNLOAD_ROOT", str(tmp_path / "downloads"))

    class UnsupportedDownloads(_FakeDownloads):
        def probe(self, element: object) -> None:
            self.probed.append(element)
            raise DownloadUnsupportedError("CLICK_TO_DOWNLOAD_API_UNAVAILABLE")

    downloads = UnsupportedDownloads()
    context, tab = _context_with_downloads(downloads)

    outcome = await element_click_and_download.execute(
        context,
        ElementClickAndDownloadInput(
            selector="#download", operation_key="unsupported-native-api", timeout=1
        ),
    )

    assert outcome.is_error is True
    assert outcome.structured_content()["error"]["code"] == "UNSUPPORTED_OPERATION"
    assert downloads.probed == [tab.element]
    assert downloads.clicked == []
    probe = context.capability_set().capabilities[-1]
    assert probe.name == "download.click_and_wait"
    assert probe.status == "unsupported"
    assert probe.reason_code == "CLICK_TO_DOWNLOAD_API_UNAVAILABLE"
    assert len(context._operation_fingerprints) == 0
    assert list(context._artifacts.values()) == []


@pytest.mark.asyncio
async def test_generic_browser_probe_unsupported_records_distinct_capability(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DP_MCP_DOWNLOAD_ROOT", str(tmp_path / "downloads"))

    class UnsupportedDownloads(_FakeDownloads):
        def probe_trigger(self) -> None:
            self.probed.append("trigger")
            raise DownloadUnsupportedError("DOWNLOAD_MISSION_API_UNAVAILABLE")

    downloads = UnsupportedDownloads()
    context, _tab = _context_with_downloads(downloads)

    outcome = await element_click_and_download.execute(
        context,
        ElementClickAndDownloadInput(
            selector={"kind": "keyboard", "keys": "\ue007"},
            operation_key="unsupported-generic-download",
            timeout=1,
        ),
    )

    assert outcome.is_error is True
    assert outcome.structured_content()["error"]["code"] == "UNSUPPORTED_OPERATION"
    assert downloads.probed == ["trigger"]
    assert downloads.generic_triggers == 0
    probe = context.capability_set().capabilities[-1]
    assert probe.name == "download.trigger_and_wait"
    assert probe.status == "unsupported"
    assert probe.reason_code == "DOWNLOAD_MISSION_API_UNAVAILABLE"


def test_browser_probe_rejects_missing_download_manager() -> None:
    downloads = DownloadOperations(SimpleNamespace(page=SimpleNamespace(browser=None)))  # type: ignore[arg-type]

    with pytest.raises(DownloadUnsupportedError) as exc_info:
        downloads.probe(SimpleNamespace(click=SimpleNamespace()))

    assert exc_info.value.reason_code == "DOWNLOAD_MANAGER_UNAVAILABLE"


def test_browser_probe_rejects_incompatible_click_api() -> None:
    downloads = DownloadOperations(
        SimpleNamespace(
            page=SimpleNamespace(
                browser=SimpleNamespace(_dl_mgr=SimpleNamespace(missions={}))
            )
        )
    )  # type: ignore[arg-type]

    with pytest.raises(DownloadUnsupportedError) as exc_info:
        downloads.probe(
            SimpleNamespace(click=SimpleNamespace(to_download=lambda: None))
        )

    assert exc_info.value.reason_code == "CLICK_TO_DOWNLOAD_API_UNAVAILABLE"


@pytest.mark.parametrize(
    ("page", "reason_code"),
    [
        (SimpleNamespace(browser=None), "DOWNLOAD_MANAGER_UNAVAILABLE"),
        (
            SimpleNamespace(
                browser=SimpleNamespace(
                    _dl_mgr=SimpleNamespace(missions={}, _waiting_tab=set())
                ),
                tab_id="tab-1",
                set=SimpleNamespace(download_path=lambda _path: None),
            ),
            "DOWNLOAD_MISSION_API_UNAVAILABLE",
        ),
        (
            SimpleNamespace(
                browser=SimpleNamespace(
                    _dl_mgr=SimpleNamespace(
                        missions={},
                        _waiting_tab=[],
                        set_flag=lambda _tab_id, _value: None,
                        get_flag=lambda _tab_id: True,
                    )
                ),
                tab_id="tab-1",
                set=SimpleNamespace(download_path=lambda _path: None),
            ),
            "DOWNLOAD_WAITING_TAB_API_UNAVAILABLE",
        ),
        (
            SimpleNamespace(
                browser=SimpleNamespace(
                    _dl_mgr=SimpleNamespace(
                        missions={},
                        _waiting_tab=set(),
                        set_flag=lambda _tab_id, _value: None,
                        get_flag=lambda _tab_id: True,
                    )
                ),
                tab_id="",
                set=SimpleNamespace(download_path=lambda _path: None),
            ),
            "DOWNLOAD_TAB_ID_UNAVAILABLE",
        ),
        (
            SimpleNamespace(
                browser=SimpleNamespace(
                    _dl_mgr=SimpleNamespace(
                        missions={},
                        _waiting_tab=set(),
                        set_flag=lambda _tab_id, _value: None,
                        get_flag=lambda _tab_id: True,
                    )
                ),
                tab_id="tab-1",
                set=SimpleNamespace(),
            ),
            "DOWNLOAD_PATH_API_UNAVAILABLE",
        ),
    ],
)
def test_generic_download_probe_rejects_missing_native_primitives(
    page: object,
    reason_code: str,
) -> None:
    downloads = DownloadOperations(SimpleNamespace(page=page))  # type: ignore[arg-type]

    with pytest.raises(DownloadUnsupportedError) as exc_info:
        downloads.probe_trigger()

    assert exc_info.value.reason_code == reason_code


def _generic_download_boundary(
    tmp_path: Path,
) -> tuple[DownloadOperations, object, object]:
    class Manager:
        def __init__(self) -> None:
            self.missions: dict[str, object] = {}
            self._waiting_tab: set[str] = set()
            self.flags: dict[str, object] = {}

        def set_flag(self, tab_id: str, value: object) -> None:
            self.flags[tab_id] = value

        def get_flag(self, tab_id: str) -> object:
            return self.flags.get(tab_id)

    manager = Manager()
    page = SimpleNamespace(
        browser=SimpleNamespace(_dl_mgr=manager),
        tab_id="native-tab-1",
        download_path=str(tmp_path / "original"),
    )

    class Setter:
        def __init__(self) -> None:
            self.paths: list[str] = []

        def download_path(self, value: str) -> None:
            self.paths.append(value)
            page.download_path = value

    setter = Setter()
    page.set = setter
    return (
        DownloadOperations(SimpleNamespace(page=page)),  # type: ignore[arg-type]
        manager,
        setter,
    )


@pytest.mark.asyncio
async def test_generic_trigger_arms_before_callback_and_restores_native_state(
    tmp_path: Path,
) -> None:
    download_dir = tmp_path / "action"
    download_dir.mkdir()
    downloads, manager, setter = _generic_download_boundary(tmp_path)

    class Mission:
        state = "completed"
        is_done = True
        name = "report.csv"
        url = "https://example.test/report.csv"

        def __init__(self, path: Path) -> None:
            self.final_path = str(path)

    async def trigger() -> None:
        assert manager.flags["native-tab-1"] is True
        assert manager._waiting_tab == {"native-tab-1"}
        assert setter.paths[-1] == str(download_dir)
        path = download_dir / "report.csv"
        path.write_bytes(DOWNLOAD_BYTES)
        manager.set_flag("native-tab-1", Mission(path))

    result = await downloads.trigger_and_wait(
        trigger,
        download_dir=download_dir,
        timeout=1,
    )

    assert result["path"] == (download_dir / "report.csv").resolve()
    assert manager.flags["native-tab-1"] is None
    assert manager._waiting_tab == set()
    assert setter.paths == [str(download_dir), str(tmp_path / "original")]


@pytest.mark.asyncio
async def test_generic_trigger_timeout_restores_native_state(tmp_path: Path) -> None:
    download_dir = tmp_path / "action-timeout"
    download_dir.mkdir()
    downloads, manager, setter = _generic_download_boundary(tmp_path)

    async def trigger() -> None:
        return None

    with pytest.raises(DownloadIndeterminateError):
        await downloads.trigger_and_wait(
            trigger,
            download_dir=download_dir,
            timeout=0.01,
        )

    assert manager.flags["native-tab-1"] is None
    assert manager._waiting_tab == set()
    assert setter.paths == [str(download_dir), str(tmp_path / "original")]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_kind", ["exception", "cancelled"])
async def test_generic_trigger_failure_restores_state(
    tmp_path: Path,
    failure_kind: str,
) -> None:
    download_dir = tmp_path / f"action-{failure_kind}"
    download_dir.mkdir()
    downloads, manager, setter = _generic_download_boundary(tmp_path)

    async def trigger() -> None:
        if failure_kind == "cancelled":
            raise asyncio.CancelledError
        raise RuntimeError("trigger failed")

    expected = (
        asyncio.CancelledError
        if failure_kind == "cancelled"
        else DownloadIndeterminateError
    )
    with pytest.raises(expected):
        await downloads.trigger_and_wait(
            trigger,
            download_dir=download_dir,
            timeout=1,
        )

    assert manager.flags["native-tab-1"] is None
    assert manager._waiting_tab == set()
    assert setter.paths == [str(download_dir), str(tmp_path / "original")]


@pytest.mark.asyncio
async def test_generic_trigger_polls_until_mission_is_correlated(tmp_path: Path) -> None:
    download_dir = tmp_path / "action-delayed-mission"
    download_dir.mkdir()
    downloads, manager, _setter = _generic_download_boundary(tmp_path)
    published = asyncio.Event()

    class Mission:
        state = "completed"
        is_done = True
        name = "report.csv"
        url = "https://example.test/report.csv"

        def __init__(self, path: Path) -> None:
            self.final_path = str(path)

    async def publish() -> None:
        await asyncio.sleep(0.01)
        path = download_dir / "report.csv"
        path.write_bytes(DOWNLOAD_BYTES)
        manager.set_flag("native-tab-1", Mission(path))
        published.set()

    async def trigger() -> None:
        asyncio.create_task(publish())

    result = await downloads.trigger_and_wait(
        trigger,
        download_dir=download_dir,
        timeout=1,
    )

    assert published.is_set()
    assert result["path"] == (download_dir / "report.csv").resolve()


@pytest.mark.asyncio
async def test_generic_trigger_manager_failure_is_indeterminate_and_restores_path(
    tmp_path: Path,
) -> None:
    download_dir = tmp_path / "action-manager-failure"
    download_dir.mkdir()
    downloads, manager, setter = _generic_download_boundary(tmp_path)

    def fail_get_flag(_tab_id: str) -> object:
        raise RuntimeError("manager failed")

    manager.get_flag = fail_get_flag

    async def trigger() -> None:
        return None

    with pytest.raises(DownloadIndeterminateError):
        await downloads.trigger_and_wait(
            trigger,
            download_dir=download_dir,
            timeout=1,
        )

    assert manager.flags["native-tab-1"] is None
    assert manager._waiting_tab == set()
    assert setter.paths == [str(download_dir), str(tmp_path / "original")]


@pytest.mark.asyncio
async def test_generic_trigger_restore_failure_cancels_correlated_mission(
    tmp_path: Path,
) -> None:
    download_dir = tmp_path / "action-restore-failure"
    download_dir.mkdir()
    downloads, manager, setter = _generic_download_boundary(tmp_path)
    real_set_download_path = setter.download_path

    class Mission:
        state = "running"
        is_done = False
        final_path = None
        name = "report.csv"
        url = "https://example.test/report.csv"

        def __init__(self) -> None:
            self.cancel_calls = 0

        def cancel(self) -> None:
            self.cancel_calls += 1

    mission = Mission()

    def fail_restore(value: str) -> None:
        if setter.paths:
            raise RuntimeError("restore failed")
        real_set_download_path(value)

    setter.download_path = fail_restore

    async def trigger() -> None:
        manager.set_flag("native-tab-1", mission)

    with pytest.raises(DownloadIndeterminateError):
        await downloads.trigger_and_wait(
            trigger,
            download_dir=download_dir,
            timeout=1,
        )

    assert mission.cancel_calls == 1
    assert manager.flags["native-tab-1"] is None
    assert manager._waiting_tab == set()


@pytest.mark.asyncio
async def test_generic_trigger_cancels_mission_discovered_after_deadline(
    tmp_path: Path,
) -> None:
    download_dir = tmp_path / "action-late-mission"
    download_dir.mkdir()
    downloads, manager, setter = _generic_download_boundary(tmp_path)

    class Mission:
        state = "completed"
        is_done = True
        name = "report.csv"
        url = "https://example.test/report.csv"

        def __init__(self, path: Path) -> None:
            self.final_path = str(path)
            self.cancel_calls = 0

        def cancel(self) -> None:
            self.cancel_calls += 1

    path = download_dir / "report.csv"
    path.write_bytes(DOWNLOAD_BYTES)
    mission = Mission(path)

    async def trigger() -> None:
        manager.set_flag("native-tab-1", mission)
        await asyncio.sleep(0.02)

    with pytest.raises(DownloadIndeterminateError):
        await downloads.trigger_and_wait(
            trigger,
            download_dir=download_dir,
            timeout=0.01,
        )

    assert mission.cancel_calls == 1
    assert manager.flags["native-tab-1"] is None
    assert manager._waiting_tab == set()
    assert setter.paths == [str(download_dir), str(tmp_path / "original")]


@pytest.mark.asyncio
async def test_generic_trigger_cancels_mission_started_during_timeout_drain(
    tmp_path: Path,
) -> None:
    download_dir = tmp_path / "action-drain-mission"
    download_dir.mkdir()
    downloads, manager, setter = _generic_download_boundary(tmp_path)

    class Mission:
        state = "running"
        is_done = False
        final_path = None
        name = "report.csv"
        url = "https://example.test/report.csv"

        def __init__(self) -> None:
            self.cancel_calls = 0

        def cancel(self) -> None:
            self.cancel_calls += 1

    mission = Mission()

    async def trigger() -> None:
        try:
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            manager.set_flag("native-tab-1", mission)

    with pytest.raises(DownloadIndeterminateError):
        await downloads.trigger_and_wait(
            trigger,
            download_dir=download_dir,
            timeout=0.01,
        )

    assert mission.cancel_calls == 1
    assert manager.flags["native-tab-1"] is None
    assert manager._waiting_tab == set()
    assert setter.paths == [str(download_dir), str(tmp_path / "original")]


@pytest.mark.asyncio
async def test_generic_trigger_guards_delayed_browser_mission_after_timeout(
    tmp_path: Path,
) -> None:
    download_dir = tmp_path / "action-delayed-browser-event"
    download_dir.mkdir()
    downloads, manager, setter = _generic_download_boundary(tmp_path)
    published = asyncio.Event()

    class Mission:
        state = "running"
        is_done = False
        final_path = None
        name = "report.csv"
        url = "https://example.test/report.csv"

        def __init__(self) -> None:
            self.cancel_calls = 0

        def cancel(self) -> None:
            self.cancel_calls += 1

    mission = Mission()

    async def publish_late() -> None:
        await asyncio.sleep(0.03)
        assert manager.flags["native-tab-1"] is False
        assert manager._waiting_tab == {"native-tab-1"}
        assert setter.paths[-1] == str(download_dir)
        manager.set_flag("native-tab-1", mission)
        published.set()

    async def trigger() -> None:
        asyncio.create_task(publish_late())

    with pytest.raises(DownloadIndeterminateError):
        await downloads.trigger_and_wait(
            trigger,
            download_dir=download_dir,
            timeout=0.01,
        )

    assert published.is_set()
    assert mission.cancel_calls == 1
    assert manager.flags["native-tab-1"] is None
    assert manager._waiting_tab == set()
    assert setter.paths == [str(download_dir), str(tmp_path / "original")]


@pytest.mark.asyncio
async def test_generic_trigger_guards_delayed_browser_mission_after_error(
    tmp_path: Path,
) -> None:
    download_dir = tmp_path / "action-delayed-error-event"
    download_dir.mkdir()
    downloads, manager, setter = _generic_download_boundary(tmp_path)
    published = asyncio.Event()
    observed_state: dict[str, object] = {}

    class Mission:
        state = "running"
        is_done = False
        final_path = None
        name = "report.csv"
        url = "https://example.test/report.csv"

        def __init__(self) -> None:
            self.cancel_calls = 0

        def cancel(self) -> None:
            self.cancel_calls += 1

    mission = Mission()

    async def publish_late() -> None:
        await asyncio.sleep(0.03)
        observed_state["flag"] = manager.flags["native-tab-1"]
        observed_state["waiting"] = set(manager._waiting_tab)
        observed_state["path"] = setter.paths[-1]
        manager.set_flag("native-tab-1", mission)
        published.set()

    async def trigger() -> None:
        asyncio.create_task(publish_late())
        raise RuntimeError("trigger failed after dispatch")

    with pytest.raises(DownloadIndeterminateError):
        await downloads.trigger_and_wait(
            trigger,
            download_dir=download_dir,
            timeout=1,
        )

    await asyncio.wait_for(published.wait(), timeout=0.5)
    assert observed_state == {
        "flag": False,
        "waiting": {"native-tab-1"},
        "path": str(download_dir),
    }
    assert mission.cancel_calls == 1
    assert manager.flags["native-tab-1"] is None
    assert manager._waiting_tab == set()
    assert setter.paths == [str(download_dir), str(tmp_path / "original")]


@pytest.mark.asyncio
async def test_generic_trigger_deadline_can_expire_while_waiting_for_lock(
    tmp_path: Path,
) -> None:
    first_dir = tmp_path / "first-trigger-lock"
    second_dir = tmp_path / "second-trigger-lock"
    first_dir.mkdir()
    second_dir.mkdir()
    downloads, manager, _setter = _generic_download_boundary(tmp_path)
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    second_calls = 0

    class Mission:
        state = "completed"
        is_done = True
        name = "report.csv"
        url = "https://example.test/report.csv"

        def __init__(self, path: Path) -> None:
            self.final_path = str(path)

    async def first_trigger() -> None:
        first_started.set()
        await release_first.wait()
        path = first_dir / "report.csv"
        path.write_bytes(DOWNLOAD_BYTES)
        manager.set_flag("native-tab-1", Mission(path))

    async def second_trigger() -> None:
        nonlocal second_calls
        second_calls += 1

    first = asyncio.create_task(
        downloads.trigger_and_wait(
            first_trigger,
            download_dir=first_dir,
            timeout=1,
        )
    )
    await first_started.wait()
    second = asyncio.create_task(
        downloads.trigger_and_wait(
            second_trigger,
            download_dir=second_dir,
            timeout=0.01,
        )
    )
    await asyncio.sleep(0.02)
    release_first.set()

    await first
    with pytest.raises(DownloadIndeterminateError):
        await second
    assert second_calls == 0


@pytest.mark.asyncio
async def test_generic_trigger_cancellation_drains_callback_and_restores_state(
    tmp_path: Path,
) -> None:
    download_dir = tmp_path / "action-cancel"
    download_dir.mkdir()
    downloads, manager, setter = _generic_download_boundary(tmp_path)
    started = asyncio.Event()
    release = asyncio.Event()

    class Mission:
        state = "completed"
        is_done = True
        name = "report.csv"
        url = "https://example.test/report.csv"

        def __init__(self, path: Path) -> None:
            self.final_path = str(path)

    async def trigger() -> None:
        started.set()
        await release.wait()
        path = download_dir / "report.csv"
        path.write_bytes(DOWNLOAD_BYTES)
        manager.set_flag("native-tab-1", Mission(path))

    task = asyncio.create_task(
        downloads.trigger_and_wait(
            trigger,
            download_dir=download_dir,
            timeout=1,
        )
    )
    await started.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert task.done() is False
    release.set()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert manager.flags["native-tab-1"] is None
    assert manager._waiting_tab == set()
    assert setter.paths == [str(download_dir), str(tmp_path / "original")]


@pytest.mark.asyncio
async def test_internal_generic_boundary_cancellation_cancels_trigger_and_mission(
    tmp_path: Path,
) -> None:
    download_dir = tmp_path / "action-internal-cancel"
    download_dir.mkdir()
    downloads, manager, setter = _generic_download_boundary(tmp_path)
    started = asyncio.Event()

    class Mission:
        state = "running"
        is_done = False
        final_path = None
        name = "report.csv"
        url = "https://example.test/report.csv"

        def __init__(self) -> None:
            self.cancel_calls = 0

        def cancel(self) -> None:
            self.cancel_calls += 1

    mission = Mission()

    async def trigger() -> None:
        manager.set_flag("native-tab-1", mission)
        started.set()
        await asyncio.sleep(1)

    task = asyncio.create_task(
        downloads._trigger_and_wait(
            trigger,
            download_dir=download_dir,
            timeout=1,
        )
    )
    await started.wait()
    await asyncio.sleep(0.01)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert mission.cancel_calls == 1
    assert manager.flags["native-tab-1"] is None
    assert manager._waiting_tab == set()
    assert setter.paths == [str(download_dir), str(tmp_path / "original")]


@pytest.mark.asyncio
async def test_correlated_completed_mission_cannot_validate_after_deadline(
    tmp_path: Path,
) -> None:
    path = tmp_path / "expired.csv"
    path.write_bytes(DOWNLOAD_BYTES)

    class Mission:
        state = "completed"
        is_done = True
        name = "expired.csv"
        url = "https://example.test/expired.csv"

        def __init__(self) -> None:
            self.final_path = str(path)
            self.cancel_calls = 0

        def cancel(self) -> None:
            self.cancel_calls += 1

    mission = Mission()
    downloads = DownloadOperations(SimpleNamespace(page=SimpleNamespace()))  # type: ignore[arg-type]

    with pytest.raises(DownloadIndeterminateError):
        await downloads._mission_result(
            mission,
            download_dir=tmp_path,
            deadline=time.monotonic() - 1,
        )

    assert mission.cancel_calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("native_result", "expected_exception"),
    [
        ("raises", DownloadIndeterminateError),
        ("no_mission", DownloadIndeterminateError),
        ("canceled", DownloadFailedError),
        ("skipped", DownloadFailedError),
        ("interrupted", DownloadIndeterminateError),
        ("missing_path", DownloadValidationError),
        ("directory_path", DownloadValidationError),
    ],
)
async def test_native_download_rejects_unconfirmed_or_invalid_missions(
    tmp_path: Path, native_result: str, expected_exception: type[Exception]
) -> None:
    manager = SimpleNamespace(missions={})

    class Mission:
        is_done = True
        url = "https://example.test/report.csv"

        def __init__(self, state: str, path: Path | None) -> None:
            self.state = state
            self.final_path = None if path is None else str(path)
            self.name = "native-name.csv"

    class Clicker:
        def to_download(self, *, save_path: str, timeout: float) -> Mission | None:
            if native_result == "raises":
                raise RuntimeError("native failed")
            if native_result == "no_mission":
                return None
            path = Path(save_path) / "report.csv"
            if native_result == "missing_path":
                return Mission("completed", None)
            if native_result == "directory_path":
                path.mkdir()
                return Mission("completed", path)
            path.write_bytes(DOWNLOAD_BYTES)
            return Mission(native_result, path)

    downloads = DownloadOperations(
        SimpleNamespace(page=SimpleNamespace(browser=SimpleNamespace(_dl_mgr=manager)))
    )  # type: ignore[arg-type]
    element = SimpleNamespace(click=Clicker())

    with pytest.raises(expected_exception):
        await downloads.click_and_wait(element, download_dir=tmp_path, timeout=1)


@pytest.mark.asyncio
async def test_native_download_uses_final_path_basename_when_mission_name_differs(
    tmp_path: Path,
) -> None:
    manager = SimpleNamespace(missions={})

    class Mission:
        state = "completed"
        is_done = True
        name = "reported.csv"
        url = "https://example.test/final.bin"

        def __init__(self, path: Path) -> None:
            self.final_path = str(path)

    class Clicker:
        def to_download(self, *, save_path: str, timeout: float) -> Mission:
            path = Path(save_path) / "actual.bin"
            path.write_bytes(DOWNLOAD_BYTES)
            return Mission(path)

    downloads = DownloadOperations(
        SimpleNamespace(page=SimpleNamespace(browser=SimpleNamespace(_dl_mgr=manager)))
    )  # type: ignore[arg-type]

    result = await downloads.click_and_wait(
        SimpleNamespace(click=Clicker()), download_dir=tmp_path, timeout=1
    )

    assert result["filename"] == "actual.bin"
    assert result["mime_type"] == "application/octet-stream"
    assert result["path"] == (tmp_path / "actual.bin").resolve()


@pytest.mark.asyncio
async def test_cancel_mission_ignores_browser_cancel_exceptions() -> None:
    class Mission:
        def __init__(self) -> None:
            self.cancel_calls = 0

        def cancel(self) -> None:
            self.cancel_calls += 1
            raise RuntimeError("cancel failed")

    mission = Mission()

    await DownloadOperations._cancel_mission(mission)

    assert mission.cancel_calls == 1


@pytest.mark.asyncio
async def test_native_artifact_change_during_integrity_is_indeterminate(
    monkeypatch, tmp_path: Path
) -> None:
    root = tmp_path / "downloads"
    root.mkdir()
    path = root / "report.csv"
    path.write_bytes(DOWNLOAD_BYTES)
    real_fdopen = os.fdopen
    mutated = False

    class MutatingReader:
        def __init__(self, stream: object) -> None:
            self._stream = stream

        def __enter__(self) -> MutatingReader:
            self._stream.__enter__()
            return self

        def __exit__(self, *args: object) -> object:
            return self._stream.__exit__(*args)

        def read(self, size: int = -1) -> bytes:
            nonlocal mutated
            chunk = self._stream.read(size)
            if chunk and not mutated:
                mutated = True
                path.write_bytes(DOWNLOAD_BYTES + b"mutated")
            return chunk

    def mutating_fdopen(
        descriptor: int, mode: str, closefd: bool = True
    ) -> MutatingReader:
        return MutatingReader(real_fdopen(descriptor, mode, closefd=closefd))

    monkeypatch.setattr(os, "fdopen", mutating_fdopen)

    with pytest.raises(DownloadIndeterminateError):
        await DownloadOperations(
            SimpleNamespace(
                page=SimpleNamespace(
                    browser=SimpleNamespace(_dl_mgr=SimpleNamespace(missions={}))
                )
            )
        )._click_and_wait(  # type: ignore[arg-type]
            SimpleNamespace(
                click=SimpleNamespace(
                    to_download=lambda *, save_path, timeout: SimpleNamespace(
                        state="completed",
                        is_done=True,
                        final_path=str(path),
                        name="report.csv",
                        url="https://example.test/report.csv",
                    )
                )
            ),
            download_dir=root,
            timeout=1,
        )


@pytest.mark.asyncio
async def test_default_operation_key_allocates_distinct_action_for_each_request(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DP_MCP_DOWNLOAD_ROOT", str(tmp_path / "downloads"))
    downloads = _FakeDownloads()
    context, _tab = _context_with_downloads(downloads)
    args = ElementClickAndDownloadInput(selector="#download", timeout=1)

    outcome = await element_click_and_download.execute(context, args)

    assert outcome.is_error is False
    data = outcome.structured_content()["data"]
    assert data["operation_key"] == "download-action-000001"
    assert data["receipt"]["action_id"] == "action-000001"
    assert len(downloads.clicked) == 1

    second = await element_click_and_download.execute(context, args)

    assert second.is_error is False
    second_data = second.structured_content()["data"]
    assert second_data["operation_key"] == "download-action-000002"
    assert second_data["receipt"]["action_id"] == "action-000002"
    assert len(downloads.clicked) == 2


@pytest.mark.asyncio
async def test_operation_claim_failure_releases_artifact_and_cleans_action_directory(
    monkeypatch, tmp_path: Path
) -> None:
    root = tmp_path / "downloads"
    monkeypatch.setenv("DP_MCP_DOWNLOAD_ROOT", str(root))
    downloads = _FakeDownloads()
    context = DrissionPageContext(operation_limit=1)
    context.claim_operation("existing", "a" * 64)
    context._current_tab = _FakeTab(downloads)  # type: ignore[assignment]

    outcome = await element_click_and_download.execute(
        context,
        ElementClickAndDownloadInput(
            selector="#download", operation_key="ledger-full-after-dir", timeout=1
        ),
    )

    assert outcome.is_error is True
    assert outcome.structured_content()["error"]["code"] == "TASK_LEDGER_FULL"
    assert downloads.clicked == []
    assert not [path for path in root.rglob("*") if path.is_file()]
    assert not context._artifact_reservations


@pytest.mark.asyncio
async def test_download_failed_status_has_failed_receipt_and_replays_failure(
    monkeypatch, tmp_path: Path
) -> None:
    root = tmp_path / "downloads"
    monkeypatch.setenv("DP_MCP_DOWNLOAD_ROOT", str(root))
    downloads = _FakeDownloads(fail=DownloadFailedError("browser canceled"))
    context, _tab = _context_with_downloads(downloads)
    args = ElementClickAndDownloadInput(
        selector="#download", operation_key="browser-failed", timeout=1
    )

    outcome = await element_click_and_download.execute(context, args)

    assert outcome.is_error is True
    assert outcome.structured_content()["error"]["code"] == "UNKNOWN_ERROR"
    receipt = context.operation_receipt("browser-failed")
    assert receipt is not None
    assert receipt.status == "failed"
    assert receipt.error_code == "DOWNLOAD_FAILED"
    assert receipt.artifact_ids == ()
    assert list(context._artifacts.values()) == []

    monkeypatch.delenv("DP_MCP_DOWNLOAD_ROOT")
    monkeypatch.setenv("DP_MCP_DENY_DOWNLOAD", "1")
    context._current_tab = None
    replay = await element_click_and_download.execute(context, args)
    assert replay.is_error is True
    assert replay.structured_content()["error"]["code"] == "UNKNOWN_ERROR"
    assert replay.structured_content()["data"] == outcome.structured_content()["data"]
    assert len(downloads.clicked) == 1


@pytest.mark.asyncio
async def test_task_download_directory_file_denies_before_claim_or_click(
    monkeypatch, tmp_path: Path
) -> None:
    root = tmp_path / "downloads"
    root.mkdir()
    monkeypatch.setenv("DP_MCP_DOWNLOAD_ROOT", str(root))
    context, tab = _context_with_downloads(_FakeDownloads())
    (root / context.task_id).write_text("not a directory", encoding="utf-8")

    outcome = await element_click_and_download.execute(
        context,
        ElementClickAndDownloadInput(
            selector="#download", operation_key="task-dir-file", timeout=1
        ),
    )

    assert outcome.is_error is True
    assert outcome.structured_content()["error"]["code"] == "POLICY_DENIED"
    assert tab.downloads.clicked == []
    assert len(context._operation_fingerprints) == 0
    assert list(context._artifacts.values()) == []
