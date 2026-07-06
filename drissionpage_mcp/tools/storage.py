"""Cookies and web storage tools for DrissionPage MCP."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import Field

from .base import ToolInput, ToolType, define_tool, tool_errors

if TYPE_CHECKING:
    from ..context import DrissionPageContext
    from ..response import ToolResponse


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
)
async def browser_cookies_get(
    context: "DrissionPageContext",
    args: BrowserCookiesGetInput,
    response: "ToolResponse",
) -> None:
    async with tool_errors(response, "Failed to read browser cookies"):
        tab = context.current_tab_or_die()
        result = await tab.cookies_get(
            all_domains=args.all_domains,
            all_info=args.all_info,
            include_values=args.include_values,
        )
        response.add_code("page.cookies()")
        response.add_result(f"Read {result['count']} cookie(s)", **result)


@define_tool(
    name="storage_get",
    title="Get Web Storage",
    description="Read localStorage or sessionStorage by key or as a bounded map.",
    input_schema=StorageGetInput,
    tool_type=ToolType.READ_ONLY,
    idempotent=True,
)
async def storage_get(
    context: "DrissionPageContext", args: StorageGetInput, response: "ToolResponse"
) -> None:
    async with tool_errors(response, f"Failed to read {args.area} storage"):
        tab = context.current_tab_or_die()
        result = await tab.storage_get(
            area=args.area,
            key=args.key,
            include_values=args.include_values,
        )
        response.add_code(f"{args.area}Storage")
        response.add_result(f"Read {args.area} storage", **result)


@define_tool(
    name="storage_set",
    title="Set Web Storage",
    description="Set one localStorage/sessionStorage item. The value is not echoed.",
    input_schema=StorageSetInput,
    tool_type=ToolType.DESTRUCTIVE,
)
async def storage_set(
    context: "DrissionPageContext", args: StorageSetInput, response: "ToolResponse"
) -> None:
    async with tool_errors(response, f"Failed to set {args.area} storage"):
        tab = context.current_tab_or_die()
        result = await tab.storage_set(area=args.area, key=args.key, value=args.value)
        response.add_code(f"{args.area}Storage.setItem({args.key!r}, <redacted>)")
        response.add_result(f"Set {args.area} storage key: {args.key}", **result)
        response.set_include_snapshot(True)


@define_tool(
    name="storage_clear",
    title="Clear Web Storage",
    description="Clear one key or all items from localStorage/sessionStorage.",
    input_schema=StorageClearInput,
    tool_type=ToolType.DESTRUCTIVE,
)
async def storage_clear(
    context: "DrissionPageContext", args: StorageClearInput, response: "ToolResponse"
) -> None:
    async with tool_errors(response, f"Failed to clear {args.area} storage"):
        tab = context.current_tab_or_die()
        result = await tab.storage_clear(area=args.area, key=args.key)
        response.add_code(f"{args.area}Storage.removeItem({args.key!r})")
        response.add_result(f"Cleared {args.area} storage", **result)
        response.set_include_snapshot(True)


tools = [browser_cookies_get, storage_get, storage_set, storage_clear]
