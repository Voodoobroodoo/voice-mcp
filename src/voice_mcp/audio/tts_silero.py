"""Silero TTS v5_ru — lazy torch.hub load.

License: main Russian Silero TTS models are often CC BY-NC (non-commercial).
For commercial redistribution prefer Piper (`VOICE_MCP_TTS=piper`). See docs/stt-tts-stack.md.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import numpy as np

from voice_mcp.audio.pcmutil import wav_bytes_from_float32

log = logging.getLogger("voice_mcp.tts")


class SileroTTS:
    name = "silero-tts"

    def __init__(
        self,
        *,
        speaker: str = "xenia",
        sample_rate: int = 24000,
        model_id: str = "v5_ru",
    ) -> None:
        self.speaker = speaker
        self.sample_rate = sample_rate
        self.model_id = model_id
        self._model: Any = None
        self._lock = asyncio.Lock()

    def _ensure_sync(self) -> None:
        if self._model is not None:
            return
        try:
            import torch  # type: ignore
        except ImportError as e:
            raise ImportError(
                "torch missing for Silero TTS — pip install torch "
                "(CPU wheel OK) or switch VOICE_MCP_TTS=piper"
            ) from e

        log.info(
            "Loading Silero TTS %s speaker=%s (torch.hub; first run downloads; CC BY-NC for many RU models)",
            self.model_id,
            self.speaker,
        )
        # trust_repo=True avoids interactive prompt in non-TTY / agent environments
        try:
            self._model, _example = torch.hub.load(  # type: ignore[misc]
                repo_or_dir="snakers4/silero-models",
                model="silero_tts",
                language="ru",
                speaker=self.model_id,
                trust_repo=True,
            )
        except TypeError:
            # Older torch without trust_repo=
            self._model, _example = torch.hub.load(  # type: ignore[misc]
                repo_or_dir="snakers4/silero-models",
                model="silero_tts",
                language="ru",
                speaker=self.model_id,
            )
        self._model.to(torch.device("cpu"))
        log.info("Silero TTS ready")

    async def synthesize(self, text: str, *, locale: str) -> bytes:
        del locale  # Silero instance is RU-focused for MVP
        text = (text or "").strip()
        if not text:
            return wav_bytes_from_float32(np.zeros(0, dtype=np.float32), sample_rate=self.sample_rate)

        async with self._lock:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._ensure_sync)

            def _run() -> bytes:
                assert self._model is not None
                audio = self._model.apply_tts(
                    text=text,
                    speaker=self.speaker,
                    sample_rate=self.sample_rate,
                )
                if hasattr(audio, "detach"):
                    audio = audio.detach().cpu().numpy()
                audio = np.asarray(audio, dtype=np.float32).reshape(-1)
                return wav_bytes_from_float32(audio, sample_rate=self.sample_rate)

            return await loop.run_in_executor(None, _run)
