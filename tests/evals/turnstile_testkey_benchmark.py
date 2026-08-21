"""Opt-in benchmark for Cloudflare's official Turnstile dummy sitekeys."""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import sys
from datetime import datetime, timezone
from math import ceil
from pathlib import Path
from time import monotonic
from typing import Any
from urllib.parse import urlencode

from drissionpage_mcp import __version__
from drissionpage_mcp.compat import DRISSIONPAGE_VERSION
from drissionpage_mcp.server import DrissionPageMCPServer
from tests.evals.task_completion_benchmark import BenchmarkClient, _runtime_evidence
from tests.fixtures.http_fixture import local_http_fixture

TEST_KEYS: dict[str, dict[str, str | bool]] = {
    "visible_pass": {
        "sitekey": "1x00000000000000000000AA",
        "size": "normal",
        "expected": "passed",
        "click_if_pending": True,
    },
    "visible_fail": {
        "sitekey": "2x00000000000000000000AB",
        "size": "normal",
        "expected": "failed",
        "click_if_pending": True,
    },
    "invisible_pass": {
        "sitekey": "1x00000000000000000000BB",
        "size": "invisible",
        "expected": "passed",
        "click_if_pending": False,
    },
    "invisible_fail": {
        "sitekey": "2x00000000000000000000BB",
        "size": "invisible",
        "expected": "failed",
        "click_if_pending": False,
    },
    "forced_interactive": {
        "sitekey": "3x00000000000000000000FF",
        "size": "normal",
        "expected": "passed",
        "click_if_pending": True,
    },
}


class TestKeyBenchmarkFailure(AssertionError):
    """One official test-key scenario missed its documented postcondition."""


async def run_benchmark(iterations: int = 10) -> dict[str, Any]:
    """Run official dummy keys; caller explicitly accepts external network use."""

    if iterations < 1:
        raise ValueError("iterations must be at least 1")
    started_at = datetime.now(timezone.utc)
    runs: list[dict[str, Any]] = []
    runtimes: list[dict[str, Any]] = []
    for iteration in range(1, iterations + 1):
        server = DrissionPageMCPServer()
        try:
            with local_http_fixture() as base_url:
                for scenario, contract in TEST_KEYS.items():
                    client = BenchmarkClient(server)
                    started = monotonic()
                    try:
                        evidence = await _run_key(client, base_url, scenario, contract)
                        success = True
                        error = ""
                        failure_category = ""
                    except Exception as exc:
                        evidence = {}
                        success = False
                        error = f"{type(exc).__name__}: {exc}"[:500]
                        failure_category = _failure_category(error)
                    runs.append(
                        {
                            "scenario": scenario,
                            "iteration": iteration,
                            "success": success,
                            "duration_ms": round((monotonic() - started) * 1000),
                            "tool_calls": list(client.calls),
                            "tool_call_count": len(client.calls),
                            "action_count": int(evidence.get("action_count", 0)),
                            "first_geometry_error_px": evidence.get(
                                "first_geometry_error_px"
                            ),
                            "postcondition": evidence.get("postcondition", ""),
                            "token_present": bool(evidence.get("token_present", False)),
                            "interactive_seen": bool(
                                evidence.get("interactive_seen", False)
                            ),
                            "error": error,
                            "failure_category": failure_category,
                        }
                    )
            runtimes.append(_runtime_evidence(server, iteration))
        finally:
            await server.cleanup()
    summary = _summarize(runs, iterations)
    summary["browser_evidence_complete"] = bool(runtimes) and all(
        item.get("browser_product") and item.get("browser_revision")
        for item in runtimes
    )
    summary["passed"] = bool(summary["passed"]) and bool(
        summary["browser_evidence_complete"]
    )
    return {
        "schema_version": "1",
        "release": __version__,
        "source": "https://developers.cloudflare.com/turnstile/troubleshooting/testing/",
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "iterations": iterations,
        "required_successes_per_scenario": ceil(iterations * 0.9),
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "drissionpage": DRISSIONPAGE_VERSION,
            "runtimes": runtimes,
        },
        "summary": summary,
        "runs": runs,
    }


