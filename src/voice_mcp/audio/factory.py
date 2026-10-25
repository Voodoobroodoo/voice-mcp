"""Build AudioStack: stub by default, real engines when VOICE_MCP_STUB=0."""

from __future__ import annotations

import logging

from voice_mcp.audio.base import AudioStack
from voice_mcp.audio.stack import CompositeAudioStack
from voice_mcp.audio.stub import StubAudioStack
from voice_mcp.config import Settings

log = logging.getLogger("voice_mcp")


def build_audio_stack(settings: Settings) -> AudioStack:
    if settings.stub:
        log.info("audio stack: STUB (set VOICE_MCP_STUB=0 / --real for live engines)")
        return StubAudioStack()

    from voice_mcp.audio.playback import SoundDevicePlayback
    from voice_mcp.audio.stt_faster_whisper import FasterWhisperSTT
    from voice_mcp.audio.vad_silero import SileroVAD

    vad = SileroVAD()
    stt = FasterWhisperSTT(
        model_size=settings.whisper_model,
        compute_type=settings.whisper_compute,
    )
    if settings.tts_backend == "piper":
        from voice_mcp.audio.tts_piper import PiperTTS

        tts = PiperTTS()
    else:
        from voice_mcp.audio.tts_silero import SileroTTS

        tts = SileroTTS()

    log.info(
        "audio stack: REAL vad=%s stt=%s(%s/%s) tts=%s — models lazy-load on first listen/speak",
        vad.name,
        stt.name,
        settings.whisper_model,
        settings.whisper_compute,
        tts.name,
    )
    return CompositeAudioStack(vad=vad, stt=stt, tts=tts, playback=SoundDevicePlayback())
