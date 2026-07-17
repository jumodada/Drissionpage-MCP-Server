"""Contracts for native dialog responses and enriched element clicks."""

from __future__ import annotations

import json
import asyncio
from datetime import datetime, timezone
from time import monotonic
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from drissionpage_mcp.browser.dialogs import (
    DialogResponseIndeterminateError,
    DialogUnsupportedError,
)
from drissionpage_mcp.browser.elements import ElementOperations
from drissionpage_mcp.context import DrissionPageContext
from drissionpage_mcp.tool_outputs import CapabilityProbe, CapabilitySet
from drissionpage_mcp.tools.dialogs import PageDialogRespondInput, page_dialog_respond
from drissionpage_mcp.tools.element import ClickElementInput, click_element


def test_dialog_input_is_strict_bounded_and_action_aware() -> None:
    value = PageDialogRespondInput(action="accept", prompt_text="office-safe")

    assert value.timeout == 5.0
    with pytest.raises(ValidationError, match="prompt_text cannot be used"):
        PageDialogRespondInput(action="dismiss", prompt_text="not-allowed")
    with pytest.raises(ValidationError):
        PageDialogRespondInput(action="accept", prompt_text="x" * 4001)
    with pytest.raises(ValidationError):
        PageDialogRespondInput(action="accept", timeout=0)
    with pytest.raises(ValidationError):
        PageDialogRespondInput(action="accept", unknown=True)  # type: ignore[call-arg]


def test_click_input_defaults_are_compatible_and_variants_are_strict() -> None:
    value = ClickElementInput(selector="#target")

    assert value.button == "left"
    assert value.click_count == 1
    with pytest.raises(ValidationError):
        ClickElementInput(selector="#target", button="primary")  # type: ignore[arg-type]
    for invalid_count in (0, 3, True, 1.5):
        with pytest.raises(ValidationError):
            ClickElementInput(selector="#target", click_count=invalid_count)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_dialog_response_returns_only_redacted_metadata_and_receipt() -> None:
    secret_message = "Secret fixture dialog message"
    prompt_text = "safe-office-value"

    class FakeDialogs:
        def __init__(self) -> None:
            self.responses: list[dict[str, object]] = []

        def probe(self) -> None:
            return None

        async def wait_for_pending(self, *, timeout: float) -> dict[str, str]:
            assert timeout == 2
            return {"dialog_type": "prompt", "message": secret_message}

        async def respond(self, **kwargs: object) -> None:
            self.responses.append(kwargs)

    context = DrissionPageContext()
    fake_dialogs = FakeDialogs()
    context._current_tab = SimpleNamespace(  # type: ignore[assignment]
        url="https://user:password@example.test/dialog?token=secret#fragment",
        mcp_tab_id="t0",
        dialogs=fake_dialogs,
    )

    outcome = await page_dialog_respond.execute(
        context,
        PageDialogRespondInput(action="accept", prompt_text=prompt_text, timeout=2),
    )

    assert outcome.is_error is False
    data = outcome.structured_content()["data"]
    assert data["dialog_type"] == "prompt"
    assert data["action"] == "accept"
    assert data["handled"] is True
    assert data["dialog_message"] == {
        "present": True,
        "length": len(secret_message),
        "redacted": True,
    }
    assert data["prompt"] == {
        "provided": True,
        "length": len(prompt_text),
        "redacted": True,
    }
    assert data["final_url"] == "https://example.test/dialog"
    receipt = data["receipt"]
    assert receipt["kind"] == "page_dialog_respond"
    assert receipt["side_effect"] == "dialog_response"
    assert receipt["status"] == "success"
    assert receipt["redacted"] is True
    assert context.task_summary().receipt_count == 1
    assert context.capability_set().capabilities[0].status == "supported"
    assert len(fake_dialogs.responses) == 1
    response_args = fake_dialogs.responses[0]
    assert response_args["pending"] == {
        "dialog_type": "prompt",
        "message": secret_message,
    }
    assert response_args["action"] == "accept"
    assert response_args["prompt_text"] == prompt_text
    assert 0 < float(response_args["timeout"]) <= 2
    encoded = json.dumps(outcome.structured_content(), ensure_ascii=False)
    assert secret_message not in encoded
    assert prompt_text not in encoded
    assert "token=secret" not in encoded


