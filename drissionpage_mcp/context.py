"""Context management for DrissionPage MCP."""

import asyncio
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, List, Mapping, Optional

from DrissionPage.errors import PageDisconnectedError

from .compat import create_browser, get_latest_tab, new_tab, quit_browser
from .tab import PageTab

logger = logging.getLogger(__name__)


SENSITIVE_HISTORY_KEYS = {
    "password",
    "passwd",
    "pwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "cookies",
    "text",
    "value",
}


class DrissionPageContext:
    """Manages DrissionPage browser context and tabs."""
    
    def __init__(self, *, history_limit: int = 100):
        self._browser: Optional[Any] = None
        self._current_tab: Optional[PageTab] = None
        self._tabs: List[PageTab] = []
        self._next_tab_index = 0
        self._is_initialized = False
        self._history_limit = history_limit
        self._action_history: Deque[dict[str, Any]] = deque(maxlen=history_limit)
    
    async def initialize(self) -> None:
        """Initialize the browser context."""
        if self._is_initialized:
            return
            
        try:
            # DrissionPage 4.2 deprecates ChromiumPage for new features. Use
            # Chromium + latest_tab and keep the wrapper compatible with 4.0/4.1.
            self._browser = create_browser()

            tab = self._wrap_page(get_latest_tab(self._browser))
            self._tabs.append(tab)
            self._current_tab = tab
            
            self._is_initialized = True
            logger.info("DrissionPage context initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize DrissionPage context: {e}")
            raise
    
    async def ensure_initialized(self) -> None:
        """Ensure the context is initialized."""
        if not self._is_initialized:
            await self.initialize()
    
    def current_tab(self) -> Optional[PageTab]:
        """Get the current active tab."""
        return self._current_tab
    
    def current_tab_or_die(self) -> PageTab:
        """Get the current tab or raise an error."""
        if not self._current_tab:
            raise RuntimeError("No active tab. Use navigate tool to open a page first.")
        return self._current_tab
    
    def tabs(self) -> List[PageTab]:
        """Get all tabs."""
        return self._tabs.copy()

    async def sync_tabs(self) -> List[PageTab]:
        """Synchronize tracked tabs with the underlying browser tab registry."""

        await self.ensure_initialized()
        if not self._browser:
            return []

        pages = self._browser_tabs()
        if not pages:
            latest = get_latest_tab(self._browser)
            pages = [latest]

        existing = {self._tab_key(tab.page): tab for tab in self._tabs}
        synced: list[PageTab] = []
        seen: set[str] = set()
        for page in pages:
            key = self._tab_key(page)
            if key in seen:
                continue
            seen.add(key)
            tab = existing.get(key)
            if tab is None:
                tab = self._wrap_page(page)
            else:
                tab.page = page
            if tab.is_connected():
                synced.append(tab)

        self._tabs = synced
        latest_key = self._tab_key(get_latest_tab(self._browser))
        current = self._find_tab_by_key(latest_key)
        if current is not None:
            self._current_tab = current
        elif self._current_tab not in self._tabs:
            self._current_tab = self._tabs[0] if self._tabs else None
        return self.tabs()

    def tab_summaries(self) -> list[dict[str, Any]]:
        """Return public summaries for currently tracked tabs."""

        current = self._current_tab
        return [tab.summary(active=tab is current) for tab in self._tabs]

    async def switch_tab(self, tab_id: str) -> PageTab:
        """Switch the active tab by MCP id or native DrissionPage id."""

        await self.sync_tabs()
        tab = self._find_tab(tab_id)
        if tab is None:
            raise ValueError(f"Tab not found: {tab_id}")

        if self._browser and hasattr(self._browser, "activate_tab"):
            try:
                self._browser.activate_tab(tab.native_tab_id or tab.page)
            except Exception:
                logger.debug("Browser activate_tab failed", exc_info=True)
        self._current_tab = tab
        return tab

    async def close_tab_by_id(self, tab_id: str) -> None:
        """Close a tab by MCP id or native DrissionPage id."""

        await self.sync_tabs()
        tab = self._find_tab(tab_id)
        if tab is None:
            raise ValueError(f"Tab not found: {tab_id}")
        await self.close_tab(tab)
        if self._browser:
            try:
                await self.sync_tabs()
            except Exception:
                logger.debug("Post-close tab sync failed", exc_info=True)
    
    async def ensure_tab(self) -> PageTab:
        """Ensure there's an active tab, creating one if necessary."""
        await self.ensure_initialized()
        
        if not self._current_tab:
            # Create a new tab if none exists
            if self._browser:
                tab = self._wrap_page(new_tab(self._browser))
                self._tabs.append(tab)
                self._current_tab = tab

        if self._current_tab is None:
            raise RuntimeError("Browser context not initialized")
        return self._current_tab
    
    async def new_tab(self) -> PageTab:
        """Create a new tab."""
        await self.ensure_initialized()
        
        if not self._browser:
            raise RuntimeError("Browser context not initialized")

        tab = self._wrap_page(new_tab(self._browser))
        self._tabs.append(tab)
        self._current_tab = tab
        return tab
    
    async def close_tab(self, tab: Optional[PageTab] = None) -> None:
        """Close a tab."""
        target_tab = tab or self._current_tab
        if not target_tab:
            return
        
        # Remove from tabs list
        if target_tab in self._tabs:
            self._tabs.remove(target_tab)
        
        # Update current tab
        if self._current_tab == target_tab:
            self._current_tab = self._tabs[0] if self._tabs else None
        
        await target_tab.close()
    
    async def close_browser(self) -> None:
        """Close the browser context."""
        if self._browser:
            try:
                quit_browser(self._browser)
            except (PageDisconnectedError, Exception) as e:
                logger.warning(f"Error closing browser: {e}")
            finally:
                self._browser = None
        
        self._tabs.clear()
        self._current_tab = None
        self._is_initialized = False
        logger.info("Browser context closed")
    
    async def cleanup(self) -> None:
        """Clean up all resources."""
        await self.close_browser()

    async def wait(self, seconds: float) -> None:
        """Wait for a specified number of seconds."""
        await asyncio.sleep(seconds)

    def is_active(self) -> bool:
        """Check if the context is active."""
        return self._is_initialized and self._browser is not None

    @property
    def browser(self) -> Optional[Any]:
        """Return the underlying DrissionPage browser object."""
        return self._browser

    def record_action(
        self,
        tool: str,
        args: Mapping[str, Any],
        result: Mapping[str, Any],
        *,
        url_before: str = "",
        url_after: str = "",
        tab_id: str = "",
    ) -> None:
        """Append a redacted tool action to the session history."""

        self._action_history.append(
            {
                "time": datetime.now(timezone.utc).isoformat(),
                "tool": tool,
                "args": _redact_history_value(dict(args)),
                "result": _summarize_result(result),
                "url_before": url_before,
                "url_after": url_after,
                "tab_id": tab_id,
            }
        )

    def action_history(self) -> dict[str, Any]:
        """Return bounded action history for the MCP resource surface."""

        return {
            "available": True,
            "limit": self._history_limit,
            "count": len(self._action_history),
            "actions": list(self._action_history),
        }

    def _wrap_page(self, page: Any) -> PageTab:
        tab = PageTab(page, self, mcp_tab_id=f"t{self._next_tab_index}")
        self._next_tab_index += 1
        return tab

    def _browser_tabs(self) -> list[Any]:
        browser = self._browser
        if browser is None:
            return []

        pages: list[Any] = []
        get_tabs = getattr(browser, "get_tabs", None)
        if callable(get_tabs):
            try:
                pages.extend(_normalize_browser_tab_list(browser, get_tabs()))
            except Exception:
                logger.debug("browser.get_tabs() failed", exc_info=True)

        if not pages:
            tab_ids = getattr(browser, "tab_ids", None)
            if callable(tab_ids):
                try:
                    tab_ids = tab_ids()
                except Exception:
                    tab_ids = None
            if tab_ids:
                for tab_id in list(tab_ids):
                    try:
                        pages.append(browser.get_tab(tab_id))
                    except Exception:
                        logger.debug("browser.get_tab(%s) failed", tab_id, exc_info=True)

        latest = get_latest_tab(browser)
        latest_key = self._tab_key(latest)
        if latest_key and all(self._tab_key(page) != latest_key for page in pages):
            pages.append(latest)
        return pages

    def _find_tab(self, tab_id: str) -> Optional[PageTab]:
        return next(
            (
                tab
                for tab in self._tabs
                if tab.mcp_tab_id == tab_id or tab.native_tab_id == tab_id
            ),
            None,
        )

    def _find_tab_by_key(self, key: str) -> Optional[PageTab]:
        return next((tab for tab in self._tabs if self._tab_key(tab.page) == key), None)

    @staticmethod
    def _tab_key(page: Any) -> str:
        try:
            native_id = getattr(page, "tab_id", "")
        except Exception:
            native_id = ""
        return str(native_id or id(page))


