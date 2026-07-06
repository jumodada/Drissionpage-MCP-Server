"""Tools module for DrissionPage MCP."""

from . import (
    common,
    debug,
    element,
    files,
    forms,
    frame,
    interaction,
    navigate,
    shadow,
    storage,
    tabs,
    wait,
)
from .base import Tool, ToolSchema, ToolType, define_tool


def get_all_tools() -> list[Tool]:
    """Get all available tools."""
    all_tools = []

    # Import tools from each module
    all_tools.extend(navigate.tools)
    all_tools.extend(tabs.tools)
    all_tools.extend(common.tools)
    all_tools.extend(debug.tools)
    all_tools.extend(element.tools)
    all_tools.extend(files.tools)
    all_tools.extend(interaction.tools)
    all_tools.extend(forms.tools)
    all_tools.extend(frame.tools)
    all_tools.extend(shadow.tools)
    all_tools.extend(storage.tools)
    all_tools.extend(wait.tools)

    return all_tools

__all__ = [
    "Tool",
    "ToolSchema",
    "ToolType",
    "define_tool",
    "get_all_tools",
]