@pytest.mark.asyncio
async def test_dialog_unsupported_fails_before_response_claim_or_receipt() -> None:
    class UnsupportedDialogs:
        response_calls = 0

        def probe(self) -> None:
            raise DialogUnsupportedError("HANDLE_ALERT_API_UNAVAILABLE")

        async def wait_for_pending(self, *, timeout: float) -> dict[str, str]:
            raise AssertionError("unsupported dialog must not be awaited")

        async def respond(self, **kwargs: object) -> None:
            self.response_calls += 1

    context = DrissionPageContext()
    fake_dialogs = UnsupportedDialogs()
    context._current_tab = SimpleNamespace(  # type: ignore[assignment]
        url="https://example.test/dialog",
        mcp_tab_id="t0",
        dialogs=fake_dialogs,
    )

    outcome = await page_dialog_respond.execute(
        context, PageDialogRespondInput(action="accept", timeout=1)
    )

    assert outcome.is_error is True
    assert outcome.structured_content()["error"]["code"] == "UNSUPPORTED_OPERATION"
    assert fake_dialogs.response_calls == 0
    assert context.task_summary().operation_count == 0
    assert context.task_summary().receipt_count == 0
    capability = context.capability_set().capabilities[0]
    assert capability.name == "dialog.respond"
    assert capability.status == "unsupported"
    assert capability.reason_code == "HANDLE_ALERT_API_UNAVAILABLE"


@pytest.mark.asyncio
async def test_prompt_text_for_non_prompt_fails_before_claim_or_response() -> None:
    class AlertDialogs:
        response_calls = 0

        def probe(self) -> None:
            return None

        async def wait_for_pending(self, *, timeout: float) -> dict[str, str]:
            return {"dialog_type": "alert", "message": "redacted"}

        async def respond(self, **kwargs: object) -> None:
            self.response_calls += 1

    context = DrissionPageContext()
    dialogs = AlertDialogs()
    context._current_tab = SimpleNamespace(  # type: ignore[assignment]
        url="https://example.test/dialog",
        mcp_tab_id="t0",
        dialogs=dialogs,
    )

    outcome = await page_dialog_respond.execute(
        context,
        PageDialogRespondInput(action="accept", prompt_text="not-for-alert"),
    )

    assert outcome.is_error is True
    assert outcome.structured_content()["error"]["code"] == "PRECONDITION_FAILED"
    assert dialogs.response_calls == 0
    assert context.task_summary().operation_count == 0
    assert context.task_summary().receipt_count == 0


@pytest.mark.asyncio
async def test_recorded_dialog_denial_happens_before_tab_access() -> None:
    context = DrissionPageContext()
    context.set_capability_set(
        CapabilitySet(
            overall_status="unsupported",
            capabilities=(
                CapabilityProbe(
                    name="dialog.respond",
                    status="unsupported",
                    evidence_source="runtime_probe",
                    reason_code="HANDLE_ALERT_API_UNAVAILABLE",
                    checked_at=datetime.now(timezone.utc),
                ),
            ),
        )
    )

    outcome = await page_dialog_respond.execute(
        context, PageDialogRespondInput(action="accept", timeout=1)
    )

    assert outcome.is_error is True
    assert outcome.structured_content()["error"]["code"] == "UNSUPPORTED_OPERATION"
    assert context.task_summary().operation_count == 0
    assert context.task_summary().receipt_count == 0


@pytest.mark.asyncio
async def test_dialog_native_error_is_redacted_and_indeterminate() -> None:
    secret = "native-secret-value"

    class FailingDialogs:
        def probe(self) -> None:
            return None

        async def wait_for_pending(self, *, timeout: float) -> dict[str, str]:
            return {"dialog_type": "prompt", "message": "redacted"}

        async def respond(self, **kwargs: object) -> None:
            raise DialogResponseIndeterminateError(secret)

    context = DrissionPageContext()
    context._current_tab = SimpleNamespace(  # type: ignore[assignment]
        url="https://example.test/dialog",
        mcp_tab_id="t0",
        dialogs=FailingDialogs(),
    )

    outcome = await page_dialog_respond.execute(
        context,
        PageDialogRespondInput(action="accept", prompt_text=secret),
    )

    encoded = json.dumps(outcome.structured_content(), ensure_ascii=False)
    assert outcome.is_error is True
    assert secret not in encoded
    receipt = context.receipt_inventory()[0]
    assert receipt.status == "indeterminate"
    assert receipt.error_code == "DIALOG_RESPONSE_INDETERMINATE"


@pytest.mark.asyncio
async def test_dialog_timeout_is_one_shared_budget() -> None:
    class SlowDialogs:
        def probe(self) -> None:
            return None

        async def wait_for_pending(self, *, timeout: float) -> dict[str, str]:
            await asyncio.sleep(timeout * 0.7)
            return {"dialog_type": "alert", "message": "redacted"}

        async def respond(self, **kwargs: object) -> None:
            await asyncio.sleep(float(kwargs["timeout"]) + 0.02)
            raise DialogResponseIndeterminateError("late")

    context = DrissionPageContext()
    context._current_tab = SimpleNamespace(  # type: ignore[assignment]
        url="https://example.test/dialog",
        mcp_tab_id="t0",
        dialogs=SlowDialogs(),
    )

    started = monotonic()
    outcome = await page_dialog_respond.execute(
        context, PageDialogRespondInput(action="accept", timeout=0.1)
    )
    elapsed = monotonic() - started

    assert outcome.is_error is True
    assert elapsed < 0.15


