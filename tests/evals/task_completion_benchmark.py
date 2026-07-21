"""Tool-orchestrated W01-W08 reliability benchmark for the 0.7 release line."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import sys
from contextlib import contextmanager, suppress
from datetime import datetime, timezone
from math import ceil
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from typing import Any, Awaitable, Callable, Iterator
from urllib.request import Request, urlopen

from drissionpage_mcp import __version__
from drissionpage_mcp.compat import DRISSIONPAGE_VERSION
from drissionpage_mcp.server import DrissionPageMCPServer
from tests.fixtures.http_fixture import (
    TASK_COMPLETION_DOWNLOAD,
    TASK_COMPLETION_DOWNLOAD_SHA256,
    local_http_fixture,
)


WORKLOAD_TOOL_REQUIREMENTS = {
    "W01": frozenset(
        {"element_type", "element_select", "element_check", "element_click"}
    ),
    "W02": frozenset({"element_type", "element_get_property", "element_click"}),
    "W03": frozenset({"element_type", "element_get_property", "element_click"}),
    "W04": frozenset({"element_upload_file", "element_type", "element_click"}),
    "W05": frozenset({"element_click", "page_dialog_respond"}),
    "W06": frozenset({"element_click", "tab_list", "tab_switch"}),
    "W07": frozenset({"element_click_and_download"}),
    "W08": frozenset({"element_click", "keyboard_press"}),
}

SIDE_EFFECT_BASELINES = {
    "W01": {"form_rich_attempted_requests": 1},
    "W02": {"form_controlled_attempted_requests": 1},
    "W03": {"validation_attempted_requests": 2},
    "W04": {"upload_attempted_requests": 1},
    "W05": {},
    "W06": {},
    "W07": {"download_requests": 1, "download_fail_requests": 1},
    "W08": {},
}


class BenchmarkFailure(AssertionError):
    """One workload failed to produce its required business evidence."""


class BenchmarkClient:
    """Call public tools through the server path while recording tool usage."""

    def __init__(self, server: DrissionPageMCPServer) -> None:
        self.server = server
        self.calls: list[str] = []

    async def call(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        expect_ok: bool = True,
    ) -> dict[str, Any]:
        self.calls.append(name)
        call_tool = getattr(self.server, "_call_tool_impl")
        result = await call_tool(name, arguments or {})
        payload = dict(result.structuredContent or {})
        if bool(payload.get("ok")) is not expect_ok:
            raise BenchmarkFailure(
                f"{name} returned ok={payload.get('ok')!r}: "
                f"{payload.get('message', '')}"
            )
        return payload


async def _w01_rich_form(
    client: BenchmarkClient, base_url: str, _run_id: str, _root: Path
) -> dict[str, Any]:
    await client.call("page_navigate", {"url": base_url + "/form-rich"})
    for selector, value in (
        ("#full-name", "Ada Lovelace"),
        ("#alias-id", "Countess"),
        ("#contact-name", "ada-contact"),
        ("#nickname", "Enchantress"),
        ('[data-testid="explicit-css-field"]', "explicit-value"),
        ("#access-code", "benchmark-secret"),
    ):
        await _type_and_verify(client, selector, value)
    await client.call(
        "element_type",
        {"selector": "#bio", "text": "First programmer", "clear": True},
    )
    bio = await client.call("element_get_text", {"selector": "#bio"})
    _require(bio["data"]["text"] == "First programmer", "W01 bio mismatch")
    await client.call(
        "element_select",
        {"selector": "#department", "value": "Research", "by": "value"},
    )
    await client.call("element_check", {"selector": "#updates", "checked": True})
    await client.call("element_click", {"selector": "#office"})
    await client.call(
        "element_click", {"selector": '#office-options [data-value="Shanghai"]'}
    )
    await client.call("element_click", {"selector": "#profile-submit"})
    business_id = await _wait_for_business_id(client)
    _require(business_id == "PROFILE-0001", "W01 submit result mismatch")
    state = await _fixture_state(base_url)
    _require_counter(state, "form_rich_attempted_requests", 1)
    _require_counter(state, "form_rich_accepted_requests", 1)
    return {"business_result": "PROFILE-0001"}


async def _w02_controlled_form(
    client: BenchmarkClient, base_url: str, _run_id: str, _root: Path
) -> dict[str, Any]:
    await client.call("page_navigate", {"url": base_url + "/form-controlled"})
    for value in ("Ada Initial", "Ada Controlled"):
        await _type_and_verify(client, "#controlled-name", value)
    await client.call("element_click", {"selector": "#controlled-submit"})
    business_id = await _wait_for_business_id(client)
    _require(business_id == "CONTROLLED-0001", "W02 submit result mismatch")
    state = await _fixture_state(base_url)
    _require_counter(state, "form_controlled_attempted_requests", 1)
    _require_counter(state, "form_controlled_accepted_requests", 1)
    return {"business_result": "CONTROLLED-0001"}


async def _w03_validation_recovery(
    client: BenchmarkClient, base_url: str, _run_id: str, _root: Path
) -> dict[str, Any]:
    await client.call("page_navigate", {"url": base_url + "/form-validation"})
    await _fill_employee_code(client, "bad")
    await client.call("element_click", {"selector": "#validation-form button"})
    client_validation = await client.call(
        "element_get_property",
        {"selector": "#employee-code", "property": "validationMessage"},
    )
    _require(
        bool(client_validation["data"]["value"]),
        "W03 client validation evidence was not observable",
    )
    _require(
        (await _fixture_state(base_url))["counters"] == {},
        "W03 submitted invalid client state",
    )

    await _fill_employee_code(client, "DP-071")
    await client.call("element_click", {"selector": "#validation-form button"})
    await client.call(
        "wait_for_element", {"selector": "#employee-code-server-error", "timeout": 3}
    )
    server_failure = await client.call(
        "element_get_text", {"selector": "#employee-code-server-error"}
    )
    _require(
        server_failure["data"]["text"] == "Employee code must be DP-070",
        "W03 server validation evidence mismatch",
    )

    await _fill_employee_code(client, "DP-070")
    await client.call("element_click", {"selector": "#validation-form button"})
    business_id = await _wait_for_business_id(client)
    _require(business_id == "VALIDATED-0001", "W03 correction did not recover")
    state = await _fixture_state(base_url)
    _require_counter(state, "validation_attempted_requests", 2)
    _require_counter(state, "validation_accepted_requests", 1)
    return {"business_result": "VALIDATED-0001"}


async def _w04_upload_submit(
    client: BenchmarkClient, base_url: str, _run_id: str, root: Path
) -> dict[str, Any]:
    upload_file = root / "uploads" / "fixture-note.txt"
    await client.call("page_navigate", {"url": base_url + "/form-upload-submit"})
    await _type_and_verify(client, "#case-name", "Quarterly notes")
    await client.call(
        "element_upload_file",
        {"selector": "#attachment", "paths": [str(upload_file)]},
    )
    await client.call("element_click", {"selector": "#upload-submit"})
    business_id = await _wait_for_business_id(client)
    _require(business_id == "UPLOAD-0001", "W04 submit result mismatch")
    state = await _fixture_state(base_url)
    _require_counter(state, "upload_attempted_requests", 1)
    _require_counter(state, "upload_accepted_requests", 1)
    return {"business_result": "UPLOAD-0001"}


async def _w05_dialog(
    client: BenchmarkClient, base_url: str, _run_id: str, _root: Path
) -> dict[str, Any]:
    await client.call("page_navigate", {"url": base_url + "/dialog"})
    click = asyncio.create_task(
        client.call("element_click", {"selector": "#confirm-button", "timeout": 2})
    )
    try:
        response = await client.call(
            "page_dialog_respond", {"action": "accept", "timeout": 2}
        )
        await click
    finally:
        if not click.done():
            click.cancel()
        await asyncio.gather(click, return_exceptions=True)
    _require(response["data"]["handled"] is True, "W05 dialog was not handled")
    status = await client.call("element_get_text", {"selector": "#dialog-status"})
    _require(status["data"]["text"] == "confirm accepted", "W05 result mismatch")
    return {"business_result": "confirm accepted"}


async def _w06_popup(
    client: BenchmarkClient, base_url: str, _run_id: str, _root: Path
) -> dict[str, Any]:
    navigate = await client.call("page_navigate", {"url": base_url + "/popup"})
    opener_id = str(navigate["data"]["tab_id"])
    await client.call("element_click", {"selector": "#popup-link", "timeout": 2})
    popup_id = ""
    for _ in range(25):
        tabs = await client.call("tab_list")
        candidates = [item for item in tabs["data"]["tabs"] if item["id"] != opener_id]
        if candidates:
            popup_id = str(candidates[0]["id"])
            break
        await asyncio.sleep(0.02)
    _require(bool(popup_id), "W06 popup tab was not discovered")
    try:
        await client.call("tab_switch", {"tab_id": popup_id})
        await client.call(
            "element_click", {"selector": "#popup-complete", "timeout": 2}
        )
        status = await client.call("element_get_text", {"selector": "#popup-result"})
        _require(status["data"]["text"] == "popup work complete", "W06 result mismatch")
        return {"business_result": "popup work complete"}
    finally:
        with suppress(Exception):
            await client.call("tab_close", {"tab_id": popup_id})


async def _w07_download(
    client: BenchmarkClient, base_url: str, run_id: str, _root: Path
) -> dict[str, Any]:
    await client.call("page_navigate", {"url": base_url + "/download"})
    arguments = {
        "selector": "#download-link",
        "operation_key": f"{run_id}-success",
        "timeout": 10,
        "expected_filename": "fixture-report.csv",
        "expected_mime_type": "text/csv",
    }
    first = await client.call("element_click_and_download", arguments)
    replay = await client.call("element_click_and_download", arguments)
    artifact = first["data"]["artifact"]
    _require(replay["data"] == first["data"], "W07 replay changed frozen result")
    _require(
        artifact["sha256"] == TASK_COMPLETION_DOWNLOAD_SHA256, "W07 checksum mismatch"
    )
    _require(
        artifact["size_bytes"] == len(TASK_COMPLETION_DOWNLOAD), "W07 size mismatch"
    )

    await client.call("page_navigate", {"url": base_url + "/download-fail"})
    failure = await client.call(
        "element_click_and_download",
        {
            "selector": "#download-fail-link",
            "operation_key": f"{run_id}-failure",
            "timeout": 2,
        },
        expect_ok=False,
    )
    _require(failure["data"]["artifact"] is None, "W07 published a failed artifact")
    state = await _fixture_state(base_url)
    _require_counter(state, "download_requests", 1)
    _require_counter(state, "download_fail_requests", 1)
    return {"business_result": artifact["artifact_id"]}


async def _w08_click_and_keyboard(
    client: BenchmarkClient, base_url: str, _run_id: str, _root: Path
) -> dict[str, Any]:
    await client.call("page_navigate", {"url": base_url + "/click-variants"})
    await client.call(
        "element_click",
        {"selector": "#click-target", "button": "left", "click_count": 2},
    )
    await client.call(
        "element_click",
        {"selector": "#click-target", "button": "right", "click_count": 1},
    )
    await client.call("keyboard_press", {"keys": "\ue009s"})
    status = await client.call("element_get_text", {"selector": "#click-status"})
    value = str(status["data"]["text"])
    for expected in ("dblclick=1", "contextmenu=1", "shortcut=1"):
        _require(expected in value, f"W08 missing {expected}")
    return {"business_result": value}


Workload = Callable[[BenchmarkClient, str, str, Path], Awaitable[dict[str, Any]]]
WORKLOADS: dict[str, Workload] = {
    "W01": _w01_rich_form,
    "W02": _w02_controlled_form,
    "W03": _w03_validation_recovery,
    "W04": _w04_upload_submit,
    "W05": _w05_dialog,
    "W06": _w06_popup,
    "W07": _w07_download,
    "W08": _w08_click_and_keyboard,
}


async def run_benchmark(iterations: int = 10) -> dict[str, Any]:
    """Run every public-tool workload and return a bounded JSON report."""

    if iterations < 1:
        raise ValueError("iterations must be at least 1")
    started_at = datetime.now(timezone.utc)
    results: list[dict[str, Any]] = []
    runtimes: list[dict[str, Any]] = []

    for iteration in range(1, iterations + 1):
        server: DrissionPageMCPServer | None = None
        with TemporaryDirectory(prefix="drissionmcp-benchmark-") as temp_dir:
            root = Path(temp_dir)
            (root / "uploads").mkdir()
            (root / "uploads" / "fixture-note.txt").write_text(
                "synthetic benchmark upload\n", encoding="utf-8"
            )
            (root / "downloads").mkdir()
            with _benchmark_environment(root), local_http_fixture() as base_url:
                try:
                    for workload_id, workload in WORKLOADS.items():
                        if server is None:
                            server = DrissionPageMCPServer()
                        await _reset_fixture(base_url)
                        client = BenchmarkClient(server)
                        started = monotonic()
                        restart_server = False
                        try:
                            evidence = await workload(
                                client,
                                base_url,
                                f"{workload_id.lower()}-{iteration:02d}",
                                root,
                            )
                            missing_tools = _missing_required_tools(
                                workload_id, client.calls
                            )
                            _require(
                                not missing_tools,
                                f"{workload_id} skipped required public tools: "
                                + ", ".join(missing_tools),
                            )
                            success = True
                            error = ""
                            failure_category = ""
                        except Exception as exc:
                            success = False
                            restart_server = True
                            evidence = {}
                            error = f"{type(exc).__name__}: {exc}"[:500]
                            failure_category = _failure_category(error)
                        side_effect_counts, duplicate_count = _side_effect_evidence(
                            workload_id, await _fixture_state(base_url)
                        )
                        evidence["side_effect_counts"] = side_effect_counts
                        evidence["duplicate_count"] = duplicate_count
                        if duplicate_count:
                            success = False
                            if not error:
                                error = (
                                    "BenchmarkFailure: observed "
                                    f"{duplicate_count} duplicate side effect(s)"
                                )
                            failure_category = "workload_failure"
                        results.append(
                            {
                                "workload_id": workload_id,
                                "iteration": iteration,
                                "success": success,
                                "duration_ms": round((monotonic() - started) * 1000),
                                "tool_calls": list(client.calls),
                                "tool_call_count": len(client.calls),
                                "side_effect_counts": dict(
                                    evidence["side_effect_counts"]
                                ),
                                "duplicate_count": int(evidence["duplicate_count"]),
                                "business_result": evidence.get("business_result", ""),
                                "error": error,
                                "failure_category": failure_category,
                            }
                        )
                        if restart_server:
                            runtimes.append(_runtime_evidence(server, iteration))
                            await server.cleanup()
                            server = None
                finally:
                    if server is not None:
                        runtimes.append(_runtime_evidence(server, iteration))
                        await server.cleanup()

    summary = _summarize(results, iterations)
    summary["browser_evidence_complete"] = _browser_evidence_complete(runtimes)
    summary["passed"] = bool(summary["passed"]) and bool(
        summary["browser_evidence_complete"]
    )
    return {
        "schema_version": "1",
        "release": __version__,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "iterations": iterations,
        "required_successes_per_workload": ceil(iterations * 0.9),
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "drissionpage": DRISSIONPAGE_VERSION,
            "headless": _env_truthy("DP_HEADLESS"),
            "no_sandbox": _env_truthy("DP_NO_SANDBOX"),
            "runtimes": runtimes,
        },
        "summary": summary,
        "runs": results,
    }


def _summarize(results: list[dict[str, Any]], iterations: int) -> dict[str, Any]:
    required = ceil(iterations * 0.9)
    workloads: dict[str, dict[str, Any]] = {}
    for workload_id in WORKLOADS:
        selected = [item for item in results if item["workload_id"] == workload_id]
        successes = sum(bool(item["success"]) for item in selected)
        workloads[workload_id] = {
            "successes": successes,
            "runs": len(selected),
            "success_rate": round(successes / len(selected), 3) if selected else 0.0,
            "passed": successes >= required,
            "tool_calls": sum(int(item["tool_call_count"]) for item in selected),
            "duplicate_count": sum(int(item["duplicate_count"]) for item in selected),
        }
    duplicate_count = sum(int(item["duplicate_count"]) for item in results)
    return {
        "passed": all(item["passed"] for item in workloads.values())
        and duplicate_count == 0,
        "total_runs": len(results),
        "successful_runs": sum(bool(item["success"]) for item in results),
        "duplicate_count": duplicate_count,
        "workloads": workloads,
    }


def _missing_required_tools(workload_id: str, calls: list[str]) -> list[str]:
    required = WORKLOAD_TOOL_REQUIREMENTS[workload_id]
    return sorted(required.difference(calls))


def _browser_evidence_complete(runtimes: list[dict[str, Any]]) -> bool:
    return bool(runtimes) and all(
        bool(item.get("browser_product")) and bool(item.get("browser_revision"))
        for item in runtimes
    )


async def _fill_employee_code(client: BenchmarkClient, value: str) -> None:
    await _type_and_verify(client, "#employee-code", value)


async def _type_and_verify(client: BenchmarkClient, selector: str, value: str) -> None:
    await client.call(
        "element_type", {"selector": selector, "text": value, "clear": True}
    )
    observed = await client.call(
        "element_get_property", {"selector": selector, "property": "value"}
    )
    if observed["data"]["value"] is None:
        observed = await client.call("element_get_text", {"selector": selector})
        actual = observed["data"]["text"]
    else:
        actual = observed["data"]["value"]
    _require(actual == value, f"{selector} expected {value!r}, observed {actual!r}")


async def _wait_for_business_id(client: BenchmarkClient) -> str:
    await client.call("wait_for_element", {"selector": "#business-id", "timeout": 3})
    payload = await client.call(
        "element_get_attribute", {"selector": "#business-id", "attribute": "value"}
    )
    return str(payload["data"]["value"] or "")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BenchmarkFailure(message)


def _require_counter(state: dict[str, Any], key: str, expected: int) -> None:
    actual = int(state["counters"].get(key, 0))
    _require(actual == expected, f"{key} expected {expected}, observed {actual}")


def _side_effect_evidence(
    workload_id: str, state: dict[str, Any]
) -> tuple[dict[str, int], int]:
    baseline = SIDE_EFFECT_BASELINES[workload_id]
    counters = state["counters"]
    observed = {key: int(counters.get(key, 0)) for key in baseline}
    duplicate_count = sum(
        max(0, observed[key] - expected) for key, expected in baseline.items()
    )
    return observed, duplicate_count


async def _fixture_state(base_url: str) -> dict[str, Any]:
    def read() -> dict[str, Any]:
        with urlopen(base_url + "/__fixture__/state", timeout=5) as response:
            return json.loads(response.read())

    return await asyncio.to_thread(read)


async def _reset_fixture(base_url: str) -> None:
    def reset() -> None:
        request = Request(base_url + "/__fixture__/reset", data=b"", method="POST")
        with urlopen(request, timeout=5) as response:
            response.read()

    await asyncio.to_thread(reset)


def _runtime_evidence(server: DrissionPageMCPServer, iteration: int) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "iteration": iteration,
        "browser_product": "",
        "browser_revision": "",
        "error": "",
    }
    context = server.context
    browser = context.browser if context is not None else None
    run_cdp = getattr(browser, "_run_cdp", None)
    if callable(run_cdp):
        try:
            version = run_cdp("Browser.getVersion")
            evidence["browser_product"] = str(version.get("product") or "")
            evidence["browser_revision"] = str(version.get("revision") or "")
        except Exception as exc:
            evidence["error"] = f"{type(exc).__name__}: {exc}"[:300]
    elif browser is None:
        evidence["error"] = "browser was not initialized"
    else:
        evidence["error"] = "Browser.getVersion is unavailable"
    return evidence


@contextmanager
def _benchmark_environment(root: Path) -> Iterator[None]:
    updates = {
        "DP_MCP_UPLOAD_ROOT": str(root / "uploads"),
        "DP_MCP_DOWNLOAD_ROOT": str(root / "downloads"),
        "DP_MCP_DENY_DOWNLOAD": None,
        "DP_MCP_DENY_EXTERNAL_SUBMISSION": None,
    }
    previous = {name: os.environ.get(name) for name in updates}
    try:
        for name, value in updates.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").lower() in {"1", "true", "yes", "on"}


def _failure_category(error: str) -> str:
    lowered = error.lower()
    browser_markers = (
        "browser",
        "chrome",
        "chromium",
        "cannot find",
        "failed to initialize",
        "executable",
    )
    if any(marker in lowered for marker in browser_markers):
        return "browser_unavailable"
    return "workload_failure"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def _console_report(report: dict[str, Any]) -> dict[str, Any]:
    failures = [
        {
            "workload_id": item["workload_id"],
            "iteration": item["iteration"],
            "error": item["error"],
            "failure_category": item["failure_category"],
            "tool_calls": item["tool_calls"],
            "side_effect_counts": item["side_effect_counts"],
            "duplicate_count": item["duplicate_count"],
        }
        for item in report["runs"]
        if not item["success"] or item["duplicate_count"]
    ]
    return {"summary": report["summary"], "failed_runs": failures}


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(sys.argv[1:] if argv is None else argv))
    report = asyncio.run(run_benchmark(args.iterations))
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
        print(json.dumps(_console_report(report), ensure_ascii=False, indent=2))
    else:
        print(encoded, end="")
    return 0 if report["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
