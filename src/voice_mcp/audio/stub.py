"""Stub engines — no model downloads; for CI and dry MCP wiring."""

from __future__ import annotations

import asyncio
import time

from voice_mcp.audio.base import ListenResult, SpeakResult


class StubVAD:
    name = "stub-vad"

    async def wait_end_of_utterance(
        self,
        *,
        timeout_ms: int,
        max_duration_ms: int,
        cancel_event: asyncio.Event,
    ) -> tuple[bytes, str, int]:
        wait_ms = min(400, timeout_ms, max_duration_ms)
        try:
            await asyncio.wait_for(cancel_event.wait(), timeout=wait_ms / 1000.0)
            return b"", "cancelled", wait_ms
        except asyncio.TimeoutError:
            return b"STUB_PCM", "end_of_utterance", wait_ms


class StubSTT:
    name = "stub-stt"

    async def transcribe(self, audio: bytes, *, locale: str) -> str:
        await asyncio.sleep(0.05)
        return f"[stub transcript locale={locale}]"


class StubTTS:
    name = "stub-tts"

    async def synthesize(self, text: str, *, locale: str) -> bytes:
        await asyncio.sleep(0.05)
        return f"STUB_AUDIO:{locale}:{text}".encode("utf-8")


class StubPlayback:
    name = "stub-playback"

    async def play(
        self,
        audio: bytes,
        *,
        allow_barge_in: bool,
        cancel_event: asyncio.Event,
        vad: object | None,
    ) -> SpeakResult:
        t0 = time.perf_counter()
        ttfa_ms = 20
        duration = min(1.5, 0.02 * max(len(audio), 1))
        try:
            await asyncio.wait_for(cancel_event.wait(), timeout=duration)
            status = "barged_in" if allow_barge_in else "cancelled"
            return SpeakResult(
                status=status,
                spoken_chars=len(audio),
                ttfa_ms=ttfa_ms,
                duration_ms=int((time.perf_counter() - t0) * 1000),
            )
        except asyncio.TimeoutError:
            return SpeakResult(
                status="completed",
                spoken_chars=len(audio),
                ttfa_ms=ttfa_ms,
                duration_ms=int(duration * 1000),
            )

    async def stop(self) -> None:
        return None


class StubAudioStack:
    stub = True
    vad_name = StubVAD.name
    stt_name = StubSTT.name
    tts_name = StubTTS.name
    playback_name = StubPlayback.name

    def __init__(self) -> None:
        self.vad = StubVAD()
        self.stt = StubSTT()
        self.tts = StubTTS()
        self.playback = StubPlayback()

    async def open_devices(self) -> None:
        return None

    async def close_devices(self) -> None:
        return None

    async def cancel_playback(self) -> None:
        await self.playback.stop()

    async def listen(
        self,
        *,
        locale: str,
        timeout_ms: int,
        max_duration_ms: int,
        cancel_event: asyncio.Event,
    ) -> ListenResult:
        pcm, reason, duration_ms = await self.vad.wait_end_of_utterance(
            timeout_ms=timeout_ms,
            max_duration_ms=max_duration_ms,
            cancel_event=cancel_event,
        )
        if reason == "cancelled":
            return ListenResult(transcript="", ended_reason="cancelled", duration_ms=duration_ms)
        transcript = await self.stt.transcribe(pcm, locale=locale)
        return ListenResult(transcript=transcript, ended_reason=reason, duration_ms=duration_ms)

    async def speak(
        self,
        *,
        text: str,
        locale: str,
        allow_barge_in: bool,
        cancel_event: asyncio.Event,
    ) -> SpeakResult:
        audio = await self.tts.synthesize(text, locale=locale)
        return await self.playback.play(
            audio,
            allow_barge_in=allow_barge_in,
            cancel_event=cancel_event,
            vad=self.vad,
        )

    def capabilities(self) -> dict:
        return {
            "barge_in": True,
            "partials": False,
            "streaming_tts": False,
            "stub": True,
            "engines": {
                "vad": self.vad_name,
                "stt": self.stt_name,
                "tts": self.tts_name,
                "playback": self.playback_name,
            },
        }
