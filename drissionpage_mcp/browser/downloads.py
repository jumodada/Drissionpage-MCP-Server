"""Capability-probed native DrissionPage download operations for one tab."""

from __future__ import annotations

import asyncio
import mimetypes
import shutil
from collections.abc import Awaitable, Callable
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING, Any, TypeVar

from ..compat import accepts_parameters
from ..response_errors import ErrorCode
from .artifacts import (
    ArtifactFileChangedError,
    ArtifactFileValidationError,
    inspect_artifact_file,
)

if TYPE_CHECKING:
    from ..tab import PageTab


_T = TypeVar("_T")
_TRIGGER_TIMEOUT_GUARD_SECONDS = 0.25


class DownloadUnsupportedError(RuntimeError):
    """Raised before a click when the attached runtime lacks download support."""

    code = ErrorCode.UNSUPPORTED_OPERATION

    def __init__(self, reason_code: str):
        super().__init__(
            "Native browser download support is unavailable "
            f"in this DrissionPage runtime ({reason_code})."
        )
        self.reason_code = reason_code


class DownloadIndeterminateError(RuntimeError):
    """Raised after a native click when its download outcome is not confirmed."""


class DownloadFailedError(RuntimeError):
    """Raised when the browser reports a terminal canceled/skipped mission."""


class DownloadValidationError(ValueError):
    """Raised when a completed mission violates the artifact contract."""

    code = ErrorCode.PRECONDITION_FAILED


