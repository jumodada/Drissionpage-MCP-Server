"""Wait and observable condition operations for a browser tab."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import TYPE_CHECKING, Any

from DrissionPage.errors import ElementNotFoundError

from ..response_json import redact_public_payload
from ..selector import SelectorPlan, normalize_selector
from ..target import ElementTargetArg, target_label
from .page_state_scripts import _selector_state_script

if TYPE_CHECKING:
    from ..tab import PageTab

logger = logging.getLogger(__name__)


class WaitTimeoutError(TimeoutError):
    """A wait deadline failure with bounded public diagnostics."""

    code = "TIMEOUT"

    def __init__(self, condition: str, elapsed_ms: int, state: dict[str, Any]) -> None:
        super().__init__(f"Condition {condition!r} was not met before its deadline")
        safe_state = redact_public_payload(state)
        if isinstance(safe_state, dict):
            safe_state = {
                str(key)[:64]: value[:500] if isinstance(value, str) else value
                for key, value in list(safe_state.items())[:16]
            }
        self.details = {
            "condition": condition,
            "elapsed_ms": elapsed_ms,
            "last_state": safe_state,
        }


class WaitOperations:
    """Own selector, URL, text, and state waits."""

    def __init__(self, tab: PageTab) -> None:
        self._tab = tab

    @property
    def _page(self) -> Any:
        return self._tab.page

    async def until(
        self,
        *,
        condition: str,
        selector: ElementTargetArg = "",
        value: str = "",
        name: str = "",
        timeout: float = 10,
        interval: float = 0.1,
        stable_ms: int = 300,
    ) -> dict[str, Any]:
        start = time.monotonic()
        timeout_seconds = max(0.0, float(timeout))
        deadline = start + timeout_seconds
        last_state: dict[str, Any] = {}
        while True:
            matched, last_state = await self._condition_matches(
                condition=condition,
                selector=selector,
                value=value,
                name=name,
                stable_ms=stable_ms,
                deadline=deadline,
            )
            now = time.monotonic()
            if matched and (timeout_seconds == 0 or now <= deadline):
                return {
                    "condition": condition,
                    "selector": target_label(selector) if selector else "",
                    "value": value,
                    "name": name,
                    "matched": True,
                    "timeout": timeout,
                    "elapsed_ms": int((now - start) * 1000),
                    "state": last_state,
                }
            if timeout_seconds == 0 or now >= deadline:
                raise WaitTimeoutError(
                    condition,
                    int((now - start) * 1000),
                    last_state,
                )
            await asyncio.sleep(min(interval, deadline - now))

    async def element(self, selector: ElementTargetArg, timeout: float = 10) -> bool:
        if isinstance(selector, str):
            return await self.for_plan(normalize_selector(selector), timeout)
        try:
            await self._tab.dom_targeting.resolve(selector, timeout=timeout)
            return True
        except ElementNotFoundError:
            return False

    async def for_plan(self, plan: SelectorPlan, timeout: float = 10) -> bool:
        try:
            waiter = self._page.wait
            if hasattr(waiter, "ele_loaded"):
                result = waiter.ele_loaded(plan.locator, timeout=timeout)
            else:
                result = waiter.eles_loaded(plan.locator, timeout=timeout, any_one=True)
            return bool(result)
        except Exception as exc:
            logger.warning(
                "Element wait failed within %ss (%s)",
                timeout,
                type(exc).__name__,
            )
            return False

    async def url(self, url_pattern: str, timeout: float = 10) -> bool:
        try:
            timeout_seconds = max(0.0, float(timeout))
            deadline = time.monotonic() + timeout_seconds
            while True:
                if url_pattern in self._tab.url:
                    return timeout_seconds == 0 or time.monotonic() <= deadline
                now = time.monotonic()
                if timeout_seconds == 0 or now >= deadline:
                    return False
                await asyncio.sleep(min(0.5, deadline - now))
        except Exception as exc:
            logger.warning(
                "URL wait failed within %ss (%s)",
                timeout,
                type(exc).__name__,
            )
            return False

    async def _condition_matches(
        self,
        *,
        condition: str,
        selector: ElementTargetArg,
        value: str,
        name: str,
        stable_ms: int,
        deadline: float,
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
            text = await self._condition_text(selector)
            matched = (
                value in text
                if condition == "text_contains"
                else re.search(value, text) is not None
            )
            return matched, {"text": text[:500]}

        if condition == "ready_state":
            if value not in {"interactive", "complete"}:
                raise ValueError(
                    "value must be 'interactive' or 'complete' for 'ready_state'"
                )
            ready_state = self._ready_state()
            matched = ready_state == value or (
                value == "interactive" and ready_state == "complete"
            )
            return matched, {"ready_state": ready_state}

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

        state = await self._selector_state(selector)
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
            stable_seconds = max(0, stable_ms) / 1000
            stable_until = time.monotonic() + stable_seconds
            while True:
                now = time.monotonic()
                if now >= stable_until:
                    return now <= deadline or stable_seconds == 0, state
                if now >= deadline:
                    return False, state
                await asyncio.sleep(min(0.05, stable_until - now, deadline - now))
                state = await self._selector_state(selector)
                signature = state.get("signature")
                if not state.get("exists") or not signature:
                    return False, state
                if signature != first:
                    first = signature
                    stable_until = time.monotonic() + stable_seconds
        raise ValueError(f"Unsupported wait condition: {condition}")

    def _ready_state(self) -> str:
        try:
            return str(self._page.states.ready_state or "")
        except Exception:
            try:
                return str(self._page.run_js("document.readyState", as_expr=True) or "")
            except Exception:
                return ""

    async def _condition_text(self, selector: ElementTargetArg) -> str:
        if not selector:
            try:
                return str(self._page.text)
            except Exception:
                return self._html()
        if isinstance(selector, str):
            plan = normalize_selector(selector)
            try:
                element = self._page.ele(plan.locator, timeout=0)
            except Exception:
                return ""
            return str(getattr(element, "text", "") or "") if element else ""
        try:
            resolved = await self._tab.dom_targeting.resolve(selector, timeout=0)
        except ElementNotFoundError:
            return ""
        return str(getattr(resolved.element, "text", "") or "")

    def _html(self) -> str:
        try:
            return str(self._page.html)
        except Exception:
            return ""

    async def _selector_state(self, selector: ElementTargetArg) -> dict[str, Any]:
        if isinstance(selector, str):
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
                    logger.debug("selector state JavaScript failed")
            return self._selector_state_fallback(plan)
        try:
            resolved = await self._tab.dom_targeting.resolve(selector, timeout=0)
        except ElementNotFoundError:
            return {
                "exists": False,
                "visible": False,
                "disabled": False,
                "tag": "",
                "text": "",
                "signature": "",
            }
        element = resolved.element
        states = element.states
        text = str(getattr(element, "text", "") or "")
        tag = str(getattr(element, "tag", "") or "")
        visible = bool(states.is_displayed)
        disabled = not bool(states.is_enabled)
        return {
            "exists": True,
            "visible": visible,
            "disabled": disabled,
            "tag": tag,
            "text": text[:500],
            "signature": f"{tag}|{text[:100]}|{visible}|{disabled}",
        }

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
