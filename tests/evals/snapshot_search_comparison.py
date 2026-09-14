"""Compare 0.8.8 full snapshots with candidate snapshot search over real stdio."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import platform
import subprocess
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from math import ceil
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

BASELINE_COMMIT = "30e8adf"
FIXTURE_ID = "snapshot-search-comparison-v1"
WORKLOADS = {
    "long_document": {
        "path": "/long-document",
        "query": "ORBITAL-NEEDLE-017",
        "expected": ("ORBITAL-NEEDLE-017",),
    },
    "repeated_cards": {
        "path": "/repeated-cards",
        "query": "MATCHING-SKU",
        "expected": tuple(f"MATCHING-SKU-{index:02d}" for index in range(1, 9)),
    },
}


def _fixture_html() -> dict[str, str]:
    paragraphs = "\n".join(
        f"<p>Section {index:03d}: deterministic reference text "
        f"{'x' * 90}{' ORBITAL-NEEDLE-017' if index == 57 else ''}</p>"
        for index in range(1, 101)
    )
    cards = "\n".join(
        "<article class='product-card'>"
        f"<h2>Inventory item {index:03d}</h2>"
        f"<p>{f'MATCHING-SKU-{index:02d}' if 1 <= index <= 8 else 'ordinary stock'} "
        f"{'y' * 45}</p><button>Inspect item {index:03d}</button></article>"
        for index in range(1, 81)
    )
    return {
        "/long-document": (
            "<!doctype html><html><head><title>Long document fixture</title></head>"
            f"<body><main><h1>Reference manual</h1>{paragraphs}</main></body></html>"
        ),
        "/repeated-cards": (
            "<!doctype html><html><head><title>Repeated cards fixture</title></head>"
            f"<body><main><h1>Inventory</h1>{cards}</main></body></html>"
        ),
    }


FIXTURE_PAGES = _fixture_html()


class _FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        page = FIXTURE_PAGES.get(self.path)
        if page is None:
            self.send_error(404)
            return
        content = page.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def local_fixture() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _strict_json_chars(value: Any) -> int:
    return len(
        json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    )


def _model_visible_chars(result: Any) -> int:
    structured = dict(result.structuredContent or {})
    text_chars = sum(
        len(item.text)
        for item in (result.content or [])
        if getattr(item, "type", None) == "text"
    )
    return _strict_json_chars(structured) + text_chars


def _tool_data(result: Any, tool_name: str) -> dict[str, Any]:
    payload = dict(result.structuredContent or {})
    if result.isError or payload.get("ok") is not True:
        raise AssertionError(f"{tool_name} failed: {payload}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise AssertionError(f"{tool_name} returned no structured data")
    return data


def _matched_values(data: dict[str, Any], expected: tuple[str, ...]) -> list[str]:
    searchable = (
        " ".join(str(item.get("text", "")) for item in data.get("matches", []))
        if "matches" in data
        else str(data.get("text_excerpt", ""))
    )
    return [value for value in expected if value in searchable]


async def _run_workload(
    session: ClientSession,
    base_url: str,
    workload_id: str,
    *,
    candidate: bool,
) -> dict[str, Any]:
    definition = WORKLOADS[workload_id]
    calls = 0
    chars = 0
    try:
        navigate = await session.call_tool(
            "page_navigate", {"url": base_url + str(definition["path"])}
        )
        calls += 1
        chars += _model_visible_chars(navigate)
        _tool_data(navigate, "page_navigate")

        arguments: dict[str, Any] = {"max_elements": 200, "max_text_chars": 20000}
        if candidate:
            arguments["query"] = definition["query"]
        snapshot = await session.call_tool("page_snapshot", arguments)
        calls += 1
        chars += _model_visible_chars(snapshot)
        data = _tool_data(snapshot, "page_snapshot")
        expected = definition["expected"]
        matched = _matched_values(data, expected)
        success = matched == list(expected)
        error = "" if success else f"expected {list(expected)!r}, observed {matched!r}"
    except Exception as exc:
        success = False
        error = f"{type(exc).__name__}: {exc}"[:500]
        matched = []
    return {
        "workload_id": workload_id,
        "success": success,
        "tool_call_count": calls,
        "model_visible_chars": chars,
        "matched_values": matched,
        "error": error,
    }


def _artifact_environment(python: Path, artifact: Path) -> dict[str, str]:
    script = """
