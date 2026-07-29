"""Atomic DrissionPage DOM targets and pointer geometry resolution."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from time import monotonic
from typing import TYPE_CHECKING, Any, Literal

from DrissionPage.errors import ElementNotFoundError
from DrissionPage.items import ChromiumElement
from pydantic import TypeAdapter

from ..response_errors import ErrorCode
from ..response_json import strict_json_dumps
from ..selector import SelectorPlan, normalize_selector
from ..target import ElementTargetArg
from .motion import Point

if TYPE_CHECKING:
    from ..tab import PageTab

TargetAnchor = Literal["center", "left", "right", "top", "bottom"]
_TARGET_ADAPTER: TypeAdapter[ElementTargetArg] = TypeAdapter(ElementTargetArg)


class TargetAmbiguousError(ValueError):
    """Raised when an accessibility target does not identify one element."""

    code = ErrorCode.AMBIGUOUS_TARGET


class TargetUnsupportedError(RuntimeError):
    """Raised when the attached runtime cannot resolve a requested target."""

    code = ErrorCode.UNSUPPORTED_OPERATION


@dataclass(frozen=True, slots=True)
class DomTarget:
    """Normalized selector or accessibility target and its document scope."""

    kind: Literal["selector", "accessibility"]
    frame_selectors: tuple[SelectorPlan, ...]
    shadow_hosts: tuple[SelectorPlan, ...]
    selector: SelectorPlan | None = None
    role: str | None = None
    name: str | None = None
    exact: bool = True
    structured: bool = False

    @classmethod
    def from_input(cls, value: ElementTargetArg | Mapping[str, Any]) -> DomTarget:
        target = _TARGET_ADAPTER.validate_python(value)
        if isinstance(target, str):
            return cls(
                kind="selector",
                selector=normalize_selector(target),
                frame_selectors=(),
                shadow_hosts=(),
            )
        frames = tuple(normalize_selector(item) for item in target.frame_selectors)
        hosts = tuple(normalize_selector(item) for item in target.shadow_hosts)
        if target.kind == "selector":
            return cls(
                kind="selector",
                selector=normalize_selector(target.selector),
                frame_selectors=frames,
                shadow_hosts=hosts,
                structured=True,
            )
        return cls(
            kind="accessibility",
            role=target.role,
            name=target.name,
            exact=target.exact,
            frame_selectors=frames,
            shadow_hosts=hosts,
            structured=True,
        )

    @property
    def label(self) -> str:
        if self.selector is not None:
            return self.selector.original
        suffix = "" if self.name is None else f" name={self.name!r}"
        return f"role={self.role!r}{suffix}"

    def metadata(self) -> dict[str, Any]:
        if self.selector is not None:
            metadata = self.selector.metadata()
        else:
            label = self.label
            metadata = {
                "selector": label,
                "locator": label,
                "selector_strategy": "accessibility",
                "selector_normalized": False,
            }
        if not self.structured:
            return metadata
        return {
            **metadata,
            "target_kind": self.kind,
            "frame_selectors": [item.original for item in self.frame_selectors],
            "shadow_hosts": [item.original for item in self.shadow_hosts],
            "role": self.role,
            "name": self.name,
            "exact": self.exact if self.kind == "accessibility" else None,
        }


@dataclass(frozen=True, slots=True)
class ResolvedDomTarget:
    """One resolved DrissionPage element plus stable target metadata."""

    target: DomTarget
    element: Any
    owner: Any

    def metadata(self) -> dict[str, Any]:
        return self.target.metadata()


class DomTargetResolver:
    """Resolve selector and AX targets through DrissionPage frame/shadow objects."""

    def __init__(self, tab: PageTab) -> None:
        self._tab = tab

    async def resolve(
        self,
        target: ElementTargetArg | Mapping[str, Any],
        *,
        timeout: float = 10,
    ) -> ResolvedDomTarget:
        spec = DomTarget.from_input(target)
        deadline = monotonic() + max(0.0, float(timeout))
        legacy_resolver = getattr(self._tab, "_element_by_plan", None)
        if (
            spec.selector is not None
            and not spec.structured
            and callable(legacy_resolver)
        ):
            element = await legacy_resolver(
                spec.selector,
                timeout=max(0, int(deadline - monotonic() + 0.999)),
            )
            return ResolvedDomTarget(
                target=spec,
                element=element,
                owner=getattr(self._tab, "page", self._tab),
            )
        owner, root = self._resolve_scope(spec, deadline)
        if spec.selector is not None:
            element = root.ele(
                spec.selector.locator,
                timeout=max(0.0, deadline - monotonic()),
            )
            if not element:
                raise ElementNotFoundError(f"Element not found: {spec.label}")
        else:
            element = await self._resolve_accessibility(spec, owner, root, deadline)
        return ResolvedDomTarget(target=spec, element=element, owner=owner)

    async def resolve_all(
        self,
        target: ElementTargetArg | Mapping[str, Any],
        *,
        timeout: float = 0,
    ) -> tuple[DomTarget, list[Any]]:
        spec = DomTarget.from_input(target)
        deadline = monotonic() + max(0.0, float(timeout))
        owner, root = self._resolve_scope(spec, deadline)
        if spec.selector is not None:
            elements = list(
                root.eles(
                    spec.selector.locator,
                    timeout=max(0.0, deadline - monotonic()),
                )
                or []
            )
        else:
            elements = self._accessibility_elements(spec, owner, root)
        return spec, elements

    def _resolve_scope(self, target: DomTarget, deadline: float) -> tuple[Any, Any]:
        owner = self._tab.page
        root = owner
        for frame in target.frame_selectors:
            getter = getattr(owner, "get_frame", None)
            if not callable(getter):
                raise TargetUnsupportedError(
                    "Nested frame target resolution is unsupported by this runtime."
                )
            owner = getter(
                frame.locator,
                timeout=max(0.0, deadline - monotonic()),
            )
            if not owner:
                raise ElementNotFoundError(f"Frame not found: {frame.original}")
            root = owner
        for host in target.shadow_hosts:
            element = root.ele(
                host.locator,
                timeout=max(0.0, deadline - monotonic()),
            )
            if not element:
                raise ElementNotFoundError(f"Shadow host not found: {host.original}")
            root = getattr(element, "shadow_root", None)
            if not root:
                raise ElementNotFoundError(f"Shadow root not found: {host.original}")
        return owner, root

    async def _resolve_accessibility(
        self, target: DomTarget, owner: Any, root: Any, deadline: float
    ) -> Any:
        while True:
            elements = self._accessibility_elements(target, owner, root)
            if len(elements) == 1:
                return elements[0]
            if len(elements) > 1:
                raise TargetAmbiguousError(
                    f"Target matched {len(elements)} accessibility targets; "
                    "provide an exact accessible name or narrower scope."
                )
            if monotonic() >= deadline:
                raise ElementNotFoundError(f"Element not found: {target.label}")
            await asyncio.sleep(min(0.05, max(0.001, deadline - monotonic())))

    def _accessibility_elements(
        self, target: DomTarget, owner: Any, root: Any
    ) -> list[Any]:
        run_cdp = getattr(owner, "run_cdp", None)
        if not callable(run_cdp):
            raise TargetUnsupportedError(
                "Accessibility target resolution is unsupported by this runtime."
            )
        backend_id = self._scope_backend_id(root)
        result = run_cdp(
            "Accessibility.queryAXTree",
            backendNodeId=backend_id,
            role=target.role,
        )
        nodes = result.get("nodes") if isinstance(result, dict) else None
        if not isinstance(nodes, list):
            raise TargetUnsupportedError(
                "Accessibility.queryAXTree returned an invalid payload."
            )
        matches: list[Any] = []
        for node in nodes:
            if not isinstance(node, Mapping) or bool(node.get("ignored")):
                continue
            role = _ax_value(node.get("role"))
            name = _ax_value(node.get("name"))
            if role.casefold() != str(target.role or "").casefold():
                continue
            if target.name is not None:
                expected = target.name.casefold()
                observed = name.casefold()
                name_mismatch = (
                    observed != expected if target.exact else expected not in observed
                )
                if name_mismatch:
                    continue
            backend = node.get("backendDOMNodeId")
            if not isinstance(backend, int) or backend <= 0:
                continue
            matches.append(ChromiumElement(owner, backend_id=backend))
        return matches

    @staticmethod
    def _scope_backend_id(root: Any) -> int:
        document = getattr(root, "doc_ele", None)
        document_backend = getattr(document, "_backend_id", None)
        if isinstance(document_backend, int) and document_backend > 0:
            return document_backend
        backend = getattr(root, "_backend_id", None)
        if isinstance(backend, int) and backend > 0:
            return backend
        element = root.ele("tag:html", timeout=0)
        backend = getattr(element, "_backend_id", None)
        if not isinstance(backend, int) or backend <= 0:
            raise TargetUnsupportedError(
                "The target scope does not expose a backend DOM node."
            )
        return backend


def _ax_value(value: Any) -> str:
    if not isinstance(value, Mapping):
        return ""
    raw = value.get("value")
    return "" if raw is None else str(raw)


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
    ) -> ElementTarget:
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
    def from_payload(cls, payload: Mapping[str, Any]) -> ResolvedTarget:
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

    def __init__(self, tab: PageTab) -> None:
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
    encoded = strict_json_dumps(payload)
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
