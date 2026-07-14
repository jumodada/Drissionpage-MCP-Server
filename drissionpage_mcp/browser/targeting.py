"""Atomic DOM target resolution for selector-first pointer actions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Mapping

from ..selector import SelectorPlan, normalize_selector
from .motion import Point

if TYPE_CHECKING:
    from ..tab import PageTab

TargetAnchor = Literal["center", "left", "right", "top", "bottom"]


@dataclass(frozen=True, slots=True)
class ElementTarget:
    """Normalized element path and viewport anchor requested by a pointer tool."""

    selector: SelectorPlan
    frame_selector: SelectorPlan | None = None
    shadow_hosts: tuple[SelectorPlan, ...] = ()
    anchor: TargetAnchor = "center"
    offset_x: float = 0
    offset_y: float = 0

    @classmethod
    def from_selectors(
        cls,
        selector: str,
        *,
        frame_selector: str | None = None,
        shadow_hosts: tuple[str, ...] = (),
        anchor: TargetAnchor = "center",
        offset_x: float = 0,
        offset_y: float = 0,
    ) -> "ElementTarget":
        selector_plan = _pointer_selector(selector)
        host_plans = tuple(_pointer_selector(item) for item in shadow_hosts)
        if host_plans and (
            selector_plan.strategy != "css"
            or any(plan.strategy != "css" for plan in host_plans)
        ):
            raise ValueError(
                "Nested open Shadow DOM paths require CSS selectors for hosts and target"
            )
        return cls(
            selector=selector_plan,
            frame_selector=(
                _pointer_selector(frame_selector)
                if frame_selector is not None
                else None
            ),
            shadow_hosts=host_plans,
            anchor=anchor,
            offset_x=offset_x,
            offset_y=offset_y,
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "selector": _selector_payload(self.selector),
            "frame_selector": (
                _selector_payload(self.frame_selector)
                if self.frame_selector is not None
                else None
            ),
            "shadow_hosts": [_selector_payload(item) for item in self.shadow_hosts],
            "anchor": self.anchor,
            "offset_x": self.offset_x,
            "offset_y": self.offset_y,
        }


@dataclass(frozen=True, slots=True)
class ResolvedTarget:
    """One element's viewport point, bounding box, and selector path metadata."""

    selector: str
    locator: str
    selector_strategy: str
    selector_normalized: bool
    frame_selector: str | None
    shadow_hosts: tuple[str, ...]
    anchor: TargetAnchor
    offset_x: float
    offset_y: float
    point: Point
    left: float
    top: float
    right: float
    bottom: float
    width: float
    height: float

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ResolvedTarget":
        return cls(
            selector=str(payload["selector"]),
            locator=str(payload["locator"]),
            selector_strategy=str(payload["selector_strategy"]),
            selector_normalized=bool(payload["selector_normalized"]),
            frame_selector=(
                str(payload["frame_selector"])
                if payload.get("frame_selector") is not None
                else None
            ),
            shadow_hosts=tuple(str(item) for item in payload.get("shadow_hosts", [])),
            anchor=str(payload["anchor"]),  # type: ignore[arg-type]
            offset_x=float(payload["offset_x"]),
            offset_y=float(payload["offset_y"]),
            point=Point(float(payload["x"]), float(payload["y"])),
            left=float(payload["left"]),
            top=float(payload["top"]),
            right=float(payload["right"]),
            bottom=float(payload["bottom"]),
            width=float(payload["width"]),
            height=float(payload["height"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "selector": self.selector,
            "locator": self.locator,
            "selector_strategy": self.selector_strategy,
            "selector_normalized": self.selector_normalized,
            "frame_selector": self.frame_selector,
            "shadow_hosts": list(self.shadow_hosts),
            "anchor": self.anchor,
            "offset_x": self.offset_x,
            "offset_y": self.offset_y,
            "x": self.point.x,
            "y": self.point.y,
            "left": self.left,
            "top": self.top,
            "right": self.right,
            "bottom": self.bottom,
            "width": self.width,
            "height": self.height,
        }


class TargetResolver:
    """Resolve multiple element paths in one synchronous browser script call."""

    def __init__(self, tab: "PageTab") -> None:
        self._tab = tab

    def resolve_many(
        self, targets: Mapping[str, ElementTarget]
    ) -> dict[str, ResolvedTarget]:
        payload = {name: target.to_payload() for name, target in targets.items()}
        result = self._tab.page.run_js(_resolution_script(payload), as_expr=True)
        if not isinstance(result, dict):
            raise RuntimeError("pointer target resolution returned an invalid payload")
        resolved: dict[str, ResolvedTarget] = {}
        for name in targets:
            item = result.get(name)
            if not isinstance(item, dict):
                raise RuntimeError(f"pointer target resolution omitted target: {name}")
            resolved[name] = ResolvedTarget.from_payload(item)
        return resolved


def _pointer_selector(selector: str) -> SelectorPlan:
    plan = normalize_selector(selector)
    if plan.strategy not in {"css", "xpath"}:
        raise ValueError(
            "Pointer element targets require a CSS or XPath selector; "
            f"received {plan.strategy}: {selector}"
        )
    return plan


def _selector_payload(plan: SelectorPlan) -> dict[str, Any]:
    locator = plan.locator
    if plan.strategy == "css":
        value = locator[4:] if locator.lower().startswith(("css:", "css=")) else locator
    else:
        lowered = locator.lower()
        for prefix in ("xpath:", "xpath=", "x:", "x="):
            if lowered.startswith(prefix):
                value = locator[len(prefix) :]
                break
        else:
            value = locator
    return {
        "original": plan.original,
        "locator": plan.locator,
        "strategy": plan.strategy,
        "normalized": plan.normalized,
        "value": value,
    }


def _resolution_script(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload)
    return f"""
    (() => {{
      const targets = {encoded};
      const find = (root, spec) => {{
        if (spec.strategy === 'css') return root.querySelector(spec.value);
        const documentNode = root.ownerDocument || root;
        return documentNode.evaluate(
          spec.value,
          root,
          null,
          XPathResult.FIRST_ORDERED_NODE_TYPE,
          null
        ).singleNodeValue;
      }};
      const resolve = target => {{
        let documentNode = document;
        let root = document;
        let frame = null;
        if (target.frame_selector) {{
          frame = find(document, target.frame_selector);
          if (!frame) throw new Error(`Frame not found: ${{target.frame_selector.original}}`);
          frame.scrollIntoView({{block:'center', inline:'center'}});
          documentNode = frame.contentDocument;
          if (!documentNode) throw new Error('Cross-origin or unavailable iframe content');
          root = documentNode;
        }}
        for (const hostSpec of target.shadow_hosts) {{
          const host = find(root, hostSpec);
          if (!host) throw new Error(`Shadow host not found: ${{hostSpec.original}}`);
          if (!host.shadowRoot) throw new Error(`Open shadow root not found: ${{hostSpec.original}}`);
          root = host.shadowRoot;
        }}
        const element = find(root, target.selector);
        if (!element) throw new Error(`Element not found: ${{target.selector.original}}`);
        element.scrollIntoView({{block:'center', inline:'center'}});
        const rect = element.getBoundingClientRect();
        const frameRect = frame ? frame.getBoundingClientRect() : {{left:0, top:0}};
        const left = frameRect.left + rect.left;
        const top = frameRect.top + rect.top;
        const right = left + rect.width;
        const bottom = top + rect.height;
        let x = left + rect.width / 2;
        let y = top + rect.height / 2;
        if (target.anchor === 'left') x = left;
        if (target.anchor === 'right') x = right;
        if (target.anchor === 'top') y = top;
        if (target.anchor === 'bottom') y = bottom;
        x += target.offset_x;
        y += target.offset_y;
        return {{
          selector: target.selector.original,
          locator: target.selector.locator,
          selector_strategy: target.selector.strategy,
          selector_normalized: target.selector.normalized,
          frame_selector: target.frame_selector ? target.frame_selector.original : null,
          shadow_hosts: target.shadow_hosts.map(item => item.original),
          anchor: target.anchor,
          offset_x: target.offset_x,
          offset_y: target.offset_y,
          x, y, left, top, right, bottom,
          width: rect.width,
          height: rect.height
        }};
      }};
      return Object.fromEntries(
        Object.entries(targets).map(([name, target]) => [name, resolve(target)])
      );
    }})()
    """
