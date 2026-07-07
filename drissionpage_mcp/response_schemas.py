"""Public MCP output schema registry for DrissionPage MCP tools."""

from typing import Any, Dict, Sequence, cast


def tool_data_schema_title(tool_name: str) -> str:
    """Return the public data schema title for a tool."""

    return cast(str, TOOL_DATA_SCHEMAS.get(tool_name, _GENERIC_DATA_SCHEMA)["title"])


def tool_result_output_schema(tool_name: str = "") -> Dict[str, Any]:
    """Return the MCP outputSchema for a tool-specific result envelope."""

    data_schema = TOOL_DATA_SCHEMAS.get(tool_name, _GENERIC_DATA_SCHEMA)
    return {
        "type": "object",
        "oneOf": [
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["ok", "message", "data"],
                "properties": {
                    "ok": {"const": True},
                    "message": {"type": "string"},
                    "data": data_schema,
                },
            },
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["ok", "message", "error"],
                "properties": {
                    "ok": {"const": False},
                    "message": {"type": "string"},
                    "error": ERROR_SCHEMA,
                    "data": {"type": "object", "additionalProperties": True},
                },
            },
        ],
    }


def _data_schema(
    title: str,
    properties: Dict[str, Any],
    required: Sequence[str],
) -> Dict[str, Any]:
    return {
        "title": title,
        "type": "object",
        "additionalProperties": False,
        "required": list(required),
        "properties": properties,
    }


STRING = {"type": "string"}
BOOLEAN = {"type": "boolean"}
INTEGER = {"type": "integer"}
NUMBER = {"type": "number"}
ANY_JSON: Dict[str, Any] = {}
NULLABLE_INTEGER = {"type": ["integer", "null"]}
SELECTOR_METADATA_SCHEMA = {
    "selector": STRING,
    "locator": STRING,
    "selector_strategy": STRING,
    "selector_normalized": BOOLEAN,
}
SELECTOR_METADATA_REQUIRED = [
    "selector",
    "locator",
    "selector_strategy",
    "selector_normalized",
]
SELECTOR_OBJECT_SCHEMA = _data_schema(
    "SelectorMetadata",
    SELECTOR_METADATA_SCHEMA,
    SELECTOR_METADATA_REQUIRED,
)

ERROR_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["code", "message"],
    "properties": {
        "code": {"type": "string"},
        "message": {"type": "string"},
        "details": {"type": "object", "additionalProperties": True},
    },
}

SCREENSHOT_METADATA_SCHEMA = _data_schema(
    "ScreenshotMetadata",
    {
        "mime_type": STRING,
        "inline": BOOLEAN,
        "encoding": STRING,
        "path": STRING,
        "full_page": BOOLEAN,
        "bytes": INTEGER,
        "width": INTEGER,
        "height": INTEGER,
    },
    ["mime_type"],
)

ELEMENT_INFO_SCHEMA = _data_schema(
    "ElementInfo",
    {
        "found": {"const": True},
        **SELECTOR_METADATA_SCHEMA,
        "text": STRING,
        "tag": STRING,
        "html": STRING,
        "visible": BOOLEAN,
    },
    ["found", *SELECTOR_METADATA_REQUIRED, "text"],
)

ELEMENT_ATTRIBUTES_SCHEMA = {
    "type": "object",
    "additionalProperties": {"type": ["string", "null"]},
}

OUTLINE_ELEMENT_SCHEMA = _data_schema(
    "OutlineElement",
    {
        "index": INTEGER,
        "tag": STRING,
        "text": STRING,
        "selector": STRING,
        "attributes": ELEMENT_ATTRIBUTES_SCHEMA,
        "html": STRING,
        "href": STRING,
        "method": STRING,
        "action": STRING,
    },
    ["index", "tag", "text", "selector", "attributes"],
)

OUTLINE_COUNTS_SCHEMA = {
    "type": "object",
    "additionalProperties": INTEGER,
}

