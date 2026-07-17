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


def _form_fill_resolve_script(
    *,
    form_locator: str,
    fields: dict[str, Any],
    redact_values: bool,
) -> str:
    """Resolve and classify form controls without mutating page state."""

    return f"""
(() => {{
  const formLocator = {json.dumps(form_locator)};
  const fields = {json.dumps(fields, ensure_ascii=False)};
  const redactValues = {json.dumps(redact_values)};

  function textOf(node) {{ return String(node && (node.innerText || node.textContent) || '').replace(/\\s+/g, ' ').trim(); }}
  function cssIdent(value) {{
    if (window.CSS && typeof window.CSS.escape === 'function') return window.CSS.escape(value);
    return String(value).replace(/[^a-zA-Z0-9_-]/g, '\\$&');
  }}
  function cssString(value) {{
    return String(value).split('\\\\').join('\\\\\\\\').replace(/"/g, '\\\\"');
  }}
  function selectedForm() {{
    const xpath = formLocator.match(/^(?:xpath|x)[:=](.*)$/s);
    const css = formLocator.match(/^css[:=](.*)$/s);
    let node = null;
    if (xpath) node = document.evaluate(xpath[1], document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
    else node = document.querySelector(css ? css[1] : 'form');
    if (!node) return null;
    return node.matches && node.matches('form') ? node : (node.querySelector && node.querySelector('form'));
  }}
  function labelFor(form, el) {{
    const id = el.getAttribute('id');
    if (id) {{ const label = form.querySelector('label[for="' + cssString(id) + '"]'); if (label) return textOf(label); }}
    const wrapping = el.closest ? el.closest('label') : null;
    return wrapping && form.contains(wrapping) ? textOf(wrapping) : '';
  }}
  function selectorFor(el, scope = document) {{
    const tag = (el.tagName || 'element').toLowerCase();
    if (el.id && scope.querySelectorAll('#' + cssIdent(el.id)).length === 1) return '#' + cssIdent(el.id);
    const testId = el.getAttribute('data-testid');
    if (testId && scope.querySelectorAll('[data-testid="' + cssString(testId) + '"]').length === 1) return '[data-testid="' + cssString(testId) + '"]';
    const name = el.getAttribute('name');
    if (name && scope.querySelectorAll(tag + '[name="' + cssString(name) + '"]').length === 1) return tag + '[name="' + cssString(name) + '"]';
    const aria = el.getAttribute('aria-label');
    if (aria && scope.querySelectorAll(tag + '[aria-label="' + cssString(aria) + '"]').length === 1) return tag + '[aria-label="' + cssString(aria) + '"]';
    const parts = []; let current = el;
    while (current && current.nodeType === Node.ELEMENT_NODE) {{
      const currentTag = (current.tagName || 'element').toLowerCase();
      let index = 1; let sibling = current;
      while ((sibling = sibling.previousElementSibling)) {{ if (sibling.tagName === current.tagName) index += 1; }}
      parts.unshift(currentTag + ':nth-of-type(' + index + ')');
      if (current === document.documentElement) break;
      current = current.parentElement;
    }}
    return parts.join(' > ');
  }}
  function relativeSelectorFor(form, el) {{
    if (el.id && form.querySelectorAll('#' + cssIdent(el.id)).length === 1) return '#' + cssIdent(el.id);
    const testId = el.getAttribute('data-testid');
    if (testId && form.querySelectorAll('[data-testid="' + cssString(testId) + '"]').length === 1) return '[data-testid="' + cssString(testId) + '"]';
    const parts = []; let current = el;
    while (current && current !== form) {{
      const tag = (current.tagName || 'element').toLowerCase();
      let index = 1; let sibling = current;
      while ((sibling = sibling.previousElementSibling)) {{ if (sibling.tagName === current.tagName) index += 1; }}
      parts.unshift(tag + ':nth-of-type(' + index + ')'); current = current.parentElement;
    }}
    return parts.join(' > ');
  }}
  function controlType(el) {{
    const role = String(el.getAttribute('role') || '').toLowerCase();
    if (el.isContentEditable) return 'contenteditable';
    const tag = (el.tagName || '').toLowerCase();
    const type = String(el.type || el.getAttribute('type') || tag).toLowerCase();
    if (tag === 'input' && ['checkbox', 'radio'].includes(type)) return type;
    if (tag === 'select') return el.multiple ? 'select-multiple' : 'select-one';
    if (['combobox', 'listbox'].includes(role)) return role;
    return type;
  }}
  function controls(form) {{
    return Array.from(form.querySelectorAll('input,textarea,select,[contenteditable="true"],[role="combobox"],[role="listbox"],[role="switch"]'));
  }}
  function exact(value, key) {{ return value && String(value) === String(key); }}
  function sameText(value, key) {{ return value && String(value).toLowerCase() === String(key).toLowerCase(); }}
  function matchControl(form, allControls, key) {{
    if (String(key).startsWith('#')) {{
      for (const control of allControls) if (exact(selectorFor(control), key)) return {{control, matchedBy: 'selector'}};
    }}
    for (const [kind, read] of [
      ['id', (el) => el.id || ''], ['name', (el) => el.getAttribute('name') || ''],
      ['label', (el) => labelFor(form, el)], ['placeholder', (el) => el.getAttribute('placeholder') || ''],
    ]) {{
      for (const control of allControls) {{
        const value = read(control);
        const matches = ['label', 'placeholder'].includes(kind) ? sameText(value, key) : exact(value, key);
        if (matches) return {{control, matchedBy: kind}};
      }}
    }}
    try {{ const node = form.querySelector(String(key)); if (node && allControls.includes(node)) return {{control: node, matchedBy: 'explicit_css'}}; }} catch (_err) {{}}
    return {{control: null, matchedBy: ''}};
  }}
  function optionMatches(option, requested) {{ return String(option.value) === String(requested) || textOf(option) === String(requested); }}
  function selectModes(el, value) {{
    const requested = Array.isArray(value) ? value.map(String) : [String(value)];
    if (!el.multiple && requested.length !== 1) return {{reason: 'INVALID_VALUE_TYPE', modes: []}};
    const modes = [];
    for (const item of requested) {{
      const options = Array.from(el.options || []);
      if (options.some((option) => String(option.value) === item)) modes.push('value');
      else if (options.some((option) => textOf(option) === item)) modes.push('text');
      else return {{reason: 'OPTION_NOT_FOUND', modes: []}};
    }}
    return {{reason: '', modes}};
  }}
  function ariaBinding(form, el) {{
    if (el.getAttribute('role') === 'listbox') return {{reason: '', id: '', self: true, multiple: el.getAttribute('aria-multiselectable') === 'true'}};
    const ids = String(el.getAttribute('aria-controls') || '').split(/\\s+/).concat(String(el.getAttribute('aria-owns') || '').split(/\\s+/)).filter(Boolean);
    if (!ids.length) return {{reason: 'ARIA_OPTION_CONTAINER_MISSING', id: '', self: false, multiple: false}};
    const containers = [];
    for (const id of ids) {{
      const matches = Array.from(form.querySelectorAll('[id="' + cssString(id) + '"]'));
      if (matches.length > 1) return {{reason: 'ARIA_OPTION_CONTAINER_AMBIGUOUS', id: '', self: false, multiple: false}};
      if (matches.length === 1) {{
        const container = matches[0];
        if (container.matches('[role="listbox"]') || container.querySelector('[role="option"]')) containers.push(container);
      }}
    }}
    const unique = Array.from(new Set(containers));
    if (!unique.length) return {{reason: 'ARIA_OPTION_CONTAINER_MISSING', id: '', self: false, multiple: false}};
    if (unique.length !== 1) return {{reason: 'ARIA_OPTION_CONTAINER_AMBIGUOUS', id: '', self: false, multiple: false}};
    const container = unique[0];
    return {{reason: '', id: container.id, self: false, multiple: el.getAttribute('aria-multiselectable') === 'true' || container.getAttribute('aria-multiselectable') === 'true'}};
  }}

  const form = selectedForm(); const entries = Object.entries(fields || {{}});
  if (!form) return {{form_found: false, form: null, field_count: 0, requested_count: entries.length, targets: []}};
  const allControls = controls(form); const targets = [];
  for (const [key, value] of entries) {{
    const match = matchControl(form, allControls, key); const el = match.control;
    if (!el) {{ targets.push({{key, matched_by: '', selector: '', relative_selector: '', control_type: '', reason: 'FIELD_NOT_MATCHED', action: '', select_modes: [], multiple: false, aria_container_id: '', aria_container_self: false}}); continue; }}
    const type = controlType(el);
    const target = {{key, matched_by: match.matchedBy, selector: selectorFor(el), relative_selector: relativeSelectorFor(form, el), control_type: type, reason: '', action: '', select_modes: [], multiple: false, aria_container_id: '', aria_container_self: false}};
    if (el.disabled || el.getAttribute('aria-disabled') === 'true') target.reason = 'FIELD_DISABLED';
    else if (el.readOnly || el.getAttribute('aria-readonly') === 'true') target.reason = 'FIELD_READONLY';
    else if (['checkbox', 'radio'].includes(type)) {{ target.action = 'native_check'; if (typeof value !== 'boolean') target.reason = 'INVALID_VALUE_TYPE'; }}
    else if (['select-one', 'select-multiple'].includes(type)) {{
      target.action = 'native_select'; target.multiple = type === 'select-multiple';
      if (typeof value !== 'string' && !Array.isArray(value)) target.reason = 'INVALID_VALUE_TYPE';
      else {{ const selection = selectModes(el, value); target.reason = selection.reason; target.select_modes = selection.modes; }}
    }}
    else if (type === 'contenteditable') {{ target.action = 'framework_contenteditable'; if (typeof value !== 'string') target.reason = 'INVALID_VALUE_TYPE'; }}
    else if (['combobox', 'listbox'].includes(type)) {{
      target.action = 'framework_aria';
      if (typeof value !== 'string' && !Array.isArray(value)) target.reason = 'INVALID_VALUE_TYPE';
      else {{
        const binding = ariaBinding(form, el); target.reason = binding.reason; target.aria_container_id = binding.id; target.aria_container_self = binding.self; target.multiple = binding.multiple;
        if (!target.reason && !binding.multiple && Array.isArray(value) && value.length !== 1) target.reason = 'INVALID_VALUE_TYPE';
      }}
    }}
    else if (['file', 'submit', 'button', 'reset', 'image', 'hidden', 'switch'].includes(type)) target.reason = 'UNSUPPORTED_CONTROL';
    else {{ target.action = 'native_input'; if (typeof value !== 'string') target.reason = 'INVALID_VALUE_TYPE'; }}
    targets.push(target);
  }}
  return {{form_found: true, form: {{selector: selectorFor(form), id: form.id || '', name: form.getAttribute('name') || '', method: String(form.method || 'get').toLowerCase(), action: form.action || ''}}, field_count: allControls.length, requested_count: entries.length, targets}};
}})()
"""


