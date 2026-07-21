"""Wait and observable condition operations for a browser tab."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import TYPE_CHECKING, Any

from ..selector import SelectorPlan, normalize_selector
from .page_state_scripts import _selector_state_script

if TYPE_CHECKING:
    from ..tab import PageTab

logger = logging.getLogger(__name__)


class WaitOperations:
    """Own selector, URL, text, and state waits."""

    def __init__(self, tab: "PageTab") -> None:
        self._tab = tab

    @property
    def _page(self) -> Any:
        return self._tab.page

    async def until(
        self,
        *,
        condition: str,
        selector: str = "",
        value: str = "",
        name: str = "",
        timeout: float = 10,
        interval: float = 0.1,
        stable_ms: int = 300,
    ) -> dict[str, Any]:
        start = time.monotonic()
        deadline = start + max(0.0, float(timeout))
        last_state: dict[str, Any] = {}
        while True:
            matched, last_state = await self._condition_matches(
                condition=condition,
                selector=selector,
                value=value,
                name=name,
                stable_ms=stable_ms,
            )
            if matched:
                return {
                    "condition": condition,
                    "selector": selector,
                    "value": value,
                    "name": name,
                    "matched": True,
                    "timeout": timeout,
                    "elapsed_ms": int((time.monotonic() - start) * 1000),
                    "state": last_state,
                }
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Condition {condition!r} was not met within {timeout} seconds"
                )
            await asyncio.sleep(interval)

    async def element(self, selector: str, timeout: int = 10) -> bool:
        return await self.for_plan(normalize_selector(selector), timeout)

    async def for_plan(self, plan: SelectorPlan, timeout: int = 10) -> bool:
        try:
            waiter = self._page.wait
            if hasattr(waiter, "ele_loaded"):
                result = waiter.ele_loaded(plan.locator, timeout=timeout)
            else:
                result = waiter.eles_loaded(plan.locator, timeout=timeout, any_one=True)
            return bool(result)
        except Exception as exc:
            logger.warning(
                "Element %s (%s) not found within %ss: %s",
                plan.original,
                plan.locator,
                timeout,
                exc,
            )
            return False

    async def url(self, url_pattern: str, timeout: int = 10) -> bool:
        try:
            start_time = time.time()
            while time.time() - start_time < timeout:
                if url_pattern in self._tab.url:
                    return True
                await asyncio.sleep(0.5)
            return False
        except Exception as exc:
            logger.warning(
                "URL pattern %s not matched within %ss: %s",
                url_pattern,
                timeout,
                exc,
            )
            return False

    async def _condition_matches(
        self,
        *,
        condition: str,
        selector: str,
        value: str,
        name: str,
        stable_ms: int,
    ) -> tuple[bool, dict[str, Any]]:
        if condition in {"url_contains", "url_matches"}:
            current_url = self._tab.url
            matched = (
                value in current_url
                if condition == "url_contains"
                else re.search(value, current_url) is not None
            )
            return matched, {"url": current_url}

        if condition in {"text_contains", "text_matches"}:
            text = self._condition_text(selector)
            matched = (
                value in text
                if condition == "text_contains"
                else re.search(value, text) is not None
            )
            return matched, {"text": text[:500]}

        if not selector:
            raise ValueError(f"selector is required for {condition!r}")

        if condition in {
            "attribute_equals",
            "attribute_nonempty",
            "property_equals",
            "property_nonempty",
        }:
            if not name:
                raise ValueError(f"name is required for {condition!r}")
            if condition.startswith("attribute_"):
                observed = await self._tab.elements.attribute(selector, name)
            else:
                observed = await self._tab.elements.property(selector, name)
            text = "" if observed is None else str(observed)
            matched = bool(text) if condition.endswith("_nonempty") else text == value
            return matched, {
                "exists": observed is not None,
                "name": name,
                "value_length": len(text),
                "nonempty": bool(text),
            }

        state = self._selector_state(selector)
        if condition == "present":
            return bool(state.get("exists")), state
        if condition == "visible":
            return bool(state.get("visible")), state
        if condition == "hidden":
            return not bool(state.get("visible")), state
        if condition == "detached":
            return not bool(state.get("exists")), state
        if condition == "clickable":
            return (
                bool(state.get("visible")) and not bool(state.get("disabled"))
            ), state
        if condition == "stable":
            first = state.get("signature")
            if not state.get("exists") or not first:
                return False, state
            await asyncio.sleep(max(0, stable_ms) / 1000)
            second_state = self._selector_state(selector)
            return first == second_state.get("signature"), second_state
        raise ValueError(f"Unsupported wait condition: {condition}")

    def _condition_text(self, selector: str) -> str:
        if not selector:
            try:
                return str(self._page.text)
            except Exception:
                return self._html()
        plan = normalize_selector(selector)
        try:
            element = self._page.ele(plan.locator, timeout=0)
        except Exception:
            return ""
        return str(getattr(element, "text", "") or "") if element else ""

    def _html(self) -> str:
        try:
            return str(self._page.html)
        except Exception:
            return ""

    def _selector_state(self, selector: str) -> dict[str, Any]:
        plan = normalize_selector(selector)
        if plan.locator.startswith(("css:", "xpath:")):
            try:
                result = self._page.run_js(
                    _selector_state_script(plan.locator),
                    as_expr=True,
                )
                if isinstance(result, dict):
                    return result
            except Exception:
                logger.debug("selector state JavaScript failed", exc_info=True)
        return self._selector_state_fallback(plan)

    def _selector_state_fallback(self, plan: SelectorPlan) -> dict[str, Any]:
        try:
            element = self._page.ele(plan.locator, timeout=0)
        except Exception:
            element = None
        exists = bool(element)
        text = str(getattr(element, "text", "") or "") if element else ""
        tag = str(getattr(element, "tag", "") or "") if element else ""
        disabled = False
        if element is not None:
            try:
                disabled_attr = element.attr("disabled")
                aria_disabled = element.attr("aria-disabled")
                disabled = (
                    disabled_attr is not None or str(aria_disabled).lower() == "true"
                )
            except Exception:
                disabled = False
        return {
            "exists": exists,
            "visible": exists,
            "disabled": disabled,
            "tag": tag,
            "text": text[:500],
            "signature": f"{tag}|{text[:100]}|{disabled}",
        }