FORM_FIELD_OPTION_SCHEMA = _data_schema(
    "FormFieldOption",
    {
        "text": STRING,
        "value": STRING,
        "selected": BOOLEAN,
    },
    ["text", "value", "selected"],
)

FORM_FIELD_SCHEMA = _data_schema(
    "FormField",
    {
        "index": INTEGER,
        "tag": STRING,
        "type": STRING,
        "name": STRING,
        "label": STRING,
        "selector": STRING,
        "placeholder": STRING,
        "required": BOOLEAN,
        "disabled": BOOLEAN,
        "readonly": BOOLEAN,
        "checked": BOOLEAN,
        "value": {"type": ["string", "null"]},
        "attributes": ELEMENT_ATTRIBUTES_SCHEMA,
        "options": {"type": "array", "items": FORM_FIELD_OPTION_SCHEMA},
    },
    [
        "index",
        "tag",
        "type",
        "name",
        "label",
        "selector",
        "placeholder",
        "required",
        "disabled",
        "readonly",
        "checked",
        "value",
        "attributes",
        "options",
    ],
)

FORM_SUMMARY_SCHEMA = _data_schema(
    "FormSummary",
    {
        "index": INTEGER,
        "selector": STRING,
        "id": STRING,
        "name": STRING,
        "method": STRING,
        "action": STRING,
        "text": STRING,
        "fields": {"type": "array", "items": FORM_FIELD_SCHEMA},
    },
    ["index", "selector", "id", "name", "method", "action", "text", "fields"],
)

FORM_INSPECT_LIMITS_SCHEMA = _data_schema(
    "FormInspectLimits",
    {
        "max_forms": INTEGER,
        "max_fields_per_form": INTEGER,
    },
    ["max_forms", "max_fields_per_form"],
)

FORM_INSPECT_TRUNCATION_SCHEMA = _data_schema(
    "FormInspectTruncation",
    {
        "forms": BOOLEAN,
        "fields": BOOLEAN,
    },
    ["forms", "fields"],
)

CONSOLE_LOG_SCHEMA = _data_schema(
    "ConsoleLog",
    {
        "index": INTEGER,
        "level": STRING,
        "text": STRING,
        "url": STRING,
        "line": INTEGER,
        "column": INTEGER,
        "source": STRING,
    },
    ["index", "level", "text", "url", "line", "column", "source"],
)

CONSOLE_LOGS_SCHEMA = _data_schema(
    "ConsoleLogsData",
    {
        "available": BOOLEAN,
        "listening": BOOLEAN,
        "count": INTEGER,
        "total": INTEGER,
        "next_cursor": INTEGER,
        "logs": {"type": "array", "items": CONSOLE_LOG_SCHEMA},
    },
    ["available", "listening", "count", "total", "next_cursor", "logs"],
)

CONSOLE_SUMMARY_SCHEMA = _data_schema(
    "ConsoleSummary",
    {
        "available": BOOLEAN,
        "listening": BOOLEAN,
        "count": INTEGER,
        "total": INTEGER,
        "next_cursor": INTEGER,
        "error_count": INTEGER,
        "warning_count": INTEGER,
        "recent": {"type": "array", "items": CONSOLE_LOG_SCHEMA},
    },
    [
        "available",
        "listening",
        "count",
        "total",
        "next_cursor",
        "error_count",
        "warning_count",
        "recent",
    ],
)

PAGE_SNAPSHOT_TRUNCATION_SCHEMA = _data_schema(
    "PageSnapshotTruncation",
    {
        "text": BOOLEAN,
        "elements": BOOLEAN,
        "returned_elements": INTEGER,
    },
    ["text", "elements", "returned_elements"],
)

PAGE_SNAPSHOT_LIMITS_SCHEMA = _data_schema(
    "PageSnapshotLimits",
    {
        "max_elements": INTEGER,
        "max_text_chars": INTEGER,
    },
    ["max_elements", "max_text_chars"],
)

META_SCHEMA = _data_schema(
    "ResponseMeta",
    {
        "approx_tokens": INTEGER,
        "json_chars": INTEGER,
        "truncated": BOOLEAN,
    },
    ["approx_tokens", "json_chars", "truncated"],
)

