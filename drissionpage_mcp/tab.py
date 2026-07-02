"""Tab management for DrissionPage MCP."""

import asyncio
import base64
import json
import logging
import os
import re
import tempfile
import time
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Dict, Optional

from DrissionPage.errors import ElementNotFoundError

from .forms import build_form_inspect_script
from .observation import bounded_json_value, build_observe_script, result_type
from .outline import build_page_snapshot_script, summarize_elements
from .selector import SelectorPlan, normalize_selector

if TYPE_CHECKING:
    from .context import DrissionPageContext

logger = logging.getLogger(__name__)


class PageTab:
    """Wrapper around a DrissionPage Chromium tab/page object."""

    def __init__(
        self,
        page: Any,
        context: "DrissionPageContext",
        *,
        mcp_tab_id: str = "",
    ):
        # Keep the historical ``page`` attribute name while allowing it to hold
        # DrissionPage 4.2 ChromiumTab objects.
        self.page = page
        self.context = context
        self.mcp_tab_id = mcp_tab_id
        self._url = ""
        self._console_log_cache: list[dict[str, Any]] = []

    @property
    def native_tab_id(self) -> str:
        """Return the underlying DrissionPage tab id when available."""

        try:
            value = getattr(self.page, "tab_id", "")
        except Exception:
            value = ""
        return "" if value is None else str(value)

    @property
    def url(self) -> str:
        """Get the current URL of the tab."""
        try:
            return self.page.url or self._url
        except Exception:
            return self._url

    @property
    def title(self) -> str:
        """Get the current page title for tab summaries."""

        try:
            value = getattr(self.page, "title", "")
        except Exception:
            value = ""
        return "" if value is None else str(value)

    def summary(self, *, active: bool = False) -> Dict[str, Any]:
        """Return a bounded public tab summary."""

        return {
            "id": self.mcp_tab_id,
            "native_id": self.native_tab_id,
            "url": self.url,
            "title": self.title,
            "active": active,
            "connected": self.is_connected(),
        }

    async def navigate(self, url: str) -> None:
        """Navigate to a URL."""
        try:
            result = self.page.get(url)
            if result is False or (hasattr(result, "ok") and result.ok is False):
                raise RuntimeError(f"Navigation failed: {result}")
            self._url = getattr(result, "url", None) or self.page.url or url
            await self._stabilize("navigation", timeout=5.0, fallback_sleep=0.05)
            logger.info(f"Navigated to: {url}")
        except Exception as e:
            logger.error(f"Failed to navigate to {url}: {e}")
            raise

    async def go_back(self) -> None:
        """Go back in history."""
        try:
            self.page.back()
            await self._stabilize("go_back", timeout=5.0, fallback_sleep=0.05)
        except Exception as e:
            logger.error(f"Failed to go back: {e}")
            raise

    async def go_forward(self) -> None:
        """Go forward in history."""
        try:
            self.page.forward()
            await self._stabilize("go_forward", timeout=5.0, fallback_sleep=0.05)
        except Exception as e:
            logger.error(f"Failed to go forward: {e}")
            raise

    async def refresh(self) -> None:
        """Refresh the page."""
        try:
            self.page.refresh()
            await self._stabilize("refresh", timeout=5.0, fallback_sleep=0.05)
        except Exception as e:
            logger.error(f"Failed to refresh: {e}")
            raise

    async def click(self, x: int, y: int) -> None:
        """Click at coordinates."""
        try:
            self.page.actions.click((x, y))
            await self._stabilize("click", timeout=1.0, fallback_sleep=0.02)
        except Exception as e:
            logger.error(f"Failed to click at ({x}, {y}): {e}")
            raise

    async def click_element(self, selector: str, timeout: int = 10) -> None:
        """Click an element by selector."""
        try:
            plan = normalize_selector(selector)
            # Wait for element if timeout is specified
            if timeout > 0:
                loaded = await self._wait_for_selector_plan(plan, timeout)
                if not loaded:
                    raise ElementNotFoundError(f"Element not found: {selector}")

            element = self.page.ele(plan.locator)
            if element:
                element.click()
                await self._stabilize("element_click", timeout=1.0, fallback_sleep=0.02)
            else:
                raise ElementNotFoundError(f"Element not found: {selector}")
        except Exception as e:
            logger.error(f"Failed to click element {selector}: {e}")
            raise

    async def input_text(self, selector: str, text: str, clear: bool = True) -> None:
        """Input text into an element."""
        try:
            plan = normalize_selector(selector)
            element = self.page.ele(plan.locator)
            if element:
                # DrissionPage 4.2.0b20 accepts input(clear=True) but leaves
                # some fields empty in practice. The explicit clear-then-input
                # sequence works across 4.1 and 4.2.
                if clear:
                    element.clear()
                element.input(text)
                await self._stabilize("input_text", timeout=1.0, fallback_sleep=0.02)
            else:
                raise ElementNotFoundError(f"Element not found: {selector}")
        except Exception as e:
            logger.error(f"Failed to input text to {selector}: {e}")
            raise

    async def type_text(
        self, selector: str, text: str, timeout: int = 10, clear: bool = True
    ) -> None:
        """Type text into an element after waiting for it to appear."""
        try:
            plan = normalize_selector(selector)
            if timeout > 0:
                loaded = await self._wait_for_selector_plan(plan, timeout)
                if not loaded:
                    raise ElementNotFoundError(f"Element not found: {selector}")

            await self.input_text(plan.locator, text, clear)
        except Exception as e:
            logger.error(f"Failed to type text to {selector}: {e}")
            raise

    async def find_element(self, selector: str, timeout: int = 10) -> Dict[str, Any]:
        """Find an element and return its information."""
        try:
            plan = normalize_selector(selector)
            # Wait for element to appear
            element_exists = await self._wait_for_selector_plan(plan, timeout)

            if not element_exists:
                raise ElementNotFoundError(f"Element not found: {selector}")

            element = self.page.ele(plan.locator)
            if not element:
                raise ElementNotFoundError(f"Element not found: {selector}")

            # Return element information
            return {
                "found": True,
                **plan.metadata(),
                "text": element.text or "",
                "tag": element.tag if hasattr(element, "tag") else "unknown",
                "html": element.html if hasattr(element, "html") else "",
                "visible": True,  # DrissionPage elements are visible if found
            }
        except Exception as e:
            logger.error(f"Failed to find element {selector}: {e}")
            raise

    async def get_text(self, selector: str = "") -> str:
        """Get text content from element or page."""
        try:
            if selector:
                plan = normalize_selector(selector)
                element = self.page.ele(plan.locator)
                if element:
                    return str(element.text)
                else:
                    raise ElementNotFoundError(f"Element not found: {selector}")
            else:
                # Get page text
                if hasattr(self.page, "text"):
                    return str(self.page.text)
                body = self.page.ele("tag:body", timeout=0)
                if body:
                    return str(body.text)
                return ""
        except Exception as e:
            logger.error(f"Failed to get text from {selector or 'page'}: {e}")
            raise

    async def get_attribute(self, selector: str, attribute: str) -> Optional[str]:
        """Get attribute value from an element."""
        try:
            plan = normalize_selector(selector)
            element = self.page.ele(plan.locator)
            if element:
                value = element.attr(attribute)
                return None if value is None else str(value)
            else:
                raise ElementNotFoundError(f"Element not found: {selector}")
        except Exception as e:
            logger.error(f"Failed to get attribute {attribute} from {selector}: {e}")
            raise

    async def get_property(self, selector: str, property_name: str) -> Any:
        """Get a live DOM property value from an element."""
        try:
            plan = normalize_selector(selector)
            element = self.page.ele(plan.locator)
            if element:
                return element.property(property_name)
            else:
                raise ElementNotFoundError(f"Element not found: {selector}")
        except Exception as e:
            logger.error(f"Failed to get property {property_name} from {selector}: {e}")
            raise

    async def get_html(self, selector: str = "") -> str:
        """Get HTML content."""
        try:
            if selector:
                plan = normalize_selector(selector)
                element = self.page.ele(plan.locator)
                if element:
                    return str(element.html)
                else:
                    raise ElementNotFoundError(f"Element not found: {selector}")
            else:
                return str(self.page.html)
        except Exception as e:
            logger.error(f"Failed to get HTML from {selector or 'page'}: {e}")
            raise

    async def page_snapshot(
        self,
        *,
        include_html: bool = False,
        max_elements: int = 50,
        max_text_chars: int = 4000,
    ) -> Dict[str, Any]:
        """Return a bounded, LLM-friendly current page outline."""

        try:
            script = build_page_snapshot_script(
                include_html=include_html,
                max_elements=max_elements,
                max_text_chars=max_text_chars,
            )
            snapshot = self.page.run_js(script, as_expr=True)
            if not isinstance(snapshot, dict):
                raise RuntimeError("page snapshot script returned no structured data")
            snapshot.setdefault("url", self.url)
            return snapshot
        except Exception as e:
            logger.error(f"Failed to build page snapshot: {e}")
            raise

    async def inspect_forms(
        self,
        *,
        selector: str = "",
        include_values: bool = False,
        max_forms: int = 10,
        max_fields_per_form: int = 50,
    ) -> Dict[str, Any]:
        """Return bounded, LLM-friendly form and field metadata."""

        try:
            script = build_form_inspect_script(
                selector=selector,
                include_values=include_values,
                max_forms=max_forms,
                max_fields_per_form=max_fields_per_form,
            )
            result = self.page.run_js(script, as_expr=True)
            if not isinstance(result, dict):
                raise RuntimeError("form inspect script returned no structured data")
            return result
        except Exception as e:
            logger.error(f"Failed to inspect forms: {e}")
            raise

    async def find_elements(
        self,
        selector: str,
        *,
        limit: int = 20,
        include_html: bool = False,
    ) -> Dict[str, Any]:
        """Find multiple elements and return bounded summaries."""

        try:
            plan = normalize_selector(selector)
            elements = list(self.page.eles(plan.locator, timeout=0) or [])
            summaries, truncated = summarize_elements(
                elements,
                limit=limit,
                include_html=include_html,
            )
            return {
                **plan.metadata(),
                "count": len(elements),
                "returned": len(summaries),
                "limit": limit,
                "truncated": truncated,
                "elements": summaries,
            }
        except Exception as e:
            logger.error(f"Failed to find elements {selector}: {e}")
            raise

    async def observe(
        self,
        *,
        max_texts: int = 20,
        max_text_chars: int = 160,
    ) -> Dict[str, Any]:
        """Return a compact current-page fingerprint."""

        try:
            script = build_observe_script(
                max_texts=max_texts,
                max_text_chars=max_text_chars,
            )
            result = self.page.run_js(script, as_expr=True)
            if not isinstance(result, dict):
                raise RuntimeError("page observe script returned no structured data")
            result.setdefault("url", self.url)
            result.setdefault("title", self.title)
            result.setdefault("ready_state", "")
            result.setdefault("counts", {})
            result.setdefault("text_samples", [])
            result.setdefault("active_element", None)
            result.setdefault("console", self._console_summary(limit=5))
            result.setdefault(
                "limits",
                {"max_texts": max_texts, "max_text_chars": max_text_chars},
            )
            return result
        except Exception as e:
            logger.error(f"Failed to observe page: {e}")
            raise

    def ensure_console_capture(self) -> bool:
        """Start DrissionPage's console capture surface when it is available."""

        console = self._console_surface()
        if console is None:
            return False
        try:
            if bool(getattr(console, "listening", False)):
                return True
            start = getattr(console, "start", None)
            if callable(start):
                start()
            return bool(getattr(console, "listening", False))
        except Exception:
            logger.debug("Could not start DrissionPage console capture", exc_info=True)
            return False

    async def console_logs(
        self,
        *,
        level: str = "all",
        since: int = -1,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """Return bounded console messages from the current tab."""

        console = self._console_surface()
        if console is None:
            return _empty_console_logs(available=False)

        self.ensure_console_capture()
        messages = self._normalized_console_messages()
        level_filter = _normalize_console_level(level)
        filtered = [item for item in messages if int(item["index"]) > int(since)]
        if level_filter != "all":
            filtered = [item for item in filtered if item["level"] == level_filter]

        max_items = max(1, min(int(limit), 100))
        logs = filtered[-max_items:] if int(since) < 0 else filtered[:max_items]

        return {
            "available": True,
            "listening": bool(getattr(console, "listening", False)),
            "count": len(logs),
            "total": len(messages),
            "next_cursor": _next_console_cursor(messages),
            "logs": logs,
        }

    async def evaluate_script(
        self,
        script: str,
        *,
        args: list[Any] | None = None,
        max_chars: int = 4000,
    ) -> Dict[str, Any]:
        """Evaluate a caller-provided JavaScript function body with bounded output."""

        try:
            args = args or []
            args_json = json.dumps(args, ensure_ascii=False, default=str)
            wrapped = (
                "(() => {\n"
                f"  const __mcpArgs = {args_json};\n"
                "  const __mcpFn = function(...args) {\n"
                f"{script}\n"
                "  };\n"
                "  return __mcpFn(...__mcpArgs);\n"
                "})()"
            )
            value = self.page.run_js(wrapped, as_expr=True)
            bounded, truncated, original_chars = bounded_json_value(
                value,
                max_chars=max_chars,
            )
            return {
                "result": bounded,
                "result_type": result_type(value),
                "truncated": truncated,
                "original_json_chars": original_chars,
                "max_chars": max_chars,
            }
        except Exception as e:
            logger.error(f"Failed to evaluate script: {e}")
            raise

    async def wait_until(
        self,
        *,
        condition: str,
        selector: str = "",
        value: str = "",
        timeout: float = 10,
        interval: float = 0.1,
        stable_ms: int = 300,
    ) -> Dict[str, Any]:
        """Wait until a page, URL, text, or element condition is satisfied."""

        start = time.monotonic()
        deadline = start + max(0.0, float(timeout))
        last_state: dict[str, Any] = {}
        while True:
            matched, last_state = await self._wait_condition_matches(
                condition=condition,
                selector=selector,
                value=value,
                stable_ms=stable_ms,
            )
            if matched:
                return {
                    "condition": condition,
                    "selector": selector,
                    "value": value,
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

    async def screenshot(
        self, path: Optional[str] = None, full_page: bool = False
    ) -> str:
        """Take a screenshot."""
        try:
            if path:
                self.page.get_screenshot(path=path, full_page=full_page)
                return path

            try:
                screenshot_data = self.page.get_screenshot(
                    as_base64=True,
                    full_page=full_page,
                )
                if isinstance(screenshot_data, bytes):
                    return base64.b64encode(screenshot_data).decode()
                if isinstance(screenshot_data, str):
                    return screenshot_data
            except TypeError:
                # Older or mocked DrissionPage builds may not accept as_base64.
                pass

            tmp_name = ""
            try:
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                    tmp_name = f.name
                self.page.get_screenshot(path=tmp_name, full_page=full_page)
                with open(tmp_name, "rb") as img_file:
                    return base64.b64encode(img_file.read()).decode()
            finally:
                if tmp_name:
                    try:
                        os.remove(tmp_name)
                    except OSError:
                        pass
        except Exception as e:
            logger.error(f"Failed to take screenshot: {e}")
            raise

    async def wait_for_element(self, selector: str, timeout: int = 10) -> bool:
        """Wait for an element to appear."""
        return await self._wait_for_selector_plan(normalize_selector(selector), timeout)

    async def _wait_for_selector_plan(
        self, plan: SelectorPlan, timeout: int = 10
    ) -> bool:
        """Wait for a normalized selector to appear."""
        try:
            waiter = self.page.wait
            if hasattr(waiter, "ele_loaded"):
                result = waiter.ele_loaded(plan.locator, timeout=timeout)
            else:
                # DrissionPage 4.1/4.2 exposes eles_loaded() instead of the
                # older singular helper.
                result = waiter.eles_loaded(plan.locator, timeout=timeout, any_one=True)
            return bool(result)
        except Exception as e:
            logger.warning(
                "Element %s (%s) not found within %ss: %s",
                plan.original,
                plan.locator,
                timeout,
                e,
            )
            return False

    async def wait_for_url(self, url_pattern: str, timeout: int = 10) -> bool:
        """Wait for URL to match pattern."""
        try:
            # Simple implementation - can be improved with proper pattern matching
            import time

            start_time = time.time()
            while time.time() - start_time < timeout:
                if url_pattern in self.url:
                    return True
                await asyncio.sleep(0.5)
            return False
        except Exception as e:
            logger.warning(
                f"URL pattern {url_pattern} not matched within {timeout}s: {e}"
            )
            return False

    async def resize(self, width: int, height: int) -> None:
        """Resize the browser window."""
        try:
            self.page.set.window.size(width, height)
        except Exception as e:
            logger.error(f"Failed to resize window to {width}x{height}: {e}")
            raise

    def _console_surface(self) -> Any | None:
        try:
            return getattr(self.page, "console", None)
        except Exception:
            logger.debug("Could not access DrissionPage console surface", exc_info=True)
            return None

    def _normalized_console_messages(self) -> list[dict[str, Any]]:
        console = self._console_surface()
        if console is None:
            return []
        try:
            raw_messages = getattr(console, "messages", []) or []
        except Exception:
            logger.debug("Could not read DrissionPage console messages", exc_info=True)
            return []
        try:
            iterable = list(raw_messages)
        except TypeError:
            return list(self._console_log_cache)
        return self._merge_console_messages(iterable)

    def _merge_console_messages(self, raw_messages: list[Any]) -> list[dict[str, Any]]:
        if not raw_messages:
            return list(self._console_log_cache)

        raw_from_zero = [
            _normalize_console_message(message, index)
            for index, message in enumerate(raw_messages)
        ]
        if _console_prefix_matches(self._console_log_cache, raw_from_zero):
            self._console_log_cache = raw_from_zero
            return list(self._console_log_cache)

        seen = {_console_signature(item) for item in self._console_log_cache}
        for message in raw_messages:
            normalized = _normalize_console_message(
                message,
                len(self._console_log_cache),
            )
            signature = _console_signature(normalized)
            if signature in seen:
                continue
            self._console_log_cache.append(normalized)
            seen.add(signature)
        return list(self._console_log_cache)

    def _console_summary(self, *, limit: int = 5) -> dict[str, Any]:
        console = self._console_surface()
        if console is None:
            return {
                "available": False,
                "listening": False,
                "count": 0,
                "total": 0,
                "next_cursor": -1,
                "error_count": 0,
                "warning_count": 0,
                "recent": [],
            }

        self.ensure_console_capture()
        messages = self._normalized_console_messages()
        recent = messages[-max(1, int(limit)):]
        return {
            "available": True,
            "listening": bool(getattr(console, "listening", False)),
            "count": len(recent),
            "total": len(messages),
            "next_cursor": _next_console_cursor(messages),
            "error_count": sum(1 for item in messages if item["level"] == "error"),
            "warning_count": sum(1 for item in messages if item["level"] == "warning"),
            "recent": recent,
        }

    async def _stabilize(
        self,
        action: str,
        *,
        timeout: float = 1.0,
        fallback_sleep: float = 0.02,
    ) -> None:
        """Prefer DrissionPage-native load waits with a bounded async fallback."""

        wait = getattr(self.page, "wait", None)
        doc_loaded = getattr(wait, "doc_loaded", None)
        if callable(doc_loaded):
            call_shapes: tuple[dict[str, Any], ...] = (
                {"timeout": timeout, "raise_err": False},
                {"timeout": timeout},
                {},
            )
            for kwargs in call_shapes:
                try:
                    doc_loaded(**kwargs)
                    return
                except TypeError:
                    continue
                except Exception:
                    logger.debug(
                        "Post-%s stabilization via doc_loaded failed",
                        action,
                        exc_info=True,
                    )
                    break

        await asyncio.sleep(fallback_sleep)

    async def close(self) -> None:
        """Close the tab."""
        try:
            browser = self.context.browser
            tab_id = getattr(self.page, "tab_id", None)
            if browser is not None and tab_id and hasattr(browser, "close_tabs"):
                browser.close_tabs(tab_id)
            elif hasattr(self.page, "close"):
                self.page.close()
            logger.info("Tab closed")
        except Exception as e:
            logger.error(f"Failed to close tab: {e}")

    def is_connected(self) -> bool:
        """Check if the tab is still connected."""
        try:
            # Try to access a basic property
            _ = self.page.url
            return True
        except Exception:
            return False

    async def _wait_condition_matches(
        self,
        *,
        condition: str,
        selector: str,
        value: str,
        stable_ms: int,
    ) -> tuple[bool, dict[str, Any]]:
        if condition in {"url_contains", "url_matches"}:
            current_url = self.url
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
                return str(self.page.text)
            except Exception:
                return self.get_html_sync()
        plan = normalize_selector(selector)
        try:
            element = self.page.ele(plan.locator, timeout=0)
        except Exception:
            return ""
        if not element:
            return ""
        return str(getattr(element, "text", "") or "")

    def get_html_sync(self) -> str:
        try:
            return str(self.page.html)
        except Exception:
            return ""

    def _selector_state(self, selector: str) -> dict[str, Any]:
        plan = normalize_selector(selector)
        if plan.locator.startswith(("css:", "xpath:")):
            try:
                result = self.page.run_js(
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
            element = self.page.ele(plan.locator, timeout=0)
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
                disabled = disabled_attr is not None or str(aria_disabled).lower() == "true"
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


def _selector_state_script(locator: str) -> str:
    strategy, raw = locator.split(":", 1)
    return f"""
(() => {{
  const strategy = {json.dumps(strategy)};
  const raw = {json.dumps(raw)};
  function find() {{
    if (strategy === 'css') return document.querySelector(raw);
    const result = document.evaluate(
      raw,
      document,
      null,
      XPathResult.FIRST_ORDERED_NODE_TYPE,
      null
    );
    return result.singleNodeValue;
  }}
  const el = find();
  if (!el) {{
    return {{
      exists: false,
      visible: false,
      disabled: false,
      tag: '',
      text: '',
      signature: '',
    }};
  }}
  const style = window.getComputedStyle(el);
  const rect = el.getBoundingClientRect();
  const visible = (
    style.visibility !== 'hidden' &&
    style.display !== 'none' &&
    (rect.width > 0 || rect.height > 0 || el.getClientRects().length > 0)
  );
  const disabled = Boolean(el.disabled || el.getAttribute('aria-disabled') === 'true');
  const text = String(el.innerText || el.textContent || el.value || '')
    .replace(/\\s+/g, ' ')
    .trim();
  return {{
    exists: true,
    visible,
    disabled,
    tag: (el.tagName || '').toLowerCase(),
    text: text.slice(0, 500),
    signature: [
      Math.round(rect.x),
      Math.round(rect.y),
      Math.round(rect.width),
      Math.round(rect.height),
      disabled,
      text.slice(0, 100),
    ].join('|'),
  }};
}})()
"""


def _empty_console_logs(*, available: bool) -> dict[str, Any]:
    return {
        "available": available,
        "listening": False,
        "count": 0,
        "total": 0,
        "next_cursor": -1,
        "logs": [],
    }


def _next_console_cursor(messages: list[dict[str, Any]]) -> int:
    if not messages:
        return -1
    return max(_safe_int(item.get("index"), -1) for item in messages)


def _console_prefix_matches(
    cached: list[dict[str, Any]],
    current: list[dict[str, Any]],
) -> bool:
    if len(current) < len(cached):
        return False
    return all(
        _console_signature(cached[index]) == _console_signature(current[index])
        for index in range(len(cached))
    )


def _console_signature(message: dict[str, Any]) -> tuple[str, str, str, int, int, str]:
    return (
        str(message.get("level") or ""),
        str(message.get("text") or ""),
        str(message.get("url") or ""),
        _safe_int(message.get("line"), 0),
        _safe_int(message.get("column"), 0),
        str(message.get("source") or ""),
    )


def _normalize_console_message(message: Any, index: int) -> dict[str, Any]:
    return {
        "index": index,
        "level": _normalize_console_level(_message_field(message, "level", "log")),
        "text": _message_text(message),
        "url": str(_message_field(message, "url", "") or ""),
        "line": _safe_int(_message_field(message, "line", 0), 0),
        "column": _safe_int(_message_field(message, "column", 0), 0),
        "source": str(_message_field(message, "source", "") or ""),
    }


def _message_text(message: Any) -> str:
    if isinstance(message, str):
        return message
    value = _message_field(message, "text", "")
    if value in ("", None):
        value = _message_field(message, "message", "")
    return str(value or "")


def _message_field(message: Any, field: str, default: Any) -> Any:
    if isinstance(message, Mapping):
        return message.get(field, default)
    try:
        return getattr(message, field)
    except Exception:
        return default


def _normalize_console_level(level: Any) -> str:
    value = str(level or "log").lower()
    if value == "warn":
        return "warning"
    if value in {"all", "error", "warning", "info", "log"}:
        return value
    return "log"


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