def _normalize_browser_tab_list(browser: Any, value: Any) -> list[Any]:
    if value is None:
        return []
    pages = []
    for item in list(value):
        if isinstance(item, str) and hasattr(browser, "get_tab"):
            pages.append(browser.get_tab(item))
        else:
            pages.append(item)
    return pages


def _redact_history_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        redacted = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if key_text in SENSITIVE_HISTORY_KEYS or any(
                marker in key_text
                for marker in ("password", "secret", "token", "cookie", "api_key")
            ):
                redacted[key] = "<redacted>"
            else:
                redacted[key] = _redact_history_value(item)
        return redacted
    if isinstance(value, list):
        return [_redact_history_value(item) for item in value]
    if isinstance(value, tuple):
        return [_redact_history_value(item) for item in value]
    return value


def _summarize_result(result: Mapping[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": bool(result.get("ok"))}
    if result.get("message"):
        payload["message"] = str(result["message"])[:300]
    error = result.get("error")
    if isinstance(error, Mapping):
        payload["error_code"] = error.get("code")
    data = result.get("data")
    if isinstance(data, Mapping):
        for key in ("url", "final_url", "tab_id", "active_tab_id"):
            if key in data:
                payload[key] = data[key]
        changes = data.get("changes")
        if isinstance(changes, Mapping):
            payload["changes"] = {
                "url_changed": bool(changes.get("url_changed")),
                "title_changed": bool(changes.get("title_changed")),
                "appeared_texts": list(changes.get("appeared_texts") or [])[:3],
                "removed_texts": list(changes.get("removed_texts") or [])[:3],
            }
    return payload
