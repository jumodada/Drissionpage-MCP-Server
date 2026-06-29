"""Page-understanding helpers for bounded MCP tool output."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from typing import Any

KNOWN_ATTRIBUTES = (
    "id",
    "class",
    "name",
    "type",
    "href",
    "value",
    "placeholder",
    "role",
    "aria-label",
    "data-testid",
)

ELEMENT_TEXT_CHARS = 500
ELEMENT_HTML_CHARS = 1000


def build_page_snapshot_script(
    *,
    include_html: bool,
    max_elements: int,
    max_text_chars: int,
) -> str:
    """Return JavaScript that extracts a bounded, serializable page outline."""

    return f"""
(() => {{
  const includeHtml = {json.dumps(include_html)};
  const maxElements = {int(max_elements)};
  const maxTextChars = {int(max_text_chars)};
  const elementTextChars = {ELEMENT_TEXT_CHARS};
  const elementHtmlChars = {ELEMENT_HTML_CHARS};
  const counts = {{}};
  const limits = {{max_elements: maxElements, max_text_chars: maxTextChars}};
  let returnedElements = 0;
  let elementsTruncated = false;

  function textOf(node) {{
    return (node.innerText || node.textContent || '').replace(/\\s+/g, ' ').trim();
  }}

  function truncate(value, limit) {{
    value = String(value || '');
    return value.length > limit ? value.slice(0, limit) : value;
  }}

  function attrMap(el) {{
    const names = {json.dumps(list(KNOWN_ATTRIBUTES))};
    const attrs = {{}};
    for (const name of names) {{
      const value = el.getAttribute(name);
      if (value !== null && value !== '') attrs[name] = value;
    }}
    return attrs;
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

  function base(el, index) {{
    const item = {{
      index,
      tag: (el.tagName || 'element').toLowerCase(),
      text: truncate(textOf(el), elementTextChars),
      selector: recommendedSelector(el),
      attributes: attrMap(el),
    }};
    if (includeHtml) item.html = truncate(el.outerHTML || '', elementHtmlChars);
    return item;
  }}

  function defineCategory(name, selector, mapper) {{
    const nodes = Array.from(document.querySelectorAll(selector));
    counts[name] = nodes.length;
    return {{name, nodes, mapper}};
  }}

  function allocateBudgets(categories) {{
    const budgets = Object.fromEntries(categories.map((category) => [category.name, 0]));
    const nonEmpty = categories.filter((category) => category.nodes.length > 0);
    if (maxElements <= 0 || nonEmpty.length === 0) return budgets;

    // Reserve a fair share for every non-empty category first.  Without this
    // pass, link-heavy pages can consume the whole budget before controls and
    // forms are summarized, which breaks LLM recovery flows.
    const fairShare = Math.max(1, Math.floor(maxElements / nonEmpty.length));
    let remaining = maxElements;
    for (const category of nonEmpty) {{
      const reserved = Math.min(category.nodes.length, fairShare, remaining);
      budgets[category.name] = reserved;
      remaining -= reserved;
      if (remaining <= 0) return budgets;
    }}

    // Preserve the existing category order for any remaining capacity while
    // still keeping the total returned element count within maxElements.
    for (const category of categories) {{
      if (remaining <= 0) break;
      const extra = Math.min(
        category.nodes.length - budgets[category.name],
        remaining
      );
      if (extra > 0) {{
        budgets[category.name] += extra;
        remaining -= extra;
      }}
    }}
    return budgets;
  }}

  function materialize(category, budget) {{
    const selected = category.nodes.slice(0, budget);
    if (selected.length < category.nodes.length) elementsTruncated = true;
    returnedElements += selected.length;
    return selected.map((el, index) => category.mapper(el, index));
  }}

  const bodyText = textOf(document.body || document.documentElement || document);
  const textTruncated = bodyText.length > maxTextChars;

  const headingCategory = defineCategory('headings', 'h1,h2,h3,h4,h5,h6', base);
  const linkCategory = defineCategory('links', 'a[href]', (el, index) => {{
    const item = base(el, index);
    item.href = el.href || el.getAttribute('href') || '';
    return item;
  }});
  const buttonCategory = defineCategory('buttons', 'button,input[type="button"],input[type="submit"],[role="button"]', base);
  const inputCategory = defineCategory('inputs', 'input,textarea,select', base);
  const formCategory = defineCategory('forms', 'form', (el, index) => {{
    const item = base(el, index);
    item.method = (el.getAttribute('method') || 'get').toLowerCase();
    item.action = el.action || el.getAttribute('action') || '';
    return item;
  }});
  const categories = [
    headingCategory,
    linkCategory,
    buttonCategory,
    inputCategory,
    formCategory,
  ];
  const budgets = allocateBudgets(categories);

  const headings = materialize(headingCategory, budgets.headings);
  const links = materialize(linkCategory, budgets.links);
  const buttons = materialize(buttonCategory, budgets.buttons);
  const inputs = materialize(inputCategory, budgets.inputs);
  const forms = materialize(formCategory, budgets.forms);

  return {{
    url: window.location.href,
    title: document.title || '',
    text_excerpt: truncate(bodyText, maxTextChars),
    headings,
    links,
    buttons,
    inputs,
    forms,
    counts,
    truncated: {{
      text: textTruncated,
      elements: elementsTruncated,
      returned_elements: returnedElements,
    }},
    limits,
  }};
}})()
"""


def summarize_elements(
    elements: Sequence[Any],
    *,
    limit: int,
    include_html: bool,
) -> tuple[list[dict[str, Any]], bool]:
    """Summarize DrissionPage elements with bounded text and optional HTML."""

    selected = list(elements[:limit])
    return (
        [
            summarize_element(element, index=index, include_html=include_html)
            for index, element in enumerate(selected)
        ],
        len(elements) > len(selected),
    )


def summarize_element(
    element: Any,
    *,
    index: int,
    include_html: bool,
) -> dict[str, Any]:
    """Return a JSON-safe, selector-oriented element summary."""

    tag = _safe_string_attr(element, "tag") or "element"
    attributes: dict[str, str] = {}
    for name in KNOWN_ATTRIBUTES:
        value = _safe_attr(element, name)
        if value is None or value == "":
            continue
        attributes[name] = value
    item: dict[str, Any] = {
        "index": index,
        "tag": tag,
        "text": _truncate(
            _normalize_text(_safe_string_attr(element, "text")),
            ELEMENT_TEXT_CHARS,
        ),
        "selector": recommend_selector(tag, attributes, index=index),
        "attributes": attributes,
    }
    if include_html:
        item["html"] = _truncate(_safe_string_attr(element, "html"), ELEMENT_HTML_CHARS)
    return item


def recommend_selector(
    tag: str,
    attributes: dict[str, str],
    *,
    index: int = 0,
) -> str:
    """Recommend a simple CSS selector for a summarized element."""

    normalized_tag = (tag or "element").lower()
    if value := attributes.get("id"):
        return f"#{_css_identifier(value)}"
    if value := attributes.get("data-testid"):
        return f'[data-testid="{_css_string(value)}"]'
    if value := attributes.get("name"):
        return f'{normalized_tag}[name="{_css_string(value)}"]'
    if value := attributes.get("aria-label"):
        return f'{normalized_tag}[aria-label="{_css_string(value)}"]'
    if value := attributes.get("class"):
        first_class = value.split()[0] if value.split() else ""
        if first_class:
            return f"{normalized_tag}.{_css_identifier(first_class)}"
    return f"{normalized_tag}:nth-of-type({index + 1})"


def _safe_attr(element: Any, name: str) -> str | None:
    try:
        value = element.attr(name)
    except Exception:
        return None
    if value is None:
        return None
    return str(value)


def _safe_string_attr(element: Any, name: str) -> str:
    try:
        value = getattr(element, name, "")
    except Exception:
        return ""
    return "" if value is None else str(value)


def _truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[:limit]


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def _css_identifier(value: str) -> str:
    if re.fullmatch(r"-?[_a-zA-Z]+[_a-zA-Z0-9-]*", value):
        return value
    return re.sub(r"([^a-zA-Z0-9_-])", r"\\\1", value)


def _css_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
