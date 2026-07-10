"""Tab management for DrissionPage MCP."""

import asyncio
import base64
import json
import logging
import os
import tempfile
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Dict, Optional

from DrissionPage.errors import ElementNotFoundError

from .browser import (
    ElementOperations,
    FrameOperations,
    InteractionOperations,
    NavigationOperations,
    NetworkOperations,
    StorageOperations,
    WaitOperations,
)
from .forms import build_form_inspect_script
from .observation import bounded_json_value, build_observe_script, result_type, safe_int
from .outline import build_page_snapshot_script
from .page_scripts import (
    _extract_links_script,
    _form_fill_preview_script,
)
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
        self.elements = ElementOperations(self)
        self.frames = FrameOperations(self)
        self.interaction = InteractionOperations(self)
        self.navigation = NavigationOperations(self)
        self.network = NetworkOperations(self)
        self.storage = StorageOperations(self)
        self.waits = WaitOperations(self)

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

    async def click(self, x: int, y: int) -> None:
        """Click at coordinates."""
        try:
            self.page.actions.click((x, y))
            await self._stabilize("click", timeout=1.0, fallback_sleep=0.02)
        except Exception as e:
            logger.error(f"Failed to click at ({x}, {y}): {e}")
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

        await self.navigation.navigate(url)
        wait_result = {
            "condition": wait_condition,
            "selector": selector,
            "value": wait_value,
            "matched": wait_condition == "",
            "timeout": wait_timeout,
        }
        if wait_condition:
            wait_result = await self.waits.until(
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
            payload["console"] = await self.console_logs(
                level="all", since=-1, limit=20
            )
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

    def _run_structured_script(self, script: str, error_message: str) -> dict[str, Any]:
        result = self.page.run_js(script, as_expr=True)
        if not isinstance(result, dict):
            raise RuntimeError(error_message)
        return result

    async def _element_by_plan(self, plan: SelectorPlan, *, timeout: int = 10) -> Any:
        if timeout > 0:
            loaded = await self.waits.for_plan(plan, timeout)
            if not loaded:
                raise ElementNotFoundError(f"Element not found: {plan.original}")
        element = self.page.ele(plan.locator, timeout=0)
        if not element:
            raise ElementNotFoundError(f"Element not found: {plan.original}")
        return element

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
        recent = messages[-max(1, int(limit)) :]
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