def _form_fill_framework_script(
    *,
    form_locator: str,
    selector: str,
    action: str,
    value: Any,
    aria_container_id: str,
    aria_container_self: bool,
) -> str:
    """Apply one framework control fallback within its resolved form scope."""

    return f"""
(() => {{
  const formLocator = {json.dumps(form_locator)};
  const selector = {json.dumps(selector)};
  const action = {json.dumps(action)};
  const value = {json.dumps(value, ensure_ascii=False)};
  const ariaContainerId = {json.dumps(aria_container_id)};
  const ariaContainerSelf = {json.dumps(aria_container_self)};
  function textOf(node) {{ return String(node && (node.innerText || node.textContent) || '').replace(/\\s+/g, ' ').trim(); }}
  function cssString(value) {{ return String(value).split('\\\\').join('\\\\\\\\').replace(/"/g, '\\\\"'); }}
  function selectedForm() {{
    const xpath = formLocator.match(/^(?:xpath|x)[:=](.*)$/s); const css = formLocator.match(/^css[:=](.*)$/s); let node = null;
    if (xpath) node = document.evaluate(xpath[1], document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
    else node = document.querySelector(css ? css[1] : 'form');
    if (!node) return null; return node.matches && node.matches('form') ? node : (node.querySelector && node.querySelector('form'));
  }}
  function boundContainer(form, el) {{
    if (ariaContainerSelf) {{
      if (el.getAttribute('role') !== 'listbox') return {{container: null, reason: 'ARIA_OPTION_CONTAINER_MISSING'}};
      return {{container: el, reason: ''}};
    }}
    const ids = String(el.getAttribute('aria-controls') || '').split(/\\s+/).concat(String(el.getAttribute('aria-owns') || '').split(/\\s+/)).filter(Boolean);
    if (!ariaContainerId || !ids.includes(ariaContainerId)) return {{container: null, reason: 'ARIA_OPTION_CONTAINER_MISSING'}};
    const matches = Array.from(form.querySelectorAll('[id="' + cssString(ariaContainerId) + '"]'));
    if (matches.length > 1) return {{container: null, reason: 'ARIA_OPTION_CONTAINER_AMBIGUOUS'}};
    if (matches.length !== 1) return {{container: null, reason: 'ARIA_OPTION_CONTAINER_MISSING'}};
    const container = matches[0];
    if (!container.matches('[role="listbox"]') && !container.querySelector('[role="option"]')) return {{container: null, reason: 'ARIA_OPTION_CONTAINER_MISSING'}};
    return {{container, reason: ''}};
  }}
  const form = selectedForm(); if (!form) return {{reason: 'FORM_NOT_FOUND'}};
  const el = document.querySelector(selector); if (!el || !form.contains(el)) return {{reason: 'FIELD_NOT_MATCHED'}};
  if (action === 'framework_contenteditable') {{
    if (!el.isContentEditable) return {{reason: 'UNSUPPORTED_CONTROL'}};
    el.focus();
    el.dispatchEvent(new InputEvent('beforeinput', {{bubbles: true, composed: true, inputType: 'insertText', data: String(value)}}));
    el.textContent = String(value);
    el.dispatchEvent(new InputEvent('input', {{bubbles: true, composed: true, inputType: 'insertText', data: String(value)}}));
    el.dispatchEvent(new Event('change', {{bubbles: true, composed: true}}));
    return {{reason: ''}};
  }}
  if (action !== 'framework_aria') return {{reason: 'UNSUPPORTED_CONTROL'}};
  el.click();
  const binding = boundContainer(form, el); if (binding.reason) return {{reason: binding.reason}};
  const options = Array.from(binding.container.querySelectorAll('[role="option"]'));
  const requested = Array.isArray(value) ? value.map(String) : [String(value)]; const selected = [];
  for (const item of requested) {{
    const matches = options.filter((option) => String(option.getAttribute('data-value') || option.getAttribute('value') || '') === item || textOf(option) === item);
    if (matches.length !== 1) return {{reason: matches.length ? 'ARIA_OPTION_AMBIGUOUS' : 'OPTION_NOT_FOUND'}};
    selected.push(matches[0]);
  }}
  for (const option of selected) option.click();
  return {{reason: ''}};
}})()
"""


def _form_fill_observe_script(
    *,
    form_locator: str,
    selector: str,
    control_type: str,
    aria_container_id: str,
    aria_container_self: bool,
) -> str:
    """Read one live control representation from the resolved form scope."""

    return f"""
(() => {{
  const formLocator = {json.dumps(form_locator)};
  const selector = {json.dumps(selector)};
  const controlType = {json.dumps(control_type)};
  const ariaContainerId = {json.dumps(aria_container_id)};
  const ariaContainerSelf = {json.dumps(aria_container_self)};
  function textOf(node) {{ return String(node && (node.innerText || node.textContent) || '').replace(/\\s+/g, ' ').trim(); }}
  function cssString(value) {{ return String(value).split('\\\\').join('\\\\\\\\').replace(/"/g, '\\\\"'); }}
  function selectedForm() {{
    const xpath = formLocator.match(/^(?:xpath|x)[:=](.*)$/s); const css = formLocator.match(/^css[:=](.*)$/s); let node = null;
    if (xpath) node = document.evaluate(xpath[1], document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
    else node = document.querySelector(css ? css[1] : 'form');
    if (!node) return null; return node.matches && node.matches('form') ? node : (node.querySelector && node.querySelector('form'));
  }}
  function boundContainer(form, el) {{
    if (ariaContainerSelf) {{
      if (el.getAttribute('role') !== 'listbox') return {{container: null, reason: 'ARIA_OPTION_CONTAINER_MISSING'}};
      return {{container: el, reason: ''}};
    }}
    const ids = String(el.getAttribute('aria-controls') || '').split(/\\s+/).concat(String(el.getAttribute('aria-owns') || '').split(/\\s+/)).filter(Boolean);
    if (!ariaContainerId || !ids.includes(ariaContainerId)) return {{container: null, reason: 'ARIA_OPTION_CONTAINER_MISSING'}};
    const matches = Array.from(form.querySelectorAll('[id="' + cssString(ariaContainerId) + '"]'));
    if (matches.length > 1) return {{container: null, reason: 'ARIA_OPTION_CONTAINER_AMBIGUOUS'}};
    if (matches.length !== 1) return {{container: null, reason: 'ARIA_OPTION_CONTAINER_MISSING'}};
    const container = matches[0];
    if (!container.matches('[role="listbox"]') && !container.querySelector('[role="option"]')) return {{container: null, reason: 'ARIA_OPTION_CONTAINER_MISSING'}};
    return {{container, reason: ''}};
  }}
  const form = selectedForm(); if (!form) return {{reason: 'FORM_NOT_FOUND', value: null}};
  const el = document.querySelector(selector); if (!el || !form.contains(el)) return {{reason: 'FIELD_NOT_MATCHED', value: null}};
  if (['checkbox', 'radio'].includes(controlType)) return {{reason: '', value: Boolean(el.checked)}};
  if (['select-one', 'select-multiple'].includes(controlType)) {{
    const values = Array.from(el.selectedOptions || []).map((option) => String(option.value));
    return {{reason: '', value: controlType === 'select-multiple' ? values : (values[0] || '')}};
  }}
  if (controlType === 'contenteditable') return {{reason: '', value: textOf(el)}};
  if (['combobox', 'listbox'].includes(controlType)) {{
    const binding = boundContainer(form, el); if (binding.reason) return {{reason: binding.reason, value: null}};
    const selected = Array.from(binding.container.querySelectorAll('[role="option"]')).filter((option) => option.getAttribute('aria-selected') === 'true').map((option) => String(option.getAttribute('data-value') || option.getAttribute('value') || textOf(option)));
    const multiple = el.getAttribute('aria-multiselectable') === 'true' || binding.container.getAttribute('aria-multiselectable') === 'true';
    if (selected.length) return {{reason: '', value: multiple ? selected : selected[0]}};
    return {{reason: '', value: String(el.getAttribute('aria-valuetext') || ('value' in el ? el.value : ''))}};
  }}
  return {{reason: '', value: String(el.value == null ? '' : el.value)}};
}})()
"""


