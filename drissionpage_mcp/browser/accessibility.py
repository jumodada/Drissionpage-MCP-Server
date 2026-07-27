"""Bounded accessibility-tree observation for one browser tab."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from ..target import ElementTargetArg
from .targeting import TargetUnsupportedError, _ax_value

if TYPE_CHECKING:
    from ..tab import PageTab

_REDACTED = "<redacted>"
_SENSITIVE_PROPERTY_NAMES = frozenset({"value", "valuetext"})


class AccessibilityOperations:
    """Read scoped Chromium accessibility nodes without mutating the page."""

    def __init__(self, tab: PageTab) -> None:
        self._tab = tab

    async def snapshot(
        self,
        *,
        scope: ElementTargetArg | None = None,
        max_nodes: int = 200,
        include_ignored: bool = False,
        include_values: bool = False,
    ) -> dict[str, Any]:
        owner = self._tab.page
        scope_metadata: dict[str, Any] | None = None
        if scope is None:
            root = owner.ele("tag:html", timeout=0)
        else:
            resolved = await self._tab.dom_targeting.resolve(scope, timeout=3)
            owner = resolved.owner
            root = resolved.element
            scope_metadata = resolved.metadata()
        backend_id = getattr(root, "_backend_id", None)
        run_cdp = getattr(owner, "run_cdp", None)
        if not isinstance(backend_id, int) or not callable(run_cdp):
            raise TargetUnsupportedError(
                "Accessibility snapshots are unsupported by this runtime or target."
            )
        result = run_cdp(
            "Accessibility.queryAXTree",
            backendNodeId=backend_id,
        )
        raw_nodes = result.get("nodes") if isinstance(result, dict) else None
        if not isinstance(raw_nodes, list):
            raise TargetUnsupportedError(
                "Accessibility.queryAXTree returned an invalid payload."
            )
        nodes = [
            _node_payload(node, include_values=include_values)
            for node in raw_nodes
            if isinstance(node, Mapping)
            and (include_ignored or not bool(node.get("ignored")))
        ]
        returned = nodes[:max_nodes]
        return {
            "nodes": returned,
            "count": len(nodes),
            "returned": len(returned),
            "max_nodes": max_nodes,
            "truncated": len(nodes) > len(returned),
            "values_included": include_values,
            "scope": scope_metadata,
        }


def _node_payload(
    node: Mapping[str, Any], *, include_values: bool
) -> dict[str, Any]:
    backend = node.get("backendDOMNodeId")
    properties: dict[str, Any] = {}
    for item in node.get("properties", []):
        if not isinstance(item, Mapping):
            continue
        name = item.get("name")
        if isinstance(name, str):
            value = _bounded_ax_value(item.get("value"))
            if (
                not include_values
                and name.lower() in _SENSITIVE_PROPERTY_NAMES
                and value not in ("", None)
            ):
                value = _REDACTED
            properties[name] = value
    value = _bounded(_ax_value(node.get("value")))
    if not include_values and value:
        value = _REDACTED
    return {
        "node_id": str(node.get("nodeId") or ""),
        "parent_id": (
            str(node["parentId"]) if node.get("parentId") is not None else None
        ),
        "backend_dom_node_id": backend if isinstance(backend, int) else None,
        "role": _bounded(_ax_value(node.get("role"))),
        "name": _bounded(_ax_value(node.get("name"))),
        "description": _bounded(_ax_value(node.get("description"))),
        "value": value,
        "ignored": bool(node.get("ignored")),
        "properties": properties,
    }


def _bounded_ax_value(value: Any) -> Any:
    if not isinstance(value, Mapping):
        return None
    raw = value.get("value")
    return _bounded(raw) if isinstance(raw, str) else raw


def _bounded(value: Any, limit: int = 500) -> str:
    return str(value or "")[:limit]
