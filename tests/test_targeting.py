"""Atomic selector target resolution contracts for pointer actions."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from pydantic import TypeAdapter, ValidationError

from drissionpage_mcp.browser.accessibility import AccessibilityOperations
from drissionpage_mcp.browser.targeting import (
    DomTargetResolver,
    ElementTarget,
    TargetAmbiguousError,
    TargetResolver,
)
from drissionpage_mcp.target import ElementTargetArg


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


def test_element_target_arg_preserves_strings_and_validates_discriminated_targets() -> None:
    adapter = TypeAdapter(ElementTargetArg)

    assert adapter.validate_python("#save") == "#save"
    with pytest.raises(ValidationError):
        adapter.validate_python("")
    with pytest.raises(ValidationError):
        adapter.validate_python("x" * 501)
    selector = adapter.validate_python(
        {
            "kind": "selector",
            "selector": "#save",
            "frame_selectors": ["#outer-frame", "#inner-frame"],
            "shadow_hosts": ["#app-host"],
        }
    )
    assert selector.kind == "selector"
    assert selector.frame_selectors == ["#outer-frame", "#inner-frame"]
    role = adapter.validate_python(
        {
            "kind": "accessibility",
            "role": "button",
            "name": "Save",
            "exact": True,
        }
    )
    assert role.kind == "accessibility"
    assert role.name == "Save"

    with pytest.raises(ValidationError):
        adapter.validate_python({"selector": "#save"})
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {"kind": "selector", "selector": "#save", "unexpected": True}
        )
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {
                "kind": "accessibility",
                "role": "button",
                "frame_selectors": ["iframe"] * 5,
            }
        )


class _FakeElement:
    def __init__(self, backend_id: int, *, text: str = "") -> None:
        self._backend_id = backend_id
        self.text = text
        self.tag = "button"
        self.html = f"<button>{text}</button>"
        self.shadow_root = None


class _FakeRoot:
    def __init__(self, elements: dict[str, _FakeElement]) -> None:
        self.elements = elements

    def ele(self, locator: str, *, timeout: float = 0):
        return self.elements.get(locator)

    def eles(self, locator: str, *, timeout: float = 0):
        element = self.elements.get(locator)
        return [] if element is None else [element]


class _FakeDomPage(_FakeRoot):
    def __init__(self) -> None:
        self.button = _FakeElement(21, text="Save")
        super().__init__({"css:#save": self.button, "tag:html": _FakeElement(1)})

    def run_cdp(self, method: str, **kwargs):
        assert method == "Accessibility.queryAXTree"
        assert kwargs["role"] == "button"
        return {
            "nodes": [
                {
                    "nodeId": "ax-save",
                    "role": {"value": "button"},
                    "name": {"value": "Save"},
                    "backendDOMNodeId": 21,
                }
            ]
        }


class _FakeDomTab:
    def __init__(self) -> None:
        self.page = _FakeDomPage()


@pytest.mark.asyncio
async def test_dom_target_resolver_supports_selector_and_accessibility_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tab = _FakeDomTab()
    resolver = DomTargetResolver(tab)
    monkeypatch.setattr(
        "drissionpage_mcp.browser.targeting.ChromiumElement",
        lambda owner, backend_id: owner.button,
    )

    selector = await resolver.resolve("#save", timeout=0)
    assert selector.element is tab.page.button
    assert selector.metadata()["selector_strategy"] == "css"

    role = await resolver.resolve(
        {
            "kind": "accessibility",
            "role": "button",
            "name": "Save",
            "exact": True,
        },
        timeout=0,
    )
    assert role.element is tab.page.button
    assert role.metadata()["selector_strategy"] == "accessibility"


@pytest.mark.asyncio
async def test_dom_target_resolver_rejects_ambiguous_accessibility_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tab = _FakeDomTab()
    original = tab.page.run_cdp

    def ambiguous(method: str, **kwargs):
        result = original(method, **kwargs)
        result["nodes"].append(
            {
                "nodeId": "ax-save-2",
                "role": {"value": "button"},
                "name": {"value": "Save"},
                "backendDOMNodeId": 22,
            }
        )
        return result

    monkeypatch.setattr(tab.page, "run_cdp", ambiguous)
    monkeypatch.setattr(
        "drissionpage_mcp.browser.targeting.ChromiumElement",
        lambda owner, backend_id: owner.button,
    )
    resolver = DomTargetResolver(tab)

    with pytest.raises(TargetAmbiguousError, match="2 accessibility targets"):
        await resolver.resolve(
            {
                "kind": "accessibility",
                "role": "button",
                "name": "Save",
            },
            timeout=0,
        )


class _FakeAccessibilityPage:
    def __init__(self) -> None:
        self.root = _FakeElement(1)

    def ele(self, locator: str, *, timeout: float = 0) -> _FakeElement | None:
        assert locator == "tag:html"
        assert timeout == 0
        return self.root

    def run_cdp(self, method: str, **kwargs: object) -> dict[str, object]:
        assert method == "Accessibility.queryAXTree"
        assert kwargs == {"backendNodeId": 1}
        return {
            "nodes": [
                {
                    "nodeId": "ax-password",
                    "role": {"value": "textbox"},
                    "name": {"value": "Password"},
                    "value": {"value": "office-secret"},
                    "backendDOMNodeId": 21,
                    "properties": [
                        {"name": "valuetext", "value": {"value": "office-secret"}},
                        {"name": "focusable", "value": {"value": True}},
                    ],
                }
            ]
        }


@pytest.mark.asyncio
async def test_accessibility_snapshot_redacts_values_by_default_and_allows_opt_in() -> None:
    operations = AccessibilityOperations(  # type: ignore[arg-type]
        SimpleNamespace(page=_FakeAccessibilityPage())
    )

    redacted = await operations.snapshot()
    included = await operations.snapshot(include_values=True)

    assert redacted["values_included"] is False
    assert redacted["nodes"][0]["value"] == "<redacted>"
    assert redacted["nodes"][0]["properties"] == {
        "valuetext": "<redacted>",
        "focusable": True,
    }
    assert included["values_included"] is True
    assert included["nodes"][0]["value"] == "office-secret"
    assert included["nodes"][0]["properties"]["valuetext"] == "office-secret"
