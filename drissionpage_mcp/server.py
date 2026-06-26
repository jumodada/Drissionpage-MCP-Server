"""MCP Server implementation for DrissionPage."""

import inspect
import logging
from typing import Any, Dict, List, Optional

from mcp.server import Server
from mcp.server.lowlevel import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.types import (
    CallToolRequest,
    CallToolResult,
    GetPromptRequest,
    ListPromptsRequest,
    ListResourcesRequest,
    ReadResourceRequest,
    ServerResult,
    Tool,
    ToolAnnotations,
)
from pydantic import ValidationError

from . import __version__
from .context import DrissionPageContext
from .prompts import get_prompt as get_prompt_definition
from .prompts import list_prompts as list_prompt_definitions
from .resources import list_resources as list_resource_definitions
from .resources import read_resource as read_resource_definition
from .response import ErrorCode, ToolResponse, classify_error, tool_result_output_schema
from .tools import Tool as DrissionTool
from .tools import get_all_tools
from .tools.base import ToolType

logger = logging.getLogger(__name__)


class DrissionPageMCPServer:
    """MCP Server for DrissionPage automation."""

    def __init__(self, name: str = "DrissionPage MCP", version: str = __version__):
        self.name = name
        self.version = version
        self.server = Server(name)
        self.context: Optional[DrissionPageContext] = None
        self.tools: Dict[str, DrissionTool] = {}

        # Load tools
        self._load_tools()

        # Register handlers
        self._setup_handlers()

    def _load_tools(self) -> None:
        """Load all available tools."""
        tools = get_all_tools()
        self.tools = {tool.name: tool for tool in tools}
        logger.info(f"Loaded {len(self.tools)} tools: {list(self.tools.keys())}")

    def _setup_handlers(self) -> None:
        """Set up MCP request handlers."""

        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            """List available tools."""
            return [self._tool_to_mcp_tool(tool) for tool in self.tools.values()]

        @self.server.list_resources()
        async def list_resources():
            """List MCP resources."""
            return list_resource_definitions()

        @self.server.read_resource()
        async def read_resource(uri):
            """Read an MCP resource without initializing the browser."""
            return read_resource_definition(
                str(uri),
                context=self.context,
                tools=self.tools,
            )

        @self.server.list_prompts()
        async def list_prompts():
            """List MCP prompts."""
            return list_prompt_definitions()

        @self.server.get_prompt()
        async def get_prompt(name: str, arguments: Optional[Dict[str, str]] = None):
            """Render an MCP prompt."""
            return get_prompt_definition(name, arguments)

        async def call_tool_impl(
            name: str, arguments: Optional[Dict[str, Any]] = None
        ) -> CallToolResult:
            """Execute a tool with given arguments and preserve isError semantics."""
            # Ensure context is available
            if not self.context:
                self.context = DrissionPageContext()

            response = ToolResponse()

            # Find tool
            tool = self.tools.get(name)
            if not tool:
                replacement = REMOVED_TOOL_REPLACEMENTS.get(name)
                message = f"Tool '{name}' not found"
                details: Dict[str, Any] = {"tool_name": name}
                if replacement:
                    message = f"{message}. Use '{replacement}' instead."
                    details["suggested_tool"] = replacement
                response.add_error(
                    message,
                    ErrorCode.TOOL_NOT_FOUND,
                    **details,
                )
                return self._call_result(response)

            try:
                # Validate input
                validated_args = tool.input_schema.model_validate(arguments or {})

                # Execute tool
                await tool.execute(self.context, validated_args, response)

                # Return response content
                return self._call_result(response)

            except ValidationError as e:
                response.clear()
                response.add_error(
                    "Input validation error: %s" % e,
                    ErrorCode.MCP_ARGUMENT_INVALID,
                    tool_name=name,
                )
                return self._call_result(response)
            except Exception as e:
                logger.exception(f"Error executing tool {name}")
                response.clear()
                response.add_error(
                    f"Error executing tool {name}: {str(e)}",
                    classify_error(e, name),
                    tool_name=name,
                )
                return self._call_result(response)

        async def call_tool_handler(req: CallToolRequest) -> ServerResult:
            """MCP request handler for tool calls.

            The low-level SDK decorator normalizes tuple/dict returns with
            ``isError=False``. Registering the handler directly keeps tool-level
            failures distinguishable while still returning structuredContent.
            """
            result = await call_tool_impl(
                req.params.name,
                dict(req.params.arguments or {}),
            )
            return ServerResult(result)

        self.server.request_handlers[CallToolRequest] = call_tool_handler
        self._call_tool_impl = call_tool_impl

        # Touch these imports so static analysis keeps the request types associated
        # with the decorators above.
        _ = (ListResourcesRequest, ReadResourceRequest, ListPromptsRequest, GetPromptRequest)

    def _tool_to_mcp_tool(self, tool: DrissionTool) -> Tool:
        """Convert an internal tool definition to an MCP SDK Tool model."""

        kwargs: Dict[str, Any] = {
            "name": tool.name,
            "title": tool.title,
            "description": tool.description,
            "inputSchema": tool.input_schema.model_json_schema(),
            "annotations": ToolAnnotations(
                title=tool.title,
                readOnlyHint=tool.tool_type == ToolType.READ_ONLY,
                destructiveHint=tool.tool_type == ToolType.DESTRUCTIVE,
                idempotentHint=tool.idempotent,
                openWorldHint=True,
            ),
        }
        if _tool_supports_output_schema():
            kwargs["outputSchema"] = tool_result_output_schema(tool.name)
        return Tool(**kwargs)

    def _call_result(self, response: ToolResponse) -> CallToolResult:
        """Build a direct MCP call result for tests and internal callers."""
        return CallToolResult(
            content=list(response.get_content()),
            structuredContent=response.get_structured_content(),
            isError=response.is_error(),
        )

    async def run_server(self, read_stream, write_stream) -> None:
        """Run the MCP server with stdio streams."""
        try:
            await self.server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name=self.name,
                    server_version=self.version,
                    capabilities=self.server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )
        except Exception as e:
            logger.error(f"Server run error: {e}")
            raise
        finally:
            await self.cleanup()

    async def cleanup(self) -> None:
        """Clean up resources."""
        if self.context:
            result = self.context.cleanup()
            if inspect.isawaitable(result):
                await result
            self.context = None
        logger.info("Server cleanup completed")


def _tool_supports_output_schema() -> bool:
    """Return whether the installed MCP SDK Tool model accepts outputSchema."""

    fields = getattr(Tool, "model_fields", None) or getattr(Tool, "__fields__", {})
    if "outputSchema" in fields:
        return True
    try:
        return "outputSchema" in inspect.signature(Tool).parameters
    except (TypeError, ValueError):
        return False


REMOVED_TOOL_REPLACEMENTS = {
    "element_input_text": "element_type",
    "wait_sleep": "wait_time",
}
