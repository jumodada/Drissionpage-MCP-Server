"""JavaScript builder for bounded selector state inspection."""

from __future__ import annotations

import json


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


__all__ = ["_selector_state_script"]
