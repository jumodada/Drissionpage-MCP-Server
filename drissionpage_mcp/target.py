"""Strict public contracts for reusable element targets."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, StringConstraints

TargetString = Annotated[
    StrictStr,
    StringConstraints(min_length=1, max_length=500, strip_whitespace=True),
]


class _StructuredTargetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frame_selectors: list[TargetString] = Field(
        default_factory=list,
        max_length=4,
        description="Ordered outer-to-inner frame selectors resolved by DrissionPage.",
    )
    shadow_hosts: list[TargetString] = Field(
        default_factory=list,
        max_length=8,
        description="Ordered outer-to-inner shadow host selectors resolved by DrissionPage.",
    )


class SelectorTargetInput(_StructuredTargetInput):
    """A selector target with optional frame and shadow-root scope."""

    kind: Literal["selector"]
    selector: TargetString


class AccessibilityTargetInput(_StructuredTargetInput):
    """A unique accessibility role/name target within an optional DOM scope."""

    kind: Literal["accessibility"]
    role: TargetString
    name: TargetString | None = None
    exact: bool = True


StructuredElementTarget = Annotated[
    SelectorTargetInput | AccessibilityTargetInput,
    Field(discriminator="kind"),
]
ElementTargetArg = TargetString | StructuredElementTarget
PageOrElementTargetArg = Literal[""] | ElementTargetArg


def target_label(target: ElementTargetArg) -> str:
    """Return a concise target label suitable for public result messages."""

    if isinstance(target, str):
        return target
    if target.kind == "selector":
        return target.selector
    suffix = "" if target.name is None else f" name={target.name!r}"
    return f"role={target.role!r}{suffix}"


def target_payload(target: ElementTargetArg) -> str | dict[str, object]:
    """Return a deterministic JSON-compatible request-fingerprint value."""

    if isinstance(target, str):
        return target
    return target.model_dump(mode="json")
