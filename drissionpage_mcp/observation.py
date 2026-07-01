"""Lightweight page observation and bounded JavaScript result helpers."""

from __future__ import annotations

import json
from typing import Any


def build_observe_script(*, max_texts: int, max_text_chars: int) -> str:
    """Return JavaScript for a compact current-page fingerprint."""

    return f"""
(() => {{
  const maxTexts = {int(max_texts)};
  const maxTextChars = {int(max_text_chars)};

  function normalize(value) {{
    return String(value || '').replace(/\\s+/g, ' ').trim();
  }}

  function truncate(value, limit) {{
    value = normalize(value);
    return value.length > limit ? value.slice(0, limit) : value;
  }}

  function visible(el) {{
    if (!el) return false;
    const style = window.getComputedStyle(el);
    if (style.visibility === 'hidden' || style.display === 'none') return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 || rect.height > 0 || el.getClientRects().length > 0;
  }}

  function cssIdent(value) {{
    if (window.CSS && typeof window.CSS.escape === 'function') {{
      return window.CSS.escape(value);
    }}
    return String(value).replace(/[^a-zA-Z0-9_-]/g, '\\\\$&');
  }}

  function selectorFor(el) {{
    if (!el || !el.tagName) return '';
    const tag = el.tagName.toLowerCase();
    if (el.id) return '#' + cssIdent(el.id);
    const testId = el.getAttribute('data-testid');
    if (testId) return '[data-testid="' + String(testId).replace(/"/g, '\\\\"') + '"]';
    const name = el.getAttribute('name');
    if (name) return tag + '[name="' + String(name).replace(/"/g, '\\\\"') + '"]';
    return tag;
  }}

  const textNodes = Array.from(document.querySelectorAll(
    'h1,h2,h3,p,button,a,label,output,li,td,[role="status"],[aria-live]'
  ));
  const seen = new Set();
  const text_samples = [];
  for (const el of textNodes) {{
    if (!visible(el)) continue;
    const text = truncate(el.innerText || el.textContent || '', maxTextChars);
    if (!text || seen.has(text)) continue;
    seen.add(text);
    text_samples.push(text);
    if (text_samples.length >= maxTexts) break;
  }}

  const active = document.activeElement;
  const active_element = active && active !== document.body ? {{
    tag: (active.tagName || '').toLowerCase(),
    selector: selectorFor(active),
    text: truncate(active.innerText || active.value || active.getAttribute('aria-label') || '', maxTextChars),
  }} : null;

  return {{
    url: window.location.href,
    title: document.title || '',
    ready_state: document.readyState,
    counts: {{
      headings: document.querySelectorAll('h1,h2,h3,h4,h5,h6').length,
      links: document.querySelectorAll('a[href]').length,
      buttons: document.querySelectorAll('button,input[type="button"],input[type="submit"],[role="button"]').length,
      inputs: document.querySelectorAll('input,textarea,select').length,
      forms: document.querySelectorAll('form').length,
    }},
    text_samples,
    active_element,
  }};
}})()
"""


def diff_observations(
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return a compact diff between two page observations."""

    before = before or {}
    after = after or {}
    before_counts = _dict(before.get("counts"))
    after_counts = _dict(after.get("counts"))
    before_texts = [str(item) for item in before.get("text_samples") or []]
    after_texts = [str(item) for item in after.get("text_samples") or []]

    all_count_keys = sorted(set(before_counts) | set(after_counts))
    counts_delta = {
        key: int(after_counts.get(key, 0)) - int(before_counts.get(key, 0))
        for key in all_count_keys
    }

    return {
        "url_before": str(before.get("url", "")),
        "url_after": str(after.get("url", "")),
        "url_changed": before.get("url", "") != after.get("url", ""),
        "title_before": str(before.get("title", "")),
        "title_after": str(after.get("title", "")),
        "title_changed": before.get("title", "") != after.get("title", ""),
        "ready_state": str(after.get("ready_state", "")),
        "counts_before": before_counts,
        "counts_after": after_counts,
        "counts_delta": counts_delta,
        "appeared_texts": _bounded_new_items(before_texts, after_texts),
        "removed_texts": _bounded_new_items(after_texts, before_texts),
        "active_element": after.get("active_element"),
    }


def bounded_json_value(
    value: Any,
    *,
    max_chars: int,
) -> tuple[Any, bool, int]:
    """Return a JSON-safe value bounded by *max_chars* serialized characters."""

    text = _json(value)
    if len(text) <= max_chars:
        return value, False, len(text)
    if isinstance(value, str):
        bounded = value[:max_chars]
    else:
        bounded = {"preview": text[:max_chars], "truncated_json": True}
    return bounded, True, len(text)


def result_type(value: Any) -> str:
    """Return a stable JSON-oriented type name for a JavaScript result."""

    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    )


def _dict(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key, item in value.items():
        try:
            result[str(key)] = int(item)
        except (TypeError, ValueError):
            result[str(key)] = 0
    return result


def _bounded_new_items(before: list[str], after: list[str], *, limit: int = 10) -> list[str]:
    before_set = set(before)
    return [item for item in after if item not in before_set][:limit]
