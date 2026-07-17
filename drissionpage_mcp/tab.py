"""Tab management for DrissionPage MCP."""

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict

from DrissionPage.errors import ElementNotFoundError

from .browser import (
    DialogOperations,
    DownloadOperations,
    ElementOperations,
    FrameOperations,
    InteractionOperations,
    NavigationOperations,
    NetworkOperations,
    ObservationOperations,
    PageOperations,
    PointerOperations,
    StorageOperations,
    TargetResolver,
    WorkflowOperations,
    WaitOperations,
    VisionOperations,
)
from .selector import SelectorPlan

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
        self.dialogs = DialogOperations(self)
        self.downloads = DownloadOperations(self)
        self.elements = ElementOperations(self)
        self.frames = FrameOperations(self)
        self.interaction = InteractionOperations(self)
        self.navigation = NavigationOperations(self)
        self.network = NetworkOperations(self)
        self.observation = ObservationOperations(self)
        self.page_ops = PageOperations(self)
        self.pointer = PointerOperations(self)
        self.storage = StorageOperations(self)
        self.targeting = TargetResolver(self)
        self.waits = WaitOperations(self)
        self.vision = VisionOperations(self)
        self.workflows = WorkflowOperations(self)

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

    async def _element_by_plan(self, plan: SelectorPlan, *, timeout: int = 10) -> Any:
        if timeout > 0:
            loaded = await self.waits.for_plan(plan, timeout)
            if not loaded:
                raise ElementNotFoundError(f"Element not found: {plan.original}")
        element = self.page.ele(plan.locator, timeout=0)
        if not element:
            raise ElementNotFoundError(f"Element not found: {plan.original}")
        return element

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
