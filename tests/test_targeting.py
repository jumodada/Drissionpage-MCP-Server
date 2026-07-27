"""Atomic selector target resolution contracts for pointer actions."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from DrissionPage.errors import ElementNotFoundError
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


class _LegacyTab:
    def __init__(self) -> None:
        self.page = SimpleNamespace()
        self.calls: list[tuple[object, int]] = []
        self.element = object()

    async def _element_by_plan(self, plan: object, *, timeout: int = 0) -> object:
        self.calls.append((plan, timeout))
        return self.element


@pytest.mark.asyncio
async def test_dom_target_resolver_uses_legacy_selector_resolver_for_string_targets() -> None:
    tab = _LegacyTab()
    resolver = DomTargetResolver(tab)  # type: ignore[arg-type]

    resolved = await resolver.resolve("#save", timeout=0.2)

    assert resolved.element is tab.element
    assert resolved.owner is tab.page
    assert tab.calls[0][1] == 1
    assert resolved.metadata()["selector"] == "#save"


class _ScopedFakePage(_FakeRoot):
    def __init__(self, frame: object | None = None) -> None:
        self.frame = frame
        self.get_frame_calls: list[str] = []
        super().__init__({"css:#host": _FakeElement(31), "tag:html": _FakeElement(1)})

    def get_frame(self, locator: str, *, timeout: float = 0) -> object | None:
        self.get_frame_calls.append(locator)
        return self.frame


class _ScopedTab:
    def __init__(self, page: object) -> None:
        self.page = page


@pytest.mark.asyncio
async def test_dom_target_resolver_rejects_unsupported_nested_frame_runtime() -> None:
    resolver = DomTargetResolver(_ScopedTab(_FakeRoot({"tag:html": _FakeElement(1)})))  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="Nested frame target resolution is unsupported"):
        await resolver.resolve(
            {"kind": "selector", "selector": "#save", "frame_selectors": ["#frame"]},
            timeout=0,
        )


@pytest.mark.asyncio
async def test_dom_target_resolver_reports_missing_frame_before_selector_lookup() -> None:
    page = _ScopedFakePage(frame=None)
    resolver = DomTargetResolver(_ScopedTab(page))  # type: ignore[arg-type]

    with pytest.raises(ElementNotFoundError, match="Frame not found: #frame"):
        await resolver.resolve(
            {"kind": "selector", "selector": "#save", "frame_selectors": ["#frame"]},
            timeout=0,
        )

    assert page.get_frame_calls == ["css:#frame"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("elements", "message"),
    [
        ({"tag:html": _FakeElement(1)}, "Shadow host not found: #host"),
        ({"css:#host": _FakeElement(31), "tag:html": _FakeElement(1)}, "Shadow root not found: #host"),
    ],
)
async def test_dom_target_resolver_reports_missing_shadow_host_or_root(
    elements: dict[str, _FakeElement], message: str
) -> None:
    resolver = DomTargetResolver(_ScopedTab(_FakeRoot(elements)))  # type: ignore[arg-type]

    with pytest.raises(ElementNotFoundError, match=message):
        await resolver.resolve(
            {"kind": "selector", "selector": "#save", "shadow_hosts": ["#host"]},
            timeout=0,
        )


@pytest.mark.asyncio
async def test_dom_target_resolver_resolves_selector_inside_shadow_scope() -> None:
    button = _FakeElement(42, text="Save")
    host = _FakeElement(31)
    host.shadow_root = _FakeRoot({"css:#save": button, "tag:html": _FakeElement(3)})
    resolver = DomTargetResolver(
        _ScopedTab(_FakeRoot({"css:#host": host, "tag:html": _FakeElement(1)}))
    )  # type: ignore[arg-type]

    resolved = await resolver.resolve(
        {"kind": "selector", "selector": "#save", "shadow_hosts": ["#host"]},
        timeout=0,
    )

    assert resolved.element is button
    assert resolved.metadata()["shadow_hosts"] == ["#host"]


@pytest.mark.asyncio
async def test_dom_target_resolver_resolve_all_returns_selector_matches() -> None:
    button = _FakeElement(21, text="Save")
    resolver = DomTargetResolver(_ScopedTab(_FakeRoot({"css:.save": button})))  # type: ignore[arg-type]

    spec, elements = await resolver.resolve_all(
        {"kind": "selector", "selector": ".save"}, timeout=0
    )

    assert spec.label == ".save"
    assert elements == [button]


class _AxPage(_FakeRoot):
    def __init__(self, result: object, *, root: _FakeElement | None = None) -> None:
        self.result = result
        self.cdp_calls: list[dict[str, object]] = []
        super().__init__({"tag:html": root or _FakeElement(1)})

    def run_cdp(self, method: str, **kwargs: object) -> object:
        assert method == "Accessibility.queryAXTree"
        self.cdp_calls.append(kwargs)
        return self.result


@pytest.mark.asyncio
async def test_dom_target_resolver_rejects_invalid_accessibility_payload() -> None:
    resolver = DomTargetResolver(_ScopedTab(_AxPage({"nodes": "invalid"})))  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="invalid payload"):
        await resolver.resolve({"kind": "accessibility", "role": "button"}, timeout=0)


@pytest.mark.asyncio
async def test_dom_target_resolver_rejects_accessibility_without_cdp_support() -> None:
    resolver = DomTargetResolver(_ScopedTab(_FakeRoot({"tag:html": _FakeElement(1)})))  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="Accessibility target resolution is unsupported"):
        await resolver.resolve({"kind": "accessibility", "role": "button"}, timeout=0)


@pytest.mark.asyncio
async def test_dom_target_resolver_times_out_when_accessibility_matches_are_filtered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nodes = [
        "not-a-node",
        {"ignored": True, "role": {"value": "button"}, "name": {"value": "Save"}, "backendDOMNodeId": 21},
        {"role": {"value": "link"}, "name": {"value": "Save"}, "backendDOMNodeId": 22},
        {"role": {"value": "button"}, "name": {"value": "Cancel"}, "backendDOMNodeId": 23},
        {"role": {"value": "button"}, "name": {"value": "Save"}, "backendDOMNodeId": 0},
    ]
    resolver = DomTargetResolver(_ScopedTab(_AxPage({"nodes": nodes})))  # type: ignore[arg-type]

    async def no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("drissionpage_mcp.browser.targeting.asyncio.sleep", no_sleep)

    with pytest.raises(
        ElementNotFoundError, match="Element not found: role='button' name='Save'"
    ):
        await resolver.resolve(
            {"kind": "accessibility", "role": "button", "name": "Save"}, timeout=0
        )


@pytest.mark.asyncio
async def test_dom_target_resolver_resolve_all_returns_partial_name_accessibility_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _AxPage(
        {
            "nodes": [
                {
                    "role": {"value": "button"},
                    "name": {"value": "Save settings"},
                    "backendDOMNodeId": 21,
                }
            ]
        },
        root=_FakeElement(9),
    )
    monkeypatch.setattr(
        "drissionpage_mcp.browser.targeting.ChromiumElement",
        lambda owner, backend_id: (owner, backend_id),
    )
    resolver = DomTargetResolver(_ScopedTab(page))  # type: ignore[arg-type]

    spec, elements = await resolver.resolve_all(
        {"kind": "accessibility", "role": "BUTTON", "name": "settings", "exact": False},
        timeout=0,
    )

    assert spec.metadata()["exact"] is False
    assert elements == [(page, 21)]
    assert page.cdp_calls == [{"backendNodeId": 9, "role": "BUTTON"}]


@pytest.mark.asyncio
async def test_dom_target_resolver_uses_document_backend_id_for_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _AxPage(
        {"nodes": [{"role": {"value": "button"}, "backendDOMNodeId": 21}]},
        root=_FakeElement(5),
    )
    page.doc_ele = _FakeElement(77)  # type: ignore[attr-defined]
    monkeypatch.setattr(
        "drissionpage_mcp.browser.targeting.ChromiumElement",
        lambda owner, backend_id: backend_id,
    )
    resolver = DomTargetResolver(_ScopedTab(page))  # type: ignore[arg-type]

    _spec, elements = await resolver.resolve_all(
        {"kind": "accessibility", "role": "button"}, timeout=0
    )

    assert elements == [21]
    assert page.cdp_calls == [{"backendNodeId": 77, "role": "button"}]


@pytest.mark.asyncio
async def test_dom_target_resolver_rejects_scope_without_backend_id() -> None:
    resolver = DomTargetResolver(_ScopedTab(_AxPage({"nodes": []}, root=_FakeElement(0))))  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="does not expose a backend DOM node"):
        await resolver.resolve_all({"kind": "accessibility", "role": "button"}, timeout=0)


def test_target_resolver_rejects_omitted_pointer_target_result() -> None:
    resolver = TargetResolver(FakeTab({}))
    target = ElementTarget.from_selectors("#thumb")

    with pytest.raises(RuntimeError, match="omitted target: thumb"):
        resolver.resolve_many({"thumb": target})


def test_target_resolver_to_dict_round_trips_resolved_pointer_payload() -> None:
    resolver = TargetResolver(
        FakeTab(
            {
                "thumb": {
                    "selector": "#thumb",
                    "locator": "css:#thumb",
                    "selector_strategy": "css",
                    "selector_normalized": True,
                    "anchor": "center",
                    "offset_x": 0,
                    "offset_y": 0,
                    "x": 10,
                    "y": 20,
                    "left": 1,
                    "top": 2,
                    "right": 11,
                    "bottom": 22,
                    "width": 10,
                    "height": 20,
                }
            }
        )
    )

    payload = resolver.resolve_many({"thumb": ElementTarget.from_selectors("#thumb")})[
        "thumb"
    ].to_dict()

    assert payload["x"] == 10
    assert payload["shadow_hosts"] == []
    assert payload["frame_selector"] is None


@pytest.mark.parametrize(
    ("selector", "expected"),
    [
        ("xpath://button", "//button"),
        ("xpath=//button", "//button"),
        ("x://button", "//button"),
        ("x=//button", "//button"),
        (".//button", ".//button"),
    ],
)
def test_element_target_payload_normalizes_xpath_prefixes(selector: str, expected: str) -> None:
    payload = ElementTarget.from_selectors(selector).to_payload()["selector"]

    assert payload["strategy"] == "xpath"
    assert payload["value"] == expected


class _SnapshotPage(_FakeRoot):
    def __init__(self, result: object, *, root: object | None = None) -> None:
        self.result = result
        super().__init__({"tag:html": root or _FakeElement(1)})

    def run_cdp(self, method: str, **kwargs: object) -> object:
        assert method == "Accessibility.queryAXTree"
        assert kwargs == {"backendNodeId": 1}
        return self.result


@pytest.mark.asyncio
async def test_accessibility_snapshot_rejects_unsupported_root_and_invalid_payload() -> None:
    unsupported = AccessibilityOperations(  # type: ignore[arg-type]
        SimpleNamespace(page=_FakeRoot({"tag:html": SimpleNamespace()}))
    )
    with pytest.raises(RuntimeError, match="snapshots are unsupported"):
        await unsupported.snapshot()

    invalid = AccessibilityOperations(  # type: ignore[arg-type]
        SimpleNamespace(page=_SnapshotPage({"nodes": "invalid"}))
    )
    with pytest.raises(RuntimeError, match="invalid payload"):
        await invalid.snapshot()


@pytest.mark.asyncio
async def test_accessibility_snapshot_includes_scope_metadata_and_truncates_nodes() -> None:
    root = _FakeElement(1)
    resolved = SimpleNamespace(
        owner=_SnapshotPage(
            {
                "nodes": [
                    {"nodeId": "ignored", "ignored": True},
                    {
                        "nodeId": "parent",
                        "parentId": "root",
                        "role": {"value": "button"},
                        "name": {"value": "A" * 600},
                        "description": {"value": "Submit"},
                        "value": {"value": "secret"},
                        "backendDOMNodeId": "not-int",
                        "properties": [
                            "bad-property",
                            {"name": 123, "value": {"value": "ignored"}},
                            {"name": "checked", "value": {"value": False}},
                            {"name": "placeholder", "value": "bad"},
                        ],
                    },
                    {"nodeId": "second", "role": {"value": "link"}},
                ]
            },
            root=root,
        ),
        element=root,
        metadata=lambda: {"selector": "#scope"},
    )
    tab = SimpleNamespace(page=SimpleNamespace(), dom_targeting=SimpleNamespace())

    async def resolve(scope: object, *, timeout: float = 0) -> object:
        assert scope == "#scope"
        assert timeout == 3
        return resolved

    tab.dom_targeting.resolve = resolve
    operations = AccessibilityOperations(tab)  # type: ignore[arg-type]

    result = await operations.snapshot(scope="#scope", max_nodes=1)

    assert result["scope"] == {"selector": "#scope"}
    assert result["count"] == 2
    assert result["returned"] == 1
    assert result["truncated"] is True
    node = result["nodes"][0]
    assert node["node_id"] == "parent"
    assert node["parent_id"] == "root"
    assert node["backend_dom_node_id"] is None
    assert node["name"] == "A" * 500
    assert node["value"] == "<redacted>"
    assert node["properties"] == {"checked": False, "placeholder": None}


@pytest.mark.asyncio
async def test_accessibility_snapshot_can_include_ignored_nodes_and_unredacted_empty_values() -> None:
    operations = AccessibilityOperations(  # type: ignore[arg-type]
        SimpleNamespace(
            page=_SnapshotPage(
                {
                    "nodes": [
                        {
                            "nodeId": None,
                            "ignored": True,
                            "role": "invalid",
                            "name": {},
                            "value": {"value": ""},
                            "properties": [
                                {"name": "value", "value": {"value": ""}},
                                {"name": "valuetext", "value": {"value": None}},
                            ],
                        }
                    ]
                }
            )
        )
    )

    result = await operations.snapshot(include_ignored=True)

    assert result["nodes"] == [
        {
            "node_id": "",
            "parent_id": None,
            "backend_dom_node_id": None,
            "role": "",
            "name": "",
            "description": "",
            "value": "",
            "ignored": True,
            "properties": {"value": "", "valuetext": None},
        }
    ]


@pytest.mark.asyncio
async def test_dom_target_resolver_reports_missing_selector_after_scope_resolution() -> None:
    frame = _FakeRoot({"tag:html": _FakeElement(2)})
    page = _ScopedFakePage(frame=frame)
    resolver = DomTargetResolver(_ScopedTab(page))  # type: ignore[arg-type]

    with pytest.raises(ElementNotFoundError, match="Element not found: #missing"):
        await resolver.resolve(
            {"kind": "selector", "selector": "#missing", "frame_selectors": ["#frame"]},
            timeout=0,
        )


@pytest.mark.asyncio
async def test_dom_target_resolver_waits_until_accessibility_target_appears(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"count": 0}
    page = _AxPage({"nodes": []})

    def run_cdp(method: str, **kwargs: object) -> object:
        calls["count"] += 1
        if calls["count"] == 1:
            return {"nodes": []}
        return {
            "nodes": [
                {"role": {"value": "button"}, "name": {"value": "Save"}, "backendDOMNodeId": 21}
            ]
        }

    async def no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr(page, "run_cdp", run_cdp)
    monkeypatch.setattr("drissionpage_mcp.browser.targeting.asyncio.sleep", no_sleep)
    monkeypatch.setattr(
        "drissionpage_mcp.browser.targeting.ChromiumElement",
        lambda owner, backend_id: backend_id,
    )
    resolver = DomTargetResolver(_ScopedTab(page))  # type: ignore[arg-type]

    resolved = await resolver.resolve({"kind": "accessibility", "role": "button"}, timeout=1)

    assert resolved.element == 21
    assert calls["count"] == 2


def test_element_target_payload_preserves_unprefixed_xpath_locator_value() -> None:
    from drissionpage_mcp.browser import targeting
    from drissionpage_mcp.selector import SelectorPlan

    payload = targeting._selector_payload(  # noqa: SLF001 - covering private normalizer branch
        SelectorPlan(original="custom", locator="//button", strategy="xpath", normalized=False)
    )

    assert payload["value"] == "//button"


@pytest.mark.asyncio
async def test_dom_target_resolver_uses_owner_backend_id_for_accessibility_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _AxPage(
        {"nodes": [{"role": {"value": "button"}, "backendDOMNodeId": 21}]},
        root=_FakeElement(0),
    )
    page._backend_id = 88  # type: ignore[attr-defined]
    monkeypatch.setattr(
        "drissionpage_mcp.browser.targeting.ChromiumElement",
        lambda owner, backend_id: backend_id,
    )
    resolver = DomTargetResolver(_ScopedTab(page))  # type: ignore[arg-type]

    _spec, elements = await resolver.resolve_all(
        {"kind": "accessibility", "role": "button"}, timeout=0
    )

    assert elements == [21]
    assert page.cdp_calls == [{"backendNodeId": 88, "role": "button"}]
