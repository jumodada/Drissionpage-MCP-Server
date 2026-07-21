"""Deterministic fixture foundation for the 0.7 task-completion benchmark."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pytest

import tests.evals.task_completion_benchmark as benchmark
from tests.fixtures.http_fixture import (
    TASK_COMPLETION_DOWNLOAD,
    TASK_COMPLETION_DOWNLOAD_SHA256,
    TASK_COMPLETION_SCENARIOS,
    local_http_fixture,
)
from tests.evals.task_completion_benchmark import (
    SIDE_EFFECT_BASELINES,
    WORKLOAD_TOOL_REQUIREMENTS,
    WORKLOADS,
    _console_report,
    _browser_evidence_complete,
    _missing_required_tools,
    _side_effect_evidence,
    _summarize,
)


def test_eval_task_completion_catalog_covers_eight_workloads() -> None:
    """Keeps executable fixture routes separate from future tool orchestration."""

    assert {scenario.workload_id for scenario in TASK_COMPLETION_SCENARIOS} == {
        f"W{index:02d}" for index in range(1, 9)
    }
    assert set(WORKLOAD_TOOL_REQUIREMENTS) == {f"W{index:02d}" for index in range(1, 9)}
    assert set(WORKLOADS) == set(WORKLOAD_TOOL_REQUIREMENTS)
    assert len({scenario.route for scenario in TASK_COMPLETION_SCENARIOS}) == 9
    assert (
        len({scenario.terminal_selector for scenario in TASK_COMPLETION_SCENARIOS}) == 9
    )


def test_eval_task_completion_enforces_declared_public_tool_path() -> None:
    assert _missing_required_tools(
        "W04", ["page_navigate", "element_type", "element_click"]
    ) == ["element_upload_file"]
    assert (
        _missing_required_tools(
            "W04",
            [
                "page_navigate",
                "element_type",
                "element_upload_file",
                "element_click",
            ],
        )
        == []
    )


def test_eval_task_completion_requires_browser_version_evidence() -> None:
    assert (
        _browser_evidence_complete(
            [{"browser_product": "Chrome/150.0", "browser_revision": "@revision"}]
        )
        is True
    )
    assert _browser_evidence_complete([{"browser_product": ""}]) is False
    assert _browser_evidence_complete([]) is False


@pytest.mark.asyncio
async def test_eval_task_completion_restarts_server_after_workload_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[object] = []
    observed_servers: list[object] = []

    class FakeServer:
        def __init__(self) -> None:
            self.cleaned = False
            created.append(self)

        async def cleanup(self) -> None:
            self.cleaned = True

    async def failing_workload(client, *_args):
        observed_servers.append(client.server)
        raise benchmark.BenchmarkFailure("expected failure")

    async def succeeding_workload(client, *_args):
        observed_servers.append(client.server)
        return {"business_result": "ok"}

    monkeypatch.setattr(benchmark, "DrissionPageMCPServer", FakeServer)
    monkeypatch.setattr(
        benchmark,
        "WORKLOADS",
        {"W01": failing_workload, "W02": succeeding_workload},
    )
    monkeypatch.setattr(
        benchmark,
        "WORKLOAD_TOOL_REQUIREMENTS",
        {"W01": frozenset(), "W02": frozenset()},
    )
    monkeypatch.setattr(
        benchmark,
        "SIDE_EFFECT_BASELINES",
        {"W01": {}, "W02": {}},
    )
    monkeypatch.setattr(
        benchmark,
        "_runtime_evidence",
        lambda *_args, **_kwargs: {
            "browser_product": "Chrome/test",
            "browser_revision": "@test",
        },
    )

    report = await benchmark.run_benchmark(iterations=1)

    assert len(created) == 2
    assert observed_servers == created
    assert all(server.cleaned for server in created)
    assert report["runs"][0]["success"] is False
    assert report["runs"][1]["success"] is True


def test_eval_task_completion_summary_requires_nine_of_ten_without_duplicates() -> None:
    results = [
        {
            "workload_id": workload_id,
            "success": iteration != 10,
            "tool_call_count": 2,
            "duplicate_count": 0,
        }
        for workload_id in WORKLOADS
        for iteration in range(1, 11)
    ]

    summary = _summarize(results, 10)

    assert summary["passed"] is True
    assert summary["total_runs"] == 80
    assert all(item["success_rate"] == 0.9 for item in summary["workloads"].values())

    results[0]["duplicate_count"] = 1
    assert _summarize(results, 10)["passed"] is False


def test_eval_task_completion_counts_duplicate_side_effects_from_fixture_state() -> (
    None
):
    assert set(SIDE_EFFECT_BASELINES) == set(WORKLOADS)
    observed, duplicate_count = _side_effect_evidence(
        "W07",
        {"counters": {"download_requests": 3, "download_fail_requests": 2}},
    )

    assert observed == {"download_requests": 3, "download_fail_requests": 2}
    assert duplicate_count == 3


def test_eval_task_completion_console_report_includes_failed_run_evidence() -> None:
    failed_run = {
        "workload_id": "W04",
        "iteration": 3,
        "success": False,
        "error": "BenchmarkFailure: W04 submit failed",
        "failure_category": "workload_failure",
        "tool_calls": [
            "page_navigate",
            "element_type",
            "element_upload_file",
            "element_click",
        ],
        "side_effect_counts": {"upload_attempted_requests": 1},
        "duplicate_count": 0,
    }
    report = {"summary": {"passed": False}, "runs": [failed_run]}

    console = _console_report(report)

    assert console["summary"] == {"passed": False}
    assert console["failed_runs"] == [
        {key: value for key, value in failed_run.items() if key != "success"}
    ]


@pytest.mark.parametrize("scenario", TASK_COMPLETION_SCENARIOS)
def test_eval_task_completion_routes_expose_terminal_evidence(scenario: Any) -> None:
    with local_http_fixture() as base_url:
        status, body, _headers = _get(base_url + scenario.route)

    assert status == 200
    assert f"<title>Fixture {scenario.title}".lower() in body.decode().lower()
    assert f'id="{scenario.terminal_selector.removeprefix("#")}"' in body.decode()


def test_eval_task_completion_state_is_resettable_and_server_local() -> None:
    with local_http_fixture() as first_url:
        _get(first_url + "/task/download.csv")
        first_state = _get_json(first_url + "/__fixture__/state")
        assert first_state["counters"] == {"download_requests": 1}

        reset_state = _post_json(first_url + "/__fixture__/reset", b"")
        assert reset_state["counters"] == {}
        assert reset_state["events"] == []

    with local_http_fixture() as second_url:
        second_state = _get_json(second_url + "/__fixture__/state")
        assert second_state["counters"] == {}
        assert second_state["events"] == []


def test_eval_validation_tracks_attempted_and_accepted_submissions() -> None:
    with local_http_fixture() as base_url:
        invalid_status, invalid_body, _ = _post_form(
            base_url + "/task/form-validation", {"employee_code": "wrong"}
        )
        valid_status, valid_body, _ = _post_form(
            base_url + "/task/form-validation", {"employee_code": "DP-070"}
        )
        state = _get_json(base_url + "/__fixture__/state")

    assert invalid_status == 422
    assert b'id="validation-form"' in invalid_body
    assert b"Employee code must be DP-070" in invalid_body
    assert valid_status == 200
    assert b'id="validation-status"' in valid_body
    assert b"VALIDATED-0001" in valid_body
    assert b'value="2"' in valid_body
    assert state["counters"] == {
        "validation_accepted_requests": 1,
        "validation_attempted_requests": 2,
    }


def test_eval_upload_records_filename_without_file_content() -> None:
    boundary = "fixture-boundary-070"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="case_name"\r\n\r\n'
        "Quarterly notes\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="attachment"; '
        'filename="fixture-note.txt"\r\n'
        "Content-Type: text/plain\r\n\r\n"
        "synthetic attachment contents\r\n"
        f"--{boundary}--\r\n"
    ).encode()
    rejected_body = body.replace(
        b'filename="fixture-note.txt"', b'filename="wrong.txt"'
    )
    with local_http_fixture() as base_url:
        rejected_status, rejected_response, _ = _post(
            base_url + "/task/form-upload-submit",
            rejected_body,
            content_type=f"multipart/form-data; boundary={boundary}",
        )
        accepted_status, accepted_response, _ = _post(
            base_url + "/task/form-upload-submit",
            body,
            content_type=f"multipart/form-data; boundary={boundary}",
        )
        state = _get_json(base_url + "/__fixture__/state")

    assert rejected_status == 422
    assert b"fixture-note.txt is required" in rejected_response
    assert accepted_status == 200
    assert b"UPLOAD-0001" in accepted_response
    assert b"fixture-note.txt" in accepted_response
    assert state["counters"] == {
        "upload_accepted_requests": 1,
        "upload_attempted_requests": 2,
    }
    evidence = state["events"][0]["evidence"]
    assert evidence["fields"]["case_name"] == ["Quarterly notes"]
    assert evidence["filenames"] == {"attachment": "wrong.txt"}
    assert "synthetic attachment contents" not in json.dumps(state)


def test_eval_download_has_fixed_bytes_checksum_and_request_count() -> None:
    with local_http_fixture() as base_url:
        first_status, first_body, first_headers = _get(base_url + "/task/download.csv")
        second_status, second_body, second_headers = _get(
            base_url + "/task/download.csv"
        )
        state = _get_json(base_url + "/__fixture__/state")

    assert first_status == second_status == 200
    assert first_body == second_body == TASK_COMPLETION_DOWNLOAD
    assert sha256(first_body).hexdigest() == TASK_COMPLETION_DOWNLOAD_SHA256
    assert first_headers["X-Fixture-Download-Count"] == "1"
    assert second_headers["X-Fixture-Download-Count"] == "2"
    assert state["counters"] == {"download_requests": 2}
    assert state["download"] == {
        "filename": "fixture-report.csv",
        "size_bytes": len(TASK_COMPLETION_DOWNLOAD),
        "sha256": TASK_COMPLETION_DOWNLOAD_SHA256,
    }


def test_eval_download_failure_is_not_an_artifact_success() -> None:
    with local_http_fixture() as base_url:
        response = _get_json(base_url + "/task/download-fail")
        state = _get_json(base_url + "/__fixture__/state")

    assert response == {"ok": False, "status": "cancelled", "count": 1}
    assert state["counters"] == {"download_fail_requests": 1}
    assert all(event["counter"] != "download_requests" for event in state["events"])


def _get(url: str) -> tuple[int, bytes, dict[str, str]]:
    try:
        with urlopen(url, timeout=5) as response:
            return response.status, response.read(), dict(response.headers.items())
    except HTTPError as error:
        return error.code, error.read(), dict(error.headers.items())


def _get_json(url: str) -> dict[str, Any]:
    _status, body, _headers = _get(url)
    return json.loads(body)


def _post_form(url: str, fields: dict[str, str]) -> tuple[int, bytes, dict[str, str]]:
    return _post(
        url,
        urlencode(fields).encode(),
        content_type="application/x-www-form-urlencoded",
    )


def _post_json(
    url: str,
    body: bytes,
    *,
    content_type: str = "application/octet-stream",
) -> dict[str, Any]:
    _status, response_body, _headers = _post(url, body, content_type=content_type)
    return json.loads(response_body)


def _post(
    url: str,
    body: bytes,
    *,
    content_type: str,
) -> tuple[int, bytes, dict[str, str]]:
    request = Request(url, data=body, headers={"Content-Type": content_type})
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, response.read(), dict(response.headers.items())
    except HTTPError as error:
        return error.code, error.read(), dict(error.headers.items())
