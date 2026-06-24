"""MCP Server implementation for DrissionPage."""

import inspect
import logging
from typing import Any, Dict, List, Optional

from mcp.server import Server
from mcp.types import (
    CallToolRequest,
    CallToolResult,
    ServerResult,
    Tool,
    ToolAnnotations,
)
from pydantic import ValidationError

from . import __version__
from .context import DrissionPageContext
from .response import ErrorCode, ToolResponse, classify_error
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
            return [
                Tool(
                    name=tool.name,
                    title=tool.title,
                    description=tool.description,
                    inputSchema=tool.input_schema.model_json_schema(),
                    annotations=ToolAnnotations(
                        title=tool.title,
                        readOnlyHint=tool.tool_type == ToolType.READ_ONLY,
                        destructiveHint=tool.tool_type == ToolType.DESTRUCTIVE,
                        idempotentHint=tool.idempotent,
                        openWorldHint=True,
                    ),
                )
                for tool in self.tools.values()
            ]

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
                response.add_error(
                    f"Tool '{name}' not found",
                    ErrorCode.TOOL_NOT_FOUND,
                    tool_name=name,
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
                read_stream, write_stream, self.server.create_initialization_options()
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
