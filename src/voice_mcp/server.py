"""MCP tools matching docs/mcp-voice-schema.md — official FastMCP (mcp>=1.9,<2)."""

from __future__ import annotations

import json
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from voice_mcp import __version__
from voice_mcp.audio import build_audio_stack
from voice_mcp.config import Settings, load_settings
from voice_mcp.errors import VoiceError
from voice_mcp.session import SessionManager

Mode = Literal["open_mic", "push_to_talk"]
CancelReason = Literal["user_barge_in", "agent_stop", "timeout", "other"]


def _ok(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def create_server(
    settings: Settings | None = None,
    presence: Any | None = None,
) -> FastMCP:
    settings = settings or load_settings()
    audio = build_audio_stack(settings)
    sessions = SessionManager(audio, presence=presence)
    if presence is not None:
        from voice_mcp import __version__ as _ver

        presence.update(version=_ver, stub=settings.stub, route=settings.route)
        sessions.publish_presence()

    mcp = FastMCP(
        name="voice-mcp",
        instructions=(
            "Local voice presence tools for the desktop agent: "
            "voice_session_start/stop, voice_listen, voice_speak, voice_cancel, voice_health. "
            "Use listen → (reason) → speak; cancel for barge-in."
        ),
    )

    @mcp.tool(name="voice_session_start")
    async def voice_session_start(
        locale: str = "ru-RU",
        mode: Mode = "open_mic",
    ) -> str:
        """Open a voice session (claim mic/speakers). Required before listen/speak."""
        try:
            return _ok(await sessions.start(locale=locale, mode=mode))
        except VoiceError as e:
            return _ok(e.to_dict())

    @mcp.tool(name="voice_session_stop")
    async def voice_session_stop(session_id: str) -> str:
        """Close the voice session and cancel any in-flight listen/speak."""
        try:
            return _ok(await sessions.stop(session_id))
        except VoiceError as e:
            return _ok(e.to_dict())

    @mcp.tool(name="voice_listen")
    async def voice_listen(
        session_id: str,
        timeout_ms: int = 15000,
        max_duration_ms: int = 30000,
        language: str | None = None,
    ) -> str:
        """Block until end-of-utterance/timeout; return final transcript."""
        try:
            return _ok(
                await sessions.listen(
                    session_id,
                    timeout_ms=timeout_ms,
                    max_duration_ms=max_duration_ms,
                    language=language,
                )
            )
        except VoiceError as e:
            return _ok(e.to_dict())

    @mcp.tool(name="voice_speak")
    async def voice_speak(
        session_id: str,
        text: str,
        allow_barge_in: bool = True,
    ) -> str:
        """Speak text via local TTS. allow_barge_in stops playback on user speech."""
        try:
            return _ok(
                await sessions.speak(
                    session_id,
                    text=text,
                    allow_barge_in=allow_barge_in,
                )
            )
        except VoiceError as e:
            return _ok(e.to_dict())

    @mcp.tool(name="voice_cancel")
    async def voice_cancel(
        session_id: str,
        reason: CancelReason = "agent_stop",
    ) -> str:
        """Cancel active listen or speak (explicit stop / barge-in)."""
        try:
            return _ok(await sessions.cancel(session_id, reason=reason))
        except VoiceError as e:
            return _ok(e.to_dict())

    @mcp.tool(name="voice_health")
    async def voice_health() -> str:
        """Server health, session snapshot, and engine capabilities."""
        snap = sessions.snapshot()
        caps = sessions.audio.capabilities()
        devices = {"mic": True, "speaker": True} if settings.stub else {"mic": None, "speaker": None}
        return _ok(
            {
                "ok": True,
                "version": __version__,
                "stub": settings.stub,
                "route": settings.route,
                "session_active": snap["session_active"],
                "session_id": snap.get("session_id"),
                "state": snap.get("state"),
                "devices": devices,
                "capabilities": caps,
            }
        )

    # Exposed for tests / diagnostics (not MCP tools)
    mcp._voice_sessions = sessions  # type: ignore[attr-defined]
    mcp._voice_settings = settings  # type: ignore[attr-defined]
    return mcp