TAB_SUMMARY_SCHEMA = _data_schema(
    "TabSummary",
    {
        "id": STRING,
        "native_id": STRING,
        "url": STRING,
        "title": STRING,
        "active": BOOLEAN,
        "connected": BOOLEAN,
    },
    ["id", "native_id", "url", "title", "active", "connected"],
)

FRAME_SUMMARY_SCHEMA = _data_schema(
    "FrameSummary",
    {
        "index": INTEGER,
        "selector": STRING,
        "id": STRING,
        "name": STRING,
        "title": STRING,
        "url": STRING,
    },
    ["index", "selector", "id", "name", "title", "url"],
)

COOKIE_SCHEMA = _data_schema(
    "CookieSummary",
    {
        "name": STRING,
        "value": STRING,
        "domain": STRING,
        "path": STRING,
        "expires": ANY_JSON,
        "secure": BOOLEAN,
        "http_only": BOOLEAN,
    },
    ["name", "value", "domain", "path", "expires", "secure", "http_only"],
)

STORAGE_ITEMS_SCHEMA = {
    "type": "object",
    "additionalProperties": STRING,
}

OBSERVATION_COUNTS_SCHEMA = {
    "type": "object",
    "additionalProperties": INTEGER,
}

OBSERVATION_ACTIVE_ELEMENT_SCHEMA = {
    "anyOf": [
        {
            "type": "object",
            "additionalProperties": True,
            "properties": {
                "tag": STRING,
                "selector": STRING,
                "text": STRING,
            },
        },
        {"type": "null"},
    ]
}

OBSERVATION_LIMITS_SCHEMA = _data_schema(
    "ObservationLimits",
    {"max_texts": INTEGER, "max_text_chars": INTEGER},
    ["max_texts", "max_text_chars"],
)

OBSERVATION_SCHEMA = _data_schema(
    "PageObservation",
    {
        "url": STRING,
        "title": STRING,
        "ready_state": STRING,
        "counts": OBSERVATION_COUNTS_SCHEMA,
        "text_samples": {"type": "array", "items": STRING},
        "active_element": OBSERVATION_ACTIVE_ELEMENT_SCHEMA,
        "console": CONSOLE_SUMMARY_SCHEMA,
        "limits": OBSERVATION_LIMITS_SCHEMA,
    },
    [
        "url",
        "title",
        "ready_state",
        "counts",
        "text_samples",
        "active_element",
        "console",
        "limits",
    ],
)

OBSERVATION_CHANGES_SCHEMA = _data_schema(
    "PageObservationChanges",
    {
        "url_before": STRING,
        "url_after": STRING,
        "url_changed": BOOLEAN,
        "title_before": STRING,
        "title_after": STRING,
        "title_changed": BOOLEAN,
        "ready_state": STRING,
        "counts_before": OBSERVATION_COUNTS_SCHEMA,
        "counts_after": OBSERVATION_COUNTS_SCHEMA,
        "counts_delta": OBSERVATION_COUNTS_SCHEMA,
        "appeared_texts": {"type": "array", "items": STRING},
        "removed_texts": {"type": "array", "items": STRING},
        "active_element": OBSERVATION_ACTIVE_ELEMENT_SCHEMA,
        "console_errors_added": INTEGER,
        "console_warnings_added": INTEGER,
        "new_console_messages": {"type": "array", "items": CONSOLE_LOG_SCHEMA},
    },
    [
        "url_before",
        "url_after",
        "url_changed",
        "title_before",
        "title_after",
        "title_changed",
        "ready_state",
        "counts_before",
        "counts_after",
        "counts_delta",
        "appeared_texts",
        "removed_texts",
        "active_element",
        "console_errors_added",
        "console_warnings_added",
        "new_console_messages",
    ],
)


