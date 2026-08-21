"""Element geometry and presentation evidence in explicit coordinate spaces."""

from __future__ import annotations

from typing import Any

_PRESENTATION_SCRIPT = """
const style = window.getComputedStyle(this);
let ancestor = this.parentElement;
let ancestor3d = false;
while (ancestor) {
  const ancestorStyle = window.getComputedStyle(ancestor);
  const ancestorTransform = ancestorStyle.transform || 'none';
  if (
    ancestorStyle.transformStyle === 'preserve-3d' ||
    (ancestorStyle.perspective && ancestorStyle.perspective !== 'none') ||
    ancestorTransform.startsWith('matrix3d(')
  ) {
    ancestor3d = true;
    break;
  }
  ancestor = ancestor.parentElement;
}
return {
  display: style.display || '',
  visibility: style.visibility || '',
  opacity: Number.parseFloat(style.opacity || '1'),
  pointer_events: style.pointerEvents || '',
  transform: style.transform || 'none',
  transform_style: style.transformStyle || 'flat',
  perspective: style.perspective || 'none',
  ancestor_3d: ancestor3d
};
"""


def element_viewport_evidence(
    element: Any,
    *,
    owner: Any,
    top_page: Any,
) -> dict[str, Any]:
    """Return outer-element state, geometry, and coordinate actionability."""

    outer = getattr(element, "frame_ele", None) or element
    states = getattr(outer, "states", None)
    viewport_coordinate_space = (
        "top_level_viewport" if owner is top_page else "target_document_viewport"
    )
    displayed = _safe_bool(states, "is_displayed")
    in_viewport = _safe_bool(states, "is_in_viewport")
    whole_in_viewport = _safe_bool(states, "is_whole_in_viewport")
    covered_by = _safe_value(states, "is_covered", False)
    try:
        rect = outer.rect
        geometry = {
            "location": _point(rect.location),
            "size": _size(rect.size),
            "midpoint": _rect_point(
                rect, "midpoint", location_attr="location", size_attr="size"
            ),
            "click_point": _rect_point(
                rect, "click_point", location_attr="location", size_attr="size"
            ),
            "viewport_location": _point(
                getattr(rect, "viewport_location", None) or rect.location
            ),
            "viewport_midpoint": _rect_point(
                rect,
                "viewport_midpoint",
                location_attr="viewport_location",
                size_attr="viewport_size",
            ),
            "viewport_click_point": _rect_point(
                rect,
                "viewport_click_point",
                location_attr="viewport_location",
                size_attr="viewport_size",
            ),
            "coordinate_space": "target_document",
            "viewport_coordinate_space": viewport_coordinate_space,
        }
    except Exception:
        geometry = _empty_geometry(viewport_coordinate_space)
    presentation = _presentation(
        outer,
        displayed=displayed,
        in_viewport=in_viewport,
        covered=bool(covered_by),
        geometry=geometry,
        viewport_coordinate_space=viewport_coordinate_space,
    )
    return {
        "displayed": displayed,
        "enabled": _safe_bool(states, "is_enabled"),
        "alive": _safe_bool(states, "is_alive"),
        "clickable": _safe_bool(states, "is_clickable"),
        "checked": _safe_bool(states, "is_checked"),
        "selected": _safe_bool(states, "is_selected"),
        "in_viewport": in_viewport,
        "whole_in_viewport": whole_in_viewport,
        "covered": bool(covered_by),
        "covering_backend_node_id": int(covered_by) if covered_by else None,
        "rect": geometry,
        "presentation": presentation,
    }


def _empty_geometry(viewport_coordinate_space: str) -> dict[str, Any]:
    point = {"x": 0.0, "y": 0.0}
    return {
        "location": point,
        "size": {"width": 0.0, "height": 0.0},
        "midpoint": point,
        "click_point": point,
        "viewport_location": point,
        "viewport_midpoint": point,
        "viewport_click_point": point,
        "coordinate_space": "target_document",
        "viewport_coordinate_space": viewport_coordinate_space,
    }


def _presentation(
    element: Any,
    *,
    displayed: bool,
    in_viewport: bool,
    covered: bool,
    geometry: dict[str, Any],
    viewport_coordinate_space: str,
) -> dict[str, Any]:
    raw = _run_presentation_probe(element)
    display = str(raw.get("display", ""))
    visibility = str(raw.get("visibility", ""))
    opacity = _safe_float(raw.get("opacity"))
    pointer_events = str(raw.get("pointer_events", ""))
    transform = str(raw.get("transform", "none") or "none")
    transform_style = str(raw.get("transform_style", "flat") or "flat")
    perspective = str(raw.get("perspective", "none") or "none")
    ancestor_3d = bool(raw.get("ancestor_3d", False))
    transformed = transform != "none"
    three_dimensional = (
        ancestor_3d
        or transform.startswith("matrix3d(")
        or transform_style == "preserve-3d"
        or perspective not in {"", "none", "0px"}
    )
    size = geometry["size"]
    hidden = (
        not displayed
        or display == "none"
        or visibility in {"hidden", "collapse"}
        or opacity == 0
        or size["width"] <= 0
        or size["height"] <= 0
    )
    if three_dimensional:
        actionability = "transformed_3d"
    elif hidden:
        actionability = "hidden"
    elif viewport_coordinate_space != "top_level_viewport":
        actionability = "target_document_only"
    elif not in_viewport:
        actionability = "off_viewport"
    elif pointer_events == "none":
        actionability = "pointer_disabled"
    elif covered:
        actionability = "covered"
    else:
        actionability = "ready"
    return {
        "display": display,
        "visibility": visibility,
        "opacity": opacity,
        "pointer_events": pointer_events,
        "transform": transform,
        "transform_style": transform_style,
        "perspective": perspective,
        "transformed": transformed,
        "ancestor_3d": ancestor_3d,
        "three_dimensional": three_dimensional,
        "coordinate_actionability": actionability,
    }


def _run_presentation_probe(element: Any) -> dict[str, Any]:
    run_js = getattr(element, "run_js", None)
    if not callable(run_js):
        return {}
    try:
        value = run_js(_PRESENTATION_SCRIPT)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _safe_value(obj: Any, name: str, default: Any) -> Any:
    try:
        return getattr(obj, name, default)
    except Exception:
        return default


def _safe_bool(obj: Any, name: str) -> bool:
    return bool(_safe_value(obj, name, False))


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _point(value: Any) -> dict[str, float]:
    x, y = value
    return {"x": float(x), "y": float(y)}


def _size(value: Any) -> dict[str, float]:
    width, height = value
    return {"width": float(width), "height": float(height)}


def _midpoint_from_location_size(location: Any, size: Any) -> dict[str, float]:
    x, y = location
    width, height = size
    return {"x": float(x) + float(width) / 2, "y": float(y) + float(height) / 2}


def _rect_point(
    rect: Any, attr: str, *, location_attr: str, size_attr: str
) -> dict[str, float]:
    value = getattr(rect, attr, None)
    if value is not None:
        return _point(value)
    location = getattr(rect, location_attr, None)
    size = getattr(rect, size_attr, None)
    if location is not None and size is not None:
        return _midpoint_from_location_size(location, size)
    return {"x": 0.0, "y": 0.0}


__all__ = ["element_viewport_evidence"]
