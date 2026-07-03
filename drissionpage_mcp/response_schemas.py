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

_GENERIC_DATA_SCHEMA = _data_schema(
    "GenericToolData",
    {},
    [],
)

TOOL_DATA_SCHEMAS: Dict[str, Dict[str, Any]] = {
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