WORKFLOW_WAIT_SCHEMA = _data_schema(
    "WorkflowWaitResult",
    {
        "condition": STRING,
        "selector": STRING,
        "value": STRING,
        "matched": BOOLEAN,
        "timeout": NUMBER,
        "elapsed_ms": INTEGER,
        "state": {"type": "object", "additionalProperties": True},
    },
    ["condition", "selector", "value", "matched", "timeout"],
)

LINK_SUMMARY_SCHEMA = _data_schema(
    "LinkSummary",
    {
        "index": INTEGER,
        "text": STRING,
        "href": STRING,
        "url": STRING,
        "absolute_url": STRING,
        "selector": STRING,
        "rel": STRING,
        "target": STRING,
    },
    ["index", "text", "href", "url", "selector", "rel", "target"],
)

FORM_FILL_FORM_SCHEMA = {
    "anyOf": [
        _data_schema(
            "FormFillForm",
            {
                "selector": STRING,
                "id": STRING,
                "name": STRING,
                "method": STRING,
                "action": STRING,
            },
            ["selector", "id", "name", "method", "action"],
        ),
        {"type": "null"},
    ]
}

FORM_FILL_FIELD_SCHEMA = _data_schema(
    "FormFillField",
    {
        "key": STRING,
        "selector": STRING,
        "matched_by": STRING,
        "tag": STRING,
        "type": STRING,
        "value": STRING,
    },
    ["key", "selector", "matched_by", "tag", "type", "value"],
)

FORM_FILL_SKIPPED_SCHEMA = _data_schema(
    "FormFillSkippedField",
    {
        "key": STRING,
        "reason": STRING,
        "selector": STRING,
    },
    ["key", "reason"],
)

NETWORK_FILTERS_SCHEMA = _data_schema(
    "NetworkListenerFilters",
    {
        "targets": {"type": "array", "items": STRING},
        "is_regex": BOOLEAN,
        "method": STRING,
        "resource_type": STRING,
    },
    ["targets", "is_regex", "method", "resource_type"],
)

NETWORK_HEADERS_SCHEMA = {
    "type": "object",
    "additionalProperties": STRING,
}

NETWORK_PACKET_SCHEMA = _data_schema(
    "NetworkPacket",
    {
        "index": INTEGER,
        "url": STRING,
        "method": STRING,
        "resource_type": STRING,
        "status": {"type": ["integer", "null"]},
        "mime_type": STRING,
        "failed": BOOLEAN,
        "fail_error": STRING,
        "request_headers": NETWORK_HEADERS_SCHEMA,
        "response_headers": NETWORK_HEADERS_SCHEMA,
        "body_excerpt": STRING,
        "body_truncated": BOOLEAN,
        "body_type": STRING,
        "request_body_excerpt": STRING,
        "request_body_truncated": BOOLEAN,
        "request_body_type": STRING,
    },
    [
        "index",
        "url",
        "method",
        "resource_type",
        "status",
        "mime_type",
        "failed",
        "fail_error",
    ],
)

_GENERIC_DATA_SCHEMA = _data_schema(
    "GenericToolData",
    {},
    [],
)

