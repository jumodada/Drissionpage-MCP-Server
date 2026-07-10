"""Canonical registry for DrissionPage MCP tool specifications."""

from . import (
    common,
    debug,
    element,
    files,
    forms,
    frame,
    interaction,
    navigate,
    network,
    shadow,
    storage,
    tabs,
    wait,
    workflow,
)
from .base import ToolSpec, ToolType, define_tool


ALL_TOOLS: tuple[ToolSpec, ...] = (
    navigate.navigate,
    navigate.go_back,
    navigate.go_forward,
    navigate.refresh,
    tabs.tab_list,
    tabs.tab_switch,
    tabs.tab_close,
    common.resize,
    common.screenshot,
    common.screenshot_save,
    common.page_snapshot,
    common.page_observe,
    common.page_evaluate,
    common.click_coordinates,
    common.close,
    common.get_url,
    debug.page_console_logs,
    element.find_element,
    element.find_all_elements,
    element.click_element,
    element.type_text,
    element.get_text,
    element.get_attribute,
    element.get_property,
    element.get_html,
    files.element_upload_file,
    interaction.page_scroll,
    interaction.element_scroll_into_view,
    interaction.element_hover,
    interaction.keyboard_press,
    interaction.element_select,
    interaction.element_check,
    forms.form_inspect,
    frame.frame_list,
    frame.frame_snapshot,
    frame.frame_find,
    shadow.shadow_find,
    shadow.shadow_find_all,
    storage.browser_cookies_get,
    storage.storage_get,
    storage.storage_set,
    storage.storage_clear,
    wait.wait_for_element,
    wait.wait_for_url,
    wait.wait_time,
    wait.wait_until,
    workflow.browser_open_and_snapshot,
    workflow.browser_extract_links,
    workflow.form_fill_preview,
    network.network_listen_start,
    network.network_listen_wait,
    network.network_listen_stop,
)


def get_all_tools() -> list[ToolSpec]:
    """Return the single ordered public tool registry."""

    return list(ALL_TOOLS)


__all__ = ["ToolSpec", "ToolType", "define_tool", "get_all_tools"]
