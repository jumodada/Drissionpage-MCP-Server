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
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, Optional

from DrissionPage.errors import ElementNotFoundError

from .forms import build_form_inspect_script
from .frame_payload import (
    _frame_snapshot_payload,
    _frame_summary,
    _safe_string_attr,
)
from .network_payload import _network_packet_payload
from .observation import bounded_json_value, build_observe_script, result_type, safe_int
from .outline import build_page_snapshot_script, summarize_elements
from .page_scripts import (
    _extract_links_script,
    _form_fill_preview_script,
    _selector_state_script,
)
from .response_errors import ErrorCode
from .selector import SelectorPlan, normalize_selector

if TYPE_CHECKING:
    from .context import DrissionPageContext

logger = logging.getLogger(__name__)


class UnsupportedOperationError(RuntimeError):
    """Raised when the installed DrissionPage build lacks an optional API."""

    code = ErrorCode.UNSUPPORTED_OPERATION


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
        self._network_started_at = ""
        self._network_filters: dict[str, Any] = {}

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
            snapshot = self._run_structured_script(
                script,
                "page snapshot script returned no structured data",
            )
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
            return self._run_structured_script(
                script,
                "form inspect script returned no structured data",
            )
        except Exception as e:
            logger.error(f"Failed to inspect forms: {e}")
            raise

    async def open_and_snapshot(
        self,
        *,
        url: str,
        wait_condition: str = "",
        selector: str = "",
        wait_value: str = "",
        wait_timeout: float = 5.0,
        include_html: bool = False,
        include_forms: bool = False,
        include_console: bool = False,
        max_elements: int = 50,
        max_text_chars: int = 4000,
    ) -> dict[str, Any]:
        """Open a URL, optionally wait, then capture a bounded page snapshot."""

        await self.navigate(url)
        wait_result = {
            "condition": wait_condition,
            "selector": selector,
            "value": wait_value,
            "matched": wait_condition == "",
            "timeout": wait_timeout,
        }
        if wait_condition:
            wait_result = await self.wait_until(
                condition=wait_condition,
                selector=selector,
                value=wait_value,
                timeout=wait_timeout,
            )

        snapshot = await self.page_snapshot(
            include_html=include_html,
            max_elements=max_elements,
            max_text_chars=max_text_chars,
        )
        payload: dict[str, Any] = {
            "url": url,
            "final_url": self.url,
            "title": str(snapshot.get("title") or self.title),
            "wait": wait_result,
            "snapshot": snapshot,
        }
        if include_forms:
            payload["forms"] = await self.inspect_forms(
                selector="",
                include_values=False,
                max_forms=10,
                max_fields_per_form=50,
            )
        if include_console:
            payload["console"] = await self.console_logs(level="all", since=-1, limit=20)
        return payload

    async def extract_links(
        self,
        *,
        selector: str = "a",
        limit: int = 50,
        include_text: bool = True,
        same_origin_only: bool = False,
        absolute_urls: bool = True,
    ) -> dict[str, Any]:
        """Extract bounded link data from the current page."""

        plan = normalize_selector(selector)
        script = _extract_links_script(
            locator=plan.locator,
            limit=limit,
            include_text=include_text,
            same_origin_only=same_origin_only,
            absolute_urls=absolute_urls,
            base_url=self.url,
        )
        result = self._run_structured_script(
            script,
            "link extraction script returned no structured data",
        )
        return {**plan.metadata(), **result}

    async def form_fill_preview(
        self,
        *,
        form_selector: str = "form",
        fields: Mapping[str, Any],
        redact_values: bool = True,
    ) -> dict[str, Any]:
        """Fill matched controls without submitting and return a redacted preview."""

        plan = normalize_selector(form_selector)
        script = _form_fill_preview_script(
            form_locator=plan.locator,
            fields=dict(fields),
            redact_values=redact_values,
        )
        result = self._run_structured_script(
            script,
            "form fill preview script returned no structured data",
        )
        return {"form_selector": plan.metadata(), **result}

    async def network_listen_start(
        self,
        *,
        targets: list[str] | None = None,
        is_regex: bool = False,
        method: str = "",
        resource_type: str = "",
        clear: bool = True,
    ) -> dict[str, Any]:
        """Start DrissionPage's HTTP/XHR/Fetch listener for the current tab."""

        listener = self._network_listener()
        if clear and bool(getattr(listener, "listening", False)):
            self._safe_network_stop(listener)
        elif clear and callable(getattr(listener, "clear", None)):
            listener.clear()

        target_arg: Any = None
        if targets:
            target_arg = targets[0] if len(targets) == 1 else list(targets)

        kwargs: dict[str, Any] = {
            "targets": target_arg,
            "is_regex": is_regex if target_arg is not None else None,
            "method": method or None,
            "res_type": resource_type or None,
        }
        try:
            listener.start(**kwargs)
        except TypeError:
            listener.start(target_arg, is_regex if target_arg is not None else None)

        self._network_started_at = datetime.now(timezone.utc).isoformat()
        self._network_filters = {
            "targets": list(targets or []),
            "is_regex": bool(is_regex),
            "method": method,
            "resource_type": resource_type,
        }
        return {
            "listening": bool(getattr(listener, "listening", False)),
            "filters": dict(self._network_filters),
            "started_at": self._network_started_at,
            "tab_id": self.mcp_tab_id,
            "cleared": bool(clear),
        }

    async def network_listen_wait(
        self,
        *,
        timeout: float = 5.0,
        limit: int = 10,
        include_headers: bool = False,
        include_body: bool = False,
        max_body_chars: int = 2000,
    ) -> dict[str, Any]:
        """Wait for network packets and normalize them into bounded JSON."""

        listener = self._network_listener()
        if not bool(getattr(listener, "listening", False)):
            raise UnsupportedOperationError("Network listener is not listening.")

        raw_packets = await asyncio.to_thread(
            listener.wait,
            count=limit,
            timeout=timeout,
            fit_count=False,
            raise_err=False,
        )
        timed_out = raw_packets is False
        if raw_packets is False or raw_packets is None:
            packets: list[Any] = []
        elif isinstance(raw_packets, list):
            packets = raw_packets
            timed_out = len(packets) < limit
        else:
            packets = [raw_packets]
            timed_out = limit > 1

        normalized = [
            _network_packet_payload(
                packet,
                index=index,
                include_headers=include_headers,
                include_body=include_body,
                max_body_chars=max_body_chars,
            )
            for index, packet in enumerate(packets[:limit])
        ]
        return {
            "listening": bool(getattr(listener, "listening", False)),
            "timed_out": bool(timed_out),
            "count": len(normalized),
            "limit": limit,
            "packets": normalized,
        }

    async def network_listen_stop(self, *, clear: bool = True) -> dict[str, Any]:
        """Stop DrissionPage's listener for the current tab."""

        listener = self._network_listener()
        was_listening = bool(getattr(listener, "listening", False))
        if was_listening:
            self._safe_network_stop(listener, clear=clear)
        elif clear and callable(getattr(listener, "clear", None)):
            listener.clear()
        return {
            "listening": bool(getattr(listener, "listening", False)),
            "was_listening": was_listening,
            "cleared": bool(clear),
        }

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
            result = self._run_structured_script(
                script,
                "page observe script returned no structured data",
            )
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

    async def upload_file(
        self, selector: str, paths: list[str], timeout: int = 10
    ) -> dict[str, Any]:
        """Set one or more files on a file input element."""

        try:
            plan = normalize_selector(selector)
            element = await self._element_by_plan(plan, timeout=timeout)
            element.input(paths)
            await self._stabilize("upload_file", timeout=1.0, fallback_sleep=0.02)
            return {
                **plan.metadata(),
                "uploaded": True,
                "file_count": len(paths),
                "filenames": [os.path.basename(path) for path in paths],
            }
        except Exception as e:
            logger.error(f"Failed to upload file into {selector}: {e}")
            raise

    async def scroll_page(
        self,
        *,
        direction: str = "down",
        pixels: int = 300,
        x: int = 0,
        y: int = 0,
    ) -> dict[str, Any]:
        """Scroll the current page."""

        try:
            scroll = getattr(self.page, "scroll", None)
            if scroll is None:
                raise RuntimeError("Current page does not expose DrissionPage scroll API.")
            if direction == "down":
                scroll.down(pixels)
            elif direction == "up":
                scroll.up(pixels)
            elif direction == "left":
                scroll.left(pixels)
            elif direction == "right":
                scroll.right(pixels)
            elif direction == "top":
                scroll.to_top()
            elif direction == "bottom":
                scroll.to_bottom()
            elif direction == "half":
                scroll.to_half()
            elif direction == "position":
                scroll.to_location(x, y)
            else:
                raise ValueError(f"Unsupported scroll direction: {direction}")
            await self._stabilize("page_scroll", timeout=0.5, fallback_sleep=0.02)
            return {"direction": direction, "pixels": pixels, "x": x, "y": y, "url": self.url}
        except Exception as e:
            logger.error(f"Failed to scroll page: {e}")
            raise

    async def scroll_element_into_view(
        self, selector: str, *, center: bool = True, timeout: int = 10
    ) -> dict[str, Any]:
        """Scroll an element into the viewport."""

        try:
            plan = normalize_selector(selector)
            element = await self._element_by_plan(plan, timeout=timeout)
            element.scroll.to_see(center=center)
            await self._stabilize("element_scroll_into_view", timeout=0.5, fallback_sleep=0.02)
            return {**plan.metadata(), "center": center, "url": self.url}
        except Exception as e:
            logger.error(f"Failed to scroll element into view {selector}: {e}")
            raise

    async def hover_element(
        self,
        selector: str,
        *,
        timeout: int = 10,
        offset_x: int | None = None,
        offset_y: int | None = None,
    ) -> dict[str, Any]:
        """Hover an element."""

        try:
            plan = normalize_selector(selector)
            element = await self._element_by_plan(plan, timeout=timeout)
            element.hover(offset_x=offset_x, offset_y=offset_y)
            await self._stabilize("element_hover", timeout=0.5, fallback_sleep=0.02)
            return {
                **plan.metadata(),
                "url": self.url,
                "offset_x": offset_x,
                "offset_y": offset_y,
            }
        except Exception as e:
            logger.error(f"Failed to hover element {selector}: {e}")
            raise

    async def keyboard_press(
        self, keys: str, *, interval: float = 0
    ) -> dict[str, Any]:
        """Send keys to the active element/page."""

        try:
            self.page.actions.type(keys, interval=interval)
            await self._stabilize("keyboard_press", timeout=0.5, fallback_sleep=0.02)
            return {"keys": keys, "interval": interval, "url": self.url}
        except Exception as e:
            logger.error(f"Failed to press keyboard keys: {e}")
            raise

    async def select_element(
        self,
        selector: str,
        *,
        value: str,
        by: str = "value",
        timeout: int = 10,
    ) -> dict[str, Any]:
        """Select an option from a select element by value, text, or index."""

        try:
            plan = normalize_selector(selector)
            element = await self._element_by_plan(plan, timeout=timeout)
            select = element.select
            if by == "value":
                select.by_value(value, timeout=timeout)
            elif by == "text":
                select.by_text(value, timeout=timeout)
            elif by == "index":
                select.by_index(int(value), timeout=timeout)
            else:
                raise ValueError(f"Unsupported select mode: {by}")
            await self._stabilize("element_select", timeout=0.5, fallback_sleep=0.02)
            return {**plan.metadata(), "selected": True, "by": by, "value": value}
        except Exception as e:
            logger.error(f"Failed to select option for {selector}: {e}")
            raise

    async def check_element(
        self,
        selector: str,
        *,
        checked: bool = True,
        by_js: bool = False,
        timeout: int = 10,
    ) -> dict[str, Any]:
        """Set a checkbox or radio element to the requested checked state."""

        try:
            plan = normalize_selector(selector)
            element = await self._element_by_plan(plan, timeout=timeout)
            element.check(uncheck=not checked, by_js=by_js)
            await self._stabilize("element_check", timeout=0.5, fallback_sleep=0.02)
            return {**plan.metadata(), "checked": checked, "by_js": by_js}
        except Exception as e:
            logger.error(f"Failed to check element {selector}: {e}")
            raise

    async def list_frames(self, *, limit: int = 20) -> dict[str, Any]:
        """List iframe/frame contexts on the current page."""

        try:
            frames = self._frames()
            summaries = [
                _frame_summary(frame, index)
                for index, frame in enumerate(frames[: max(0, limit)])
            ]
            return {
                "count": len(frames),
                "returned": len(summaries),
                "limit": limit,
                "frames": summaries,
            }
        except Exception as e:
            logger.error(f"Failed to list frames: {e}")
            raise

    async def frame_snapshot(
        self,
        *,
        frame_selector: str = "",
        frame_index: int = 0,
        include_html: bool = False,
        max_elements: int = 50,
        max_text_chars: int = 4000,
        timeout: int = 3,
    ) -> dict[str, Any]:
        """Return a bounded page snapshot from a selected iframe."""

        try:
            frame, index = self._resolve_frame(
                frame_selector=frame_selector,
                frame_index=frame_index,
                timeout=timeout,
            )
            result = _frame_snapshot_payload(
                frame,
                include_html=include_html,
                max_elements=max_elements,
                max_text_chars=max_text_chars,
            )
            return {"frame": _frame_summary(frame, index, frame_selector), **result}
        except Exception as e:
            logger.error(f"Failed to capture frame snapshot: {e}")
            raise

    async def frame_find(
        self,
        *,
        selector: str,
        frame_selector: str = "",
        frame_index: int = 0,
        timeout: int = 3,
    ) -> dict[str, Any]:
        """Find one element inside a selected iframe."""

        try:
            frame, index = self._resolve_frame(
                frame_selector=frame_selector,
                frame_index=frame_index,
                timeout=timeout,
            )
            plan = normalize_selector(selector)
            element = frame.ele(plan.locator, timeout=timeout)
            if not element:
                raise ElementNotFoundError(f"Element not found: {selector}")
            return {
                "frame": _frame_summary(frame, index, frame_selector),
                "element": _element_info(element, plan),
            }
        except Exception as e:
            logger.error(f"Failed to find frame element {selector}: {e}")
            raise

    async def shadow_find(
        self,
        *,
        host_selector: str,
        selector: str,
        timeout: int = 3,
    ) -> dict[str, Any]:
        """Find one element inside an open shadow root."""

        try:
            host_plan, root = await self._shadow_root(host_selector, timeout=timeout)
            target_plan = normalize_selector(selector)
            element = root.ele(target_plan.locator, timeout=timeout)
            if not element:
                raise ElementNotFoundError(f"Element not found: {selector}")
            return {
                "host": host_plan.metadata(),
                "element": _element_info(element, target_plan),
            }
        except Exception as e:
            logger.error(f"Failed to find shadow element {selector}: {e}")
            raise

    async def shadow_find_all(
        self,
        *,
        host_selector: str,
        selector: str,
        limit: int = 20,
        include_html: bool = False,
    ) -> dict[str, Any]:
        """Find multiple elements inside an open shadow root."""

        try:
            host_plan, root = await self._shadow_root(host_selector, timeout=3)
            target_plan = normalize_selector(selector)
            elements = list(root.eles(target_plan.locator, timeout=0) or [])
            summaries, truncated = summarize_elements(
                elements,
                limit=limit,
                include_html=include_html,
            )
            return {
                "host": host_plan.metadata(),
                "target": target_plan.metadata(),
                "count": len(elements),
                "returned": len(summaries),
                "limit": limit,
                "truncated": truncated,
                "elements": summaries,
            }
        except Exception as e:
            logger.error(f"Failed to find shadow elements {selector}: {e}")
            raise

    async def cookies_get(
        self,
        *,
        all_domains: bool = False,
        all_info: bool = False,
        include_values: bool = False,
    ) -> dict[str, Any]:
        """Return normalized browser cookies with opt-in values."""

        try:
            cookies = self._cookies(
                all_domains=all_domains,
                all_info=all_info,
                include_values=include_values,
            )
            return {
                "count": len(cookies),
                "include_values": include_values,
                "all_domains": all_domains,
                "cookies": cookies,
            }
        except Exception as e:
            logger.error(f"Failed to read cookies: {e}")
            raise

    async def storage_get(
        self, *, area: str = "local", key: str = "", include_values: bool = True
    ) -> dict[str, Any]:
        """Read localStorage or sessionStorage."""

        try:
            return self._storage_get(area=area, key=key, include_values=include_values)
        except Exception as e:
            logger.error(f"Failed to read {area} storage: {e}")
            raise

    async def storage_set(self, *, area: str, key: str, value: str) -> dict[str, Any]:
        """Set localStorage or sessionStorage item."""

        try:
            storage_name = _storage_name(area)
            self.page.run_js(
                (
                    "(() => {"
                    f"{storage_name}.setItem({json.dumps(key)}, {json.dumps(value)});"
                    "return true;"
                    "})()"
                ),
                as_expr=True,
            )
            return {"area": area, "key": key, "set": True}
        except Exception as e:
            logger.error(f"Failed to set {area} storage key {key}: {e}")
            raise

    async def storage_clear(self, *, area: str, key: str = "") -> dict[str, Any]:
        """Clear one or all localStorage/sessionStorage items."""

        try:
            storage_name = _storage_name(area)
            if key:
                script = f"{storage_name}.removeItem({json.dumps(key)});"
            else:
                script = f"{storage_name}.clear();"
            self.page.run_js(f"(() => {{{script} return true;}})()", as_expr=True)
            return {"area": area, "key": key, "cleared": True}
        except Exception as e:
            logger.error(f"Failed to clear {area} storage: {e}")
            raise

    def session_state(self) -> dict[str, Any]:
        """Return a redacted current-tab state summary for MCP Resources."""

        return {
            "available": True,
            "browser_active": bool(self.context and self.context.is_active()),
            "current_url": self.url,
            "cookies": {
                "count": len(self._cookies(include_values=False)),
                "names": [
                    cookie["name"]
                    for cookie in self._cookies(include_values=False)
                    if cookie.get("name")
                ],
            },
            "storage": {
                "local": _storage_summary(
                    self._storage_get(area="local", include_values=False)
                ),
                "session": _storage_summary(
                    self._storage_get(area="session", include_values=False)
                ),
            },
        }

    def _network_listener(self) -> Any:
        listener = getattr(self.page, "listen", None)
        if listener is None:
            raise UnsupportedOperationError(
                "Network listener is unavailable on this DrissionPage tab."
            )
        required = ("start", "wait", "stop")
        missing = [name for name in required if not callable(getattr(listener, name, None))]
        if missing:
            raise UnsupportedOperationError(
                "Network listener is unsupported; missing: " + ", ".join(missing)
            )
        return listener

    def _safe_network_stop(self, listener: Any, *, clear: bool = True) -> None:
        try:
            if clear:
                listener.stop()
            else:
                pause = getattr(listener, "pause", None)
                if callable(pause):
                    pause(clear=False)
                else:
                    listener.stop()
        except AttributeError:
            logger.debug("Network listener stop hit a partial driver state", exc_info=True)
        except Exception:
            logger.debug("Network listener stop failed", exc_info=True)
            raise

    def _console_surface(self) -> Any | None:
        try:
            return getattr(self.page, "console", None)
        except Exception:
            logger.debug("Could not access DrissionPage console surface", exc_info=True)
            return None

    def _run_structured_script(self, script: str, error_message: str) -> dict[str, Any]:
        result = self.page.run_js(script, as_expr=True)
        if not isinstance(result, dict):
            raise RuntimeError(error_message)
        return result

    async def _element_by_plan(
        self, plan: SelectorPlan, *, timeout: int = 10
    ) -> Any:
        if timeout > 0:
            loaded = await self._wait_for_selector_plan(plan, timeout)
            if not loaded:
                raise ElementNotFoundError(f"Element not found: {plan.original}")
        element = self.page.ele(plan.locator, timeout=0)
        if not element:
            raise ElementNotFoundError(f"Element not found: {plan.original}")
        return element

    def _frames(self) -> list[Any]:
        get_frames = getattr(self.page, "get_frames", None)
        if not callable(get_frames):
            return []
        try:
            raw_frames = list(get_frames(timeout=0) or [])
        except TypeError:
            raw_frames = list(get_frames() or [])
        frames: list[Any] = []
        for raw in raw_frames:
            frame = self._coerce_frame(raw)
            if frame is not None:
                frames.append(frame)
        return frames

    def _coerce_frame(self, frame_like: Any) -> Any | None:
        if hasattr(frame_like, "frame_ele") or (
            hasattr(frame_like, "ele") and hasattr(frame_like, "run_js")
        ):
            return frame_like
        get_frame = getattr(self.page, "get_frame", None)
        if not callable(get_frame):
            return None
        try:
            return get_frame(frame_like, timeout=0)
        except Exception:
            logger.debug("Could not resolve frame object", exc_info=True)
            return None

    def _resolve_frame(
        self,
        *,
        frame_selector: str = "",
        frame_index: int = 0,
        timeout: int = 3,
    ) -> tuple[Any, int]:
        if frame_selector:
            plan = normalize_selector(frame_selector)
            get_frame = getattr(self.page, "get_frame", None)
            if not callable(get_frame):
                raise ElementNotFoundError("Frames are not supported by this page")
            frame = get_frame(plan.locator, timeout=timeout)
            if not frame:
                raise ElementNotFoundError(f"Frame not found: {frame_selector}")
            frames = self._frames()
            index = next(
                (idx for idx, candidate in enumerate(frames) if candidate is frame),
                max(0, frame_index),
            )
            return frame, index

        frames = self._frames()
        if frame_index < 0 or frame_index >= len(frames):
            raise ElementNotFoundError(f"Frame index not found: {frame_index}")
        return frames[frame_index], frame_index

    async def _shadow_root(
        self, host_selector: str, *, timeout: int = 3
    ) -> tuple[SelectorPlan, Any]:
        host_plan = normalize_selector(host_selector)
        host = await self._element_by_plan(host_plan, timeout=timeout)
        root = getattr(host, "shadow_root", None)
        if not root:
            raise ElementNotFoundError(f"Shadow root not found: {host_selector}")
        return host_plan, root

    def _cookies(
        self,
        *,
        all_domains: bool = False,
        all_info: bool = False,
        include_values: bool = False,
    ) -> list[dict[str, Any]]:
        raw = self.page.cookies(all_domains=all_domains, all_info=all_info)
        if isinstance(raw, Mapping):
            items = [
                {"name": str(name), "value": value}
                for name, value in raw.items()
            ]
        else:
            try:
                items = list(raw or [])
            except TypeError:
                items = []
        return [_normalize_cookie(item, include_values=include_values) for item in items]

    def _storage_get(
        self, *, area: str = "local", key: str = "", include_values: bool = True
    ) -> dict[str, Any]:
        storage_name = _storage_name(area)
        script = f"""
(() => {{
  const storage = {storage_name};
  const key = {json.dumps(key)};
  const items = {{}};
  if (key) {{
    const value = storage.getItem(key);
    if (value !== null) items[key] = value;
  }} else {{
    for (let i = 0; i < storage.length; i += 1) {{
      const itemKey = storage.key(i);
      if (itemKey !== null) items[itemKey] = storage.getItem(itemKey);
    }}
  }}
  return items;
}})()
"""
        result = self.page.run_js(script, as_expr=True)
        items = dict(result) if isinstance(result, Mapping) else {}
        if not include_values:
            items = {
                str(item_key): "<redacted>" if item_value not in ("", None) else ""
                for item_key, item_value in items.items()
            }
        else:
            items = {
                str(item_key): "" if item_value is None else str(item_value)
                for item_key, item_value in items.items()
            }
        return {
            "area": area,
            "key": key,
            "include_values": include_values,
            "count": len(items),
            "items": items,
        }

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

    async def close(self) -> bool:
        """Close the tab."""
        try:
            browser = self.context.browser
            tab_id = getattr(self.page, "tab_id", None)
            if browser is not None and tab_id and hasattr(browser, "close_tabs"):
                browser.close_tabs(tab_id)
            elif hasattr(self.page, "close"):
                self.page.close()
            logger.info("Tab closed")
            return True
        except Exception as e:
            logger.error(f"Failed to close tab: {e}")
            return False

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


