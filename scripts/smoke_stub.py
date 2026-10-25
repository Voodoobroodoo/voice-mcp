"""Smoke test: SessionManager + stub audio, plus FastMCP server import/list_tools.

Does not invent MCPServer APIs — exercises presence loop directly, then verifies
tools are registered on official FastMCP.
"""

from __future__ import annotations

import asyncio
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ["VOICE_MCP_STUB"] = "1"


async def main() -> None:
    # --- 1) core loop without MCP transport ---
    from voice_mcp.audio import build_audio_stack
    from voice_mcp.config import load_settings
    from voice_mcp.session import SessionManager

    settings = load_settings(stub=True)
    assert settings.stub is True
    audio = build_audio_stack(settings)
    assert audio.capabilities()["stub"] is True
    print("engines:", audio.capabilities()["engines"])

    sm = SessionManager(audio)
    started = await sm.start(locale="ru-RU", mode="open_mic")
    sid = started["session_id"]
    print("session_start →", started)

    listened = await sm.listen(sid, timeout_ms=2000)
    print("listen →", listened)
    assert listened["is_final"] is True
    assert listened["transcript"]

    spoken = await sm.speak(sid, text="Привет, это stub TTS.", allow_barge_in=True)
    print("speak →", spoken)
    assert spoken["status"] in ("completed", "barged_in", "cancelled")

    stopped = await sm.stop(sid)
    print("session_stop →", stopped)
    assert stopped["state"] == "stopped"

    # --- 2) official FastMCP server import + tool registration ---
    from mcp.server.fastmcp import FastMCP

    from voice_mcp.server import create_server

    server = create_server(load_settings(stub=True))
    assert isinstance(server, FastMCP)
    tools = await server.list_tools()
    names = sorted(t.name for t in tools)
    print("mcp tools:", names)
    assert names == [
        "voice_cancel",
        "voice_health",
        "voice_listen",
        "voice_session_start",
        "voice_session_stop",
        "voice_speak",
    ]
    print("SMOKE OK")


if __name__ == "__main__":
    asyncio.run(main())
