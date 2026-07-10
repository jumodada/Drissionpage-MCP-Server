"""Cookies and web storage tools for DrissionPage MCP."""

from __future__ import annotations
from typing import TYPE_CHECKING, Literal
from pydantic import Field
from .base import ToolInput, ToolType, define_tool, ToolOutcome
from ..tool_outputs import (
    BrowserCookiesGetData,
    StorageGetData,
    StorageSetData,
    StorageClearData,
)

if TYPE_CHECKING:
    from ..context import DrissionPageContext
StorageArea = Literal["local", "session"]


class BrowserCookiesGetInput(ToolInput):
    """Input schema for reading cookies."""

    all_domains: bool = Field(default=False)
    all_info: bool = Field(default=False)
    include_values: bool = Field(
        default=False,
        description="Return cookie values. Defaults to false to avoid leaking secrets.",
    )


class StorageGetInput(ToolInput):
    """Input schema for reading web storage."""

    area: StorageArea = Field(default="local")
    key: str = Field(default="", description="Optional key. Empty returns all keys.")
    include_values: bool = Field(default=True)


class StorageSetInput(ToolInput):
    """Input schema for setting web storage."""

    area: StorageArea = Field(default="local")
    key: str = Field(..., min_length=1)
    value: str = Field(..., description="String value to store. Not echoed in result.")


class StorageClearInput(ToolInput):
    """Input schema for clearing web storage."""

    area: StorageArea = Field(default="local")
    key: str = Field(default="", description="Optional key. Empty clears the area.")


@define_tool(
    name="browser_cookies_get",
    title="Get Browser Cookies",
    description="Read normalized cookies with values redacted by default.",
    input_schema=BrowserCookiesGetInput,
    tool_type=ToolType.READ_ONLY,
    idempotent=True,
    output_model=BrowserCookiesGetData,
    failure_message=lambda args, exc: "Failed to read browser cookies: " + str(exc),
)
async def browser_cookies_get(
    context: "DrissionPageContext", args: BrowserCookiesGetInput
) -> "ToolOutcome":
    outcome = ToolOutcome()
    tab = context.current_tab_or_die()
    result = await tab.storage.cookies_get(
        all_domains=args.all_domains,
        all_info=args.all_info,
        include_values=args.include_values,
    )
    outcome.add_code("page.cookies()")
    outcome.add_result(f"Read {result['count']} cookie(s)", **result)
    return outcome


@define_tool(
    name="storage_get",
    title="Get Web Storage",
    description="Read localStorage or sessionStorage by key or as a bounded map.",
    input_schema=StorageGetInput,
    tool_type=ToolType.READ_ONLY,
    idempotent=True,
    output_model=StorageGetData,
    failure_message=lambda args, exc: f"{f'Failed to read {args.area} storage'}: {exc}",
)
async def storage_get(
    context: "DrissionPageContext", args: StorageGetInput
) -> "ToolOutcome":
    outcome = ToolOutcome()
    tab = context.current_tab_or_die()
    result = await tab.storage.get(
        area=args.area, key=args.key, include_values=args.include_values
    )
    outcome.add_code(f"{args.area}Storage")
    outcome.add_result(f"Read {args.area} storage", **result)
    return outcome


@define_tool(
    name="storage_set",
    title="Set Web Storage",
    description="Set one localStorage/sessionStorage item. The value is not echoed.",
    input_schema=StorageSetInput,
    tool_type=ToolType.DESTRUCTIVE,
    output_model=StorageSetData,
    failure_message=lambda args, exc: f"{f'Failed to set {args.area} storage'}: {exc}",
)
async def storage_set(
    context: "DrissionPageContext", args: StorageSetInput
) -> "ToolOutcome":
    outcome = ToolOutcome()
    tab = context.current_tab_or_die()
    result = await tab.storage.set(area=args.area, key=args.key, value=args.value)
    outcome.add_code(f"{args.area}Storage.setItem({args.key!r}, <redacted>)")
    outcome.add_result(f"Set {args.area} storage key: {args.key}", **result)
    outcome.set_include_snapshot(True)
    return outcome


@define_tool(
    name="storage_clear",
    title="Clear Web Storage",
    description="Clear one key or all items from localStorage/sessionStorage.",
    input_schema=StorageClearInput,
    tool_type=ToolType.DESTRUCTIVE,
    output_model=StorageClearData,
    failure_message=lambda args, exc: f"{f'Failed to clear {args.area} storage'}: {exc}",
)
async def storage_clear(
    context: "DrissionPageContext", args: StorageClearInput
) -> "ToolOutcome":
    outcome = ToolOutcome()
    tab = context.current_tab_or_die()
    result = await tab.storage.clear(area=args.area, key=args.key)
    outcome.add_code(f"{args.area}Storage.removeItem({args.key!r})")
    outcome.add_result(f"Cleared {args.area} storage", **result)
    outcome.set_include_snapshot(True)
    return outcome
