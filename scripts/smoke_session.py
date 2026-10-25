"""Mic-free session smoke (no pytest required). Always uses stub audio."""

from __future__ import annotations

import asyncio
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ["VOICE_MCP_STUB"] = "1"

from voice_mcp.audio import build_audio_stack
from voice_mcp.config import load_settings
from voice_mcp.errors import VoiceError
from voice_mcp.session import SessionManager


async def main() -> None:
    sm = SessionManager(build_audio_stack(load_settings(stub=True)))

    started = await sm.start(locale="ru-RU")
    sid = started["session_id"]
    print("start", started)

    try:
        await sm.start()
        raise AssertionError("expected already_active")
    except VoiceError as e:
        assert e.code == "already_active"
        print("double_start", e.code)

    listened = await sm.listen(sid, timeout_ms=2000)
    print("listen", listened["transcript"], listened["state"])

    task = asyncio.create_task(sm.speak(sid, text=("тест " * 40).strip()))
    await asyncio.sleep(0.05)
    cancel = await sm.cancel(sid, reason="agent_stop")
    spoken = await task
    print("cancel", cancel)
    print("speak_after_cancel", spoken["status"])

    health_snap = sm.snapshot()
    print("snapshot", health_snap)
    print("capabilities", sm.audio.capabilities())

    stopped = await sm.stop(sid)
    print("stop", stopped)
    print("SMOKE_SESSION OK")


if __name__ == "__main__":
    asyncio.run(main())
