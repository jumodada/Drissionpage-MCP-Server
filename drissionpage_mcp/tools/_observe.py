"""Shared helpers for optional post-action observation."""

from __future__ import annotations

import asyncio
from typing import Any, cast

from ..observation import diff_observations, safe_int

_CONSOLE_SETTLE_ATTEMPTS = 4
_CONSOLE_SETTLE_INTERVAL = 0.05


async def maybe_observe(tab: Any, enabled: bool) -> dict[str, Any] | None:
    """Return a page observation only when the caller opted in."""

    if not enabled:
        return None
    return cast(dict[str, Any], await tab.observation.observe())


async def observed_changes(
    tab: Any,
    before: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return a before/after diff when observation was enabled."""

    if before is None:
        return None
    after = await _observe_after_console_settles(tab, before)
    return diff_observations(before, after)


async def _observe_after_console_settles(
    tab: Any,
    before: dict[str, Any],
) -> dict[str, Any]:
    """Observe after an action, allowing browser console events to flush."""

    after = cast(dict[str, Any], await tab.observation.observe())
    before_cursor = _console_cursor(before)
    if before_cursor < 0 or not _console_is_available(before):
        return after
    if _console_cursor(after) > before_cursor:
        return after

    for _ in range(_CONSOLE_SETTLE_ATTEMPTS):
        await asyncio.sleep(_CONSOLE_SETTLE_INTERVAL)
        after = cast(dict[str, Any], await tab.observation.observe())
        if _console_cursor(after) > before_cursor:
            break
    return after


def _console_cursor(observation: dict[str, Any]) -> int:
    console = observation.get("console")
    if not isinstance(console, dict):
        return -1
    return safe_int(console.get("next_cursor"), -1)


def _console_is_available(observation: dict[str, Any]) -> bool:
    console = observation.get("console")
    return isinstance(console, dict) and bool(console.get("available"))