class DownloadOperations:
    """Own one-click/one-download lifecycle and integrity verification."""

    def __init__(self, tab: PageTab) -> None:
        self._tab = tab
        self._download_lock = asyncio.Lock()

    @property
    def _page(self) -> Any:
        return self._tab.page

    def probe(self, element: Any) -> Any:
        """Fail closed unless the native mission lifecycle is available."""

        browser = getattr(self._page, "browser", None)
        manager = getattr(browser, "_dl_mgr", None)
        if manager is None or not isinstance(getattr(manager, "missions", None), dict):
            raise DownloadUnsupportedError("DOWNLOAD_MANAGER_UNAVAILABLE")
        clicker = getattr(element, "click", None)
        downloader = getattr(clicker, "to_download", None)
        if not callable(downloader) or not accepts_parameters(
            downloader, "save_path", "timeout"
        ):
            raise DownloadUnsupportedError("CLICK_TO_DOWNLOAD_API_UNAVAILABLE")
        return downloader

    def probe_trigger(self) -> None:
        """Fail closed unless generic trigger correlation primitives exist."""

        self._trigger_primitives()

    async def click_and_wait(
        self,
        element: Any,
        *,
        download_dir: Path,
        timeout: float,
    ) -> dict[str, Any]:
        """Serialize native download settings and mission correlation per tab."""

        lock_started = monotonic()
        async with self._download_lock:
            remaining = timeout - (monotonic() - lock_started)
            if remaining <= 0:
                raise DownloadIndeterminateError(
                    "The download deadline expired while waiting for the tab boundary."
                )
            operation = asyncio.create_task(
                self._click_and_wait(
                    element, download_dir=download_dir, timeout=remaining
                )
            )
            return await _await_terminal(operation)

    async def trigger_and_wait(
        self,
        trigger: Callable[[], Awaitable[Any]],
        *,
        download_dir: Path,
        timeout: float,
    ) -> dict[str, Any]:
        """Correlate one async pointer/keyboard trigger with one mission."""

        lock_started = monotonic()
        async with self._download_lock:
            remaining = timeout - (monotonic() - lock_started)
            if remaining <= 0:
                raise DownloadIndeterminateError(
                    "The download deadline expired while waiting for the tab boundary."
                )
            operation = asyncio.create_task(
                self._trigger_and_wait(
                    trigger,
                    download_dir=download_dir,
                    timeout=remaining,
                )
            )
            return await _await_terminal(operation)

    async def _click_and_wait(
        self,
        element: Any,
        *,
        download_dir: Path,
        timeout: float,
    ) -> dict[str, Any]:
        downloader = self.probe(element)
        deadline = monotonic() + timeout

        try:
            # Await the complete native call. DrissionPage's own timeout bounds
            # mission discovery; cancellation here would leave a native click
            # running after the MCP response returned.
            mission = await asyncio.to_thread(
                downloader,
                save_path=str(download_dir),
                timeout=timeout,
            )
        except Exception as exc:
            raise DownloadIndeterminateError(
                "The native download click outcome is indeterminate."
            ) from exc

        if not mission:
            raise DownloadIndeterminateError(
                "The native click did not produce a confirmed download mission."
            )

        return await self._mission_result(
            mission,
            download_dir=download_dir,
            deadline=deadline,
        )

    async def _trigger_and_wait(
        self,
        trigger: Callable[[], Awaitable[Any]],
        *,
        download_dir: Path,
        timeout: float,
    ) -> dict[str, Any]:
        manager, tab_id, set_download_path = self._trigger_primitives()
        deadline = monotonic() + timeout
        previous_path = str(getattr(self._page, "download_path", "") or ".")
        mission: Any = None
        trigger_error: BaseException | None = None
        cleanup_error: Exception | None = None
        deadline_expired = False
        boundary_armed = False
        trigger_task: asyncio.Task[Any] | None = None

        try:
            set_download_path(str(download_dir))
            manager._waiting_tab.add(tab_id)
            manager.set_flag(tab_id, True)
            boundary_armed = True

            async def invoke_trigger() -> Any:
                return await trigger()

            trigger_task = asyncio.create_task(invoke_trigger())
            while trigger_error is None:
                candidate = manager.get_flag(tab_id)
                if not isinstance(candidate, bool):
                    mission = candidate
                if trigger_task.done():
                    try:
                        trigger_task.result()
                    except asyncio.CancelledError as exc:
                        trigger_error = exc
                    except Exception as exc:
                        trigger_error = exc
                    if mission is not None or trigger_error is not None:
                        break
                if monotonic() >= deadline:
                    deadline_expired = True
                    manager.set_flag(tab_id, False)
                    await _cancel_and_drain(trigger_task)
                    candidate = manager.get_flag(tab_id)
                    if not isinstance(candidate, bool):
                        mission = candidate
                    manager.set_flag(tab_id, False)
                    break
                await asyncio.sleep(
                    min(0.005, max(0.001, deadline - monotonic()))
                )
        except asyncio.CancelledError as exc:
            trigger_error = exc
        except Exception as exc:
            trigger_error = exc
        finally:
            if trigger_task is not None and not trigger_task.done():
                try:
                    manager.set_flag(tab_id, False)
                except Exception as exc:
                    cleanup_error = exc
                await _cancel_and_drain(trigger_task)
                try:
                    candidate = manager.get_flag(tab_id)
                    if not isinstance(candidate, bool):
                        mission = candidate
                except Exception as exc:
                    if cleanup_error is None:
                        cleanup_error = exc
            if boundary_armed and (deadline_expired or trigger_error is not None):
                try:
                    manager.set_flag(tab_id, False)
                    await self._guard_late_missions(manager, tab_id)
                except asyncio.CancelledError as exc:
                    trigger_error = exc
                except Exception as exc:
                    if cleanup_error is None:
                        cleanup_error = exc
            cleanup_steps = (
                lambda: manager.set_flag(tab_id, None),
                lambda: manager._waiting_tab.discard(tab_id),
                lambda: set_download_path(previous_path),
            )
            for cleanup_step in cleanup_steps:
                try:
                    cleanup_step()
                except Exception as exc:
                    if cleanup_error is None:
                        cleanup_error = exc

        if isinstance(trigger_error, asyncio.CancelledError):
            if mission is not None:
                await self._cancel_mission(mission)
            raise trigger_error
        if deadline_expired or trigger_error is not None or cleanup_error is not None:
            if mission is not None:
                await self._cancel_mission(mission)
            raise DownloadIndeterminateError(
                "The browser download trigger outcome is indeterminate."
            ) from (trigger_error or cleanup_error)
        if not mission:
            raise DownloadIndeterminateError(
                "The browser trigger did not produce a confirmed download mission."
            )
        return await self._mission_result(
            mission,
            download_dir=download_dir,
            deadline=deadline,
        )

    def _trigger_primitives(self) -> tuple[Any, str, Callable[[str], Any]]:
        browser = getattr(self._page, "browser", None)
        manager = getattr(browser, "_dl_mgr", None)
        if manager is None or not isinstance(getattr(manager, "missions", None), dict):
            raise DownloadUnsupportedError("DOWNLOAD_MANAGER_UNAVAILABLE")
        if not callable(getattr(manager, "set_flag", None)) or not callable(
            getattr(manager, "get_flag", None)
        ):
            raise DownloadUnsupportedError("DOWNLOAD_MISSION_API_UNAVAILABLE")
        if not isinstance(getattr(manager, "_waiting_tab", None), set):
            raise DownloadUnsupportedError("DOWNLOAD_WAITING_TAB_API_UNAVAILABLE")
        tab_id = str(getattr(self._page, "tab_id", "") or "")
        if not tab_id:
            raise DownloadUnsupportedError("DOWNLOAD_TAB_ID_UNAVAILABLE")
        setter = getattr(getattr(self._page, "set", None), "download_path", None)
        if not callable(setter):
            raise DownloadUnsupportedError("DOWNLOAD_PATH_API_UNAVAILABLE")
        return manager, tab_id, setter

    async def _guard_late_missions(self, manager: Any, tab_id: str) -> None:
        """Keep indeterminate trigger downloads fail-closed for a bounded drain."""

        guard_deadline = monotonic() + _TRIGGER_TIMEOUT_GUARD_SECONDS
        while monotonic() < guard_deadline:
            candidate = manager.get_flag(tab_id)
            if not isinstance(candidate, bool):
                if candidate is not None:
                    await self._cancel_mission(candidate)
                manager.set_flag(tab_id, False)
            await asyncio.sleep(
                min(0.005, max(0.001, guard_deadline - monotonic()))
            )

    async def _mission_result(
        self,
        mission: Any,
        *,
        download_dir: Path,
        deadline: float,
    ) -> dict[str, Any]:
        """Await and validate one already-correlated download mission."""

        if monotonic() >= deadline:
            await self._cancel_mission(mission)
            raise DownloadIndeterminateError(
                "The download deadline expired before artifact validation."
            )

        while not bool(getattr(mission, "is_done", False)):
            if monotonic() >= deadline:
                await self._cancel_mission(mission)
                raise DownloadIndeterminateError(
                    "The download did not reach a terminal state before the timeout."
                )
            await asyncio.sleep(min(0.02, max(0.001, deadline - monotonic())))

        state = str(getattr(mission, "state", ""))
        if state in {"canceled", "skipped"}:
            raise DownloadFailedError("The browser reported a canceled download.")
        if state != "completed":
            raise DownloadIndeterminateError(
                "The download reached a non-success terminal state."
            )

        final_path = getattr(mission, "final_path", None)
        if not final_path:
            raise DownloadValidationError("Completed download has no artifact path.")
        path = Path(str(final_path)).expanduser()
        base = download_dir.resolve()
        try:
            artifact = inspect_artifact_file(path, approved_root=base)
        except ArtifactFileChangedError as exc:
            raise DownloadIndeterminateError(
                "The completed artifact changed during integrity validation."
            ) from exc
        except ArtifactFileValidationError as exc:
            raise DownloadValidationError(
                "Completed download is not a stable regular non-symlink file."
            ) from exc
        filename = Path(str(getattr(mission, "name", "") or path.name)).name
        if filename != path.name:
            filename = path.name
        mime_type = mimetypes.guess_type(filename)[0]
        return {
            "path": artifact.path,
            "filename": filename,
            "mime_type": mime_type,
            "size_bytes": artifact.size_bytes,
            "sha256": artifact.sha256,
            "source_url": str(getattr(mission, "url", "") or ""),
        }

    async def cleanup(self, download_dir: Path) -> None:
        """Remove a failed mission directory without touching the approved root."""

        await asyncio.to_thread(shutil.rmtree, download_dir, True)

    @staticmethod
    async def _cancel_mission(mission: Any) -> None:
        cancel = getattr(mission, "cancel", None)
        if callable(cancel):
            try:
                await asyncio.to_thread(cancel)
            except Exception:
                pass


async def _await_terminal(task: asyncio.Task[_T]) -> _T:
    cancellation: asyncio.CancelledError | None = None
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError as exc:
            cancellation = exc
    try:
        result = task.result()
    except BaseException:
        if cancellation is not None:
            raise cancellation from None
        raise
    if cancellation is not None:
        raise cancellation
    return result


async def _cancel_and_drain(task: asyncio.Task[Any]) -> None:
    task.cancel()
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            continue
    try:
        task.result()
    except (asyncio.CancelledError, Exception):
        pass