def _element_info(element: Any, plan: SelectorPlan) -> dict[str, Any]:
    return {
        "found": True,
        **plan.metadata(),
        "text": _safe_string_attr(element, "text"),
        "tag": _safe_string_attr(element, "tag") or "unknown",
        "html": _safe_string_attr(element, "html"),
        "visible": True,
    }


def _normalize_cookie(cookie: Any, *, include_values: bool = False) -> dict[str, Any]:
    if isinstance(cookie, Mapping):
        get = cookie.get
    else:
        def get(name: str, default: Any = None) -> Any:
            return getattr(cookie, name, default)

    value = get("value", "")
    if not include_values and value not in ("", None):
        value = "<redacted>"
    return {
        "name": "" if get("name", "") is None else str(get("name", "")),
        "value": "" if value is None else str(value),
        "domain": "" if get("domain", "") is None else str(get("domain", "")),
        "path": "" if get("path", "") is None else str(get("path", "")),
        "expires": get("expires", None),
        "secure": bool(get("secure", False)),
        "http_only": bool(get("httpOnly", get("http_only", False))),
    }


def _storage_name(area: str) -> str:
    if area == "local":
        return "localStorage"
    if area == "session":
        return "sessionStorage"
    raise ValueError(f"Unsupported storage area: {area}")


def _storage_summary(storage_payload: dict[str, Any]) -> dict[str, Any]:
    items = storage_payload.get("items") or {}
    keys = sorted(str(key) for key in items.keys()) if isinstance(items, Mapping) else []
    return {"count": len(keys), "keys": keys}


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
    return max(safe_int(item.get("index"), -1) for item in messages)


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
        safe_int(message.get("line"), 0),
        safe_int(message.get("column"), 0),
        str(message.get("source") or ""),
    )


def _normalize_console_message(message: Any, index: int) -> dict[str, Any]:
    return {
        "index": index,
        "level": _normalize_console_level(_message_field(message, "level", "log")),
        "text": _message_text(message),
        "url": str(_message_field(message, "url", "") or ""),
        "line": safe_int(_message_field(message, "line", 0), 0),
        "column": safe_int(_message_field(message, "column", 0), 0),
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
