"""Audio engine interfaces (vendor-agnostic)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol


@dataclass
class ListenResult:
    transcript: str
    ended_reason: str
    duration_ms: int


@dataclass
class SpeakResult:
    status: str
    spoken_chars: int
    ttfa_ms: int
    duration_ms: int


class VADEngine(Protocol):
    name: str

    async def wait_end_of_utterance(
        self,
        *,
        timeout_ms: int,
        max_duration_ms: int,
        cancel_event: asyncio.Event,
    ) -> tuple[bytes, str, int]: ...


class STTEngine(Protocol):
    name: str

    async def transcribe(self, audio: bytes, *, locale: str) -> str: ...


class TTSEngine(Protocol):
    name: str

    async def synthesize(self, text: str, *, locale: str) -> bytes: ...


class PlaybackEngine(Protocol):
    name: str

    async def play(
        self,
        audio: bytes,
        *,
        allow_barge_in: bool,
        cancel_event: asyncio.Event,
        vad: VADEngine | None,
    ) -> SpeakResult: ...

    async def stop(self) -> None: ...


class AudioStack(Protocol):
    stub: bool
    vad_name: str
    stt_name: str
    tts_name: str
    playback_name: str

    async def open_devices(self) -> None: ...
    async def close_devices(self) -> None: ...
    async def cancel_playback(self) -> None: ...
    async def listen(
        self,
        *,
        locale: str,
        timeout_ms: int,
        max_duration_ms: int,
        cancel_event: asyncio.Event,
    ) -> ListenResult: ...
    async def speak(
        self,
        *,
        text: str,
        locale: str,
        allow_barge_in: bool,
        cancel_event: asyncio.Event,
    ) -> SpeakResult: ...
    def capabilities(self) -> dict: ...