class _Clicker:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def __call__(self) -> None:
        self.calls.append(("call", {}))

    def right(self) -> None:
        self.calls.append(("right", {}))

    def multi(self, *, times: int) -> None:
        self.calls.append(("multi", {"times": times}))

    def at(self, *, button: str, count: int) -> None:
        self.calls.append(("at", {"button": button, "count": count}))


class _ElementTab:
    def __init__(self, clicker: object) -> None:
        self.element = SimpleNamespace(click=clicker)
        self.stabilize_calls = 0

    async def _element_by_plan(self, plan: object, *, timeout: int) -> object:
        return self.element

    async def _stabilize(self, *args: object, **kwargs: object) -> None:
        self.stabilize_calls += 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("button", "click_count", "expected"),
    [
        ("left", 1, ("call", {})),
        ("right", 1, ("right", {})),
        ("left", 2, ("multi", {"times": 2})),
        ("middle", 2, ("at", {"button": "middle", "count": 2})),
    ],
)
async def test_element_click_uses_exact_native_clicker_path(
    button: str, click_count: int, expected: tuple[str, dict[str, object]]
) -> None:
    clicker = _Clicker()
    tab = _ElementTab(clicker)

    await ElementOperations(tab).click(  # type: ignore[arg-type]
        "#target", timeout=1, button=button, click_count=click_count
    )

    assert clicker.calls == [expected]
    assert tab.stabilize_calls == 1


@pytest.mark.asyncio
async def test_unsupported_click_variant_never_substitutes_a_left_click() -> None:
    class LeftOnlyClicker:
        calls = 0

        def __call__(self) -> None:
            self.calls += 1

    clicker = LeftOnlyClicker()
    element_tab = _ElementTab(clicker)
    context = DrissionPageContext()
    context._current_tab = SimpleNamespace(  # type: ignore[assignment]
        url="https://example.test/click-variants",
        mcp_tab_id="t0",
        elements=ElementOperations(element_tab),  # type: ignore[arg-type]
    )

    outcome = await click_element.execute(
        context,
        ClickElementInput(
            selector="#click-target", button="right", click_count=1, timeout=1
        ),
    )

    assert outcome.is_error is True
    assert outcome.structured_content()["error"]["code"] == "UNSUPPORTED_OPERATION"
    assert clicker.calls == 0
    assert element_tab.stabilize_calls == 0
    capability = context.capability_set().capabilities[0]
    assert capability.name == "element.click.right"
    assert capability.status == "unsupported"
    assert capability.reason_code == "RIGHT_CLICK_UNAVAILABLE"


@pytest.mark.asyncio
async def test_recorded_click_denial_happens_before_tab_or_dom_access() -> None:
    context = DrissionPageContext()
    context.set_capability_set(
        CapabilitySet(
            overall_status="unsupported",
            capabilities=(
                CapabilityProbe(
                    name="element.click.right",
                    status="unsupported",
                    evidence_source="runtime_probe",
                    reason_code="RIGHT_CLICK_UNAVAILABLE",
                    checked_at=datetime.now(timezone.utc),
                ),
            ),
        )
    )

    outcome = await click_element.execute(
        context,
        ClickElementInput(selector="#target", button="right", timeout=1),
    )

    assert outcome.is_error is True
    assert outcome.structured_content()["error"]["code"] == "UNSUPPORTED_OPERATION"


@pytest.mark.asyncio
async def test_right_click_denial_does_not_block_supported_double_click() -> None:
    class DoubleOnlyClicker:
        def __init__(self) -> None:
            self.multi_calls = 0

        def __call__(self) -> None:
            raise AssertionError("left single click must not be substituted")

        def multi(self, *, times: int) -> None:
            assert times == 2
            self.multi_calls += 1

    clicker = DoubleOnlyClicker()
    element_tab = _ElementTab(clicker)
    context = DrissionPageContext()
    context._current_tab = SimpleNamespace(  # type: ignore[assignment]
        url="https://example.test/click-variants",
        mcp_tab_id="t0",
        elements=ElementOperations(element_tab),  # type: ignore[arg-type]
    )

    right = await click_element.execute(
        context,
        ClickElementInput(selector="#target", button="right", timeout=1),
    )
    double = await click_element.execute(
        context,
        ClickElementInput(selector="#target", click_count=2, timeout=1),
    )

    assert right.is_error is True
    assert double.is_error is False
    assert clicker.multi_calls == 1
