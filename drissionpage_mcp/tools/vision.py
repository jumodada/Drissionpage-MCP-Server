"""Autonomous visual orchestration tools for DrissionPage MCP."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field, model_validator

from ..tool_outputs import BatchClickData, DetectChallengesData, WaitChallengeData
from .base import ToolInput, ToolOutcome, ToolType, define_tool

if TYPE_CHECKING:
    from ..context import DrissionPageContext


class DetectChallengesInput(ToolInput):
    keywords: list[str] = Field(
        default_factory=lambda: [
            "turnstile",
            "recaptcha",
            "hcaptcha",
            "challenges.cloudflare.com",
            "g-recaptcha",
        ],
        max_length=50,
        description="Iframe, script, and DOM signal keywords used for read-only verification-widget detection.",
    )
    include_screenshot: bool = Field(
        default=False,
        description="Attach an inline viewport screenshot for multimodal analysis.",
    )


class ClickTarget(BaseModel):
    x: float = Field(..., ge=0, description="Viewport X coordinate in CSS pixels")
    y: float = Field(..., ge=0, description="Viewport Y coordinate in CSS pixels")
    label: str = Field("", max_length=200, description="Optional target label")


class BatchClickInput(ToolInput):
    targets: list[ClickTarget] = Field(
        ...,
        min_length=1,
        max_length=25,
        description="Ordered viewport targets derived from one stable visual state.",
    )
    profile: Literal["natural", "precise", "direct"] = Field(default="natural")
    button: Literal["left", "right", "middle"] = Field(default="left")
    inter_click_delay_min_ms: int = Field(default=200, ge=0, le=5000)
    inter_click_delay_max_ms: int = Field(default=500, ge=0, le=5000)
    continue_on_error: bool = Field(
        default=False,
        description="Continue after a failed target; false avoids unsafe partial-state continuation.",
    )
    stop_on_url_change: bool = Field(
        default=True,
        description="Abort remaining coordinates if a click changes the page URL.",
    )

    @model_validator(mode="after")
    def _ordered_delay(self) -> "BatchClickInput":
        if self.inter_click_delay_min_ms > self.inter_click_delay_max_ms:
            raise ValueError(
                "inter_click_delay_min_ms cannot exceed inter_click_delay_max_ms"
            )
        return self


class WaitChallengeInput(ToolInput):
    timeout_s: float = Field(default=10, ge=0.1, le=60)
    poll_interval_s: float = Field(default=0.5, ge=0.1, le=5)
    token_selectors: list[str] = Field(
        default_factory=lambda: [
            'input[name="cf-turnstile-response"]',
            'textarea[name="g-recaptcha-response"]',
            'textarea[name="h-captcha-response"]',
        ],
        max_length=20,
        description="Token fields; only non-empty length is returned, never the token value.",
    )
    success_selectors: list[str] = Field(default_factory=list, max_length=20)
    retry_selectors: list[str] = Field(default_factory=list, max_length=20)
    challenge_selectors: list[str] = Field(
        default_factory=lambda: [".cf-turnstile", ".g-recaptcha", ".h-captcha"],
        max_length=20,
    )


@define_tool(
    name="page_detect_challenges",
    title="Detect Interactive Challenges",
    description=(
        "Read-only detection of verification-widget signals in frames, scripts, DOM "
        "containers, and hidden fields. Provides autonomous next-step suggestions but "
        "performs no interaction. General capability for authorized testing and technical research."
    ),
    input_schema=DetectChallengesInput,
    tool_type=ToolType.READ_ONLY,
    idempotent=True,
    output_model=DetectChallengesData,
    failure_message=lambda _args, exc: "Failed to detect interactive challenges: "
    + str(exc),
)
async def detect_challenges(
    context: "DrissionPageContext", args: DetectChallengesInput
) -> "ToolOutcome":
    outcome = ToolOutcome()
    tab = context.current_tab_or_die()
    result = await tab.vision.detect_challenges(args.keywords)
    screenshot_attached = False
    if args.include_screenshot:
        screenshot = await tab.page_ops.screenshot(full_page=False)
        outcome.add_image(screenshot, "image/png")
        screenshot_attached = True
    outcome.add_code("# inspect verification-widget DOM/frame/script signals")
    outcome.add_result(
        (
            "Detected interactive challenge signals"
            if result["detected"]
            else "No known interactive challenge signals detected"
        ),
        **result,
        screenshot_attached=screenshot_attached,
    )
    return outcome


@define_tool(
    name="page_click_xy_batch",
    title="Batch Click Coordinates",
    description=(
        "Click an ordered set of viewport CSS coordinates in one autonomous call using "
        "natural pointer motion between targets. Intended as a general visual UI primitive; "
        "all coordinates must come from one stable page state."
    ),
    input_schema=BatchClickInput,
    tool_type=ToolType.DESTRUCTIVE,
    output_model=BatchClickData,
    failure_message=lambda _args, exc: "Failed to execute batch coordinate clicks: "
    + str(exc),
)
async def click_xy_batch(
    context: "DrissionPageContext", args: BatchClickInput
) -> "ToolOutcome":
    outcome = ToolOutcome()
    tab = context.current_tab_or_die()
    result = await tab.vision.click_batch(
        [target.model_dump() for target in args.targets],
        profile=args.profile,
        button=args.button,
        delay_min_ms=args.inter_click_delay_min_ms,
        delay_max_ms=args.inter_click_delay_max_ms,
        continue_on_error=args.continue_on_error,
        stop_on_url_change=args.stop_on_url_change,
    )
    outcome.add_code(
        "# sequential pointer.click_at(...) with bounded inter-click delays"
    )
    outcome.add_result(
        f"Completed {result['clicks_completed']} of {result['total_targets']} coordinate clicks",
        **result,
    )
    outcome.set_include_snapshot(True)
    return outcome


@define_tool(
    name="page_wait_challenge_result",
    title="Wait For Challenge Result",
    description=(
        "Autonomously poll bounded observable token, success, retry, and challenge-state "
        "signals. Returns status without exposing token values or promising verification completion."
    ),
    input_schema=WaitChallengeInput,
    tool_type=ToolType.READ_ONLY,
    idempotent=True,
    output_model=WaitChallengeData,
    failure_message=lambda _args, exc: "Failed while waiting for challenge result: "
    + str(exc),
)
async def wait_challenge_result(
    context: "DrissionPageContext", args: WaitChallengeInput
) -> "ToolOutcome":
    outcome = ToolOutcome()
    tab = context.current_tab_or_die()
    result = await tab.vision.wait_challenge_result(
        timeout_s=args.timeout_s,
        poll_interval_s=args.poll_interval_s,
        token_selectors=args.token_selectors,
        success_selectors=args.success_selectors,
        retry_selectors=args.retry_selectors,
        challenge_selectors=args.challenge_selectors,
    )
    outcome.add_code(
        "# poll observable challenge/result signals without returning token values"
    )
    outcome.add_result(f"Challenge result status: {result['status']}", **result)
    return outcome
