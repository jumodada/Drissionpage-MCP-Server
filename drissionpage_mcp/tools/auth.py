"""Credential-redacted HTTP authentication navigation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, StrictStr, StringConstraints, field_validator

from ..limits import MAX_WAIT_SECONDS
from ..policy import PolicyDeniedError, validate_navigation
from ..response_errors import ErrorCode
from ..tool_outputs import PageNavigateWithHttpAuthData
from .base import ToolInput, ToolOutcome, ToolType, define_tool

if TYPE_CHECKING:
    from ..context import DrissionPageContext


AuthUrl = Annotated[
    StrictStr,
    StringConstraints(min_length=1, max_length=4096, strip_whitespace=True),
]
AuthRealm = Annotated[
    StrictStr,
    StringConstraints(min_length=1, max_length=1024),
]


class PageNavigateWithHttpAuthInput(ToolInput):
    """Navigate in an isolated browser context using one HTTP auth challenge."""

    url: AuthUrl
    username: SecretStr = Field(..., min_length=1, max_length=1024)
    password: SecretStr = Field(..., min_length=1, max_length=4096)
    realm: AuthRealm | None = Field(
        default=None,
        description="Optional exact HTTP authentication realm constraint.",
    )
    timeout: float = Field(default=30.0, gt=0, le=MAX_WAIT_SECONDS)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        try:
            parts = urlsplit(value)
            _ = parts.port
        except (TypeError, ValueError) as exc:
            raise ValueError("url must be an absolute HTTP(S) URL") from exc
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
        ):
            raise ValueError(
                "url must be an absolute HTTP(S) URL without embedded credentials"
            )
        return value


@define_tool(
    name="page_navigate_with_http_auth",
    title="Navigate With HTTP Authentication",
    description="Open an isolated Chromium context, answer a bounded HTTP auth challenge, clean Fetch handlers, and retain the isolated authenticated tab until it is closed.",
    input_schema=PageNavigateWithHttpAuthInput,
    tool_type=ToolType.DESTRUCTIVE,
    output_model=PageNavigateWithHttpAuthData,
    failure_message=lambda args, exc: (
        "HTTP authentication navigation failed; credentials and diagnostic "
        "arguments were redacted."
    ),
)
async def page_navigate_with_http_auth(
    context: DrissionPageContext, args: PageNavigateWithHttpAuthInput
) -> ToolOutcome:
    outcome = ToolOutcome()
    try:
        validate_navigation(args.url)
    except PolicyDeniedError as exc:
        outcome.add_error(
            str(exc), ErrorCode.POLICY_DENIED, rule=exc.rule, value=exc.value
        )
        return outcome
    result = await context.navigate_with_http_auth(
        url=args.url,
        username=args.username.get_secret_value(),
        password=args.password.get_secret_value(),
        realm=args.realm,
        timeout=args.timeout,
    )
    outcome.set_result("Completed isolated HTTP authentication navigation", result)
    return outcome


__all__ = ["PageNavigateWithHttpAuthInput", "page_navigate_with_http_auth"]
