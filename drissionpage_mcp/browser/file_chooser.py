"""One-shot browser file-chooser interception and cleanup."""

from __future__ import annotations

import asyncio
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING, Any

from ..response_errors import ErrorCode
from ..target import ElementTargetArg
from .targeting import DomTargetResolver

if TYPE_CHECKING:
    from ..tab import PageTab


class FileChooserError(RuntimeError):
    """Safe file-chooser failure that never includes local file paths."""

    code = ErrorCode.UNSUPPORTED_OPERATION

    def __init__(self, reason_code: str):
        super().__init__(f"Browser file chooser failed ({reason_code}).")
        self.reason_code = reason_code


class FileChooserOperations:
    """Arm, click, await, and always disarm one Chromium file chooser."""

    def __init__(self, tab: PageTab) -> None:
        self._tab = tab
        self._targeting = getattr(tab, "dom_targeting", DomTargetResolver(tab))

    async def click_and_upload(
        self,
        selector: ElementTargetArg,
        paths: list[str],
        *,
        timeout: float,
    ) -> dict[str, Any]:
        page = self._tab.page
        setter = getattr(getattr(page, "set", None), "upload_files", None)
        run_cdp = getattr(page, "run_cdp", None)
        driver = getattr(page, "driver", None)
        set_callback = getattr(driver, "set_callback", None)
        if not callable(setter):
            raise FileChooserError("FILE_CHOOSER_API_UNAVAILABLE")
        if not callable(run_cdp):
            raise FileChooserError("FILE_CHOOSER_API_UNAVAILABLE")
        if not callable(set_callback):
            raise FileChooserError("FILE_CHOOSER_API_UNAVAILABLE")
        if getattr(page, "_upload_list", None):
            raise FileChooserError("FILE_CHOOSER_ALREADY_ARMED")

        resolved = await self._targeting.resolve(selector, timeout=timeout)
        click = getattr(resolved.element, "click", None)
        if not callable(click):
            raise FileChooserError("NATIVE_CLICK_UNAVAILABLE")

        try:
            setter(paths)
            await asyncio.to_thread(click)
            deadline = monotonic() + timeout
            while getattr(page, "_upload_list", None):
                if monotonic() >= deadline:
                    raise TimeoutError("Browser file chooser timed out.")
                await asyncio.sleep(0.01)
            await self._tab._stabilize(
                "file_chooser_upload", timeout=1.0, fallback_sleep=0.02
            )
            return {
                **resolved.metadata(),
                "uploaded": True,
                "file_count": len(paths),
                "filenames": [Path(path).name for path in paths],
            }
        finally:
            self._cleanup(page, run_cdp, set_callback)

    @staticmethod
    def _cleanup(page: Any, run_cdp: Any, set_callback: Any) -> None:
        try:
            set_callback("Page.fileChooserOpened", None)
        except Exception:
            pass
        try:
            run_cdp("Page.setInterceptFileChooserDialog", enabled=False)
        except Exception:
            pass
        try:
            page._upload_list = None
        except Exception:
            pass


__all__ = ["FileChooserError", "FileChooserOperations"]
