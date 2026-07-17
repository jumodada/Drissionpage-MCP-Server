"""Capability-probed JavaScript dialog operations for one browser tab."""

from __future__ import annotations

import asyncio
from inspect import Parameter, signature
from time import monotonic
from typing import TYPE_CHECKING, Any

from ..response_errors import ErrorCode

if TYPE_CHECKING:
    from ..tab import PageTab


class DialogUnsupportedError(RuntimeError):
    """Raised before response when the attached runtime cannot honor dialogs."""

    code = ErrorCode.UNSUPPORTED_OPERATION

    def __init__(self, reason_code: str):
        super().__init__(
            f"JavaScript dialog response is unsupported by this runtime ({reason_code})."
        )
        self.reason_code = reason_code


class DialogPreconditionError(ValueError):
    """Raised when the pending dialog cannot honor the requested response."""

    code = ErrorCode.PRECONDITION_FAILED


class DialogResponseIndeterminateError(RuntimeError):
    """Raised after native invocation when the final dialog state is uncertain."""


class DialogOperations:
    """Own pending-dialog inspection and native DrissionPage response calls."""

    def __init__(self, tab: "PageTab") -> None:
        self._tab = tab

    @property
    def _page(self) -> Any:
        return self._tab.page

    def probe(self) -> None:
        """Fail closed unless the attached runtime exposes the required lifecycle."""

        handler = getattr(self._page, "handle_alert", None)
        if not callable(handler) or not _accepts_parameters(
            handler, "accept", "send", "timeout", "next_one"
        ):
            raise DialogUnsupportedError("HANDLE_ALERT_API_UNAVAILABLE")
        bounded_handler = getattr(self._page, "_handle_alert", None)
        if not callable(bounded_handler) or not _accepts_parameters(
            bounded_handler, "accept", "send", "timeout", "next_one"
        ):
            raise DialogUnsupportedError("BOUNDED_HANDLE_ALERT_API_UNAVAILABLE")
        states = getattr(self._page, "states", None)
        if (
            states is None
            or not hasattr(type(states), "has_alert")
            and not hasattr(states, "has_alert")
        ):
            raise DialogUnsupportedError("ALERT_STATE_UNAVAILABLE")
        alert = getattr(self._page, "_alert", None)
        if alert is None or any(
            not hasattr(alert, name) for name in ("activated", "type", "text")
        ):
            raise DialogUnsupportedError("ALERT_METADATA_UNAVAILABLE")

    async def wait_for_pending(self, *, timeout: float) -> dict[str, Any]:
        """Wait for one supported pending dialog without responding to it."""

        self.probe()
        deadline = monotonic() + timeout
        while True:
            states = self._page.states
            if bool(states.has_alert):
                alert = self._page._alert
                dialog_type = str(alert.type or "").lower()
                if dialog_type not in {"alert", "confirm", "prompt"}:
                    raise DialogUnsupportedError("DIALOG_TYPE_UNSUPPORTED")
                return {
                    "dialog_type": dialog_type,
                    "message": str(alert.text or ""),
                }
            if monotonic() >= deadline:
                raise TimeoutError(
                    "No pending JavaScript dialog was observed within the timeout."
                )
            await asyncio.sleep(min(0.02, max(0.001, deadline - monotonic())))

    async def respond(
        self,
        *,
        pending: dict[str, Any],
        action: str,
        prompt_text: str | None,
        timeout: float,
    ) -> None:
        """Dispatch one native response and verify closure under one deadline."""

        self.probe()
        alert = self._page._alert
        current_type = str(alert.type or "").lower()
        current_message = str(alert.text or "")
        if not bool(self._page.states.has_alert) or (
            current_type != pending["dialog_type"]
            or current_message != pending["message"]
        ):
            raise DialogPreconditionError(
                "The pending JavaScript dialog changed before it could be handled."
            )
        if prompt_text is not None and current_type != "prompt":
            raise DialogPreconditionError(
                "prompt_text is valid only for a pending prompt dialog."
            )

        deadline = monotonic() + timeout
        try:
            result = self._page._handle_alert(
                accept=action == "accept",
                send=prompt_text,
                timeout=timeout,
                next_one=False,
            )
        except Exception as exc:
            raise DialogResponseIndeterminateError(
                "Dialog response outcome is indeterminate after native invocation."
            ) from exc
        if result is False:
            raise DialogResponseIndeterminateError(
                "Dialog response outcome is indeterminate after native invocation."
            )
        while bool(self._page.states.has_alert):
            if monotonic() >= deadline:
                raise DialogResponseIndeterminateError(
                    "Dialog response outcome is indeterminate after native invocation."
                )
            await asyncio.sleep(min(0.01, max(0.001, deadline - monotonic())))


def _accepts_parameters(callable_obj: Any, *names: str) -> bool:
    try:
        parameters = signature(callable_obj).parameters
    except (TypeError, ValueError):
        return False
    if any(item.kind == Parameter.VAR_KEYWORD for item in parameters.values()):
        return True
    return all(name in parameters for name in names)
