"""High-level browser workflows composed from focused tab capabilities."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from ..forms import build_form_inspect_script
from ..page_scripts import _extract_links_script, _form_fill_preview_script
from ..selector import normalize_selector
from ._scripts import run_structured_script

if TYPE_CHECKING:
    from ..tab import PageTab

logger = logging.getLogger(__name__)


class WorkflowOperations:
    """Own bounded multi-step browser workflows and page data extraction."""

    def __init__(self, tab: "PageTab") -> None:
        self._tab = tab

    @property
    def _page(self) -> Any:
        return self._tab.page

    async def inspect_forms(
        self,
        *,
        selector: str = "",
        include_values: bool = False,
        max_forms: int = 10,
        max_fields_per_form: int = 50,
    ) -> dict[str, Any]:
        try:
            return run_structured_script(
                self._page,
                build_form_inspect_script(
                    selector=selector,
                    include_values=include_values,
                    max_forms=max_forms,
                    max_fields_per_form=max_fields_per_form,
                ),
                "form inspect script returned no structured data",
            )
        except Exception as exc:
            logger.error("Failed to inspect forms: %s", exc)
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
        await self._tab.navigation.navigate(url)
        wait_result = {
            "condition": wait_condition,
            "selector": selector,
            "value": wait_value,
            "matched": wait_condition == "",
            "timeout": wait_timeout,
        }
        if wait_condition:
            wait_result = await self._tab.waits.until(
                condition=wait_condition,
                selector=selector,
                value=wait_value,
                timeout=wait_timeout,
            )
        snapshot = await self._tab.observation.snapshot(
            include_html=include_html,
            max_elements=max_elements,
            max_text_chars=max_text_chars,
        )
        payload: dict[str, Any] = {
            "url": url,
            "final_url": self._tab.url,
            "title": str(snapshot.get("title") or self._tab.title),
            "wait": wait_result,
            "snapshot": snapshot,
        }
        if include_forms:
            payload["forms"] = await self.inspect_forms()
        if include_console:
            payload["console"] = await self._tab.observation.console_logs(
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
        plan = normalize_selector(selector)
        result = run_structured_script(
            self._page,
            _extract_links_script(
                locator=plan.locator,
                limit=limit,
                include_text=include_text,
                same_origin_only=same_origin_only,
                absolute_urls=absolute_urls,
                base_url=self._tab.url,
            ),
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
        plan = normalize_selector(form_selector)
        result = run_structured_script(
            self._page,
            _form_fill_preview_script(
                form_locator=plan.locator,
                fields=dict(fields),
                redact_values=redact_values,
            ),
            "form fill preview script returned no structured data",
        )
        return {"form_selector": plan.metadata(), **result}