async def _run_key(
    client: BenchmarkClient,
    base_url: str,
    scenario: str,
    contract: dict[str, str | bool],
) -> dict[str, Any]:
    query = urlencode(
        {"sitekey": str(contract["sitekey"]), "size": str(contract["size"])}
    )
    await client.call("page_navigate", {"url": base_url + "/turnstile-test?" + query})
    await client.call("page_resize", {"width": 900, "height": 700})
    await client.call(
        "wait_until",
        {
            "condition": "text_matches",
            "selector": "#turnstile-status",
            "value": "^(pending|interactive|passed|failed)$",
            "timeout": 15,
        },
    )
    evidence = await _read_evidence(client)
    action_count = 0
    geometry_error: float | None = None
    if evidence["status"] not in {"passed", "failed"} and bool(
        contract["click_if_pending"]
    ):
        await client.call(
            "wait_for_element",
            {
                "selector": "iframe[src*='challenges.cloudflare.com']",
                "timeout": 15,
            },
        )
        state = await client.call(
            "element_state_get",
            {
                "selector": "iframe[src*='challenges.cloudflare.com']",
                "timeout": 3,
            },
        )
        location = state["data"]["rect"]["viewport_location"]
        await client.call(
            "page_click_xy",
            {
                "x": location["x"] + 32,
                "y": location["y"] + 32,
                "element": "official Turnstile test widget",
            },
        )
        action_count = 1
    await client.call(
        "wait_until",
        {
            "condition": "text_contains",
            "selector": "#turnstile-status",
            "value": str(contract["expected"]),
            "timeout": 15,
        },
    )
    final = await _read_evidence(client)
    expected = str(contract["expected"])
    if final["status"] != expected:
        raise TestKeyBenchmarkFailure(
            f"expected {expected}, observed {final['status']}"
        )
    token_present = int(final["tokenLength"]) > 0
    if expected == "passed" and not token_present:
        raise TestKeyBenchmarkFailure("pass callback did not expose token presence")
    if expected == "failed" and token_present:
        raise TestKeyBenchmarkFailure("failed key unexpectedly exposed a token")
    if scenario == "forced_interactive" and not bool(final["interactiveSeen"]):
        raise TestKeyBenchmarkFailure("forced key did not enter interactive phase")
    await client.call("page_screenshot")
    return {
        "action_count": action_count,
        "first_geometry_error_px": (
            None if geometry_error is None else round(geometry_error, 3)
        ),
        "postcondition": final["status"],
        "token_present": token_present,
        "interactive_seen": bool(final["interactiveSeen"]),
    }


async def _read_evidence(client: BenchmarkClient) -> dict[str, Any]:
    result = await client.call(
        "page_evaluate",
        {
            "script": (
                "const e=window.__turnstileEvidence||{}; return {"
                "status:String(e.status||''),tokenLength:Number(e.tokenLength||0),"
                "interactiveSeen:Boolean(e.interactiveSeen),"
                "interactiveExited:Boolean(e.interactiveExited),"
                "errorPresent:Boolean(e.errorCode)};"
            )
        },
    )
    return dict(result["data"]["result"])


def _summarize(runs: list[dict[str, Any]], iterations: int) -> dict[str, Any]:
    required = ceil(iterations * 0.9)
    scenarios: dict[str, dict[str, Any]] = {}
    for scenario in TEST_KEYS:
        selected = [item for item in runs if item["scenario"] == scenario]
        successes = sum(bool(item["success"]) for item in selected)
        scenarios[scenario] = {
            "successes": successes,
            "runs": len(selected),
            "success_rate": round(successes / len(selected), 3) if selected else 0.0,
            "passed": successes >= required,
            "action_count": sum(int(item["action_count"]) for item in selected),
        }
    return {
        "passed": all(item["passed"] for item in scenarios.values()),
        "total_runs": len(runs),
        "successful_runs": sum(bool(item["success"]) for item in runs),
        "scenarios": scenarios,
    }


def _failure_category(error: str) -> str:
    lowered = error.lower()
    if "geometry" in lowered:
        return "geometry_mismatch"
    if "timeout" in lowered or "condition" in lowered:
        return "external_timeout"
    if "token" in lowered or "callback" in lowered:
        return "postcondition_failed"
    return "external_service_failure"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--allow-external",
        action="store_true",
        help="Acknowledge that the benchmark loads Cloudflare's official test script.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(sys.argv[1:] if argv is None else argv))
    if not args.allow_external:
        print("--allow-external is required", file=sys.stderr)
        return 2
    report = asyncio.run(run_benchmark(args.iterations))
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
        print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    else:
        print(encoded, end="")
    return 0 if report["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
