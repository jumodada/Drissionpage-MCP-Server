"""Tab management for DrissionPage MCP."""

import asyncio
import base64
import logging
import os
import tempfile
from typing import TYPE_CHECKING, Any, Dict, Optional

from DrissionPage.errors import ElementNotFoundError, PageDisconnectedError

if TYPE_CHECKING:
    from .context import DrissionPageContext

logger = logging.getLogger(__name__)


class PageTab:
    """Wrapper around a DrissionPage Chromium tab/page object."""

    def __init__(self, page: Any, context: "DrissionPageContext"):
        # Keep the historical ``page`` attribute name while allowing it to hold
        # DrissionPage 4.2 ChromiumTab objects.
        self.page = page
        self.context = context
        self._url = ""

    @property
    def url(self) -> str:
        """Get the current URL of the tab."""
        try:
            return self.page.url or self._url
        except (PageDisconnectedError, Exception):
            return self._url

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
            # Wait for element if timeout is specified
            if timeout > 0:
                loaded = await self.wait_for_element(selector, timeout)
                if not loaded:
                    raise ElementNotFoundError(f"Element not found: {selector}")

            element = self.page.ele(selector)
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
            element = self.page.ele(selector)
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
            if timeout > 0:
                loaded = await self.wait_for_element(selector, timeout)
                if not loaded:
                    raise ElementNotFoundError(f"Element not found: {selector}")

            await self.input_text(selector, text, clear)
        except Exception as e:
            logger.error(f"Failed to type text to {selector}: {e}")
            raise

    async def find_element(self, selector: str, timeout: int = 10) -> Dict[str, Any]:
        """Find an element and return its information."""
        try:
            # Wait for element to appear
            element_exists = await self.wait_for_element(selector, timeout)

            if not element_exists:
                raise ElementNotFoundError(f"Element not found: {selector}")

            element = self.page.ele(selector)
            if not element:
                raise ElementNotFoundError(f"Element not found: {selector}")

            # Return element information
            return {
                "found": True,
                "selector": selector,
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
                element = self.page.ele(selector)
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
            element = self.page.ele(selector)
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
            element = self.page.ele(selector)
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
                element = self.page.ele(selector)
                if element:
                    return str(element.html)
                else:
                    raise ElementNotFoundError(f"Element not found: {selector}")
            else:
                return str(self.page.html)
        except Exception as e:
            logger.error(f"Failed to get HTML from {selector or 'page'}: {e}")
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

    async def wait_for_element(self, selector: str, timeout: int = 10) -> bool:
        """Wait for an element to appear."""
        try:
            waiter = self.page.wait
            if hasattr(waiter, "ele_loaded"):
                result = waiter.ele_loaded(selector, timeout=timeout)
            else:
                # DrissionPage 4.1/4.2 exposes eles_loaded() instead of the
                # older singular helper.
                result = waiter.eles_loaded(selector, timeout=timeout, any_one=True)
            return bool(result)
        except Exception as e:
            logger.warning(f"Element {selector} not found within {timeout}s: {e}")
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
        except (PageDisconnectedError, Exception):
            return False
