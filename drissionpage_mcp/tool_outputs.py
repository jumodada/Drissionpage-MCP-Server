"""Typed data models returned by public MCP tools."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class ToolData(BaseModel):
    """Strict base for tool data payloads."""

    model_config = ConfigDict(extra="forbid")


class PageNavigateData(ToolData):
    url: str
    final_url: str
    new_tab: bool
    tab_id: str
    changes: dict[str, Any] | None = None


class PageGoBackData(ToolData):
    url: str


class PageGoForwardData(ToolData):
    url: str


class PageRefreshData(ToolData):
    url: str


class TabListData(ToolData):
    tabs: list[dict[str, Any]]
    count: int
    active_tab_id: str


class TabSwitchData(ToolData):
    tab: dict[str, Any]
    tab_id: str
    url: str


class TabCloseData(ToolData):
    closed: Literal[True]
    tab_id: str
    remaining_count: int
    active_tab_id: str


class PageResizeData(ToolData):
    width: int
    height: int


class PageScreenshotData(ToolData):
    screenshot: dict[str, Any]


class PageScreenshotSaveData(ToolData):
    screenshot: dict[str, Any]


class PageSnapshotData(ToolData):
    url: str
    title: str
    text_excerpt: str
    headings: list[dict[str, Any]]
    links: list[dict[str, Any]]
    buttons: list[dict[str, Any]]
    inputs: list[dict[str, Any]]
    forms: list[dict[str, Any]]
    counts: dict[str, int]
    truncated: dict[str, Any]
    limits: dict[str, Any]
    meta: dict[str, Any]


class PageObservation(ToolData):
    url: str
    title: str
    ready_state: str
    counts: dict[str, int]
    text_samples: list[str]
    active_element: Any
    console: dict[str, Any]
    limits: dict[str, Any]


class PageEvaluateData(ToolData):
    result: Any
    result_type: str
    truncated: bool
    original_json_chars: int
    max_chars: int


class PointerMoveData(ToolData):
    profile: Literal["natural", "precise", "direct"]
    start_x: float
    start_y: float
    target_x: float
    target_y: float
    steps: int
    planned_duration_ms: int


class PointerMotionData(PointerMoveData):
    button: Literal["left", "right", "middle"]
    start_x: float
    start_y: float
    target_x: float
    target_y: float
    steps: int
    reaction_delay_ms: int
    delay_before_press_ms: int
    hold_duration_ms: int
    planned_duration_ms: int


class PagePointerMoveData(ToolData):
    x: float
    y: float
    element: str
    url: str
    motion: PointerMoveData


class PointerDragData(ToolData):
    profile: Literal["natural", "precise", "direct"]
    button: Literal["left", "right", "middle"]
    start_x: float
    start_y: float
    target_x: float
    target_y: float
    approach_steps: int
    drag_steps: int
    main_drag_steps: int
    overshoot_steps: int
    correction_steps: int
    micro_pause_count: int
    overshoot_px: float
    reaction_delay_ms: int
    grip_delay_ms: int
    movement_duration_ms: int
    micro_pause_duration_ms: int
    release_delay_ms: int
    planned_duration_ms: int


class PagePointerDragData(ToolData):
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    element: str
    url: str
    motion: PointerDragData


class ResolvedPointerTargetData(ToolData):
    selector: str
    locator: str
    selector_strategy: str
    selector_normalized: bool
    frame_selector: str | None
    shadow_hosts: list[str]
    anchor: Literal["center", "left", "right", "top", "bottom"]
    offset_x: float
    offset_y: float
    x: float
    y: float
    left: float
    top: float
    right: float
    bottom: float
    width: float
    height: float


class PointerDragElementDestinationData(ToolData):
    kind: Literal["element", "offset", "track_ratio"]
    x: float
    y: float
    target: ResolvedPointerTargetData | None = None
    track: ResolvedPointerTargetData | None = None
    offset_x: float | None = None
    offset_y: float | None = None
    ratio: float | None = None
    axis: Literal["x", "y"] | None = None


class PagePointerDragElementData(ToolData):
    source: ResolvedPointerTargetData
    destination: PointerDragElementDestinationData
    url: str
    motion: PointerDragData


class PageClickXYData(ToolData):
    x: float
    y: float
    element: str
    url: str
    motion: PointerMotionData


class PageCloseData(ToolData):
    closed: Literal[True]


class PageGetUrlData(ToolData):
    url: str


class ConsoleLogsData(ToolData):
    available: bool
    listening: bool
    count: int
    total: int
    next_cursor: int
    logs: list[dict[str, Any]]


class ElementFindData(ToolData):
    element: dict[str, Any]


class ElementFindAllData(ToolData):
    selector: str
    locator: str
    selector_strategy: str
    selector_normalized: bool
    count: int
    returned: int
    limit: int
    truncated: bool
    elements: list[dict[str, Any]]
    meta: dict[str, Any]


class ElementClickData(ToolData):
    selector: str
    locator: str
    selector_strategy: str
    selector_normalized: bool
    url: str
    changes: dict[str, Any] | None = None


class ElementTypeData(ToolData):
    selector: str
    locator: str
    selector_strategy: str
    selector_normalized: bool
    typed: Literal[True]
    cleared: bool
    changes: dict[str, Any] | None = None


class ElementGetTextData(ToolData):
    text: str
    selector: str
    locator: str
    selector_strategy: str
    selector_normalized: bool


class ElementGetAttributeData(ToolData):
    selector: str
    locator: str
    selector_strategy: str
    selector_normalized: bool
    attribute: str
    value: str | None


class ElementGetPropertyData(ToolData):
    selector: str
    locator: str
    selector_strategy: str
    selector_normalized: bool
    property: str
    value: Any


class ElementGetHtmlData(ToolData):
    html: str
    selector: str
    locator: str
    selector_strategy: str
    selector_normalized: bool


class ElementUploadFileData(ToolData):
    selector: str
    locator: str
    selector_strategy: str
    selector_normalized: bool
    uploaded: Literal[True]
    file_count: int
    filenames: list[str]


class PageScrollData(ToolData):
    direction: str
    pixels: int
    x: int
    y: int
    url: str


class ElementScrollIntoViewData(ToolData):
    selector: str
    locator: str
    selector_strategy: str
    selector_normalized: bool
    center: bool
    url: str


class ElementHoverData(ToolData):
    selector: str
    locator: str
    selector_strategy: str
    selector_normalized: bool
    url: str
    offset_x: int | None
    offset_y: int | None


class KeyboardPressData(ToolData):
    keys: str
    interval: float
    url: str


class ElementSelectData(ToolData):
    selector: str
    locator: str
    selector_strategy: str
    selector_normalized: bool
    selected: Literal[True]
    by: str
    value: str


class ElementCheckData(ToolData):
    selector: str
    locator: str
    selector_strategy: str
    selector_normalized: bool
    checked: bool
    by_js: bool


class FormInspectData(ToolData):
    selector: str
    include_values: bool
    count: int
    returned: int
    limits: dict[str, Any]
    truncated: dict[str, Any]
    forms: list[dict[str, Any]]
    meta: dict[str, Any]


class FrameListData(ToolData):
    count: int
    returned: int
    limit: int
    frames: list[dict[str, Any]]


class FrameSnapshotData(ToolData):
    frame: dict[str, Any]
    url: str
    title: str
    text_excerpt: str
    headings: list[dict[str, Any]]
    links: list[dict[str, Any]]
    buttons: list[dict[str, Any]]
    inputs: list[dict[str, Any]]
    forms: list[dict[str, Any]]
    counts: dict[str, int]
    truncated: dict[str, Any]
    limits: dict[str, Any]
    meta: dict[str, Any]


class FrameFindData(ToolData):
    frame: dict[str, Any]
    element: dict[str, Any]


class ShadowFindData(ToolData):
    host: dict[str, Any]
    element: dict[str, Any]


class ShadowFindAllData(ToolData):
    host: dict[str, Any]
    target: dict[str, Any]
    count: int
    returned: int
    limit: int
    truncated: bool
    elements: list[dict[str, Any]]
    meta: dict[str, Any]


class BrowserCookiesGetData(ToolData):
    count: int
    include_values: bool
    all_domains: bool
    cookies: list[dict[str, Any]]


class StorageGetData(ToolData):
    area: str
    key: str
    include_values: bool
    count: int
    items: dict[str, str]


class StorageSetData(ToolData):
    area: str
    key: str
    set: Literal[True]


class StorageClearData(ToolData):
    area: str
    key: str
    cleared: Literal[True]


class WaitForElementData(ToolData):
    selector: str
    locator: str
    selector_strategy: str
    selector_normalized: bool
    found: Literal[True]
    timeout: float


class WaitForUrlData(ToolData):
    url_pattern: str
    matched: Literal[True]
    url: str
    timeout: float


class WaitTimeData(ToolData):
    waited_seconds: float


class WaitUntilData(ToolData):
    condition: str
    selector: str
    value: str
    name: str
    matched: Literal[True]
    timeout: float
    elapsed_ms: int
    state: dict[str, Any]


class BrowserOpenAndSnapshotData(ToolData):
    url: str
    final_url: str
    title: str
    wait: dict[str, Any]
    snapshot: dict[str, Any]
    forms: dict[str, Any] | None = None
    console: dict[str, Any] | None = None
    meta: dict[str, Any]


class BrowserExtractLinksData(ToolData):
    selector: str
    locator: str
    selector_strategy: str
    selector_normalized: bool
    include_text: bool
    same_origin_only: bool
    absolute_urls: bool
    count: int
    returned: int
    limit: int
    truncated: bool
    links: list[dict[str, Any]]
    meta: dict[str, Any]


class FormFillPreviewData(ToolData):
    form_selector: dict[str, Any]
    form_found: bool
    form: Any
    field_count: int
    filled_count: int
    skipped_count: int
    filled: list[dict[str, Any]]
    skipped: list[dict[str, Any]]
    requires_confirmation: bool
    submitted: bool
    redacted: bool


class NetworkListenStartData(ToolData):
    listening: bool
    filters: dict[str, Any]
    started_at: str
    tab_id: str
    cleared: bool


class NetworkListenWaitData(ToolData):
    listening: bool
    timed_out: bool
    count: int
    limit: int
    packets: list[dict[str, Any]]
    meta: dict[str, Any]


class NetworkListenStopData(ToolData):
    listening: bool
    was_listening: bool
    cleared: bool


def tool_outcome_schema(output_model: type[ToolData]) -> dict[str, Any]:
    """Wrap typed tool data in the stable success/failure envelope."""

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
                    "data": output_model.model_json_schema(),
                },
            },
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["ok", "message", "error"],
                "properties": {
                    "ok": {"const": False},
                    "message": {"type": "string"},
                    "error": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["code", "message"],
                        "properties": {
                            "code": {"type": "string"},
                            "message": {"type": "string"},
                            "details": {"type": "object", "additionalProperties": True},
                        },
                    },
                    "data": {"type": "object", "additionalProperties": True},
                },
            },
        ],
    }


class ChallengeSignalData(ToolData):
    source: str
    provider_hint: str
    matched_signal: str
    frame_index: int | None


class DetectChallengesData(ToolData):
    detected: bool
    challenge_types: list[str]
    signals: list[dict[str, Any]]
    iframes: list[dict[str, Any]]
    page_state: dict[str, str]
    suggestions: list[str]
    screenshot_attached: bool


class BatchClickResultData(ToolData):
    index: int
    x: float
    y: float
    label: str
    success: bool
    error: str | None
    motion: PointerMotionData | None


class BatchClickData(ToolData):
    total_targets: int
    clicks_completed: int
    results: list[BatchClickResultData]
    aborted: bool
    abort_index: int | None
    initial_url: str
    final_url: str


class WaitChallengeData(ToolData):
    status: Literal[
        "passed", "needs_retry", "new_challenge", "pending", "timeout", "indeterminate"
    ]
    passed: bool
    needs_retry: bool
    new_challenge: bool
    token_present: bool
    token_length: int
    matched_selector: str
    elapsed_ms: int
    observations: int
