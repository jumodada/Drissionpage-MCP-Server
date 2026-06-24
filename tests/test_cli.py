"""CLI entrypoint tests without starting a real MCP stdio server."""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

import drissionpage_mcp.cli as cli
from drissionpage_mcp import __version__


@pytest.mark.asyncio
async def test_main_async_prints_version(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        await cli.main_async(["--version"])

    assert exc_info.value.code == 0
    assert f"drissionpage-mcp {__version__}" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_main_async_doctor_success(monkeypatch, capsys) -> None:
    calls = []

    def fake_run_diagnostics(launch_browser: bool = False):
        calls.append(launch_browser)
        return {"ok": True, "checks": []}

    monkeypatch.setattr("drissionpage_mcp.doctor.run_diagnostics", fake_run_diagnostics)
    monkeypatch.setattr(
        "drissionpage_mcp.doctor.format_diagnostics",
        lambda report: f"doctor={report['ok']}",
    )

    await cli.main_async(["--log-level", "DEBUG", "doctor", "--launch-browser"])

    assert calls == [True]
    assert "doctor=True" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_main_async_doctor_failure_exits(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "drissionpage_mcp.doctor.run_diagnostics",
        lambda launch_browser=False: {"ok": False},
    )
    monkeypatch.setattr(
        "drissionpage_mcp.doctor.format_diagnostics", lambda report: "doctor failed"
    )

    with pytest.raises(SystemExit) as exc_info:
        await cli.main_async(["self-test"])

    assert exc_info.value.code == 1
    assert "doctor failed" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_main_async_runs_stdio_server_and_cleans_up(monkeypatch) -> None:
    events = []

    class FakeServer:
        async def run_server(self, read_stream, write_stream) -> None:
            events.append(("run", read_stream, write_stream))

        async def cleanup(self) -> None:
            events.append(("cleanup",))

    @asynccontextmanager
    async def fake_stdio_server():
        events.append(("stdio-enter",))
        yield "read", "write"
        events.append(("stdio-exit",))

    monkeypatch.setattr(cli, "DrissionPageMCPServer", FakeServer)
    monkeypatch.setattr(cli, "stdio_server", fake_stdio_server)

    await cli.main_async(["--log-level", "ERROR"])

    assert events == [
        ("stdio-enter",),
        ("run", "read", "write"),
        ("stdio-exit",),
        ("cleanup",),
    ]


@pytest.mark.asyncio
async def test_main_async_logs_keyboard_interrupt_and_cleans_up(monkeypatch) -> None:
    events = []

    class FakeServer:
        async def run_server(self, _read_stream, _write_stream) -> None:
            events.append(("run",))
            raise KeyboardInterrupt

        async def cleanup(self) -> None:
            events.append(("cleanup",))

    @asynccontextmanager
    async def fake_stdio_server():
        yield "read", "write"

    monkeypatch.setattr(cli, "DrissionPageMCPServer", FakeServer)
    monkeypatch.setattr(cli, "stdio_server", fake_stdio_server)

    await cli.main_async([])

    assert events == [("run",), ("cleanup",)]


def test_main_converts_keyboard_interrupt_to_zero_exit(monkeypatch) -> None:
    async def interrupted(_args=None) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "main_async", interrupted)

    with pytest.raises(SystemExit) as exc_info:
        cli.main([])

    assert exc_info.value.code == 0


def test_main_converts_unhandled_exception_to_error_exit(monkeypatch) -> None:
    async def failed(_args=None) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(cli, "main_async", failed)

    with pytest.raises(SystemExit) as exc_info:
        cli.main([])

    assert exc_info.value.code == 1