import json, platform
from importlib.metadata import version
print(json.dumps({
    "python": platform.python_version(),
    "mcp_sdk": version("mcp"),
    "drissionpage": version("DrissionPage"),
}))
"""
    completed = subprocess.run(
        [str(python), "-c", script],
        check=True,
        capture_output=True,
        cwd=tempfile.gettempdir(),
        text=True,
    )
    environment = json.loads(completed.stdout)
    environment["artifact_sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
    return environment


async def _run_artifact(
    label: str,
    python: Path,
    artifact: Path,
    base_url: str,
    iterations: int,
) -> dict[str, Any]:
    environment = _artifact_environment(python, artifact)
    runs: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix=f"snapshot-{label}-") as temp_dir:
        child_env = os.environ.copy()
        child_env.pop("DP_USER_DATA_PATH", None)
        params = StdioServerParameters(
            command=str(python),
            args=["-m", "drissionpage_mcp.cli", "--log-level", "ERROR"],
            env=child_env,
            cwd=temp_dir,
        )
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                initialized = await session.initialize()
                environment["server_version"] = initialized.serverInfo.version
                environment["package"] = initialized.serverInfo.version
                probe = await session.call_tool(
                    "page_navigate", {"url": base_url + "/long-document"}
                )
                _tool_data(probe, "page_navigate")
                browser = await session.call_tool(
                    "page_evaluate",
                    {"script": "return navigator.userAgent", "max_chars": 1000},
                )
                environment["chrome"] = str(
                    _tool_data(browser, "page_evaluate").get("result", "")
                )
                for iteration in range(1, iterations + 1):
                    for workload_id in WORKLOADS:
                        run = await _run_workload(
                            session,
                            base_url,
                            workload_id,
                            candidate=label == "candidate",
                        )
                        run["iteration"] = iteration
                        runs.append(run)
                with suppress(Exception):
                    await session.call_tool("page_close", {})
    return {"environment": environment, "runs": runs}


def _nearest_rank(values: list[int], percentile: int) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[ceil(percentile / 100 * len(ordered)) - 1]


def _summarize(runs: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for workload_id in WORKLOADS:
        selected = [run for run in runs if run["workload_id"] == workload_id]
        summary[workload_id] = {
            "successes": sum(bool(run["success"]) for run in selected),
            "runs": len(selected),
            "completion_rate": round(
                sum(bool(run["success"]) for run in selected) / len(selected), 3
            )
            if selected
            else 0.0,
            "tool_call_count_p50": _nearest_rank(
                [int(run["tool_call_count"]) for run in selected], 50
            ),
            "tool_call_count_max": max(
                (int(run["tool_call_count"]) for run in selected), default=0
            ),
            "model_visible_chars_p50": _nearest_rank(
                [int(run["model_visible_chars"]) for run in selected], 50
            ),
            "model_visible_chars_p95": _nearest_rank(
                [int(run["model_visible_chars"]) for run in selected], 95
            ),
        }
    return summary


def _compare(
    baseline: dict[str, Any], candidate: dict[str, Any], iterations: int
) -> dict[str, Any]:
    comparisons: dict[str, Any] = {}
    passed = True
    for workload_id in WORKLOADS:
        old = baseline[workload_id]
        new = candidate[workload_id]
        reduction = (
            1 - new["model_visible_chars_p50"] / old["model_visible_chars_p50"]
            if old["model_visible_chars_p50"]
            else 0.0
        )
        item_passed = (
            old["successes"] == iterations
            and new["successes"] == iterations
            and new["tool_call_count_max"] <= old["tool_call_count_max"]
            and reduction >= 0.30
        )
        comparisons[workload_id] = {
            "passed": item_passed,
            "p50_char_reduction": round(reduction, 4),
        }
        passed = passed and item_passed
    return {"passed": passed, "workloads": comparisons}


async def run_comparison(
    baseline_python: Path,
    baseline_artifact: Path,
    candidate_python: Path,
    candidate_artifact: Path,
    iterations: int = 20,
) -> dict[str, Any]:
    if iterations < 1:
        raise ValueError("iterations must be at least 1")
    with local_fixture() as base_url:
        baseline = await _run_artifact(
            "baseline", baseline_python, baseline_artifact, base_url, iterations
        )
        candidate = await _run_artifact(
            "candidate", candidate_python, candidate_artifact, base_url, iterations
        )
    baseline_summary = _summarize(baseline["runs"])
    candidate_summary = _summarize(candidate["runs"])
    environments_match = all(
        baseline["environment"][key] == candidate["environment"][key]
        for key in ("python", "mcp_sdk", "drissionpage", "chrome")
    )
    comparison = _compare(baseline_summary, candidate_summary, iterations)
    comparison["environments_match"] = environments_match
    comparison["passed"] = comparison["passed"] and environments_match
    return {
        "schema_version": "1",
        "baseline_commit": BASELINE_COMMIT,
        "fixture_id": FIXTURE_ID,
        "iterations": iterations,
        "host_python": platform.python_version(),
        "percentile_method": "nearest-rank",
        "baseline": {**baseline, "summary": baseline_summary},
        "candidate": {**candidate, "summary": candidate_summary},
        "comparison": comparison,
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-python", type=Path, required=True)
    parser.add_argument("--baseline-artifact", type=Path, required=True)
    parser.add_argument("--candidate-python", type=Path, required=True)
    parser.add_argument("--candidate-artifact", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=20)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    report = asyncio.run(
        run_comparison(
            args.baseline_python,
            args.baseline_artifact,
            args.candidate_python,
            args.candidate_artifact,
            args.iterations,
        )
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["comparison"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
