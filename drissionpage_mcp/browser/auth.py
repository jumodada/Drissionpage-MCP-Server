"""Isolated Chromium HTTP authentication navigation."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit, urlunsplit

from ..compat import accepts_parameters
from ..response_errors import ErrorCode
from ..tool_outputs import sanitize_public_url

if TYPE_CHECKING:
    from ..tab import PageTab


class HttpAuthError(RuntimeError):
    """Safe HTTP-auth failure that never renders credentials or CDP arguments."""

    code = ErrorCode.PAGE_NAVIGATION_FAILED

    def __init__(self, reason_code: str):
        super().__init__(f"HTTP authentication navigation failed ({reason_code}).")
        self.reason_code = reason_code


class HttpAuthOperations:
    """Handle one Fetch auth lifetime inside a dedicated browser context."""

    def __init__(self, tab: PageTab) -> None:
        self._tab = tab

    async def navigate(
        self,
        *,
        url: str,
        username: str,
        password: str,
        realm: str | None,
        timeout: float,
    ) -> dict[str, Any]:
        page = self._tab.page
        driver = getattr(page, "driver", None)
        set_callback = getattr(driver, "set_callback", None)
        run_cdp = getattr(page, "run_cdp", None)
        navigate = getattr(page, "get", None)
        if not callable(set_callback):
            raise HttpAuthError("FETCH_AUTH_API_UNAVAILABLE")
        if not callable(run_cdp):
            raise HttpAuthError("FETCH_AUTH_API_UNAVAILABLE")
        if not callable(navigate):
            raise HttpAuthError("FETCH_AUTH_API_UNAVAILABLE")
        handlers = getattr(driver, "event_handlers", {})
        if any(
            name in handlers for name in ("Fetch.requestPaused", "Fetch.authRequired")
        ):
            raise HttpAuthError("FETCH_HANDLER_ALREADY_ACTIVE")

        origin = _http_origin(url)
        target_url = urlunsplit((*urlsplit(url)[:4], ""))
        attempts: dict[str, int] = {}
        callback_errors: list[str] = []
        challenge_count = 0
        provided_count = 0
        response_status: int | None = None

        def continue_paused(**event: Any) -> None:
            nonlocal response_status
            request_url = str(event.get("request", {}).get("url", ""))
            if request_url == target_url and isinstance(
                event.get("responseStatusCode"), int
            ):
                response_status = event["responseStatusCode"]
            try:
                run_cdp("Fetch.continueRequest", requestId=event["requestId"])
            except Exception:
                callback_errors.append("CONTINUE_REQUEST_FAILED")

        def continue_auth(**event: Any) -> None:
            nonlocal challenge_count, provided_count
            challenge_count += 1
            request_id = str(event.get("requestId", ""))
            request_url = str(event.get("request", {}).get("url", ""))
            challenge = event.get("authChallenge", {})
            seen = attempts.get(request_id, 0)
            attempts[request_id] = seen + 1
            matches_scope = _safe_origin(request_url) == origin
            matches_realm = realm is None or challenge.get("realm") == realm
            if seen == 0 and matches_scope and matches_realm:
                response = {
                    "response": "ProvideCredentials",
                    "username": username,
                    "password": password,
                }
                provided_count += 1
            else:
                response = {"response": "CancelAuth"}
            try:
                run_cdp(
                    "Fetch.continueWithAuth",
                    requestId=event["requestId"],
                    authChallengeResponse=response,
                )
            except Exception:
                callback_errors.append("CONTINUE_AUTH_FAILED")

        cleanup_error = self._run_auth_lifetime(
            run_cdp=run_cdp,
            set_callback=set_callback,
            continue_paused=continue_paused,
            continue_auth=continue_auth,
            navigate=navigate,
            url=url,
            timeout=timeout,
            callback_errors=callback_errors,
        )
        if cleanup_error is not None:
            raise HttpAuthError(cleanup_error)
        if callback_errors:
            raise HttpAuthError(callback_errors[0])

        authenticated = (
            provided_count > 0
            and response_status is not None
            and response_status not in {401, 407}
        )
        return {
            "url": sanitize_public_url(url),
            "final_url": sanitize_public_url(self._tab.url),
            "authenticated": authenticated,
            "tab_id": self._tab.mcp_tab_id,
            "realm": realm,
            "challenge_count": challenge_count,
            "response_status": response_status,
            "handlers_cleaned": True,
            "credential_scope": "isolated_browser_context",
            "username_provided": bool(username),
            "password_provided": bool(password),
            "credentials_redacted": True,
        }

    @staticmethod
    def _run_auth_lifetime(
        *,
        run_cdp: Callable[..., Any],
        set_callback: Callable[..., Any],
        continue_paused: Callable[..., None],
        continue_auth: Callable[..., None],
        navigate: Callable[..., Any],
        url: str,
        timeout: float,
        callback_errors: list[str],
    ) -> str | None:
        enabled = False
        navigation_result: Any = None
        try:
            set_callback("Fetch.requestPaused", continue_paused)
            set_callback("Fetch.authRequired", continue_auth)
            run_cdp(
                "Fetch.enable",
                patterns=[
                    {"urlPattern": "*", "requestStage": "Request"},
                    {"urlPattern": "*", "requestStage": "Response"},
                ],
                handleAuthRequests=True,
            )
            enabled = True
            if accepts_parameters(navigate, "retry", "timeout"):
                navigation_result = navigate(url, retry=0, timeout=timeout)
            else:
                navigation_result = navigate(url)
        except Exception:
            callback_errors.append("AUTH_NAVIGATION_INVOCATION_FAILED")
        finally:
            cleanup_error: str | None = None
            if enabled:
                try:
                    run_cdp("Fetch.disable")
                except Exception:
                    cleanup_error = "FETCH_DISABLE_FAILED"
            try:
                set_callback("Fetch.requestPaused", None)
                set_callback("Fetch.authRequired", None)
            except Exception:
                cleanup_error = cleanup_error or "FETCH_CALLBACK_CLEANUP_FAILED"
        if navigation_result is False:
            callback_errors.append("AUTHENTICATION_REJECTED")
        return cleanup_error


def _http_origin(value: str) -> str:
    origin = _safe_origin(value)
    if not origin:
        raise HttpAuthError("INVALID_AUTH_ORIGIN")
    return origin


def _safe_origin(value: str) -> str:
    try:
        parts = urlsplit(value)
        port = parts.port
    except (TypeError, ValueError):
        return ""
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
    ):
        return ""
    host = parts.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = host if port is None else f"{host}:{port}"
    return urlunsplit((parts.scheme, netloc, "", "", ""))


__all__ = ["HttpAuthError", "HttpAuthOperations"]
