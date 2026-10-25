"""faster-whisper STT — lazy-loads model on first transcribe."""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from voice_mcp.audio.pcmutil import float32_from_wav_bytes

log = logging.getLogger("voice_mcp.stt")


def _resample_linear(samples: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    if src_sr == dst_sr or len(samples) == 0:
        return samples.astype(np.float32)
    duration = len(samples) / float(src_sr)
    target = max(1, int(duration * dst_sr))
    x_old = np.linspace(0.0, 1.0, num=len(samples), endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=target, endpoint=False)
    return np.interp(x_new, x_old, samples).astype(np.float32)


class FasterWhisperSTT:
    name = "faster-whisper"

    def __init__(self, *, model_size: str = "small", compute_type: str = "int8") -> None:
        self.model_size = model_size
        self.compute_type = compute_type
        self._model: Any = None
        self._lock = asyncio.Lock()

    def _ensure_sync(self) -> None:
        if self._model is not None:
            return
        try:
            from faster_whisper import WhisperModel  # type: ignore
        except ImportError as e:
            raise ImportError(
                "faster-whisper missing — pip install -r requirements-real.txt"
            ) from e
        log.info(
            "Loading faster-whisper model=%s compute=%s (first run may download weights)",
            self.model_size,
            self.compute_type,
        )
        self._model = WhisperModel(self.model_size, device="cpu", compute_type=self.compute_type)
        log.info("faster-whisper ready")

    async def transcribe(self, audio: bytes, *, locale: str) -> str:
        async with self._lock:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._ensure_sync)
            lang = (locale or "ru-RU").split("-")[0].lower() or None

            def _run() -> str:
                assert self._model is not None
                try:
                    samples, sr = float32_from_wav_bytes(audio)
                    samples = _resample_linear(samples, sr, 16000)
                    if samples.size == 0:
                        return ""
                    segments, _info = self._model.transcribe(
                        samples,
                        language=lang,
                        beam_size=1,
                        vad_filter=False,
                    )
                    return "".join(seg.text for seg in segments).strip()
                except Exception as e:
                    log.warning("ndarray transcribe failed (%s); falling back to temp wav", e)
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                        tmp.write(audio)
                        path = tmp.name
                    try:
                        segments, _info = self._model.transcribe(
                            path,
                            language=lang,
                            beam_size=1,
                            vad_filter=False,
                        )
                        return "".join(seg.text for seg in segments).strip()
                    finally:
                        Path(path).unlink(missing_ok=True)

            return await loop.run_in_executor(None, _run)
