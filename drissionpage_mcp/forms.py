"""Form-inspection helpers for bounded MCP tool output."""

from __future__ import annotations

import json

from .outline import ELEMENT_TEXT_CHARS, KNOWN_ATTRIBUTES

FORM_TEXT_CHARS = 500


def build_form_inspect_script(
    *,
    selector: str,
    include_values: bool,
    max_forms: int,
    max_fields_per_form: int,
) -> str:
    """Return JavaScript that extracts bounded form and field metadata."""

    return f"""
(() => {{
  const selector = {json.dumps(selector)};
  const includeValues = {json.dumps(include_values)};
  const maxForms = {int(max_forms)};
  const maxFieldsPerForm = {int(max_fields_per_form)};
  const formTextChars = {FORM_TEXT_CHARS};
  const fieldTextChars = {ELEMENT_TEXT_CHARS};
  const knownAttributes = {json.dumps(list(KNOWN_ATTRIBUTES))};
  const limits = {{max_forms: maxForms, max_fields_per_form: maxFieldsPerForm}};

  function textOf(node) {{
    return (node.innerText || node.textContent || '').replace(/\\s+/g, ' ').trim();
  }}

  function truncate(value, limit) {{
    value = String(value || '');
    return value.length > limit ? value.slice(0, limit) : value;
  }}

  function cssIdent(value) {{
    if (window.CSS && typeof window.CSS.escape === 'function') {{
      return window.CSS.escape(value);
    }}
    return String(value).replace(/[^a-zA-Z0-9_-]/g, '\\\\$&');
  }}

  function cssString(value) {{
    return String(value).replace(/\\\\/g, '\\\\\\\\').replace(/"/g, '\\\\"');
  }}

  function attrMap(el, type) {{
    const attrs = {{}};
    for (const name of knownAttributes) {{
      if (name === 'value' && (!includeValues || type === 'password')) continue;
      const value = el.getAttribute(name);
      if (value !== null && value !== '') attrs[name] = value;
    }}
    return attrs;
  }}

  function recommendedSelector(el) {{
    const tag = (el.tagName || 'element').toLowerCase();
    if (el.id) return '#' + cssIdent(el.id);
    const testId = el.getAttribute('data-testid');
    if (testId) return '[data-testid="' + cssString(testId) + '"]';
    const name = el.getAttribute('name');
    if (name) return tag + '[name="' + cssString(name) + '"]';
    const aria = el.getAttribute('aria-label');
    if (aria) return tag + '[aria-label="' + cssString(aria) + '"]';
    if (el.classList && el.classList.length) return tag + '.' + cssIdent(el.classList[0]);
    let index = 1;
    let sibling = el;
    while ((sibling = sibling.previousElementSibling)) {{
      if (sibling.tagName === el.tagName) index += 1;
    }}
    return tag + ':nth-of-type(' + index + ')';
  }}

  function xpathNodes(rawSelector) {{
    const expression = rawSelector.startsWith('xpath:')
      ? rawSelector.slice('xpath:'.length)
      : rawSelector;
    const result = document.evaluate(
      expression,
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

  function selectedNodes(rawSelector) {{
    const trimmed = String(rawSelector || '').trim();
    if (!trimmed) return Array.from(document.querySelectorAll('form'));
    if (
      trimmed.startsWith('xpath:') ||
      trimmed.startsWith('//') ||
      trimmed.startsWith('.//') ||
      trimmed.startsWith('(//')
    ) {{
      return xpathNodes(trimmed);
    }}
    const css = trimmed.startsWith('css:') ? trimmed.slice('css:'.length) : trimmed;
    return Array.from(document.querySelectorAll(css));
  }}

  function normalizeForms(nodes) {{
    const seen = new Set();
    const forms = [];
    for (const node of nodes) {{
      const candidates = [];
      if (node.matches && node.matches('form')) candidates.push(node);
      if (node.querySelectorAll) {{
        candidates.push(...Array.from(node.querySelectorAll('form')));
      }}
      for (const form of candidates) {{
        if (!seen.has(form)) {{
          seen.add(form);
          forms.push(form);
        }}
      }}
    }}
    return forms;
  }}

  function fieldLabel(el) {{
    const id = el.getAttribute('id');
    if (id) {{
      const explicit = document.querySelector('label[for="' + cssString(id) + '"]');
      if (explicit) return truncate(textOf(explicit), fieldTextChars);
    }}
    const wrapping = el.closest ? el.closest('label') : null;
    if (wrapping) return truncate(textOf(wrapping), fieldTextChars);
    return (
      el.getAttribute('aria-label') ||
      el.getAttribute('placeholder') ||
      el.getAttribute('name') ||
      ''
    );
  }}

  function fieldType(el) {{
    const tag = (el.tagName || 'element').toLowerCase();
    return String(el.type || el.getAttribute('type') || tag).toLowerCase();
  }}

  function fieldValue(el, type) {{
    if (!includeValues || type === 'password') return null;
    if ('value' in el) return String(el.value || '');
    return null;
  }}

  function fieldOptions(el) {{
    if (!el.options) return [];
    return Array.from(el.options).map((option) => ({{
      text: truncate(textOf(option), fieldTextChars),
      value: String(option.value || ''),
      selected: Boolean(option.selected),
    }}));
  }}

  function summarizeField(el, index) {{
    const type = fieldType(el);
    return {{
      index,
      tag: (el.tagName || 'element').toLowerCase(),
      type,
      name: el.getAttribute('name') || '',
      label: fieldLabel(el),
      selector: recommendedSelector(el),
      placeholder: el.getAttribute('placeholder') || '',
      required: Boolean(el.required),
      disabled: Boolean(el.disabled),
      readonly: Boolean(el.readOnly),
      checked: Boolean(el.checked),
      value: fieldValue(el, type),
      attributes: attrMap(el, type),
      options: fieldOptions(el),
    }};
  }}

  function summarizeForm(form, index) {{
    const fields = Array.from(
      form.querySelectorAll('input,textarea,select,button')
    );
    const selectedFields = fields.slice(0, maxFieldsPerForm);
    return {{
      index,
      selector: recommendedSelector(form),
      id: form.getAttribute('id') || '',
      name: form.getAttribute('name') || '',
      method: (form.getAttribute('method') || 'get').toLowerCase(),
      action: form.action || form.getAttribute('action') || '',
      text: truncate(textOf(form), formTextChars),
      fields: selectedFields.map((field, fieldIndex) => summarizeField(field, fieldIndex)),
      fields_truncated: selectedFields.length < fields.length,
    }};
  }}

  const allForms = normalizeForms(selectedNodes(selector));
  const selectedForms = allForms.slice(0, maxForms);
  const forms = selectedForms.map((form, index) => summarizeForm(form, index));
  const fieldsTruncated = forms.some((form) => form.fields_truncated);
  for (const form of forms) delete form.fields_truncated;

  return {{
    selector,
    include_values: includeValues,
    count: allForms.length,
    returned: forms.length,
    limits,
    truncated: {{
      forms: selectedForms.length < allForms.length,
      fields: fieldsTruncated,
    }},
    forms,
  }};
}})()
"""
