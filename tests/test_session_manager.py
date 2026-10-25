"""Mic-free SessionManager tests (always stub audio)."""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ["VOICE_MCP_STUB"] = "1"

from voice_mcp.audio import build_audio_stack
from voice_mcp.config import load_settings
from voice_mcp.errors import VoiceError
from voice_mcp.session import SessionManager


@pytest.fixture
def sm() -> SessionManager:
    return SessionManager(build_audio_stack(load_settings(stub=True)))


@pytest.mark.asyncio
async def test_start_stop(sm: SessionManager) -> None:
    started = await sm.start(locale="ru-RU")
    assert started["state"] == "idle"
    assert started["session_id"].startswith("ses_")
    snap = sm.snapshot()
    assert snap["session_active"] is True
    stopped = await sm.stop(started["session_id"])
    assert stopped["state"] == "stopped"
    assert sm.snapshot()["session_active"] is False


@pytest.mark.asyncio
async def test_listen_speak_loop(sm: SessionManager) -> None:
    sid = (await sm.start())["session_id"]
    listened = await sm.listen(sid, timeout_ms=2000)
    assert listened["is_final"] is True
    assert listened["transcript"]
    assert listened["state"] == "think"
    spoken = await sm.speak(sid, text="Краткий ответ.", allow_barge_in=True)
    assert spoken["status"] in ("completed", "barged_in", "cancelled")
    await sm.stop(sid)


@pytest.mark.asyncio
async def test_double_start_errors(sm: SessionManager) -> None:
    await sm.start()
    with pytest.raises(VoiceError) as ei:
        await sm.start()
    assert ei.value.code == "already_active"
    sid = sm.snapshot()["session_id"]
    assert sid
    await sm.stop(sid)


@pytest.mark.asyncio
async def test_cancel_during_speak(sm: SessionManager) -> None:
    sid = (await sm.start())["session_id"]
    # Long-ish stub playback (~ proportional to payload)
    task = asyncio.create_task(
        sm.speak(sid, text=("слово " * 80).strip(), allow_barge_in=True)
    )
    await asyncio.sleep(0.05)
    cancelled = await sm.cancel(sid, reason="agent_stop")
    assert cancelled["cancelled_op"] in ("speak", "none", "listen")
    result = await task
    assert result["status"] in ("cancelled", "barged_in", "completed")
    await sm.stop(sid)


@pytest.mark.asyncio
async def test_unknown_session(sm: SessionManager) -> None:
    with pytest.raises(VoiceError) as ei:
        await sm.listen("ses_does_not_exist")
    assert ei.value.code in ("no_session", "unknown_session")


@pytest.mark.asyncio
async def test_health_via_server_tools() -> None:
    from mcp.server.fastmcp import FastMCP

    from voice_mcp.server import create_server

    server = create_server(load_settings(stub=True))
    assert isinstance(server, FastMCP)
    tools = await server.list_tools()
    names = {t.name for t in tools}
    assert "voice_health" in names
    assert "voice_listen" in names

    # Exercise health path through SessionManager snapshot (no devices)
    sm = server._voice_sessions  # type: ignore[attr-defined]
    snap = sm.snapshot()
    caps = sm.audio.capabilities()
    assert snap["session_active"] is False
    assert caps["stub"] is True
