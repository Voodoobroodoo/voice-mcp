"""Presence session state machine (idle/listen/think/speak/barge-in)."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from voice_mcp.audio.base import AudioStack, ListenResult, SpeakResult
from voice_mcp.errors import VoiceError


class SessionState(str, Enum):
    IDLE = "idle"
    LISTEN = "listen"
    THINK = "think"
    SPEAK = "speak"
    BARGE_IN = "barge_in"
    STOPPED = "stopped"


@dataclass
class Session:
    session_id: str
    locale: str
    mode: str
    state: SessionState = SessionState.IDLE
    created_at: float = field(default_factory=time.time)


class SessionManager:
    """Single active session per process (MVP)."""

    def __init__(self, audio: AudioStack, presence: Any | None = None) -> None:
        self._audio = audio
        self._presence = presence
        self._session: Session | None = None
        self._op_lock = asyncio.Lock()
        self._cancel = asyncio.Event()
        self._last_transcript = ""
        self._last_listen_latency_ms: int | None = None
        self._last_ttfa_ms: int | None = None

    @property
    def audio(self) -> AudioStack:
        return self._audio

    def set_presence(self, presence: Any | None) -> None:
        self._presence = presence
        self.publish_presence()

    def publish_presence(self) -> None:
        if self._presence is None:
            return
        snap = self.snapshot()
        caps = self._audio.capabilities()
        self._presence.update(
            session_active=snap.get("session_active", False),
            session_id=snap.get("session_id"),
            state=snap.get("state", "stopped"),
            locale=snap.get("locale", "ru-RU"),
            mode=snap.get("mode", "open_mic"),
            stub=bool(caps.get("stub", True)),
            engines=caps.get("engines", {}),
            last_transcript=self._last_transcript,
            last_listen_latency_ms=self._last_listen_latency_ms,
            last_ttfa_ms=self._last_ttfa_ms,
        )

    def snapshot(self) -> dict[str, Any]:
        if not self._session:
            return {
                "session_active": False,
                "session_id": None,
                "state": SessionState.STOPPED.value,
            }
        return {
            "session_active": True,
            "session_id": self._session.session_id,
            "state": self._session.state.value,
            "locale": self._session.locale,
            "mode": self._session.mode,
        }

    def _require(self, session_id: str) -> Session:
        if not self._session or self._session.session_id != session_id:
            raise VoiceError(
                "unknown_session" if self._session else "no_session",
                "Unknown or missing session",
                session_id=session_id,
                state=self._session.state.value if self._session else None,
            )
        return self._session

    async def start(self, *, locale: str = "ru-RU", mode: str = "open_mic") -> dict[str, Any]:
        async with self._op_lock:
            if self._session and self._session.state != SessionState.STOPPED:
                raise VoiceError(
                    "already_active",
                    "A voice session is already active",
                    session_id=self._session.session_id,
                    state=self._session.state.value,
                )
            self._cancel.clear()
            await self._audio.open_devices()
            sid = f"ses_{uuid.uuid4().hex[:12]}"
            self._session = Session(session_id=sid, locale=locale, mode=mode)
            out = {
                "session_id": sid,
                "state": SessionState.IDLE.value,
                "locale": locale,
                "mode": mode,
            }
            self.publish_presence()
            return out

    async def stop(self, session_id: str) -> dict[str, Any]:
        async with self._op_lock:
            session = self._require(session_id)
            self._cancel.set()
            await self._audio.cancel_playback()
            session.state = SessionState.STOPPED
            await self._audio.close_devices()
            out = {
                "session_id": session.session_id,
                "state": SessionState.STOPPED.value,
                "cancelled": True,
            }
            self._session = None
            self._cancel.clear()
            self.publish_presence()
            return out

    async def listen(
        self,
        session_id: str,
        *,
        timeout_ms: int = 15000,
        max_duration_ms: int = 30000,
        language: str | None = None,
    ) -> dict[str, Any]:
        session = self._require(session_id)
        if session.state in (SessionState.LISTEN, SessionState.SPEAK):
            raise VoiceError(
                "busy",
                f"Cannot listen while state={session.state.value}",
                session_id=session_id,
                state=session.state.value,
            )

        self._cancel.clear()
        session.state = SessionState.LISTEN
        self.publish_presence()
        t0 = time.perf_counter()
        try:
            result: ListenResult = await self._audio.listen(
                locale=language or session.locale,
                timeout_ms=timeout_ms,
                max_duration_ms=max_duration_ms,
                cancel_event=self._cancel,
            )
        except VoiceError as e:
            session.state = SessionState.IDLE
            e.session_id = session_id
            e.state = session.state.value
            self.publish_presence()
            raise

        if result.ended_reason == "cancelled":
            session.state = SessionState.IDLE
            self.publish_presence()
            raise VoiceError(
                "cancelled",
                "Listen cancelled",
                session_id=session_id,
                state=session.state.value,
            )

        session.state = SessionState.THINK
        listen_latency_ms = int((time.perf_counter() - t0) * 1000)
        self._last_transcript = result.transcript
        self._last_listen_latency_ms = listen_latency_ms
        self.publish_presence()
        return {
            "session_id": session.session_id,
            "state": session.state.value,
            "transcript": result.transcript,
            "is_final": True,
            "ended_reason": result.ended_reason,
            "duration_ms": result.duration_ms,
            "listen_latency_ms": listen_latency_ms,
        }

    async def speak(
        self,
        session_id: str,
        *,
        text: str,
        allow_barge_in: bool = True,
    ) -> dict[str, Any]:
        session = self._require(session_id)
        if not text.strip():
            raise VoiceError(
                "empty_text",
                "text must be non-empty",
                session_id=session_id,
                state=session.state.value,
            )
        if session.state in (SessionState.LISTEN, SessionState.SPEAK):
            raise VoiceError(
                "busy",
                f"Cannot speak while state={session.state.value}",
                session_id=session_id,
                state=session.state.value,
            )

        if self._presence is not None and self._presence.snapshot().get("muted"):
            raise VoiceError(
                "muted",
                "muted — unmute in the control panel (or POST /control unmute) to speak",
                session_id=session_id,
                state=session.state.value,
            )

        self._cancel.clear()
        session.state = SessionState.SPEAK
        self.publish_presence()
        try:
            result: SpeakResult = await self._audio.speak(
                text=text,
                locale=session.locale,
                allow_barge_in=allow_barge_in,
                cancel_event=self._cancel,
            )
        except VoiceError as e:
            session.state = SessionState.IDLE
            e.session_id = session_id
            e.state = session.state.value
            self.publish_presence()
            raise

        session.state = SessionState.IDLE
        self._last_ttfa_ms = result.ttfa_ms
        self.publish_presence()
        return {
            "session_id": session.session_id,
            "state": session.state.value,
            "status": result.status,
            "spoken_chars": result.spoken_chars,
            "ttfa_ms": result.ttfa_ms,
            "duration_ms": result.duration_ms,
        }

    async def cancel(self, session_id: str, *, reason: str = "agent_stop") -> dict[str, Any]:
        session = self._require(session_id)
        op = "none"
        if session.state == SessionState.LISTEN:
            op = "listen"
        elif session.state == SessionState.SPEAK:
            op = "speak"
        self._cancel.set()
        await self._audio.cancel_playback()
        session.state = SessionState.IDLE
        self.publish_presence()
        return {
            "session_id": session.session_id,
            "state": session.state.value,
            "cancelled_op": op,
            "reason": reason,
        }
