"""Selector normalization for LLM-facing MCP tools.

DrissionPage treats an unprefixed locator as fuzzy text matching. That is useful
for humans who already know DrissionPage, but it conflicts with the MCP tool
contract where LLMs naturally send browser-style CSS selectors such as ``h1`` or
``input[name=q]``. Normalize the public MCP surface to deterministic CSS/XPath
semantics while still allowing explicit DrissionPage locator forms.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SelectorStrategy = Literal["css", "xpath", "tag", "text", "drissionpage", "page"]


@dataclass(frozen=True)
class SelectorPlan:
    """Resolved selector metadata used for DrissionPage calls and tool output."""

    original: str
    locator: str
    strategy: SelectorStrategy
    normalized: bool

    def metadata(self) -> dict[str, object]:
        """Return JSON-safe selector metadata for structured MCP responses."""

        return {
            "selector": self.original,
            "locator": self.locator,
            "selector_strategy": self.strategy,
            "selector_normalized": self.normalized,
        }


def normalize_selector(selector: str) -> SelectorPlan:
    """Normalize an MCP selector into an explicit DrissionPage locator.

    Public MCP behavior:
    - empty string targets the whole page for reader tools
    - explicit DrissionPage locator forms are preserved
    - XPath-looking bare expressions get an ``xpath:`` prefix
    - all other bare selectors are treated as CSS
    - text matching must be explicit via ``text:...`` / ``text=...``
    """

    if selector == "":
        return SelectorPlan(
            original=selector,
            locator="",
            strategy="page",
            normalized=False,
        )

    stripped = selector.strip()
    if not stripped:
        raise ValueError("blank selector is not valid; use an empty string for page scope")

    explicit_strategy = _explicit_strategy(stripped)
    if explicit_strategy is not None:
        return SelectorPlan(
            original=selector,
            locator=stripped,
            strategy=explicit_strategy,
            normalized=stripped != selector,
        )

    if _looks_like_xpath(stripped):
        return SelectorPlan(
            original=selector,
            locator=f"xpath:{stripped}",
            strategy="xpath",
            normalized=True,
        )

    return SelectorPlan(
        original=selector,
        locator=f"css:{stripped}",
        strategy="css",
        normalized=True,
    )


def _explicit_strategy(selector: str) -> SelectorStrategy | None:
    lowered = selector.lower()

    if lowered.startswith(("css:", "css=")):
        return "css"
    if lowered.startswith(("xpath:", "xpath=", "x:", "x=")):
        return "xpath"
    if lowered.startswith(("tag:", "tag=")):
        return "tag"
    if lowered.startswith(("text:", "text=")):
        return "text"
    if selector.startswith("@"):
        return "drissionpage"
    return None


def _looks_like_xpath(selector: str) -> bool:
    return selector.startswith(("/", "./", ".//", "("))
