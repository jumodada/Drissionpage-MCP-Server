"""Typed data models returned by public MCP tools."""

from __future__ import annotations

from datetime import datetime
from ipaddress import ip_address
from pathlib import PurePosixPath
import re
from typing import Annotated, Any, Literal, Union, cast
from urllib.parse import urlsplit, urlunsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    StringConstraints,
    field_validator,
    model_validator,
)

class ToolData(BaseModel):
    """Strict base for tool data payloads."""

    model_config = ConfigDict(extra="forbid")


class ContractData(BaseModel):
    """Strict immutable base for shared task-runtime contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


ContractId = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z][a-z0-9_-]{2,127}$"),
]
Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
SafeRelativePath = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=500,
        pattern=r"^[^/\\:]+(?:/[^/\\:]+)*$",
    ),
]
PublicSourceUrl = Annotated[
    str,
    StringConstraints(
        max_length=500,
        pattern=r"^(?:|https?://[^/?#\s]+(?:/[^?#\s\\]*)?)$",
    ),
]

_HOST_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", re.I)
_INVALID_PERCENT_ESCAPE_RE = re.compile(r"%(?![0-9a-f]{2})", re.I)


def _normalize_public_host(hostname: str) -> str:
    """Return one normalized domain/IP literal or an empty invalid marker."""

    try:
        address = ip_address(hostname)
    except ValueError:
        try:
            ascii_host = hostname.encode("idna").decode("ascii").rstrip(".")
        except UnicodeError:
            return ""
        if len(ascii_host) > 253 or not all(
            _HOST_LABEL_RE.fullmatch(label) for label in ascii_host.split(".")
        ):
            return ""
        return ascii_host.lower()
    return f"[{address.compressed}]" if address.version == 6 else address.compressed


def sanitize_public_url(value: Any) -> str:
    """Return a query-free public HTTP(S) URL or an empty redaction."""

    if not isinstance(value, str) or not value:
        return ""
    if "\\" in value or any(
        character.isspace() or ord(character) < 32 for character in value
    ):
        return ""
    try:
        parts = urlsplit(value)
        hostname = parts.hostname
        port = parts.port
    except (TypeError, ValueError):
        return ""
    if (
        parts.scheme.lower() not in {"http", "https"}
        or not hostname
        or not hostname.strip(".")
        or (parts.path and not parts.path.startswith("/"))
        or _INVALID_PERCENT_ESCAPE_RE.search(parts.path)
    ):
        return ""
    normalized_host = _normalize_public_host(hostname)
    if not normalized_host:
        return ""
    netloc = normalized_host if port is None else f"{normalized_host}:{port}"
    sanitized = urlunsplit((parts.scheme.lower(), netloc, parts.path, "", ""))
    return sanitized if len(sanitized) <= 500 else ""


class ActionReceipt(ContractData):
    """Redacted evidence for one live-task consequential browser invocation."""

    schema_version: Literal["1"] = "1"
    action_id: ContractId
    task_id: ContractId
    operation_key: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    request_fingerprint: Sha256Hex
    kind: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    side_effect: Literal["external_download", "dialog_response"]
    status: Literal[
        "success",
        "validation_failed",
        "indeterminate",
        "failed",
    ]
    started_at: datetime
    finished_at: datetime
    tab_id: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    target_fingerprint: Sha256Hex | None = None
    artifact_ids: Annotated[tuple[ContractId, ...], Field(max_length=16)] = Field(
        default_factory=tuple
    )
    error_code: (
        Annotated[str, StringConstraints(min_length=1, max_length=100)] | None
    ) = None
    redacted: Literal[True] = True

    @model_validator(mode="after")
    def validate_timestamps(self) -> "ActionReceipt":
        if self.finished_at < self.started_at:
            raise ValueError("finished_at must not precede started_at")
        return self


class ArtifactRef(ContractData):
    """Safe metadata for one complete artifact produced in the live task."""

    schema_version: Literal["1"] = "1"
    artifact_id: ContractId
    task_id: ContractId
    producing_action_id: ContractId
    kind: Literal["download"]
    filename: Annotated[str, StringConstraints(min_length=1, max_length=255)]
    mime_type: (
        Annotated[str, StringConstraints(min_length=1, max_length=200)] | None
    ) = None
    size_bytes: Annotated[int, Field(ge=0)]
    sha256: Sha256Hex
    safe_relative_path: SafeRelativePath
    source_url: PublicSourceUrl = ""
    created_at: datetime
    status: Literal["complete"] = "complete"
    redacted: bool = False

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        if value in {".", ".."} or PurePosixPath(value).name != value:
            raise ValueError("filename must be a basename")
        return value

    @field_validator("safe_relative_path")
    @classmethod
    def validate_safe_relative_path(cls, value: str) -> str:
        if "\\" in value or ":" in value.split("/", 1)[0]:
            raise ValueError("safe_relative_path must use relative POSIX syntax")
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or "." in path.parts:
            raise ValueError("safe_relative_path must be a normalized relative path")
        return path.as_posix()

    @field_validator("source_url", mode="before")
    @classmethod
    def sanitize_source_url(cls, value: Any) -> str:
        return sanitize_public_url(value)


class CapabilityProbe(ContractData):
    """Evidence-backed state for one browser/runtime capability."""

    name: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_.-]{1,63}$")]
    status: Literal["unprobed", "supported", "unsupported", "degraded"]
    evidence_source: Literal[
        "none",
        "runtime_probe",
        "browser_event",
        "integration_probe",
    ] = "none"
    reason_code: (
        Annotated[str, StringConstraints(min_length=1, max_length=100)] | None
    ) = None
    checked_at: datetime | None = None

    @model_validator(mode="after")
    def validate_probe_evidence(self) -> "CapabilityProbe":
        if self.status == "unprobed":
            if self.evidence_source != "none" or self.checked_at is not None:
                raise ValueError("unprobed capabilities cannot include probe evidence")
        elif self.evidence_source == "none" or self.checked_at is None:
            raise ValueError(
                "probed capabilities require evidence_source and checked_at"
            )
        if self.status == "supported" and self.evidence_source not in {
            "browser_event",
            "integration_probe",
        }:
            raise ValueError("supported capabilities require behavioral probe evidence")
        return self


class CapabilitySet(ContractData):
    """Bounded capability discovery snapshot without implicit probing."""

    schema_version: Literal["1"] = "1"
    overall_status: Literal["unprobed", "supported", "unsupported", "degraded"] = (
        "unprobed"
    )
    drissionpage_version: Annotated[str, StringConstraints(max_length=100)] = ""
    browser_product: Annotated[str, StringConstraints(max_length=100)] = ""
    browser_version: Annotated[str, StringConstraints(max_length=100)] = ""
    capabilities: Annotated[tuple[CapabilityProbe, ...], Field(max_length=24)] = Field(
        default_factory=tuple
    )


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
    profile: Literal["direct", "natural"]
    start_x: float
    start_y: float
    target_x: float
    target_y: float
    steps: int
    planned_duration_ms: int


class PointerMotionData(PointerMoveData):
    button: Literal["left", "right", "middle"]
    delay_before_press_ms: int


class PagePointerMoveData(ToolData):
    x: float
    y: float
    element: str
    url: str
    motion: PointerMoveData


class PointerDragData(ToolData):
    profile: Literal["direct", "natural"]
    button: Literal["left", "right", "middle"]
    start_x: float
    start_y: float
    target_x: float
    target_y: float
    approach_steps: int
    drag_steps: int
    waypoint_count: int
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


class BrowserHeadersSetData(ToolData):
    count: int
    headers: dict[str, str]
    set: Literal[True]


class BrowserUserAgentSetData(ToolData):
    previous_user_agent: str
    user_agent: str
    platform: str | None
    set: Literal[True]


class BrowserCacheClearData(ToolData):
    cleared: Literal[True]


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
    button: Literal["left", "right", "middle"]
    click_count: Literal[1, 2]
    changes: dict[str, Any] | None = None


class ElementClickAndDownloadSuccessReceipt(ActionReceipt):
    kind: Literal["element_click_and_download"]
    side_effect: Literal["external_download"]
    status: Literal["success"]
    artifact_ids: Annotated[tuple[ContractId, ...], Field(min_length=1, max_length=1)]


class ElementClickAndDownloadFailedReceipt(ActionReceipt):
    kind: Literal["element_click_and_download"]
    side_effect: Literal["external_download"]
    status: Literal["failed"]
    artifact_ids: Annotated[tuple[ContractId, ...], Field(max_length=0)] = ()


class ElementClickAndDownloadValidationFailedReceipt(ActionReceipt):
    kind: Literal["element_click_and_download"]
    side_effect: Literal["external_download"]
    status: Literal["validation_failed"]
    artifact_ids: Annotated[tuple[ContractId, ...], Field(max_length=0)] = ()


class ElementClickAndDownloadIndeterminateReceipt(ActionReceipt):
    kind: Literal["element_click_and_download"]
    side_effect: Literal["external_download"]
    status: Literal["indeterminate"]
    artifact_ids: Annotated[tuple[ContractId, ...], Field(max_length=0)] = ()


class _ElementClickAndDownloadDataBase(ToolData):
    operation_key: str
    selector: str
    locator: str
    selector_strategy: str
    selector_normalized: bool


class ElementClickAndDownloadSuccessData(_ElementClickAndDownloadDataBase):
    status: Literal["success"]
    artifact: ArtifactRef
    receipt: ElementClickAndDownloadSuccessReceipt

    @model_validator(mode="after")
    def validate_correlations(self) -> "ElementClickAndDownloadSuccessData":
        if self.receipt.operation_key != self.operation_key:
            raise ValueError("receipt operation_key must match data operation_key")
        if self.artifact.task_id != self.receipt.task_id:
            raise ValueError("artifact task_id must match receipt task_id")
        if self.artifact.producing_action_id != self.receipt.action_id:
            raise ValueError(
                "artifact producing_action_id must match receipt action_id"
            )
        if self.receipt.artifact_ids != (self.artifact.artifact_id,):
            raise ValueError(
                "receipt artifact_ids must contain exactly the artifact id"
            )
        return self


class ElementClickAndDownloadFailedData(_ElementClickAndDownloadDataBase):
    status: Literal["failed"]
    artifact: None
    receipt: ElementClickAndDownloadFailedReceipt

    @model_validator(mode="after")
    def validate_operation_key(self) -> "ElementClickAndDownloadFailedData":
        if self.receipt.operation_key != self.operation_key:
            raise ValueError("receipt operation_key must match data operation_key")
        return self


class ElementClickAndDownloadValidationFailedData(_ElementClickAndDownloadDataBase):
    status: Literal["validation_failed"]
    artifact: None
    receipt: ElementClickAndDownloadValidationFailedReceipt

    @model_validator(mode="after")
    def validate_operation_key(self) -> "ElementClickAndDownloadValidationFailedData":
        if self.receipt.operation_key != self.operation_key:
            raise ValueError("receipt operation_key must match data operation_key")
        return self


class ElementClickAndDownloadIndeterminateData(_ElementClickAndDownloadDataBase):
    status: Literal["indeterminate"]
    artifact: None
    receipt: ElementClickAndDownloadIndeterminateReceipt

    @model_validator(mode="after")
    def validate_operation_key(self) -> "ElementClickAndDownloadIndeterminateData":
        if self.receipt.operation_key != self.operation_key:
            raise ValueError("receipt operation_key must match data operation_key")
        return self


ElementClickAndDownloadVariant = Annotated[
    Union[
        ElementClickAndDownloadSuccessData,
        ElementClickAndDownloadFailedData,
        ElementClickAndDownloadValidationFailedData,
        ElementClickAndDownloadIndeterminateData,
    ],
    Field(discriminator="status"),
]


class ElementClickAndDownloadData(RootModel[ElementClickAndDownloadVariant]):
    """Status-discriminated download result with correlated public evidence."""


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


class DialogMessageMetadata(ToolData):
    present: bool
    length: Annotated[int, Field(ge=0)]
    redacted: Literal[True]


class DialogPromptMetadata(ToolData):
    provided: bool
    length: Annotated[int, Field(ge=0)]
    redacted: Literal[True]


class PageDialogRespondData(ToolData):
    dialog_type: Literal["alert", "confirm", "prompt"]
    action: Literal["accept", "dismiss"]
    handled: Literal[True]
    dialog_message: DialogMessageMetadata
    prompt: DialogPromptMetadata
    final_url: str
    receipt: ActionReceipt


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


class BrowserCookieWriteData(ToolData):
    name: str
    value: str
    url: str = ""
    domain: str = ""
    path: str = ""
    expires: float | None = None
    secure: bool | None = None
    http_only: bool | None = None
    same_site: Literal["None", "Lax", "Strict", "no_restriction"] | None = None
    priority: Literal["Low", "Medium", "High"] | None = None
    source_scheme: Literal["Unset", "NonSecure", "Secure"] | None = None


class BrowserCookiesSetData(ToolData):
    count: int
    set: Literal[True]
    cookies: list[BrowserCookieWriteData]


class BrowserCookiesDeleteData(ToolData):
    name: str
    url: str | None
    domain: str | None
    path: str | None
    deleted: Literal[True]


class BrowserCookiesClearData(ToolData):
    cleared: Literal[True]


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


class NetworkBlockedUrlsSetData(ToolData):
    count: int
    urls: list[str]
    set: Literal[True]


def tool_outcome_schema(output_model: type[ToolData]) -> dict[str, Any]:
    """Wrap typed tool data in the stable success/failure envelope."""

    data_schema = output_model.model_json_schema()
    definitions = data_schema.pop("$defs", None)
    error_data_schema = (
        data_schema
        if cast(type[BaseModel], output_model) is ElementClickAndDownloadData
        else {"type": "object", "additionalProperties": True}
    )
    schema: dict[str, Any] = {
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
                    "data": error_data_schema,
                },
            },
        ],
    }
    if definitions:
        schema["$defs"] = definitions
    return schema
