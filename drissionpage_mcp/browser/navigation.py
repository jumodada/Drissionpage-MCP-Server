"""Navigation operations for a browser tab."""

from __future__ import annotations

import asyncio
import inspect
import logging
from time import monotonic
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..tab import PageTab

logger = logging.getLogger(__name__)


class NavigationOperations:
    """Own page navigation and history behavior."""

    def __init__(self, tab: PageTab) -> None:
        self._tab = tab

    @property
    def _page(self) -> Any:
        return self._tab.page

    async def navigate(
        self, url: str, *, timeout: float | None = None
    ) -> dict[str, str | bool | int | None]:
        try:
            await self._clear_snapshots()
            started = monotonic()
            deadline = None if timeout is None else started + timeout
            get = self._page.get
            kwargs = _native_navigation_kwargs(get, deadline)
            result = await _await_native_call(get, url, **kwargs)
            navigation_finished = monotonic()
            _remaining(deadline, stage="stabilization")
            if result is False or (hasattr(result, "ok") and result.ok is False):
                raise RuntimeError(f"Navigation failed: {result}")
            self._tab._url = getattr(result, "url", None) or self._page.url or url
            settle_timeout = _remaining(deadline, stage="stabilization")
            settle_started = monotonic()
            settled = await self._tab._stabilize(
                "navigation",
                timeout=5.0 if settle_timeout is None else settle_timeout,
                fallback_sleep=0.05,
                **({"strict_timeout": True} if timeout is not None else {}),
            )
            finished = monotonic()
            if deadline is not None and finished > deadline:
                raise TimeoutError(
                    "Navigation budget expired while native browser work was draining."
                )
            ready_state = _ready_state(self._page)
            logger.info("Navigation completed")
            return {
                "final_url": self._tab.url,
                "ready_state": ready_state,
                "settled": settled,
                "navigation_ms": _elapsed_ms(started, navigation_finished),
                "settle_ms": _elapsed_ms(settle_started, finished),
                "total_ms": _elapsed_ms(started, finished),
            }
        except Exception as exc:
            logger.error("Failed to navigate (%s)", type(exc).__name__)
            raise

    async def back(self) -> None:
        try:
            await self._clear_snapshots()
            self._page.back()
            await self._tab._stabilize("go_back", timeout=5.0, fallback_sleep=0.05)
        except Exception as exc:
            logger.error("Failed to go back (%s)", type(exc).__name__)
            raise

    async def forward(self) -> None:
        try:
            await self._clear_snapshots()
            self._page.forward()
            await self._tab._stabilize("go_forward", timeout=5.0, fallback_sleep=0.05)
        except Exception as exc:
            logger.error("Failed to go forward (%s)", type(exc).__name__)
            raise

    async def refresh(self) -> None:
        try:
            await self._clear_snapshots()
            self._page.refresh()
            await self._tab._stabilize("refresh", timeout=5.0, fallback_sleep=0.05)
        except Exception as exc:
            logger.error("Failed to refresh page (%s)", type(exc).__name__)
            raise

    async def _clear_snapshots(self) -> None:
        observation = getattr(self._tab, "observation", None)
        clear = getattr(observation, "clear_snapshots", None)
        if not callable(clear):
            return
        result = clear()
        if inspect.isawaitable(result):
            await result


def _native_navigation_kwargs(
    get: Any, deadline: float | None
) -> dict[str, float | int]:
    if deadline is None:
        return {}
    try:
        parameters = inspect.signature(get).parameters
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            "Cannot verify that this DrissionPage navigation surface supports "
            "timeout and retry controls."
        ) from exc
    accepts_kwargs = any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )
    if not accepts_kwargs and not {"timeout", "retry"}.issubset(parameters):
        raise RuntimeError(
            "This DrissionPage navigation surface does not support the requested "
            "timeout budget and retry suppression."
        )
    remaining = _remaining(deadline, stage="native navigation")
    assert remaining is not None
    return {"timeout": remaining, "retry": 0}


def _remaining(deadline: float | None, *, stage: str) -> float | None:
    if deadline is None:
        return None
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise TimeoutError(f"Navigation budget expired before {stage}.")
    return remaining


async def _await_native_call(call: Any, /, *args: Any, **kwargs: Any) -> Any:
    """Do not release tab ownership until uncancellable native work has drained."""

    worker = asyncio.create_task(asyncio.to_thread(call, *args, **kwargs))
    cancellation: asyncio.CancelledError | None = None
    try:
        while not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError as exc:
                cancellation = exc
        result = worker.result()
    except BaseException:
        if cancellation is not None:
            raise cancellation from None
        raise
    if cancellation is not None:
        raise cancellation
    return result


def _ready_state(page: Any) -> str:
    try:
        value = getattr(page.states, "ready_state", "")
    except Exception:
        return ""
    return value if isinstance(value, str) else ""


def _elapsed_ms(started: float, finished: float) -> int:
    return max(0, int((finished - started) * 1000))
