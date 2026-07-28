"""Origin-scoped Chromium permission controls."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlsplit, urlunsplit

from ..response_errors import ErrorCode

if TYPE_CHECKING:
    from ..tab import PageTab


PermissionName = Literal[
    "geolocation",
    "notifications",
    "camera",
    "microphone",
    "clipboard-read",
    "clipboard-write",
    "midi",
    "midi-sysex",
    "background-sync",
    "persistent-storage",
    "sensors",
    "payment-handler",
    "idle-detection",
]
PermissionSetting = Literal["granted", "denied", "prompt"]
PermissionState = Literal["granted", "denied", "prompt", "unsupported"]

_CDP_PERMISSION_NAMES: dict[str, str] = {
    "geolocation": "geolocation",
    "notifications": "notifications",
    "camera": "videoCapture",
    "microphone": "audioCapture",
    "clipboard-read": "clipboardReadWrite",
    "clipboard-write": "clipboardSanitizedWrite",
    "midi": "midi",
    "midi-sysex": "midiSysex",
    "background-sync": "backgroundSync",
    "persistent-storage": "durableStorage",
    "sensors": "sensors",
    "payment-handler": "paymentHandler",
    "idle-detection": "idleDetection",
}


class PermissionUnsupportedError(RuntimeError):
    """Raised when the attached DrissionPage browser cannot control permissions."""

    code = ErrorCode.UNSUPPORTED_OPERATION

    def __init__(self, reason_code: str):
        super().__init__(
            "Browser permission control is unsupported by this runtime "
            f"({reason_code})."
        )
        self.reason_code = reason_code


class PermissionOperations:
    """Own permission observation and Browser-domain overrides for one tab."""

    def __init__(self, tab: PageTab) -> None:
        self._tab = tab

    @property
    def _page(self) -> Any:
        return self._tab.page

    def current_origin(self) -> str:
        """Return the current document's normalized HTTP(S) origin."""

        return _origin_from_url(self._tab.url)

    def get(self, permission: PermissionName) -> dict[str, Any]:
        """Query the current document through the Permissions API."""

        query = getattr(self._page, "run_js", None)
        if not callable(query):
            raise PermissionUnsupportedError("NAVIGATOR_PERMISSIONS_UNAVAILABLE")
        script = """
        return navigator.permissions.query({name: arguments[0]})
          .then(result => ({supported: true, state: result.state}))
          .catch(error => ({supported: false, error_name: String(error && error.name || 'Error')}));
        """
        try:
            result = query(script, permission)
        except Exception as exc:
            raise PermissionUnsupportedError("PERMISSION_QUERY_FAILED") from exc
        if not isinstance(result, dict):
            raise PermissionUnsupportedError("PERMISSION_QUERY_INVALID_RESULT")
        state = result.get("state")
        if result.get("supported") is True and state in {
            "granted",
            "denied",
            "prompt",
        }:
            return {
                "permission": permission,
                "state": state,
                "origin": self.current_origin(),
                "query_supported": True,
            }
        return {
            "permission": permission,
            "state": "unsupported",
            "origin": self.current_origin(),
            "query_supported": False,
        }

    def set(
        self,
        permission: PermissionName,
        setting: PermissionSetting,
        origin: str,
    ) -> dict[str, Any]:
        """Apply one permission setting to one origin in the current context."""

        run_cdp = self._browser_cdp()
        arguments: dict[str, Any] = {
            "permission": {"name": _CDP_PERMISSION_NAMES[permission]},
            "setting": setting,
            "origin": origin,
        }
        browser_context_id = self.browser_context_id()
        if browser_context_id is not None:
            arguments["browserContextId"] = browser_context_id
        try:
            run_cdp("Browser.setPermission", **arguments)
        except Exception as exc:
            raise PermissionUnsupportedError("BROWSER_SET_PERMISSION_FAILED") from exc

        observed_state: PermissionState | None = None
        verified = False
        if self.current_origin() == origin:
            try:
                observation = self.get(permission)
            except PermissionUnsupportedError:
                pass
            else:
                observed_state = observation["state"]
                verified = observed_state == setting
        return {
            "permission": permission,
            "setting": setting,
            "origin": origin,
            "applied": True,
            "verified": verified,
            "observed_state": observed_state,
            "context_scope": "current_browser_context",
        }

    def reset(self) -> dict[str, Any]:
        """Reset all permission overrides in the current browser context."""

        run_cdp = self._browser_cdp()
        arguments: dict[str, str] = {}
        browser_context_id = self.browser_context_id()
        if browser_context_id is not None:
            arguments["browserContextId"] = browser_context_id
        try:
            run_cdp("Browser.resetPermissions", **arguments)
        except Exception as exc:
            raise PermissionUnsupportedError("BROWSER_RESET_PERMISSIONS_FAILED") from exc
        return {"reset": True, "context_scope": "current_browser_context"}

    def browser_context_id(self) -> str | None:
        """Return a real non-default context id, omitting Chromium's default id."""

        run_cdp = self._browser_cdp()
        try:
            contexts = run_cdp("Target.getBrowserContexts").get(
                "browserContextIds", []
            )
            target = run_cdp(
                "Target.getTargetInfo", targetId=self._tab.native_tab_id
            ).get("targetInfo", {})
        except Exception:
            return None
        context_id = target.get("browserContextId")
        return context_id if context_id in contexts else None

    def _browser_cdp(self) -> Any:
        browser = getattr(self._page, "browser", None)
        run_cdp = getattr(browser, "_run_cdp", None)
        if not callable(run_cdp):
            run_cdp = getattr(browser, "run_cdp", None)
        if not callable(run_cdp):
            raise PermissionUnsupportedError("BROWSER_CDP_UNAVAILABLE")
        return run_cdp


def _origin_from_url(value: str) -> str:
    try:
        parts = urlsplit(value)
        port = parts.port
    except (TypeError, ValueError) as exc:
        raise ValueError("Current page does not have a valid HTTP(S) origin.") from exc
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("Current page does not have a valid HTTP(S) origin.")
    host = parts.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = host if port is None else f"{host}:{port}"
    return urlunsplit((parts.scheme, netloc, "", "", ""))


__all__ = [
    "PermissionName",
    "PermissionOperations",
    "PermissionSetting",
    "PermissionState",
    "PermissionUnsupportedError",
]
