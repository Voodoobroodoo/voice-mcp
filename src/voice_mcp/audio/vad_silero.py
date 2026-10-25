"""Silero VAD (ONNX) + sounddevice mic capture until end-of-utterance."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import numpy as np

from voice_mcp.audio.pcmutil import CACHE_DIR, download_file, wav_bytes_from_float32

log = logging.getLogger("voice_mcp.vad")

# Official ONNX packaged with silero-vad
SILERO_VAD_ONNX_URL = (
    "https://github.com/snakers4/silero-vad/raw/master/"
    "src/silero_vad/data/silero_vad.onnx"
)
SAMPLE_RATE = 16000
WINDOW = 512  # Silero VAD v4/v5 window at 16 kHz


class SileroVAD:
    name = "silero-vad"

    def __init__(
        self,
        *,
        speech_threshold: float = 0.5,
        silence_ms: int = 500,
        min_speech_ms: int = 250,
        preroll_ms: int = 200,
    ) -> None:
        self.speech_threshold = speech_threshold
        self.silence_ms = silence_ms
        self.min_speech_ms = min_speech_ms
        self.preroll_ms = preroll_ms
        self._session: Any = None
        self._state: np.ndarray | None = None
        self._context: np.ndarray | None = None

    def _ensure_onnx(self) -> None:
        if self._session is not None:
            return
        try:
            import onnxruntime as ort  # type: ignore
        except ImportError as e:
            raise ImportError(
                "onnxruntime missing — pip install -r requirements-real.txt"
            ) from e

        model_path = download_file(SILERO_VAD_ONNX_URL, CACHE_DIR / "silero_vad.onnx")
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        self._session = ort.InferenceSession(
            str(model_path),
            sess_options=opts,
            providers=["CPUExecutionProvider"],
        )
        self._reset_state()
        log.info("Silero VAD ONNX loaded from %s", model_path)

    def _ensure_capture(self) -> None:
        self._ensure_onnx()
        try:
            import sounddevice  # noqa: F401
        except Exception as e:
            raise ImportError(
                "sounddevice/PortAudio unavailable — pip install -r requirements-real.txt "
                "and install PortAudio (Linux: portaudio19-dev, macOS: brew install portaudio); "
                f"detail: {e}"
            ) from e

    def _ensure(self) -> None:
        """Back-compat: ONNX only (mic checked in wait_end_of_utterance)."""
        self._ensure_onnx()

    def _reset_state(self) -> None:
        # state shape for silero_vad.onnx: (2, 1, 128)
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros(0, dtype=np.float32)

    def _prob(self, chunk: np.ndarray) -> float:
        assert self._session is not None and self._state is not None
        if chunk.shape[0] != WINDOW:
            # pad/trim
            if chunk.shape[0] < WINDOW:
                chunk = np.pad(chunk, (0, WINDOW - chunk.shape[0]))
            else:
                chunk = chunk[:WINDOW]
        x = chunk.astype(np.float32).reshape(1, -1)
        ort_inputs = {
            "input": x,
            "state": self._state,
            "sr": np.array(SAMPLE_RATE, dtype=np.int64),
        }
        out, self._state = self._session.run(None, ort_inputs)
        return float(out.squeeze())

    def speech_probability(self, chunk_f32: np.ndarray) -> float:
        """Public helper for barge-in during playback (single WINDOW chunk)."""
        self._ensure()
        return self._prob(chunk_f32)

    async def wait_end_of_utterance(
        self,
        *,
        timeout_ms: int,
        max_duration_ms: int,
        cancel_event: asyncio.Event,
    ) -> tuple[bytes, str, int]:
        self._ensure_capture()
        import sounddevice as sd

        self._reset_state()
        loop = asyncio.get_running_loop()

        def _record_blocking() -> tuple[bytes, str, int]:
            block = WINDOW
            silence_needed = max(1, int(SAMPLE_RATE * self.silence_ms / 1000 / block))
            min_speech_blocks = max(1, int(SAMPLE_RATE * self.min_speech_ms / 1000 / block))
            preroll_blocks = max(1, int(SAMPLE_RATE * self.preroll_ms / 1000 / block))
            max_blocks = max(1, int(SAMPLE_RATE * max_duration_ms / 1000 / block))
            timeout_blocks = max(1, int(SAMPLE_RATE * timeout_ms / 1000 / block))

            buf: list[np.ndarray] = []
            preroll: list[np.ndarray] = []
            speech_started = False
            speech_blocks = 0
            silence_blocks = 0
            started = time.perf_counter()

            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=block,
            ) as stream:
                for i in range(max(timeout_blocks, max_blocks) + 1):
                    if cancel_event.is_set():
                        audio = np.concatenate(buf) if buf else np.zeros(0, dtype=np.float32)
                        return (
                            wav_bytes_from_float32(audio, sample_rate=SAMPLE_RATE),
                            "cancelled",
                            int((time.perf_counter() - started) * 1000),
                        )

                    frames, _overflowed = stream.read(block)
                    chunk = frames.reshape(-1)
                    prob = self._prob(chunk)

                    if not speech_started:
                        preroll.append(chunk.copy())
                        if len(preroll) > preroll_blocks:
                            preroll.pop(0)
                        if prob >= self.speech_threshold:
                            speech_started = True
                            buf.extend(preroll)
                            buf.append(chunk.copy())
                            speech_blocks = 1
                            silence_blocks = 0
                        elif i >= timeout_blocks:
                            return (
                                wav_bytes_from_float32(
                                    np.zeros(0, dtype=np.float32), sample_rate=SAMPLE_RATE
                                ),
                                "timeout",
                                int((time.perf_counter() - started) * 1000),
                            )
                        continue

                    buf.append(chunk.copy())
                    speech_blocks += 1
                    if prob < self.speech_threshold:
                        silence_blocks += 1
                    else:
                        silence_blocks = 0

                    if (
                        speech_blocks >= min_speech_blocks
                        and silence_blocks >= silence_needed
                    ):
                        audio = np.concatenate(buf)
                        return (
                            wav_bytes_from_float32(audio, sample_rate=SAMPLE_RATE),
                            "end_of_utterance",
                            int((time.perf_counter() - started) * 1000),
                        )

                    if speech_blocks >= max_blocks:
                        audio = np.concatenate(buf)
                        return (
                            wav_bytes_from_float32(audio, sample_rate=SAMPLE_RATE),
                            "max_duration",
                            int((time.perf_counter() - started) * 1000),
                        )

            audio = np.concatenate(buf) if buf else np.zeros(0, dtype=np.float32)
            return (
                wav_bytes_from_float32(audio, sample_rate=SAMPLE_RATE),
                "max_duration",
                int((time.perf_counter() - started) * 1000),
            )

        return await loop.run_in_executor(None, _record_blocking)
