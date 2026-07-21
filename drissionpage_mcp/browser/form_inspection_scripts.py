"""Form-inspection helpers for bounded MCP tool output."""

from __future__ import annotations

import json

from ..outline import ELEMENT_TEXT_CHARS, KNOWN_ATTRIBUTES
from .script_fragments import css_text_helpers_script

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
{css_text_helpers_script()}

  function truncate(value, limit) {{
    value = String(value || '');
    return value.length > limit ? value.slice(0, limit) : value;
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
    const role = String(el.getAttribute('role') || '').toLowerCase();
    if (el.isContentEditable) return 'contenteditable';
    if (role) return role;
    return String(el.type || el.getAttribute('type') || tag).toLowerCase();
  }}

  function fieldValue(el, type) {{
    if (!includeValues || type === 'password') return null;
    if (el.isContentEditable) return truncate(textOf(el), fieldTextChars);
    if (type === 'checkbox' || type === 'radio' || type === 'switch') {{
      return Boolean(el.checked || el.getAttribute('aria-checked') === 'true');
    }}
    if (el.multiple && el.options) {{
      return Array.from(el.selectedOptions || []).map((option) => String(option.value || ''));
    }}
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
    const role = String(el.getAttribute('role') || '').toLowerCase();
    const editable = Boolean(
      !el.disabled &&
      !el.readOnly &&
      el.getAttribute('aria-disabled') !== 'true' &&
      (el.isContentEditable || 'value' in el || ['checkbox', 'radio', 'switch', 'combobox', 'listbox'].includes(type))
    );
    const selectedValues = el.options
      ? Array.from(el.selectedOptions || []).map((option) => String(option.value || ''))
      : [];
    const validity = el.validity ? {{
      valid: Boolean(el.validity.valid),
      value_missing: Boolean(el.validity.valueMissing),
      type_mismatch: Boolean(el.validity.typeMismatch),
      pattern_mismatch: Boolean(el.validity.patternMismatch),
      too_long: Boolean(el.validity.tooLong),
      too_short: Boolean(el.validity.tooShort),
      range_underflow: Boolean(el.validity.rangeUnderflow),
      range_overflow: Boolean(el.validity.rangeOverflow),
      step_mismatch: Boolean(el.validity.stepMismatch),
      custom_error: Boolean(el.validity.customError),
      message: truncate(el.validationMessage || '', fieldTextChars),
    }} : {{valid: true, message: ''}};
    return {{
      index,
      tag: (el.tagName || 'element').toLowerCase(),
      type,
      role,
      name: el.getAttribute('name') || '',
      label: fieldLabel(el),
      selector: recommendedSelector(el),
      placeholder: el.getAttribute('placeholder') || '',
      required: Boolean(el.required),
      disabled: Boolean(el.disabled || el.getAttribute('aria-disabled') === 'true'),
      readonly: Boolean(el.readOnly || el.getAttribute('aria-readonly') === 'true'),
      editable,
      checked: Boolean(el.checked || el.getAttribute('aria-checked') === 'true'),
      multiple: Boolean(el.multiple || el.getAttribute('aria-multiselectable') === 'true'),
      value: fieldValue(el, type),
      selected_values: selectedValues,
      validity,
      attributes: attrMap(el, type),
      options: fieldOptions(el),
      capabilities: {{
        fill: editable && !['file', 'submit', 'button', 'reset', 'image', 'hidden'].includes(type),
        text_input: editable && ['text', 'search', 'email', 'url', 'tel', 'password', 'textarea', 'contenteditable'].includes(type),
        boolean_input: editable && ['checkbox', 'radio', 'switch'].includes(type),
        option_input: editable && ['select-one', 'select-multiple', 'combobox', 'listbox'].includes(type),
        date_time_input: editable && ['date', 'datetime-local', 'time', 'month', 'week'].includes(type),
      }},
    }};
  }}

  function summarizeForm(form, index) {{
    const fields = Array.from(
      form.querySelectorAll('input,textarea,select,button,[contenteditable="true"],[role="combobox"],[role="listbox"],[role="switch"]')
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
