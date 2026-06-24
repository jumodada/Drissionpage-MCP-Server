"""MCP Server implementation for DrissionPage."""

import inspect
import logging
from typing import Any, Dict, List, Optional, Sequence

from mcp.server import Server
from mcp.types import (
    ImageContent,
    TextContent,
    Tool,
    ToolAnnotations,
)

from .context import DrissionPageContext
from .response import ToolResponse
from . import __version__
from .tools import get_all_tools, Tool as DrissionTool
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
                        openWorldHint=True,
                    ),
                )
                for tool in self.tools.values()
            ]
        
        @self.server.call_tool()
        async def call_tool(name: str, arguments: Optional[Dict[str, Any]] = None) -> Sequence[TextContent | ImageContent]:
            """Execute a tool with given arguments."""
            # Ensure context is available
            if not self.context:
                self.context = DrissionPageContext()
            
            # Find tool
            tool = self.tools.get(name)
            if not tool:
                return [TextContent(type="text", text=f"Tool '{name}' not found")]
            
            try:
                # Validate input
                validated_args = tool.input_schema.model_validate(arguments or {})
                
                # Create response object
                response = ToolResponse()
                
                # Execute tool
                await tool.execute(self.context, validated_args, response)
                
                # Return response content
                return response.get_content()
                
            except Exception as e:
                logger.exception(f"Error executing tool {name}")
                return [TextContent(
                    type="text", 
                    text=f"Error executing tool {name}: {str(e)}"
                )]
    
    async def run_server(self, read_stream, write_stream) -> None:
        """Run the MCP server with stdio streams."""
        try:
            from mcp.server.stdio import stdio_server
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options()
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
