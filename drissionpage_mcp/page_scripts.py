"""JavaScript builders for PageTab workflows."""

from __future__ import annotations

import json
from typing import Any


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

  function cssIdent(value) {{
    if (window.CSS && typeof window.CSS.escape === 'function') {{
      return window.CSS.escape(value);
    }}
    return String(value).replace(/[^a-zA-Z0-9_-]/g, '\\\\$&');
  }}

  function cssString(value) {{
    return String(value).split('\\\\').join('\\\\\\\\').replace(/"/g, '\\\\"');
  }}

  function textOf(node) {{
    return (node.innerText || node.textContent || '').replace(/\\s+/g, ' ').trim();
  }}

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


def _form_fill_preview_script(
    *,
    form_locator: str,
    fields: dict[str, Any],
    redact_values: bool,
) -> str:
    return f"""
(() => {{
  const formLocator = {json.dumps(form_locator)};
  const fields = {json.dumps(fields, ensure_ascii=False, default=str)};
  const redactValues = {json.dumps(redact_values)};

  function cssIdent(value) {{
    if (window.CSS && typeof window.CSS.escape === 'function') {{
      return window.CSS.escape(value);
    }}
    return String(value).replace(/[^a-zA-Z0-9_-]/g, '\\\\$&');
  }}

  function cssString(value) {{
    return String(value).split('\\\\').join('\\\\\\\\').replace(/"/g, '\\\\"');
  }}

  function textOf(node) {{
    return (node.innerText || node.textContent || '').replace(/\\s+/g, ' ').trim();
  }}

  function selectedForm() {{
    const strategy = formLocator.split(':', 1)[0];
    const raw = formLocator.slice(strategy.length + 1);
    if (strategy === 'xpath' || strategy === 'x') {{
      const result = document.evaluate(
        raw,
        document,
        null,
        XPathResult.FIRST_ORDERED_NODE_TYPE,
        null
      );
      const node = result.singleNodeValue;
      if (!node) return null;
      return node.matches && node.matches('form') ? node : node.querySelector('form');
    }}
    const css = strategy === 'css' ? raw : 'form';
    const node = document.querySelector(css);
    if (!node) return null;
    return node.matches && node.matches('form') ? node : node.querySelector('form');
  }}

  function labelFor(el) {{
    const id = el.getAttribute('id');
    if (id) {{
      const label = document.querySelector('label[for="' + cssString(id) + '"]');
      if (label) return textOf(label);
    }}
    const wrapping = el.closest ? el.closest('label') : null;
    return wrapping ? textOf(wrapping) : '';
  }}

  function selectorFor(el) {{
    const tag = (el.tagName || 'input').toLowerCase();
    if (el.id) return '#' + cssIdent(el.id);
    const name = el.getAttribute('name');
    if (name) return tag + '[name="' + cssString(name) + '"]';
    let index = 1;
    let sibling = el;
    while ((sibling = sibling.previousElementSibling)) {{
      if (sibling.tagName === el.tagName) index += 1;
    }}
    return tag + ':nth-of-type(' + index + ')';
  }}

  function controls(form) {{
    return Array.from(form.querySelectorAll('input,textarea,select'));
  }}

  function matchesControl(el, key) {{
    const lowered = String(key).toLowerCase();
    const selector = selectorFor(el);
    const options = [
      ['selector', selector],
      ['id', el.getAttribute('id') || ''],
      ['name', el.getAttribute('name') || ''],
      ['label', labelFor(el)],
      ['placeholder', el.getAttribute('placeholder') || ''],
    ];
    for (const [kind, value] of options) {{
      if (value && String(value).toLowerCase() === lowered) return kind;
    }}
    try {{
      if (key && (String(key).startsWith('#') || String(key).startsWith('.') || String(key).includes('['))) {{
        if (el.matches(key)) return 'selector';
      }}
    }} catch (_err) {{}}
    return '';
  }}

  function previewValue(el, value) {{
    const type = String(el.type || el.getAttribute('type') || '').toLowerCase();
    if (redactValues || type === 'password') return '<redacted>';
    if (typeof value === 'boolean') return value ? 'true' : 'false';
    return String(value ?? '');
  }}

  function applyValue(el, value) {{
    const tag = (el.tagName || '').toLowerCase();
    const type = String(el.type || el.getAttribute('type') || '').toLowerCase();
    if (type === 'checkbox' || type === 'radio') {{
      el.checked = Boolean(value);
    }} else if (tag === 'select') {{
      const stringValue = String(value ?? '');
      let matched = false;
      for (const option of Array.from(el.options || [])) {{
        if (option.value === stringValue || textOf(option) === stringValue) {{
          option.selected = true;
          matched = true;
        }} else if (!el.multiple) {{
          option.selected = false;
        }}
      }}
      if (!matched) return 'OPTION_NOT_FOUND';
    }} else {{
      el.value = String(value ?? '');
    }}
    el.dispatchEvent(new Event('input', {{bubbles: true}}));
    el.dispatchEvent(new Event('change', {{bubbles: true}}));
    return '';
  }}

  const form = selectedForm();
  const keys = Object.keys(fields || {{}});
  if (!form) {{
    return {{
      form_found: false,
      form: null,
      field_count: 0,
      filled_count: 0,
      skipped_count: keys.length,
      filled: [],
      skipped: keys.map((key) => ({{key, reason: 'FORM_NOT_FOUND'}})),
      requires_confirmation: true,
      submitted: false,
      redacted: redactValues,
    }};
  }}

  const allControls = controls(form);
  const filled = [];
  const skipped = [];
  for (const key of keys) {{
    const value = fields[key];
    let matched = null;
    let matchedBy = '';
    for (const control of allControls) {{
      matchedBy = matchesControl(control, key);
      if (matchedBy) {{ matched = control; break; }}
    }}
    if (!matched) {{
      skipped.push({{key, reason: 'FIELD_NOT_MATCHED'}});
      continue;
    }}
    if (matched.disabled || matched.readOnly) {{
      skipped.push({{key, reason: matched.disabled ? 'FIELD_DISABLED' : 'FIELD_READONLY'}});
      continue;
    }}
    const applyError = applyValue(matched, value);
    if (applyError) {{
      skipped.push({{key, reason: applyError, selector: selectorFor(matched)}});
      continue;
    }}
    filled.push({{
      key,
      selector: selectorFor(matched),
      matched_by: matchedBy,
      tag: (matched.tagName || '').toLowerCase(),
      type: String(matched.type || matched.getAttribute('type') || '').toLowerCase(),
      value: previewValue(matched, value),
    }});
  }}

  return {{
    form_found: true,
    form: {{
      selector: selectorFor(form),
      id: form.getAttribute('id') || '',
      name: form.getAttribute('name') || '',
      method: (form.getAttribute('method') || 'get').toLowerCase(),
      action: form.action || form.getAttribute('action') || '',
    }},
    field_count: allControls.length,
    filled_count: filled.length,
    skipped_count: skipped.length,
    filled,
    skipped,
    requires_confirmation: true,
    submitted: false,
    redacted: redactValues,
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
