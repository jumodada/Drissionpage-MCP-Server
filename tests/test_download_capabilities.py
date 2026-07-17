"""Contracts for one-click downloads and safe artifact delivery."""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from drissionpage_mcp.browser.downloads import DownloadIndeterminateError
from drissionpage_mcp.browser.downloads import DownloadOperations
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
    with pytest.raises(ValidationError):
        ElementClickAndDownloadInput(selector="")
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
        self.cleanup_dirs: list[Path] = []

    def probe(self, element: object) -> None:
        self.probed.append(element)

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

    async def cleanup(self, download_dir: Path) -> None:
        self.cleanup_dirs.append(download_dir)
        shutil.rmtree(download_dir, ignore_errors=True)


class _FakeTab:
    def __init__(self, downloads: _FakeDownloads, *, element: object | None = None):
        self.url = "https://example.test/download?private=secret"
        self.mcp_tab_id = "t0"
        self.downloads = downloads
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

    assert context.artifact_inventory() == [second]
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
    assert context.task_summary().operation_count == 0
    assert context.task_summary().receipt_count == 0
    assert context.artifact_inventory() == []


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
    assert context.task_summary().operation_count == 0
    assert context.task_summary().receipt_count == 0
    assert context.artifact_inventory() == []


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
    assert context.task_summary().operation_count == 0
    assert context.task_summary().receipt_count == 0


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
    assert context.task_summary().operation_count == 0
    assert context.task_summary().receipt_count == 0
    assert len(context.artifact_inventory()) == 1


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
    assert context.artifact_inventory()[0].model_dump(mode="json") == artifact
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

    inventory = context.artifact_inventory()
    if inventory:
        assert outcome.is_error is False
        artifact_path = root / inventory[0].safe_relative_path
        assert artifact_path.read_bytes() == DOWNLOAD_BYTES
        receipt = context.receipt_inventory()[0]
        assert receipt.status == "success"
        assert receipt.artifact_ids == (inventory[0].artifact_id,)
    else:
        assert outcome.is_error is True
        assert context.receipt_inventory()[0].status != "success"
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
    assert context.task_summary().receipt_count == 1
    assert len(context.artifact_inventory()) == 1


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
    artifacts = context.artifact_inventory()
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
    assert context.artifact_inventory() == []
    receipt = context.receipt_inventory()[0]
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
    assert context.artifact_inventory() == []


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
    assert context.artifact_inventory() == []
    receipt = context.receipt_inventory()[0]
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
    assert context.artifact_inventory() == []
    receipt = context.receipt_inventory()[0]
    assert receipt.status == "validation_failed"
    assert receipt.artifact_ids == ()


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