def _form_submit_resolve_script(*, form_locator: str, submit_locator: str = "") -> str:
    """Resolve one live form and one enabled submitter without mutating the page."""

    return f"""
(() => {{
  const formLocator = {json.dumps(form_locator)};
  const submitLocator = {json.dumps(submit_locator)};
  function locateAll(locator) {{
    if (!locator) return [];
    const split = locator.indexOf(':');
    const strategy = split < 0 ? 'css' : locator.slice(0, split);
    const raw = split < 0 ? locator : locator.slice(split + 1);
    if (strategy === 'xpath') {{
      const result = document.evaluate(raw, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
      return Array.from({{length: result.snapshotLength}}, (_, index) => result.snapshotItem(index)).filter(Boolean);
    }}
    return Array.from(document.querySelectorAll(raw));
  }}
  function cssPath(el) {{
    if (el.id && document.querySelectorAll('#' + CSS.escape(el.id)).length === 1) return '#' + CSS.escape(el.id);
    const parts = [];
    let node = el;
    while (node && node.nodeType === Node.ELEMENT_NODE && node !== document.documentElement) {{
      let part = node.tagName.toLowerCase();
      const siblings = node.parentElement ? Array.from(node.parentElement.children).filter(item => item.tagName === node.tagName) : [];
      if (siblings.length > 1) part += ':nth-of-type(' + (siblings.indexOf(node) + 1) + ')';
      parts.unshift(part);
      node = node.parentElement;
    }}
    return parts.join(' > ');
  }}
  function visible(el) {{
    const style = getComputedStyle(el); const rect = el.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && (rect.width > 0 || rect.height > 0 || el.getClientRects().length > 0);
  }}
  function enabledSubmitter(el) {{
    if (!el || !el.matches) return false;
    const type = String(el.getAttribute('type') || (el.tagName === 'BUTTON' ? 'submit' : '')).toLowerCase();
    const submitCapable = (el.tagName === 'BUTTON' && type === 'submit') || (el.tagName === 'INPUT' && ['submit', 'image'].includes(type));
    return submitCapable && !el.disabled && el.getAttribute('aria-disabled') !== 'true' && visible(el);
  }}
  const formNodes = [];
  for (const node of locateAll(formLocator)) {{
    if (node.matches && node.matches('form')) formNodes.push(node);
    else if (node.querySelectorAll) formNodes.push(...node.querySelectorAll('form'));
  }}
  const forms = Array.from(new Set(formNodes));
  if (forms.length !== 1) return {{form_found: false, reason: forms.length ? 'FORM_AMBIGUOUS' : 'FORM_NOT_FOUND', form_count: forms.length, submitter_count: 0, submitter: null}};
  const form = forms[0];
  const rawCandidates = submitLocator
    ? locateAll(submitLocator).filter(el => form.contains(el))
    : Array.from(form.querySelectorAll('button:not([type]), button[type="submit"], input[type="submit"], input[type="image"]'));
  const candidates = rawCandidates.filter(enabledSubmitter);
  if (candidates.length !== 1) return {{
    form_found: true,
    reason: candidates.length ? 'SUBMITTER_AMBIGUOUS' : 'SUBMITTER_NOT_FOUND',
    form_count: 1,
    submitter_count: candidates.length,
    submitter: null,
  }};
  const submitter = candidates[0];
  const selector = cssPath(submitter);
  return {{
    form_found: true,
    reason: '',
    form_count: 1,
    submitter_count: 1,
    form: {{
      selector: cssPath(form),
      id: String(form.id || ''),
      name: String(form.getAttribute('name') || ''),
      method: String(form.method || 'get').toLowerCase(),
      action: String(form.action || location.href).slice(0, 500),
    }},
    submitter: {{
      selector,
      id: String(submitter.id || ''),
      name: String(submitter.getAttribute('name') || ''),
      tag: submitter.tagName.toLowerCase(),
      type: String(submitter.getAttribute('type') || 'submit').toLowerCase(),
      text: String(submitter.innerText || submitter.value || '').replace(/\\s+/g, ' ').trim().slice(0, 200),
      disabled: false,
    }},
  }};
}})()
"""


