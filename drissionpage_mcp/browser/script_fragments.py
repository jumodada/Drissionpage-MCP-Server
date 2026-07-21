"""Reusable JavaScript fragments shared by bounded browser script builders."""

from __future__ import annotations


def css_text_helpers_script() -> str:
    """Return stable text and CSS escaping helpers for page-executed scripts."""

    return r"""
  function textOf(node) {
    return String(node && (node.innerText || node.textContent) || '').replace(/\s+/g, ' ').trim();
  }

  function cssIdent(value) {
    if (window.CSS && typeof window.CSS.escape === 'function') {
      return window.CSS.escape(value);
    }
    return String(value).replace(/[^a-zA-Z0-9_-]/g, '\\$&');
  }

  function cssString(value) {
    return String(value).split('\\').join('\\\\').replace(/"/g, '\\"');
  }
"""


__all__ = ["css_text_helpers_script"]
