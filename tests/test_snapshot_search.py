"""Bounded immutable snapshot search, cursor isolation, and public contracts."""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from drissionpage_mcp.snapshot import SnapshotStore
from drissionpage_mcp.tools.common import PageSnapshotInput, page_snapshot


def capture(*texts):
    return {
        "url": "https://example.test/list?token=private",
        "title": "Products",
        "document_id": "document-a",
        "candidates": [
            {"text": text, "selector": f"#item-{i}", "tag": "p", "category": "text"}
            for i, text in enumerate(texts)
        ],
        "scanned_nodes": len(texts),
        "scanned_chars": sum(map(len, texts)),
        "scan_truncated": False,
    }


def search(store, payload=None, *, tab="tab-1", document="document-a", **options):
    return store.search(
        tab_id=tab,
        document_id=document,
        query=options.pop("query", "needle"),
        max_elements=options.pop("max_elements", 1),
        max_text_chars=options.pop("max_text_chars", 120),
        capture=payload,
        **options,
    )


def test_pages_are_immutable_replayable_and_do_not_repeat_matches():
    store = SnapshotStore()
    original = capture("Needle first", "needle second", "needle third")
    first = search(store, original)
    original["candidates"][1]["text"] = "changed"
    assert first["match_count"] == 3
    assert first["has_more"] is True
    second = search(store, cursor=first["next_cursor"])
    assert second == search(store, cursor=first["next_cursor"])
    assert second["matches"][0]["text"] == "needle second"
    second["matches"][0]["text"] = "caller mutated"
    assert (
        search(store, cursor=first["next_cursor"])["matches"][0]["text"]
        == "needle second"
    )
    third = search(store, cursor=second["next_cursor"])
    assert [page["matches"][0]["index"] for page in (first, second, third)] == [0, 1, 2]
    assert third["has_more"] is False
    assert third["next_cursor"] is None


@pytest.mark.parametrize(
    "override",
    [
        {"tab": "tab-2"},
        {"document": "document-b"},
        {"query": "other"},
        {"max_elements": 2},
        {"max_text_chars": 121},
    ],
)
def test_cursor_is_bound_to_original_tab_document_and_options(override):
    store = SnapshotStore()
    first = search(store, capture("needle first", "needle second"))
    with pytest.raises(ValueError, match="snapshot cursor"):
        search(store, cursor=first["next_cursor"], **override)


def test_cursor_rejects_tampering_and_another_server():
    store = SnapshotStore()
    first = search(store, capture("needle first", "needle second"))
    cursor = first["next_cursor"]
    for invalid in ("garbage", cursor[:-1] + ("a" if cursor[-1] != "a" else "b")):
        with pytest.raises(ValueError, match="snapshot cursor"):
            search(store, cursor=invalid)
    with pytest.raises(ValueError, match="snapshot cursor"):
        search(SnapshotStore(), cursor=cursor)


def test_expiration_and_tab_clear_remove_saved_pages():
    now = [0.0]
    store = SnapshotStore(clock=lambda: now[0], ttl=2)
    first = search(store, capture("needle first", "needle second"))
    now[0] = 2
    with pytest.raises(ValueError, match="snapshot cursor"):
        search(store, cursor=first["next_cursor"])
    assert store.size_bytes == 0
    fresh = search(store, capture("needle first", "needle second"))
    store.clear_tab("tab-1")
    with pytest.raises(ValueError, match="snapshot cursor"):
        search(store, cursor=fresh["next_cursor"])


def test_quotas_evict_oldest_without_cross_tab_replay():
    store = SnapshotStore(max_entries_per_tab=1, max_bytes=4000, max_bytes_per_tab=2000)
    first = search(store, capture("needle first", "needle second"))
    second = search(store, capture("needle third", "needle fourth"))
    with pytest.raises(ValueError, match="snapshot cursor"):
        search(store, cursor=first["next_cursor"])
    assert (
        search(store, cursor=second["next_cursor"])["matches"][0]["text"]
        == "needle fourth"
    )
    assert store.size_bytes <= 2000
    for i in range(20):
        search(store, capture("needle " + "x" * 150, "needle other"), tab=f"tab-{i}")
    assert store.size_bytes <= 4000
    store.clear()
    assert store.size_bytes == 0


def test_global_entry_quota_evicts_small_cross_tab_snapshots():
    store = SnapshotStore(max_entries=2, max_entries_per_tab=2)
    first = search(store, capture("needle first", "needle second"), tab="tab-1")
    second = search(store, capture("needle third", "needle fourth"), tab="tab-2")
    search(store, capture("needle fifth", "needle sixth"), tab="tab-3")

    with pytest.raises(ValueError, match="snapshot cursor"):
        search(store, cursor=first["next_cursor"], tab="tab-1")
    assert search(store, cursor=second["next_cursor"], tab="tab-2")["returned"] == 1


def test_redaction_happens_before_snippets_and_cache_storage():
    store = SnapshotStore()
    payload = capture(
        "password=needle-secret",
        "needle token=" + "x" * 200,
        "needle /Users/private/person/account.json",
        "needle ordinary",
    )
    result = search(store, payload, max_elements=10)
    assert result["match_count"] == 3
    encoded = str(result) + repr(store._entries)
    for secret in ("needle-secret", "x" * 20, "/Users/private", "token=private"):
        assert secret not in encoded
    assert "<redacted>" in encoded


def test_literal_unicode_search_counts_matches_and_reports_scan_limits():
    store = SnapshotStore()
    payload = capture("中文针 文本", "prefix .* suffix", "nothing")
    payload["scan_truncated"] = True
    result = search(store, payload, query=".*", max_elements=10)
    assert result["match_count"] == 1
    assert result["matches"][0]["text"] == "prefix .* suffix"
    assert result["scan"]["truncated"] is True
    assert search(store, payload, query="中文针")["match_count"] == 1
    empty = search(store, payload, query="not present")
    assert empty["matches"] == []
    assert empty["has_more"] is False


@pytest.mark.parametrize(
    "kwargs",
    [
        {"query": ""},
        {"query": " "},
        {"query": "x" * 257},
        {"cursor": "orphan"},
        {"query": "text", "include_html": True},
        {"query": "text", "max_text_chars": 0},
    ],
)
def test_invalid_query_inputs_fail_before_browser_work(kwargs):
    with pytest.raises(ValidationError):
        PageSnapshotInput(**kwargs)


@pytest.mark.asyncio
async def test_query_result_validates_through_public_tool_and_redacts_mirrors():
    store = SnapshotStore()

    async def snapshot(**kwargs):
        return search(store, capture("needle one", "needle two"), **kwargs)

    context = SimpleNamespace(
        current_tab_or_die=lambda: SimpleNamespace(
            observation=SimpleNamespace(search_snapshot=snapshot)
        )
    )
    outcome = await page_snapshot.execute(
        context, PageSnapshotInput(query="needle", max_elements=1, max_text_chars=120)
    )
    result = outcome.structured_content()
    assert result["ok"], result
    assert result["data"]["has_more"] is True
    assert "token=private" not in str(outcome.content())
