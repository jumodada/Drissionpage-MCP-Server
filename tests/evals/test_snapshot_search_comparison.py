"""Deterministic tests for the packaged snapshot-search comparison benchmark."""

from types import SimpleNamespace

import pytest

from tests.evals.snapshot_search_comparison import (
    FIXTURE_ID,
    WORKLOADS,
    _compare,
    _model_visible_chars,
    _run_workload,
    _summarize,
)


def _result(data):
    payload = {"ok": True, "message": "done", "data": data}
    return SimpleNamespace(
        structuredContent=payload,
        content=[SimpleNamespace(type="text", text="mirror")],
        isError=False,
    )


def test_model_visible_chars_counts_strict_structured_json_and_text_mirror() -> None:
    result = _result({"text": "上海"})

    assert _model_visible_chars(result) == len(
        '{"ok":true,"message":"done","data":{"text":"上海"}}mirror'
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("candidate", [False, True])
async def test_workloads_use_two_calls_and_require_complete_results(candidate) -> None:
    definition = WORKLOADS["long_document"]
    snapshot_data = (
        {"matches": [{"text": definition["expected"][0]}]}
        if candidate
        else {"text_excerpt": definition["expected"][0]}
    )

    class Session:
        def __init__(self):
            self.calls = []

        async def call_tool(self, name, arguments):
            self.calls.append((name, arguments))
            return _result(
                {"tab_id": "tab-1"} if name == "page_navigate" else snapshot_data
            )

    session = Session()
    run = await _run_workload(
        session, "http://fixture", "long_document", candidate=candidate
    )

    assert run["success"] is True
    assert run["tool_call_count"] == 2
    assert [call[0] for call in session.calls] == ["page_navigate", "page_snapshot"]
    assert ("query" in session.calls[1][1]) is candidate


def test_comparison_requires_twenty_successes_no_extra_calls_and_30_percent() -> None:
    runs = []
    for workload_id in WORKLOADS:
        for iteration in range(1, 21):
            runs.append(
                {
                    "workload_id": workload_id,
                    "success": True,
                    "tool_call_count": 2,
                    "model_visible_chars": 1000 + iteration,
                }
            )
    baseline = _summarize(runs)
    candidate_runs = [{**run, "model_visible_chars": 700} for run in runs]
    candidate = _summarize(candidate_runs)

    comparison = _compare(baseline, candidate, 20)

    assert comparison["passed"] is True
    assert all(
        item["p50_char_reduction"] >= 0.30 for item in comparison["workloads"].values()
    )

    candidate_runs[0]["success"] = False
    assert _compare(baseline, _summarize(candidate_runs), 20)["passed"] is False
    candidate_runs[0]["success"] = True
    candidate_runs[0]["tool_call_count"] = 3
    assert _compare(baseline, _summarize(candidate_runs), 20)["passed"] is False
    assert FIXTURE_ID == "snapshot-search-comparison-v1"