def _form_submit_state_script(*, form_locator: str) -> str:
    """Collect bounded post-submit validation and document state evidence."""

    return f"""
(() => {{
  const formLocator = {json.dumps(form_locator)};
  function locateOne(locator) {{
    const split = locator.indexOf(':');
    const strategy = split < 0 ? 'css' : locator.slice(0, split);
    const raw = split < 0 ? locator : locator.slice(split + 1);
    if (strategy === 'xpath') return document.evaluate(raw, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
    return document.querySelector(raw);
  }}
  function cssPath(el) {{
    if (el.id && document.querySelectorAll('#' + CSS.escape(el.id)).length === 1) return '#' + CSS.escape(el.id);
    return (el.tagName || '').toLowerCase();
  }}
  function visible(el) {{
    const style = getComputedStyle(el); const rect = el.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && (rect.width > 0 || rect.height > 0 || el.getClientRects().length > 0);
  }}
  const selected = locateOne(formLocator);
  const form = selected && selected.matches && selected.matches('form') ? selected : (selected && selected.querySelector ? selected.querySelector('form') : null);
  const sensitiveValues = [];
  if (form) {{
    for (const control of Array.from(form.querySelectorAll('input, textarea')).slice(0, 100)) {{
      const marker = [control.type, control.name, control.id, control.getAttribute('autocomplete')].join(' ').toLowerCase();
      if (!/(?:password|passwd|pwd|secret|token|api[_-]?key|authorization|current-password|new-password)/.test(marker)) continue;
      const value = String(control.value || '');
      if (value && value.length <= 1000 && !sensitiveValues.includes(value)) sensitiveValues.push(value);
    }}
  }}
  let validation = [];
  if (form) {{
    for (const control of Array.from(form.querySelectorAll('input, select, textarea')).slice(0, 100)) {{
      if (!control.willValidate || control.validity.valid) continue;
      let code = 'CONSTRAINT_INVALID';
      for (const [name, value] of Object.entries({{
        valueMissing: control.validity.valueMissing,
        typeMismatch: control.validity.typeMismatch,
        patternMismatch: control.validity.patternMismatch,
        tooLong: control.validity.tooLong,
        tooShort: control.validity.tooShort,
        rangeUnderflow: control.validity.rangeUnderflow,
        rangeOverflow: control.validity.rangeOverflow,
        stepMismatch: control.validity.stepMismatch,
        badInput: control.validity.badInput,
        customError: control.validity.customError,
      }})) {{ if (value) {{ code = String(name).replace(/([a-z])([A-Z])/g, '$1_$2').toUpperCase(); break; }} }}
      validation.push({{selector: cssPath(control), name: String(control.name || ''), message: String(control.validationMessage || '').slice(0, 300), code, source: 'client'}});
    }}
    const serverValidation = [];
    for (const alert of Array.from(document.querySelectorAll('[data-server-validation], form [role="alert"], form [aria-live="assertive"]')).slice(0, 20)) {{
      const message = String(alert.innerText || alert.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 300);
      if (visible(alert) && message) serverValidation.push({{selector: cssPath(alert), name: '', message, code: 'SERVER_VALIDATION', source: 'server'}});
    }}
    if (serverValidation.length) validation = serverValidation;
  }}
  return {{
    url: String(location.href),
    title: String(document.title || '').slice(0, 300),
    ready_state: String(document.readyState || ''),
    form_found: Boolean(form),
    validation_messages: validation.slice(0, 20),
    sensitive_values: sensitiveValues.slice(0, 20),
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
