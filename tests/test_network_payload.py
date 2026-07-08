"""Focused coverage for network packet payload normalization."""

from __future__ import annotations

import base64
from types import SimpleNamespace

from drissionpage_mcp.network_payload import (
    _bounded_body,
    _network_packet_payload,
    _redact_network_headers,
    _safe_int_or_none,
    _safe_packet_attr,
)


class BadHeaders:
    def __iter__(self):
        raise RuntimeError("bad headers")


class RaisingAttr:
    @property
    def headers(self):
        raise RuntimeError("headers unavailable")

    @property
    def status(self):
        raise RuntimeError("status unavailable")


class RaisingPacket:
    @property
    def request(self):
        raise RuntimeError("request unavailable")

    @property
    def response(self):
        raise RuntimeError("response unavailable")

    @property
    def url(self):
        raise RuntimeError("url unavailable")


class FailedPacket(SimpleNamespace):
    is_failed = True


def test_redact_network_headers_covers_sensitive_markers_and_bad_headers() -> None:
    redacted = _redact_network_headers(
        {
            "Authorization": "bearer secret",
            "Cookie": "sid=1",
            "Set-Cookie": "sid=2",
            "X-Api-Key": "key",
            "X-Token": "token",
            "Client-Secret": "secret",
            "Content-Type": "application/json",
            "X-Empty": None,
        }
    )

    assert redacted == {
        "Authorization": "<redacted>",
        "Cookie": "<redacted>",
        "Set-Cookie": "<redacted>",
        "X-Api-Key": "<redacted>",
        "X-Token": "<redacted>",
        "Client-Secret": "<redacted>",
        "Content-Type": "application/json",
        "X-Empty": "",
    }
    assert _redact_network_headers(BadHeaders()) == {}


def test_bounded_body_handles_empty_binary_json_text_and_zero_limits() -> None:
    assert _bounded_body(None, 10) == ("", False, "none")
    assert _bounded_body(False, 10) == ("", False, "none")
    assert _bounded_body(b"abc", 20) == (base64.b64encode(b"abc").decode(), False, "bytes_base64")
    assert _bounded_body(bytearray(b"abcdef"), 4) == ("YWJj", True, "bytes_base64")
    assert _bounded_body({"b": 2, "a": 1}, 100) == ('{"a": 1, "b": 2}', False, "json")
    assert _bounded_body([1, "二"], 100) == ('[1, "二"]', False, "json")
    assert _bounded_body(("x", "y"), 100) == ('["x", "y"]', False, "json")
    assert _bounded_body("abcdef", 3) == ("abc", True, "text")
    assert _bounded_body("abcdef", 0) == ("", True, "text")
    assert _bounded_body("abcdef", -5) == ("", True, "text")


def test_network_packet_payload_include_flags_and_failed_packet() -> None:
    packet = FailedPacket(
        url="https://example.test/api",
        method="POST",
        resourceType="XHR",
        request=SimpleNamespace(headers={"Authorization": "secret"}, postData={"q": "abc"}),
        response=SimpleNamespace(
            status="201",
            mimeType="application/json",
            headers={"Content-Type": "application/json"},
            body={"ok": True, "token": "still body"},
        ),
        fail_info=SimpleNamespace(errorText="net::ERR_FAILED"),
    )

    minimal = _network_packet_payload(
        packet,
        index=2,
        include_headers=False,
        include_body=False,
        max_body_chars=8,
    )
    assert "request_headers" not in minimal
    assert "body_excerpt" not in minimal
    assert minimal["failed"] is True
    assert minimal["fail_error"] == "net::ERR_FAILED"

    full = _network_packet_payload(
        packet,
        index=2,
        include_headers=True,
        include_body=True,
        max_body_chars=8,
    )
    assert full["request_headers"] == {"Authorization": "<redacted>"}
    assert full["response_headers"] == {"Content-Type": "application/json"}
    assert full["body_excerpt"] == '{"ok": t'
    assert full["body_truncated"] is True
    assert full["body_type"] == "json"
    assert full["request_body_excerpt"] == '{"q": "a'
    assert full["request_body_truncated"] is True
    assert full["request_body_type"] == "json"


def test_safe_packet_attr_and_packet_payload_tolerate_raising_attrs() -> None:
    assert _safe_packet_attr(RaisingAttr(), "headers", {}) == {}
    assert _safe_int_or_none("200") == 200
    assert _safe_int_or_none("bad") is None

    payload = _network_packet_payload(
        RaisingPacket(),
        index=0,
        include_headers=True,
        include_body=True,
        max_body_chars=10,
    )

    assert payload == {
        "index": 0,
        "url": "",
        "method": "",
        "resource_type": "",
        "status": None,
        "mime_type": "",
        "failed": False,
        "fail_error": "",
        "request_headers": {},
        "response_headers": {},
        "body_excerpt": "",
        "body_truncated": False,
        "body_type": "none",
        "request_body_excerpt": "",
        "request_body_truncated": False,
        "request_body_type": "none",
    }
