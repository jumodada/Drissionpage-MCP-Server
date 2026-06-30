"""Tools module for DrissionPage MCP."""

from . import common, element, forms, navigate, tabs, wait
from .base import Tool, ToolSchema, ToolType, define_tool


def get_all_tools() -> list[Tool]:
    """Get all available tools."""
    all_tools = []

    # Import tools from each module
    all_tools.extend(navigate.tools)
    all_tools.extend(tabs.tools)
    all_tools.extend(common.tools)
    all_tools.extend(element.tools)
    all_tools.extend(forms.tools)
    all_tools.extend(wait.tools)

    return all_tools

__all__ = [
    "Tool",
    "ToolSchema",
    "ToolType",
    "define_tool",
    "get_all_tools",
]
