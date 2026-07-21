"""High-level browser workflows composed from focused tab capabilities."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Mapping
from time import monotonic
from typing import TYPE_CHECKING, Any

from ..response_errors import ErrorCode
from ..selector import normalize_selector
from ..tool_outputs import ConditionEvaluation, Expectation
from ._scripts import run_structured_script
from .form_inspection_scripts import build_form_inspect_script
from .form_scripts import (
    _form_fill_framework_script,
    _form_fill_observe_script,
    _form_fill_preview_script,
    _form_fill_resolve_script,
    _form_submit_resolve_script,
    _form_submit_state_script,
)
from .page_state_scripts import _extract_links_script

if TYPE_CHECKING:
    from ..tab import PageTab

logger = logging.getLogger(__name__)


class FormSubmitPreconditionError(ValueError):
    """Raised before operation claim when form/submitter resolution is unsafe."""

    code = ErrorCode.PRECONDITION_FAILED


class FormSubmitExecutionError(RuntimeError):
    """Preserve whether the resolved submitter was invoked before failure."""

    def __init__(self, message: str, *, triggered: bool) -> None:
        super().__init__(message)
        self.triggered = triggered


class WorkflowOperations:
    """Own bounded multi-step browser workflows and page data extraction."""

    def __init__(self, tab: "PageTab") -> None:
        self._tab = tab

    @property
    def _page(self) -> Any:
        return self._tab.page

    async def inspect_forms(
        self,
        *,
        selector: str = "",
        include_values: bool = False,
        max_forms: int = 10,
        max_fields_per_form: int = 50,
    ) -> dict[str, Any]:
        try:
            return run_structured_script(
                self._page,
                build_form_inspect_script(
                    selector=selector,
                    include_values=include_values,
                    max_forms=max_forms,
                    max_fields_per_form=max_fields_per_form,
                ),
                "form inspect script returned no structured data",
            )
        except Exception as exc:
            logger.error("Failed to inspect forms: %s", exc)
            raise

    async def open_and_snapshot(
        self,
        *,
        url: str,
        wait_condition: str = "",
        selector: str = "",
        wait_value: str = "",
        wait_timeout: float = 5.0,
        include_html: bool = False,
        include_forms: bool = False,
        include_console: bool = False,
        max_elements: int = 50,
        max_text_chars: int = 4000,
    ) -> dict[str, Any]:
        await self._tab.navigation.navigate(url)
        wait_result = {
            "condition": wait_condition,
            "selector": selector,
            "value": wait_value,
            "matched": wait_condition == "",
            "timeout": wait_timeout,
        }
        if wait_condition:
            wait_result = await self._tab.waits.until(
                condition=wait_condition,
                selector=selector,
                value=wait_value,
                timeout=wait_timeout,
            )
        snapshot = await self._tab.observation.snapshot(
            include_html=include_html,
            max_elements=max_elements,
            max_text_chars=max_text_chars,
        )
        payload: dict[str, Any] = {
            "url": url,
            "final_url": self._tab.url,
            "title": str(snapshot.get("title") or self._tab.title),
            "wait": wait_result,
            "snapshot": snapshot,
        }
        if include_forms:
            payload["forms"] = await self.inspect_forms()
        if include_console:
            payload["console"] = await self._tab.observation.console_logs(
                level="all", since=-1, limit=20
            )
        return payload

    async def extract_links(
        self,
        *,
        selector: str = "a",
        limit: int = 50,
        include_text: bool = True,
        same_origin_only: bool = False,
        absolute_urls: bool = True,
    ) -> dict[str, Any]:
        plan = normalize_selector(selector)
        result = run_structured_script(
            self._page,
            _extract_links_script(
                locator=plan.locator,
                limit=limit,
                include_text=include_text,
                same_origin_only=same_origin_only,
                absolute_urls=absolute_urls,
                base_url=self._tab.url,
            ),
            "link extraction script returned no structured data",
        )
        return {**plan.metadata(), **result}

    async def form_fill_preview(
        self,
        *,
        form_selector: str = "form",
        fields: Mapping[str, Any],
        redact_values: bool = True,
    ) -> dict[str, Any]:
        plan = normalize_selector(form_selector)
        result = run_structured_script(
            self._page,
            _form_fill_preview_script(
                form_locator=plan.locator,
                fields=dict(fields),
                redact_values=redact_values,
            ),
            "form fill preview script returned no structured data",
        )
        return {"form_selector": plan.metadata(), **result}

    async def form_fill(
        self,
        *,
        form_selector: str,
        fields: Mapping[str, str | bool | list[str]],
        redact_values: bool,
        verify: bool,
        timeout: float,
    ) -> dict[str, Any]:
        """Fill supported rich controls without submitting the form."""

        plan = normalize_selector(form_selector)
        resolution = run_structured_script(
            self._page,
            _form_fill_resolve_script(
                form_locator=plan.locator,
                fields=dict(fields),
                redact_values=redact_values,
            ),
            "form fill resolution script returned no structured data",
        )
        targets = list(resolution.pop("targets", []))
        if not resolution.get("form_found"):
            missing_results = [
                self._field_result(
                    key=key,
                    value=value,
                    redact=redact_values,
                    reason="FORM_NOT_FOUND",
                )
                for key, value in fields.items()
            ]
            return {
                "form_selector": plan.metadata(),
                **resolution,
                **self._result_counts(missing_results),
                "fields": missing_results,
            }

        deadline = monotonic() + timeout
        form_selector_css = str(resolution["form"]["selector"])
        results: list[dict[str, Any]] = []
        for target in targets:
            key = str(target["key"])
            value = fields[key]
            control_type = str(target.get("control_type") or "")
            redact = redact_values or control_type == "password"
            base = {
                "key": key,
                "matched_by": str(target.get("matched_by") or ""),
                "selector": str(target.get("selector") or ""),
                "control_type": control_type,
                "requested_value": "<redacted>" if redact else value,
                "redacted": redact,
            }
            reason = str(target.get("reason") or "")
            if reason:
                results.append(
                    {
                        **base,
                        "success": False,
                        "reason": reason,
                        "observed_value": None,
                        "verified": False,
                    }
                )
                continue
            if monotonic() >= deadline:
                results.append(
                    {
                        **base,
                        "success": False,
                        "reason": "INTERACTION_TIMEOUT",
                        "observed_value": None,
                        "verified": False,
                    }
                )
                continue

            interaction_error = ""
            try:
                action = str(target["action"])
                if action.startswith("native_"):
                    self._apply_native_form_value(
                        form_selector=form_selector_css,
                        target=target,
                        value=value,
                        deadline=deadline,
                    )
                else:
                    interaction_error = self._apply_framework_form_value(
                        form_locator=plan.locator,
                        target=target,
                        action=action,
                        value=value,
                    )
            except Exception:
                logger.debug("Form field interaction failed", exc_info=True)
                interaction_error = "INTERACTION_FAILED"

            await self._tab._stabilize(
                "form_fill_field", timeout=min(max(deadline - monotonic(), 0), 0.5)
            )
            try:
                observation = await self._observe_form_value(
                    form_locator=plan.locator,
                    target=target,
                    requested=value,
                    deadline=deadline,
                )
            except Exception:
                logger.debug("Form field observation failed", exc_info=True)
                observation = {"reason": "INTERACTION_FAILED", "value": None}
            observation_error = str(observation.get("reason") or "")
            actual = observation.get("value")
            matches = self._form_value_matches(value, actual, control_type)
            if (
                control_type in {"date", "time"}
                and not observation_error
                and not matches
                and monotonic() < deadline
            ):
                try:
                    fallback_error = self._apply_framework_form_value(
                        form_locator=plan.locator,
                        target=target,
                        action="framework_date_time",
                        value=value,
                    )
                    if not fallback_error:
                        interaction_error = ""
                        await self._tab._stabilize(
                            "form_fill_date_time_fallback",
                            timeout=min(max(deadline - monotonic(), 0), 0.5),
                        )
                        observation = await self._observe_form_value(
                            form_locator=plan.locator,
                            target=target,
                            requested=value,
                            deadline=deadline,
                        )
                        observation_error = str(observation.get("reason") or "")
                        actual = observation.get("value")
                        matches = self._form_value_matches(value, actual, control_type)
                    elif not interaction_error:
                        interaction_error = fallback_error
                except Exception:
                    logger.debug("Date/time form fallback failed", exc_info=True)
                    if not interaction_error:
                        interaction_error = "INTERACTION_FAILED"

            reason = interaction_error or observation_error
            success, verified, reason = self._classify_form_value(
                reason=reason,
                matches=matches,
                verify=verify,
            )
            results.append(
                {
                    **base,
                    "success": success,
                    "reason": reason,
                    "observed_value": "<redacted>" if redact else actual,
                    "verified": verified,
                }
            )

        return {
            "form_selector": plan.metadata(),
            **resolution,
            **self._result_counts(results),
            "fields": results,
        }

    def resolve_form_submit(
        self, *, form_selector: str, submit_selector: str = ""
    ) -> dict[str, Any]:
        """Resolve one enabled submitter without reserving or mutating state."""

        form_plan = normalize_selector(form_selector)
        submit_plan = normalize_selector(submit_selector) if submit_selector else None
        result = run_structured_script(
            self._page,
            _form_submit_resolve_script(
                form_locator=form_plan.locator,
                submit_locator=submit_plan.locator if submit_plan else "",
            ),
            "form submit resolution script returned no structured data",
        )
        if result.get("reason"):
            raise FormSubmitPreconditionError(str(result["reason"]))
        return {
            "form_selector": form_plan.metadata(),
            "form_locator": form_plan.locator,
            "submit_selector": submit_plan.metadata() if submit_plan else None,
            **result,
        }

    async def form_submit(
        self,
        *,
        resolved: Mapping[str, Any],
        expect: Expectation | None,
    ) -> dict[str, Any]:
        """Invoke one resolved submitter once, then classify fresh page evidence."""

        original_url = self._tab.url
        timeout = expect.timeout if expect is not None else 1.0
        deadline = monotonic() + timeout
        submitter = dict(resolved["submitter"])
        try:
            initial_state = run_structured_script(
                self._page,
                _form_submit_state_script(form_locator=str(resolved["form_locator"])),
                "form submit precondition script returned no structured data",
            )
        except Exception as exc:
            raise FormSubmitExecutionError(
                "SUBMIT_PRECONDITION_STATE_FAILED", triggered=False
            ) from exc
        sensitive_values = tuple(
            str(value)
            for value in list(initial_state.get("sensitive_values") or [])
            if str(value)
        )
        baseline_server_validation = self._server_validation_tokens(initial_state)
        baselines: list[tuple[bool, str]] = []
        preconditions: list[ConditionEvaluation] = []
        try:
            if expect is not None:
                for index, condition in enumerate(expect.conditions):
                    pre_matched, token = await self._observe_expectation_condition(
                        condition=condition,
                        original_url=original_url,
                    )
                    baselines.append((pre_matched, token))
                    preconditions.append(
                        ConditionEvaluation(
                            condition_index=index,
                            kind=condition.kind,
                            status="matched" if pre_matched else "unmatched",
                            evidence=(
                                ("PRECONDITION_MATCHED",)
                                if pre_matched
                                else ("PRECONDITION_UNMATCHED",)
                            ),
                        )
                    )
        except Exception as exc:
            raise FormSubmitExecutionError(
                "SUBMIT_PRECONDITION_OBSERVATION_FAILED", triggered=False
            ) from exc
        click_error = ""
        try:
            await self._tab.elements.click(
                str(submitter["selector"]),
                timeout=max(1, min(int(timeout + 0.999), 10)),
            )
        except Exception:
            logger.debug("Resolved form submitter invocation failed", exc_info=True)
            click_error = "SUBMIT_INVOCATION_FAILED"

        last_state: dict[str, Any] = {}
        evaluations: list[ConditionEvaluation] = []
        while True:
            try:
                last_state = run_structured_script(
                    self._page,
                    _form_submit_state_script(
                        form_locator=str(resolved["form_locator"])
                    ),
                    "form submit state script returned no structured data",
                )
            except Exception:
                logger.debug("Form submit state observation failed", exc_info=True)
                last_state = {
                    "url": self._tab.url,
                    "title": self._tab.title,
                    "validation_messages": [],
                }

            validation_messages = list(last_state.get("validation_messages") or [])
            client_validation = [
                item
                for item in validation_messages
                if str(item.get("source") or "") == "client"
            ]
            server_validation = [
                item
                for item in validation_messages
                if str(item.get("source") or "") == "server"
            ]
            fresh_server_validation = self._server_validation_tokens(last_state) - (
                baseline_server_validation
            )
            if client_validation or fresh_server_validation:
                if not client_validation:
                    last_state = {
                        **last_state,
                        "validation_messages": [
                            item
                            for item in server_validation
                            if self._validation_token(item) in fresh_server_validation
                        ],
                    }
                return self._form_submit_result(
                    status="validation_failed",
                    state=last_state,
                    preconditions=preconditions,
                    evaluations=evaluations,
                    click_error=click_error,
                    sensitive_values=sensitive_values,
                )

            if expect is None:
                return self._form_submit_result(
                    status="indeterminate" if click_error else "submitted_pending",
                    state=last_state,
                    preconditions=preconditions,
                    evaluations=evaluations,
                    click_error=click_error,
                    sensitive_values=sensitive_values,
                )

            evaluations = await self._evaluate_expectation(
                expect=expect,
                original_url=original_url,
                baselines=baselines,
            )
            condition_matches = [item.status == "matched" for item in evaluations]
            expectation_matched = (
                all(condition_matches)
                if expect.mode == "all"
                else any(condition_matches)
            )
            if expectation_matched:
                try:
                    last_state = run_structured_script(
                        self._page,
                        _form_submit_state_script(
                            form_locator=str(resolved["form_locator"])
                        ),
                        "form submit terminal state script returned no structured data",
                    )
                except Exception:
                    last_state = {
                        **last_state,
                        "url": self._tab.url,
                        "title": self._tab.title,
                    }
                return self._form_submit_result(
                    status="success",
                    state=last_state,
                    preconditions=preconditions,
                    evaluations=evaluations,
                    click_error=click_error,
                    sensitive_values=sensitive_values,
                )
            if monotonic() >= deadline:
                return self._form_submit_result(
                    status="indeterminate",
                    state=last_state,
                    preconditions=preconditions,
                    evaluations=evaluations,
                    click_error=click_error or "EXPECTATION_TIMEOUT",
                    sensitive_values=sensitive_values,
                )
            await asyncio.sleep(min(0.1, max(0.01, deadline - monotonic())))

    async def _evaluate_expectation(
        self,
        *,
        expect: Expectation,
        original_url: str,
        baselines: list[tuple[bool, str]],
    ) -> list[ConditionEvaluation]:
        results: list[ConditionEvaluation] = []
        for index, condition in enumerate(expect.conditions):
            kind = condition.kind
            try:
                matched, token = await self._observe_expectation_condition(
                    condition=condition,
                    original_url=original_url,
                )
                baseline_matched, baseline_token = baselines[index]
                fresh = (
                    not baseline_matched
                    or token != baseline_token
                    or self._tab.url != original_url
                )
                matched = matched and fresh
                results.append(
                    ConditionEvaluation(
                        condition_index=index,
                        kind=kind,
                        status="matched" if matched else "unmatched",
                        evidence=(
                            ("POSTCONDITION_MATCHED",)
                            if matched
                            else ("POSTCONDITION_UNMATCHED",)
                        ),
                    )
                )
            except Exception:
                logger.debug("Postcondition evaluation failed", exc_info=True)
                results.append(
                    ConditionEvaluation(
                        condition_index=index,
                        kind=kind,
                        status="error",
                        evidence=("POSTCONDITION_EVALUATION_ERROR",),
                    )
                )
        return results

    def _server_validation_tokens(self, state: Mapping[str, Any]) -> set[str]:
        return {
            self._validation_token(item)
            for item in list(state.get("validation_messages") or [])
            if isinstance(item, Mapping) and str(item.get("source") or "") == "server"
        }

    @staticmethod
    def _validation_token(item: Mapping[str, Any]) -> str:
        return json.dumps(
            {
                "selector": item.get("selector"),
                "message": item.get("message"),
                "code": item.get("code"),
                "source": item.get("source"),
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )

    async def _observe_expectation_condition(
        self, *, condition: Any, original_url: str
    ) -> tuple[bool, str]:
        kind = condition.kind
        if kind == "url_changed":
            current_url = self._tab.url
            return current_url != original_url, current_url
        if kind == "url_contains":
            current_url = self._tab.url
            return condition.value in current_url, current_url
        if kind in {"selector_visible", "selector_hidden"}:
            matched, state = await self._tab.waits._condition_matches(
                condition="visible" if kind == "selector_visible" else "hidden",
                selector=condition.selector,
                value="",
                name="",
                stable_ms=0,
            )
            return matched, json.dumps(state, sort_keys=True, default=str)
        if kind == "text_contains":
            matched, state = await self._tab.waits._condition_matches(
                condition="text_contains",
                selector=condition.selector or "",
                value=condition.value,
                name="",
                stable_ms=0,
            )
            return matched, json.dumps(state, sort_keys=True, default=str)
        observed = await self._tab.elements.property(
            condition.selector, condition.property
        )
        return observed == condition.value, json.dumps(observed, default=str)

    def _form_submit_result(
        self,
        *,
        status: str,
        state: Mapping[str, Any],
        preconditions: list[ConditionEvaluation],
        evaluations: list[ConditionEvaluation],
        click_error: str,
        sensitive_values: tuple[str, ...],
    ) -> dict[str, Any]:
        validation_messages = []
        for item in list(state.get("validation_messages") or []):
            sanitized = dict(item)
            sanitized["message"] = self._redact_sensitive_text(
                str(sanitized.get("message") or ""), sensitive_values
            )
            validation_messages.append(sanitized)
        return {
            "status": status,
            "triggered": True,
            "current_url": str(state.get("url") or self._tab.url),
            "title": self._redact_sensitive_text(
                str(state.get("title") or self._tab.title), sensitive_values
            ),
            "validation_messages": validation_messages,
            "preconditions": [item.model_dump(mode="json") for item in preconditions],
            "postconditions": [item.model_dump(mode="json") for item in evaluations],
            "error_code": click_error,
            "_sensitive_values": list(sensitive_values),
        }

    @staticmethod
    def _redact_sensitive_text(value: str, sensitive_values: tuple[str, ...]) -> str:
        redacted = value
        for secret in sorted(set(sensitive_values), key=len, reverse=True):
            if secret:
                redacted = redacted.replace(secret, "<redacted>")
        return redacted

    def _apply_native_form_value(
        self,
        *,
        form_selector: str,
        target: Mapping[str, Any],
        value: str | bool | list[str],
        deadline: float,
    ) -> None:
        """Apply one value through the scoped DrissionPage element API."""

        form = self._page.ele(f"css:{form_selector}", timeout=0)
        if not form:
            raise RuntimeError("Resolved form is no longer available")
        element = form.ele(f"css:{target['relative_selector']}", timeout=0)
        if not element:
            raise RuntimeError("Resolved form control is no longer available")

        action = str(target["action"])
        if action == "native_input":
            # DrissionPage 4.1 clears with a platform-specific key chord on Linux.
            # Its JS path is consistent across platforms; real input still follows.
            element.clear(by_js=True)
            element.input(
                self._native_input_value(str(value), str(target["control_type"])),
                clear=False,
            )
            actions = getattr(self._page, "actions", None)
            if actions is not None:
                actions.type("\ue004")
            return
        if action == "native_check":
            element.check(uncheck=not bool(value))
            return
        if action != "native_select":
            raise RuntimeError(f"Unknown native form action: {action}")

        select = element.select
        modes = list(target.get("select_modes") or [])
        if isinstance(value, bool):
            raise RuntimeError("Boolean value is not valid for native select")
        requested: list[str] = value if isinstance(value, list) else [value]
        if bool(target.get("multiple")):
            select.clear()
        for item, mode in zip(requested, modes, strict=True):
            remaining = max(deadline - monotonic(), 0.01)
            if mode == "value":
                select.by_value(item, timeout=remaining)
            elif mode == "text":
                select.by_text(item, timeout=remaining)
            else:
                raise RuntimeError(f"Unknown native select mode: {mode}")

    def _apply_framework_form_value(
        self,
        *,
        form_locator: str,
        target: Mapping[str, Any],
        action: str,
        value: str | bool | list[str],
    ) -> str:
        """Apply one scoped JavaScript fallback and return its reason code."""

        result = run_structured_script(
            self._page,
            _form_fill_framework_script(
                form_locator=form_locator,
                selector=str(target["selector"]),
                action=action,
                value=value,
                aria_container_id=str(target.get("aria_container_id") or ""),
                aria_container_self=bool(target.get("aria_container_self")),
            ),
            "form fill fallback script returned no structured data",
        )
        return str(result.get("reason") or "")

    async def _observe_form_value(
        self,
        *,
        form_locator: str,
        target: Mapping[str, Any],
        requested: str | bool | list[str],
        deadline: float,
    ) -> dict[str, Any]:
        """Poll briefly for the live control state produced by one interaction."""

        settle_deadline = min(deadline, monotonic() + 0.75)
        while True:
            observation = run_structured_script(
                self._page,
                _form_fill_observe_script(
                    form_locator=form_locator,
                    selector=str(target["selector"]),
                    control_type=str(target["control_type"]),
                    aria_container_id=str(target.get("aria_container_id") or ""),
                    aria_container_self=bool(target.get("aria_container_self")),
                ),
                "form fill observation script returned no structured data",
            )
            if observation.get("reason") or self._form_value_matches(
                requested,
                observation.get("value"),
                str(target["control_type"]),
            ):
                return observation
            remaining = settle_deadline - monotonic()
            if remaining <= 0:
                return observation
            await asyncio.sleep(min(0.02, remaining))

    @staticmethod
    def _native_input_value(value: str, control_type: str) -> str | list[str]:
        """Use segmented native keystrokes for Chromium date/time controls."""

        right = "\ue014"
        if control_type == "date" and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            year, month, day = value.split("-")
            return [*year, right, *month, right, *day]
        if control_type == "time" and re.fullmatch(r"\d{2}:\d{2}(?::\d{2})?", value):
            parts = value.split(":")
            sequence: list[str] = []
            for index, part in enumerate(parts):
                if index:
                    sequence.append(right)
                sequence.extend(part)
            return sequence
        return value

    @staticmethod
    def _form_value_matches(
        requested: str | bool | list[str], actual: Any, control_type: str
    ) -> bool:
        if isinstance(requested, list):
            expected = sorted(str(item) for item in requested)
            observed = actual if isinstance(actual, list) else [actual]
            return expected == sorted(str(item) for item in observed)
        if isinstance(requested, bool):
            return actual is requested
        if control_type in {"combobox", "listbox"}:
            return str(actual).lower() == requested.lower()
        return str(actual) == requested

    @staticmethod
    def _classify_form_value(
        *, reason: str, matches: bool, verify: bool
    ) -> tuple[bool, bool, str]:
        """Separate interaction success from optional value verification."""

        if reason:
            return False, False, reason
        if matches:
            return True, True, ""
        if verify:
            return False, False, "VERIFICATION_FAILED"
        return True, False, ""

    @staticmethod
    def _field_result(
        *,
        key: str,
        value: str | bool | list[str],
        redact: bool,
        reason: str,
    ) -> dict[str, Any]:
        return {
            "key": key,
            "success": False,
            "reason": reason,
            "matched_by": "",
            "selector": "",
            "control_type": "",
            "requested_value": "<redacted>" if redact else value,
            "observed_value": None,
            "redacted": redact,
            "verified": False,
        }

    @staticmethod
    def _result_counts(results: list[dict[str, Any]]) -> dict[str, int]:
        filled = sum(bool(item["success"]) for item in results)
        return {
            "filled_count": filled,
            "failed_count": len(results) - filled,
            "verified_count": sum(bool(item["verified"]) for item in results),
        }
