"""Deterministic fixture foundation for the 0.7 task-completion benchmark."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pytest

from tests.fixtures.http_fixture import (
    TASK_COMPLETION_DOWNLOAD,
    TASK_COMPLETION_DOWNLOAD_SHA256,
    TASK_COMPLETION_SCENARIOS,
    local_http_fixture,
)


WORKLOAD_TOOL_REQUIREMENTS = {
    "W01": frozenset({"form_fill", "form_submit"}),
    "W02": frozenset({"form_fill", "form_submit"}),
    "W03": frozenset({"form_fill", "form_submit"}),
    "W04": frozenset({"element_upload_file", "form_fill", "form_submit"}),
    "W05": frozenset({"element_click", "page_dialog_respond"}),
    "W06": frozenset({"element_click", "tab_list", "tab_switch"}),
    "W07": frozenset({"element_click_and_download"}),
    "W08": frozenset({"element_click", "keyboard_press"}),
}


def test_eval_task_completion_catalog_covers_eight_workloads() -> None:
    """Keeps executable fixture routes separate from future tool orchestration."""

    assert {scenario.workload_id for scenario in TASK_COMPLETION_SCENARIOS} == {
        f"W{index:02d}" for index in range(1, 9)
    }
    assert set(WORKLOAD_TOOL_REQUIREMENTS) == {f"W{index:02d}" for index in range(1, 9)}
    assert len({scenario.route for scenario in TASK_COMPLETION_SCENARIOS}) == 9
    assert (
        len({scenario.terminal_selector for scenario in TASK_COMPLETION_SCENARIOS}) == 9
    )


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
