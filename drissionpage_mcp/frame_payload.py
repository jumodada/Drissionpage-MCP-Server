"""Frame payload normalization helpers."""

from __future__ import annotations

import logging
from typing import Any

from .outline import summarize_elements

logger = logging.getLogger(__name__)


def _frame_summary(frame: Any, index: int, selector: str = "") -> dict[str, Any]:
    frame_ele = getattr(frame, "frame_ele", None) or frame
    frame_id = _safe_element_attr(frame_ele, "id")
    frame_name = _safe_element_attr(frame_ele, "name")
    if selector:
        frame_selector = selector
    elif frame_id:
        frame_selector = f"#{frame_id}"
    elif frame_name:
        frame_selector = f'iframe[name="{frame_name}"]'
    else:
        frame_selector = f"iframe:nth-of-type({index + 1})"

    return {
        "index": index,
        "selector": frame_selector,
        "id": frame_id,
        "name": frame_name,
        "title": _safe_string_attr(frame, "title"),
        "url": _safe_string_attr(frame, "url"),
    }


def _frame_snapshot_payload(
    frame: Any,
    *,
    include_html: bool = False,
    max_elements: int = 50,
    max_text_chars: int = 4000,
) -> dict[str, Any]:
    text = _safe_string_attr(frame, "text")
    if not text:
        try:
            body = frame.ele("tag:body", timeout=0)
            text = _safe_string_attr(body, "text") if body else ""
        except Exception:
            text = ""
    text_excerpt = text[:max_text_chars]
    text_truncated = len(text) > max_text_chars

    remaining = max(0, max_elements)
    groups: dict[str, tuple[str, ...]] = {
        "headings": ("css:h1,h2,h3,h4,h5,h6",),
        "links": ("css:a",),
        "buttons": ("css:button,input[type='button'],input[type='submit']",),
        "inputs": ("css:input,textarea,select",),
        "forms": ("css:form",),
    }
    payload: dict[str, Any] = {}
    counts: dict[str, int] = {}
    returned_total = 0
    elements_truncated = False
    for name, locators in groups.items():
        elements = _frame_elements(frame, locators)
        counts[name] = len(elements)
        summaries, truncated = summarize_elements(
            elements,
            limit=remaining,
            include_html=include_html,
        )
        payload[name] = summaries
        returned_total += len(summaries)
        remaining = max(0, remaining - len(summaries))
        elements_truncated = elements_truncated or truncated

    return {
        "url": _safe_string_attr(frame, "url"),
        "title": _safe_string_attr(frame, "title"),
        "text_excerpt": text_excerpt,
        **payload,
        "counts": counts,
        "truncated": {
            "text": text_truncated,
            "elements": elements_truncated,
            "returned_elements": returned_total,
        },
        "limits": {
            "max_elements": max_elements,
            "max_text_chars": max_text_chars,
        },
    }


def _frame_elements(frame: Any, locators: tuple[str, ...]) -> list[Any]:
    for locator in locators:
        try:
            return list(frame.eles(locator, timeout=0) or [])
        except Exception:
            logger.debug("Frame element lookup failed for %s", locator, exc_info=True)
    return []


def _safe_string_attr(obj: Any, name: str) -> str:
    try:
        value = getattr(obj, name, "")
    except Exception:
        return ""
    return "" if value is None else str(value)


def _safe_element_attr(element: Any, name: str) -> str:
    attr = getattr(element, "attr", None)
    if callable(attr):
        try:
            value = attr(name)
            return "" if value is None else str(value)
        except Exception:
            return ""
    return _safe_string_attr(element, name)
