"""Atomic selector target resolution contracts for pointer actions."""

from __future__ import annotations

import json

import pytest

from drissionpage_mcp.browser.targeting import ElementTarget, TargetResolver


class FakePage:
    def __init__(self, result: object) -> None:
        self.result = result
        self.scripts: list[str] = []

    def run_js(self, script: str, *, as_expr: bool = False):
        assert as_expr is True
        self.scripts.append(script)
        return self.result


class FakeTab:
    def __init__(self, result: object) -> None:
        self.page = FakePage(result)


def test_element_target_rejects_unsupported_locator_forms() -> None:
    with pytest.raises(ValueError, match="CSS or XPath"):
        ElementTarget.from_selectors("text:Drag me")
    with pytest.raises(ValueError, match="CSS or XPath"):
        ElementTarget.from_selectors("#thumb", shadow_hosts=("text:Host",))
    with pytest.raises(ValueError, match="Shadow DOM paths require CSS"):
        ElementTarget.from_selectors("xpath:.//*[@id='thumb']", shadow_hosts=("#host",))


def test_target_resolver_serializes_frame_shadow_path_and_anchor() -> None:
    tab = FakeTab(
        {
            "thumb": {
                "selector": "#thumb",
                "locator": "css:#thumb",
                "selector_strategy": "css",
                "selector_normalized": True,
                "frame_selector": "#frame",
                "shadow_hosts": ["#outer", "#inner"],
                "anchor": "right",
                "offset_x": -2,
                "offset_y": 1,
                "x": 428,
                "y": 115,
                "left": 400,
                "top": 100,
                "right": 430,
                "bottom": 130,
                "width": 30,
                "height": 30,
            }
        }
    )
    resolver = TargetResolver(tab)
    target = ElementTarget.from_selectors(
        "#thumb",
        frame_selector="#frame",
        shadow_hosts=("#outer", "#inner"),
        anchor="right",
        offset_x=-2,
        offset_y=1,
    )

    resolved = resolver.resolve_many({"thumb": target})

    assert resolved["thumb"].point.x == 428
    assert resolved["thumb"].point.y == 115
    assert resolved["thumb"].width == 30
    assert resolved["thumb"].shadow_hosts == ("#outer", "#inner")
    script = tab.page.scripts[0]
    assert json.dumps("#frame") in script
    assert json.dumps("#outer") in script
    assert "contentDocument" in script
    assert "shadowRoot" in script
    assert "scrollIntoView" in script


def test_target_resolver_rejects_invalid_script_payload() -> None:
    resolver = TargetResolver(FakeTab(None))
    target = ElementTarget.from_selectors("#thumb")

    with pytest.raises(RuntimeError, match="invalid payload"):
        resolver.resolve_many({"thumb": target})


def test_pointer_drag_element_schema_uses_discriminated_destination() -> None:
    from pydantic import ValidationError

    from drissionpage_mcp.tools.pointer import PointerDragElementInput

    slider = PointerDragElementInput.model_validate(
        {
            "source": {
                "selector": "#thumb",
                "frame_selector": "#frame",
                "shadow_hosts": ["#outer", "#inner"],
            },
            "destination": {
                "kind": "track_ratio",
                "track": {
                    "selector": "#track",
                    "frame_selector": "#frame",
                    "shadow_hosts": ["#outer", "#inner"],
                },
                "ratio": 0.75,
                "axis": "x",
            },
        }
    )
    assert slider.destination.kind == "track_ratio"
    assert slider.destination.ratio == 0.75

    with pytest.raises(ValidationError):
        PointerDragElementInput.model_validate(
            {
                "source": {"selector": "#thumb"},
                "destination": {
                    "kind": "track_ratio",
                    "track": {"selector": "#track"},
                    "ratio": 1.1,
                },
            }
        )
    with pytest.raises(ValidationError):
        PointerDragElementInput.model_validate(
            {
                "source": {"selector": "#thumb", "shadow_hosts": ["#x"] * 6},
                "destination": {"kind": "offset", "x": 10, "y": 0},
            }
        )
