"""Base classes for DrissionPage MCP tools."""

from enum import Enum
from typing import TYPE_CHECKING, Awaitable, Callable

from pydantic import BaseModel

if TYPE_CHECKING:
    from ..context import DrissionPageContext
    from ..response import ToolResponse


class ToolType(Enum):
    """Tool operation types."""

    READ_ONLY = "readOnly"
    DESTRUCTIVE = "destructive"


class ToolSchema:
    """Schema definition for a tool."""

    def __init__(
        self,
        name: str,
        title: str,
        description: str,
        input_schema: type[BaseModel],
        tool_type: ToolType = ToolType.READ_ONLY,
        idempotent: bool = False,
    ):
        self.name = name
        self.title = title
        self.description = description
        self.input_schema = input_schema
        self.tool_type = tool_type
        self.idempotent = idempotent


class Tool:
    """Defines a DrissionPage MCP tool."""

    def __init__(
        self,
        schema: ToolSchema,
        handler: Callable[
            ["DrissionPageContext", BaseModel, "ToolResponse"], Awaitable[None]
        ],
    ):
        self.schema = schema
        self.handler = handler

    @property
    def name(self) -> str:
        return self.schema.name

    @property
    def title(self) -> str:
        return self.schema.title

    @property
    def description(self) -> str:
        return self.schema.description

    @property
    def input_schema(self) -> type[BaseModel]:
        return self.schema.input_schema

    @property
    def tool_type(self) -> ToolType:
        return self.schema.tool_type

    @property
    def idempotent(self) -> bool:
        return self.schema.idempotent

    @property
    def execute_func(
        self,
    ) -> Callable[["DrissionPageContext", BaseModel, "ToolResponse"], Awaitable[None]]:
        """Backward-compatible alias for older tests/integrations."""
        return self.handler

    async def execute(
        self, context: "DrissionPageContext", args: BaseModel, response: "ToolResponse"
    ) -> None:
        """Execute the tool."""
        await self.handler(context, args, response)


def define_tool(
    name: str,
    title: str,
    description: str,
    input_schema: type[BaseModel],
    tool_type: ToolType = ToolType.READ_ONLY,
    idempotent: bool = False,
):
    """Decorator for defining tools."""

    def decorator(func):
        schema = ToolSchema(
            name, title, description, input_schema, tool_type, idempotent
        )
        return Tool(schema, func)

    return decorator