TOOL_DATA_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "browser_open_and_snapshot": _data_schema(
        "BrowserOpenAndSnapshotData",
        {
            "url": STRING,
            "final_url": STRING,
            "title": STRING,
            "wait": WORKFLOW_WAIT_SCHEMA,
            "snapshot": {"type": "object", "additionalProperties": True},
            "forms": {"type": "object", "additionalProperties": True},
            "console": {"type": "object", "additionalProperties": True},
            "meta": META_SCHEMA,
        },
        ["url", "final_url", "title", "wait", "snapshot", "meta"],
    ),
    "browser_extract_links": _data_schema(
        "BrowserExtractLinksData",
        {
            **SELECTOR_METADATA_SCHEMA,
            "include_text": BOOLEAN,
            "same_origin_only": BOOLEAN,
            "absolute_urls": BOOLEAN,
            "count": INTEGER,
            "returned": INTEGER,
            "limit": INTEGER,
            "truncated": BOOLEAN,
            "links": {"type": "array", "items": LINK_SUMMARY_SCHEMA},
            "meta": META_SCHEMA,
        },
        [
            *SELECTOR_METADATA_REQUIRED,
            "include_text",
            "same_origin_only",
            "absolute_urls",
            "count",
            "returned",
            "limit",
            "truncated",
            "links",
            "meta",
        ],
    ),
    "form_fill_preview": _data_schema(
        "FormFillPreviewData",
        {
            "form_selector": SELECTOR_OBJECT_SCHEMA,
            "form_found": BOOLEAN,
            "form": FORM_FILL_FORM_SCHEMA,
            "field_count": INTEGER,
            "filled_count": INTEGER,
            "skipped_count": INTEGER,
            "filled": {"type": "array", "items": FORM_FILL_FIELD_SCHEMA},
            "skipped": {"type": "array", "items": FORM_FILL_SKIPPED_SCHEMA},
            "requires_confirmation": BOOLEAN,
            "submitted": BOOLEAN,
            "redacted": BOOLEAN,
        },
        [
            "form_selector",
            "form_found",
            "form",
            "field_count",
            "filled_count",
            "skipped_count",
            "filled",
            "skipped",
            "requires_confirmation",
            "submitted",
            "redacted",
        ],
    ),
    "network_listen_start": _data_schema(
        "NetworkListenStartData",
        {
            "listening": BOOLEAN,
            "filters": NETWORK_FILTERS_SCHEMA,
            "started_at": STRING,
            "tab_id": STRING,
            "cleared": BOOLEAN,
        },
        ["listening", "filters", "started_at", "tab_id", "cleared"],
    ),
    "network_listen_wait": _data_schema(
        "NetworkListenWaitData",
        {
            "listening": BOOLEAN,
            "timed_out": BOOLEAN,
            "count": INTEGER,
            "limit": INTEGER,
            "packets": {"type": "array", "items": NETWORK_PACKET_SCHEMA},
            "meta": META_SCHEMA,
        },
        ["listening", "timed_out", "count", "limit", "packets", "meta"],
    ),
    "network_listen_stop": _data_schema(
        "NetworkListenStopData",
        {
            "listening": BOOLEAN,
            "was_listening": BOOLEAN,
            "cleared": BOOLEAN,
        },
        ["listening", "was_listening", "cleared"],
    ),
    "page_navigate": _data_schema(
        "PageNavigateData",
        {
            "url": STRING,
            "final_url": STRING,
            "new_tab": BOOLEAN,
            "tab_id": STRING,
            "changes": OBSERVATION_CHANGES_SCHEMA,
        },
        ["url", "final_url", "new_tab", "tab_id"],
    ),
    "tab_list": _data_schema(
        "TabListData",
        {
            "tabs": {"type": "array", "items": TAB_SUMMARY_SCHEMA},
            "count": INTEGER,
            "active_tab_id": STRING,
        },
        ["tabs", "count", "active_tab_id"],
    ),
    "tab_switch": _data_schema(
        "TabSwitchData",
        {"tab": TAB_SUMMARY_SCHEMA, "tab_id": STRING, "url": STRING},
        ["tab", "tab_id", "url"],
    ),
    "tab_close": _data_schema(
        "TabCloseData",
        {
            "closed": {"const": True},
            "tab_id": STRING,
            "remaining_count": INTEGER,
            "active_tab_id": STRING,
        },
        ["closed", "tab_id", "remaining_count", "active_tab_id"],
    ),
    "page_go_back": _data_schema("PageGoBackData", {"url": STRING}, ["url"]),
    "page_go_forward": _data_schema("PageGoForwardData", {"url": STRING}, ["url"]),
    "page_refresh": _data_schema("PageRefreshData", {"url": STRING}, ["url"]),
    "page_resize": _data_schema(
        "PageResizeData",
        {"width": INTEGER, "height": INTEGER},
        ["width", "height"],
    ),
    "page_screenshot": _data_schema(
        "PageScreenshotData",
        {"screenshot": SCREENSHOT_METADATA_SCHEMA},
        ["screenshot"],
    ),
    "page_screenshot_save": _data_schema(
        "PageScreenshotSaveData",
        {"screenshot": SCREENSHOT_METADATA_SCHEMA},
        ["screenshot"],
    ),
    "page_snapshot": _data_schema(
        "PageSnapshotData",
        {
            "url": STRING,
            "title": STRING,
            "text_excerpt": STRING,
            "headings": {"type": "array", "items": OUTLINE_ELEMENT_SCHEMA},
            "links": {"type": "array", "items": OUTLINE_ELEMENT_SCHEMA},
            "buttons": {"type": "array", "items": OUTLINE_ELEMENT_SCHEMA},
            "inputs": {"type": "array", "items": OUTLINE_ELEMENT_SCHEMA},
            "forms": {"type": "array", "items": OUTLINE_ELEMENT_SCHEMA},
            "counts": OUTLINE_COUNTS_SCHEMA,
            "truncated": PAGE_SNAPSHOT_TRUNCATION_SCHEMA,
            "limits": PAGE_SNAPSHOT_LIMITS_SCHEMA,
            "meta": META_SCHEMA,
        },
        [
            "url",
            "title",
            "text_excerpt",
            "headings",
            "links",
            "buttons",
            "inputs",
            "forms",
            "counts",
            "truncated",
            "limits",
            "meta",
        ],
    ),
    "page_observe": OBSERVATION_SCHEMA,
    "page_console_logs": CONSOLE_LOGS_SCHEMA,
    "page_evaluate": _data_schema(
        "PageEvaluateData",
        {
            "result": ANY_JSON,
            "result_type": STRING,
            "truncated": BOOLEAN,
            "original_json_chars": INTEGER,
            "max_chars": INTEGER,
        },
        ["result", "result_type", "truncated", "original_json_chars", "max_chars"],
    ),
    "page_click_xy": _data_schema(
        "PageClickXYData",
        {"x": INTEGER, "y": INTEGER, "element": STRING, "url": STRING},
        ["x", "y", "element", "url"],
    ),
    "page_close": _data_schema(
        "PageCloseData",
        {"closed": {"const": True}},
        ["closed"],
    ),
    "page_get_url": _data_schema("PageGetUrlData", {"url": STRING}, ["url"]),
    "element_find": _data_schema(
        "ElementFindData",
        {"element": ELEMENT_INFO_SCHEMA},
        ["element"],
    ),
    "element_find_all": _data_schema(
        "ElementFindAllData",
        {
            **SELECTOR_METADATA_SCHEMA,
            "count": INTEGER,
            "returned": INTEGER,
            "limit": INTEGER,
            "truncated": BOOLEAN,
            "elements": {"type": "array", "items": OUTLINE_ELEMENT_SCHEMA},
            "meta": META_SCHEMA,
        },
        [
            *SELECTOR_METADATA_REQUIRED,
            "count",
            "returned",
            "limit",
            "truncated",
            "elements",
            "meta",
        ],
    ),
    "form_inspect": _data_schema(
        "FormInspectData",
        {
            "selector": STRING,
            "include_values": BOOLEAN,
            "count": INTEGER,
            "returned": INTEGER,
            "limits": FORM_INSPECT_LIMITS_SCHEMA,
            "truncated": FORM_INSPECT_TRUNCATION_SCHEMA,
            "forms": {"type": "array", "items": FORM_SUMMARY_SCHEMA},
            "meta": META_SCHEMA,
        },
        [
            "selector",
            "include_values",
            "count",
            "returned",
            "limits",
            "truncated",
            "forms",
            "meta",
        ],
    ),
    "element_click": _data_schema(
        "ElementClickData",
        {
            **SELECTOR_METADATA_SCHEMA,
            "url": STRING,
            "changes": OBSERVATION_CHANGES_SCHEMA,
        },
        [*SELECTOR_METADATA_REQUIRED, "url"],
    ),
    "element_type": _data_schema(
        "ElementTypeData",
        {
            **SELECTOR_METADATA_SCHEMA,
            "typed": {"const": True},
            "cleared": BOOLEAN,
            "changes": OBSERVATION_CHANGES_SCHEMA,
        },
        [*SELECTOR_METADATA_REQUIRED, "typed", "cleared"],
    ),
    "element_upload_file": _data_schema(
        "ElementUploadFileData",
        {
            **SELECTOR_METADATA_SCHEMA,
            "uploaded": {"const": True},
            "file_count": INTEGER,
            "filenames": {"type": "array", "items": STRING},
        },
        [*SELECTOR_METADATA_REQUIRED, "uploaded", "file_count", "filenames"],
    ),
    "page_scroll": _data_schema(
        "PageScrollData",
        {
            "direction": STRING,
            "pixels": INTEGER,
            "x": INTEGER,
            "y": INTEGER,
            "url": STRING,
        },
        ["direction", "pixels", "x", "y", "url"],
    ),
    "element_scroll_into_view": _data_schema(
        "ElementScrollIntoViewData",
        {**SELECTOR_METADATA_SCHEMA, "center": BOOLEAN, "url": STRING},
        [*SELECTOR_METADATA_REQUIRED, "center", "url"],
    ),
    "element_hover": _data_schema(
        "ElementHoverData",
        {
            **SELECTOR_METADATA_SCHEMA,
            "url": STRING,
            "offset_x": NULLABLE_INTEGER,
            "offset_y": NULLABLE_INTEGER,
        },
        [*SELECTOR_METADATA_REQUIRED, "url", "offset_x", "offset_y"],
    ),
    "keyboard_press": _data_schema(
        "KeyboardPressData",
        {"keys": STRING, "interval": NUMBER, "url": STRING},
        ["keys", "interval", "url"],
    ),
    "element_select": _data_schema(
        "ElementSelectData",
        {
            **SELECTOR_METADATA_SCHEMA,
            "selected": {"const": True},
            "by": STRING,
            "value": STRING,
        },
        [*SELECTOR_METADATA_REQUIRED, "selected", "by", "value"],
    ),
    "element_check": _data_schema(
        "ElementCheckData",
        {
            **SELECTOR_METADATA_SCHEMA,
            "checked": BOOLEAN,
            "by_js": BOOLEAN,
        },
        [*SELECTOR_METADATA_REQUIRED, "checked", "by_js"],
    ),
    "element_get_text": _data_schema(
        "ElementGetTextData",
        {"text": STRING, **SELECTOR_METADATA_SCHEMA},
        ["text", *SELECTOR_METADATA_REQUIRED],
    ),
    "element_get_attribute": _data_schema(
        "ElementGetAttributeData",
        {
            **SELECTOR_METADATA_SCHEMA,
            "attribute": STRING,
            "value": {"type": ["string", "null"]},
        },
        [*SELECTOR_METADATA_REQUIRED, "attribute", "value"],
    ),
    "element_get_property": _data_schema(
        "ElementGetPropertyData",
        {**SELECTOR_METADATA_SCHEMA, "property": STRING, "value": ANY_JSON},
        [*SELECTOR_METADATA_REQUIRED, "property", "value"],
    ),
    "element_get_html": _data_schema(
        "ElementGetHtmlData",
        {"html": STRING, **SELECTOR_METADATA_SCHEMA},
        ["html", *SELECTOR_METADATA_REQUIRED],
    ),
    "frame_list": _data_schema(
        "FrameListData",
        {
            "count": INTEGER,
            "returned": INTEGER,
            "limit": INTEGER,
            "frames": {"type": "array", "items": FRAME_SUMMARY_SCHEMA},
        },
        ["count", "returned", "limit", "frames"],
    ),
    "frame_snapshot": _data_schema(
        "FrameSnapshotData",
        {
            "frame": FRAME_SUMMARY_SCHEMA,
            "url": STRING,
            "title": STRING,
            "text_excerpt": STRING,
            "headings": {"type": "array", "items": OUTLINE_ELEMENT_SCHEMA},
            "links": {"type": "array", "items": OUTLINE_ELEMENT_SCHEMA},
            "buttons": {"type": "array", "items": OUTLINE_ELEMENT_SCHEMA},
            "inputs": {"type": "array", "items": OUTLINE_ELEMENT_SCHEMA},
            "forms": {"type": "array", "items": OUTLINE_ELEMENT_SCHEMA},
            "counts": OUTLINE_COUNTS_SCHEMA,
            "truncated": PAGE_SNAPSHOT_TRUNCATION_SCHEMA,
            "limits": PAGE_SNAPSHOT_LIMITS_SCHEMA,
            "meta": META_SCHEMA,
        },
        [
            "frame",
            "url",
            "title",
            "text_excerpt",
            "headings",
            "links",
            "buttons",
            "inputs",
            "forms",
            "counts",
            "truncated",
            "limits",
            "meta",
        ],
    ),
    "frame_find": _data_schema(
        "FrameFindData",
        {"frame": FRAME_SUMMARY_SCHEMA, "element": ELEMENT_INFO_SCHEMA},
        ["frame", "element"],
    ),
    "shadow_find": _data_schema(
        "ShadowFindData",
        {"host": SELECTOR_OBJECT_SCHEMA, "element": ELEMENT_INFO_SCHEMA},
        ["host", "element"],
    ),
    "shadow_find_all": _data_schema(
        "ShadowFindAllData",
        {
            "host": SELECTOR_OBJECT_SCHEMA,
            "target": SELECTOR_OBJECT_SCHEMA,
            "count": INTEGER,
            "returned": INTEGER,
            "limit": INTEGER,
            "truncated": BOOLEAN,
            "elements": {"type": "array", "items": OUTLINE_ELEMENT_SCHEMA},
            "meta": META_SCHEMA,
        },
        [
            "host",
            "target",
            "count",
            "returned",
            "limit",
            "truncated",
            "elements",
            "meta",
        ],
    ),
    "browser_cookies_get": _data_schema(
        "BrowserCookiesGetData",
        {
            "count": INTEGER,
            "include_values": BOOLEAN,
            "all_domains": BOOLEAN,
            "cookies": {"type": "array", "items": COOKIE_SCHEMA},
        },
        ["count", "include_values", "all_domains", "cookies"],
    ),
    "storage_get": _data_schema(
        "StorageGetData",
        {
            "area": STRING,
            "key": STRING,
            "include_values": BOOLEAN,
            "count": INTEGER,
            "items": STORAGE_ITEMS_SCHEMA,
        },
        ["area", "key", "include_values", "count", "items"],
    ),
    "storage_set": _data_schema(
        "StorageSetData",
        {"area": STRING, "key": STRING, "set": {"const": True}},
        ["area", "key", "set"],
    ),
    "storage_clear": _data_schema(
        "StorageClearData",
        {"area": STRING, "key": STRING, "cleared": {"const": True}},
        ["area", "key", "cleared"],
    ),
    "wait_for_element": _data_schema(
        "WaitForElementData",
        {**SELECTOR_METADATA_SCHEMA, "found": {"const": True}, "timeout": NUMBER},
        [*SELECTOR_METADATA_REQUIRED, "found", "timeout"],
    ),
    "wait_for_url": _data_schema(
        "WaitForUrlData",
        {
            "url_pattern": STRING,
            "matched": {"const": True},
            "url": STRING,
            "timeout": NUMBER,
        },
        ["url_pattern", "matched", "url", "timeout"],
    ),
    "wait_time": _data_schema(
        "WaitTimeData",
        {"waited_seconds": NUMBER},
        ["waited_seconds"],
    ),
    "wait_until": _data_schema(
        "WaitUntilData",
        {
            "condition": STRING,
            "selector": STRING,
            "value": STRING,
            "matched": {"const": True},
            "timeout": NUMBER,
            "elapsed_ms": INTEGER,
            "state": {"type": "object", "additionalProperties": True},
        },
        [
            "condition",
            "selector",
            "value",
            "matched",
            "timeout",
            "elapsed_ms",
            "state",
        ],
    ),
}
