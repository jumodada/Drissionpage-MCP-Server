"""Shared helpers for optional post-action observation."""

from __future__ import annotations

from typing import Any, cast

from ..observation import diff_observations


async def maybe_observe(tab: Any, enabled: bool) -> dict[str, Any] | None:
    """Return a page observation only when the caller opted in."""

    if not enabled:
        return None
    return cast(dict[str, Any], await tab.observe())


async def observed_changes(
    tab: Any,
    before: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return a before/after diff when observation was enabled."""

    if before is None:
        return None
    after = await tab.observe()
    return diff_observations(before, after)
