"""Cancellable sounddevice playback with optional VAD barge-in."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import numpy as np

from voice_mcp.audio.base import SpeakResult
from voice_mcp.audio.pcmutil import float32_from_wav_bytes

log = logging.getLogger("voice_mcp.playback")


class SoundDevicePlayback:
    name = "sounddevice"

    def __init__(self) -> None:
        self._stop = asyncio.Event()

    async def stop(self) -> None:
        self._stop.set()

    async def play(
        self,
        audio: bytes,
        *,
        allow_barge_in: bool,
        cancel_event: asyncio.Event,
        vad: Any | None,
    ) -> SpeakResult:
        try:
            import sounddevice as sd
        except Exception as e:
            raise ImportError(
                "sounddevice/PortAudio unavailable — pip install -r requirements-real.txt "
                f"and system PortAudio; detail: {e}"
            ) from e

        self._stop.clear()
        try:
            samples, sr = float32_from_wav_bytes(audio)
        except Exception:
            # Non-WAV fallback: treat as raw float32 mono @ 24k (unlikely)
            samples = np.frombuffer(audio, dtype=np.float32)
            sr = 24000

        if samples.size == 0:
            return SpeakResult(status="completed", spoken_chars=0, ttfa_ms=0, duration_ms=0)

        spoken_chars = len(audio)
        loop = asyncio.get_running_loop()
        t0 = time.perf_counter()
        ttfa_holder = {"ms": 0}

        def _play_blocking() -> str:
            block = 1024
            idx = 0
            ttfa_set = False
            # Optional mic for barge-in (best-effort; ignore if no device)
            mic = None
            vad_window = 512
            if allow_barge_in and vad is not None and hasattr(vad, "speech_probability"):
                try:
                    mic = sd.InputStream(
                        samplerate=16000,
                        channels=1,
                        dtype="float32",
                        blocksize=vad_window,
                    )
                    mic.start()
                except Exception as e:
                    log.warning("barge-in mic unavailable: %s", e)
                    mic = None

            try:
                with sd.OutputStream(
                    samplerate=sr,
                    channels=1,
                    dtype="float32",
                    blocksize=block,
                ) as stream:
                    while idx < len(samples):
                        if cancel_event.is_set() or self._stop.is_set():
                            return "cancelled" if not allow_barge_in else "barged_in"

                        if mic is not None:
                            try:
                                frames, _ = mic.read(vad_window)
                                chunk = frames.reshape(-1)
                                # Resample-ish: if output sr != 16k, still use raw chunk for VAD
                                # (Silero expects 16k — InputStream already 16k)
                                if float(vad.speech_probability(chunk)) >= 0.6:
                                    return "barged_in"
                            except Exception:
                                pass

                        end = min(idx + block, len(samples))
                        chunk_out = samples[idx:end].reshape(-1, 1)
                        stream.write(chunk_out)
                        if not ttfa_set:
                            ttfa_holder["ms"] = int((time.perf_counter() - t0) * 1000)
                            ttfa_set = True
                        idx = end
                return "completed"
            finally:
                if mic is not None:
                    try:
                        mic.stop()
                        mic.close()
                    except Exception:
                        pass

        status = await loop.run_in_executor(None, _play_blocking)
        return SpeakResult(
            status=status,
            spoken_chars=spoken_chars,
            ttfa_ms=ttfa_holder["ms"],
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )
