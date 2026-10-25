"""Composite AudioStack wiring VAD → STT and TTS → playback."""

from __future__ import annotations

import asyncio

from voice_mcp.audio.base import ListenResult, SpeakResult, STTEngine, TTSEngine, VADEngine
from voice_mcp.audio.playback import SoundDevicePlayback
from voice_mcp.errors import VoiceError


class CompositeAudioStack:
    stub = False

    def __init__(
        self,
        *,
        vad: VADEngine,
        stt: STTEngine,
        tts: TTSEngine,
        playback: SoundDevicePlayback | None = None,
    ) -> None:
        self.vad = vad
        self.stt = stt
        self.tts = tts
        self.playback = playback or SoundDevicePlayback()
        self.vad_name = getattr(vad, "name", type(vad).__name__)
        self.stt_name = getattr(stt, "name", type(stt).__name__)
        self.tts_name = getattr(tts, "name", type(tts).__name__)
        self.playback_name = getattr(self.playback, "name", "playback")

    async def open_devices(self) -> None:
        # Best-effort probe: fail early if sounddevice / PortAudio missing
        try:
            import sounddevice as sd

            _ = sd.query_devices()
        except Exception as e:
            raise VoiceError(
                "device_unavailable",
                f"Audio devices unavailable: {e}. Install PortAudio + sounddevice; "
                "grant mic/speaker permissions (macOS TCC / Windows privacy).",
            ) from e

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
        try:
            pcm, reason, duration_ms = await self.vad.wait_end_of_utterance(
                timeout_ms=timeout_ms,
                max_duration_ms=max_duration_ms,
                cancel_event=cancel_event,
            )
        except (NotImplementedError, ImportError) as e:
            raise VoiceError("device_unavailable", str(e)) from e

        if reason == "cancelled":
            return ListenResult(transcript="", ended_reason="cancelled", duration_ms=duration_ms)

        try:
            transcript = await self.stt.transcribe(pcm, locale=locale)
        except Exception as e:
            raise VoiceError("stt_failed", str(e)) from e
        return ListenResult(transcript=transcript, ended_reason=reason, duration_ms=duration_ms)

    async def speak(
        self,
        *,
        text: str,
        locale: str,
        allow_barge_in: bool,
        cancel_event: asyncio.Event,
    ) -> SpeakResult:
        try:
            audio = await self.tts.synthesize(text, locale=locale)
        except Exception as e:
            raise VoiceError("tts_failed", str(e)) from e
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
            "stub": False,
            "engines": {
                "vad": self.vad_name,
                "stt": self.stt_name,
                "tts": self.tts_name,
                "playback": self.playback_name,
            },
        }
