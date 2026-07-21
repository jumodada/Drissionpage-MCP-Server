"""JavaScript builders for bounded link and selector state inspection."""

from __future__ import annotations

import json

from .script_fragments import css_text_helpers_script


def _extract_links_script(
    *,
    locator: str,
    limit: int,
    include_text: bool,
    same_origin_only: bool,
    absolute_urls: bool,
    base_url: str,
) -> str:
    return f"""
(() => {{
  const locator = {json.dumps(locator)};
  const limit = {int(limit)};
  const includeText = {json.dumps(include_text)};
  const sameOriginOnly = {json.dumps(same_origin_only)};
  const absoluteUrls = {json.dumps(absolute_urls)};
  const baseUrl = {json.dumps(base_url)};
{css_text_helpers_script()}

  function recommendedSelector(el) {{
    if (el.id) return '#' + cssIdent(el.id);
    const testId = el.getAttribute('data-testid');
    if (testId) return '[data-testid="' + cssString(testId) + '"]';
    let index = 1;
    let sibling = el;
    while ((sibling = sibling.previousElementSibling)) {{
      if (sibling.tagName === el.tagName) index += 1;
    }}
    return (el.tagName || 'a').toLowerCase() + ':nth-of-type(' + index + ')';
  }}

  function selectedNodes() {{
    const strategy = locator.split(':', 1)[0];
    const raw = locator.slice(strategy.length + 1);
    if (strategy === 'xpath' || strategy === 'x') {{
      const result = document.evaluate(
        raw,
        document,
        null,
        XPathResult.ORDERED_NODE_SNAPSHOT_TYPE,
        null
      );
      const nodes = [];
      for (let index = 0; index < result.snapshotLength; index += 1) {{
        const node = result.snapshotItem(index);
        if (node && node.nodeType === Node.ELEMENT_NODE) nodes.push(node);
      }}
      return nodes;
    }}
    const css = strategy === 'css' ? raw : 'a';
    return Array.from(document.querySelectorAll(css));
  }}

  const pageUrl = new URL(window.location.href || baseUrl);
  const allLinks = selectedNodes()
    .filter((el) => (el.tagName || '').toLowerCase() === 'a' || el.href)
    .map((el, index) => {{
      const href = el.getAttribute('href') || '';
      let absolute = '';
      try {{ absolute = href ? new URL(href, pageUrl.href).href : ''; }} catch (_err) {{}}
      return {{
        index,
        text: includeText ? textOf(el).slice(0, 300) : '',
        href,
        url: absoluteUrls ? absolute : href,
        absolute_url: absolute,
        selector: recommendedSelector(el),
        rel: el.getAttribute('rel') || '',
        target: el.getAttribute('target') || '',
        origin: absolute ? new URL(absolute).origin : '',
      }};
    }})
    .filter((item) => !sameOriginOnly || !item.origin || item.origin === pageUrl.origin);

  const selected = allLinks.slice(0, limit).map((item) => {{
    const copy = Object.assign({{}}, item);
    delete copy.origin;
    if (!absoluteUrls) delete copy.absolute_url;
    return copy;
  }});
  return {{
    include_text: includeText,
    same_origin_only: sameOriginOnly,
    absolute_urls: absoluteUrls,
    count: allLinks.length,
    returned: selected.length,
    limit,
    truncated: selected.length < allLinks.length,
    links: selected,
  }};
}})()
"""


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


__all__ = ["_extract_links_script", "_selector_state_script"]
