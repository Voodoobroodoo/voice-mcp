"""Piper TTS — license-friendly fallback (CLI binary or piper-tts).

Env:
  VOICE_MCP_PIPER_VOICE — path to .onnx voice (required)
  VOICE_MCP_PIPER_BIN — piper executable (default: piper)
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger("voice_mcp.tts")


class PiperTTS:
    name = "piper-tts"

    def __init__(self, *, voice_path: str | None = None, piper_bin: str | None = None) -> None:
        self.voice_path = voice_path or os.environ.get("VOICE_MCP_PIPER_VOICE", "")
        self.piper_bin = piper_bin or os.environ.get("VOICE_MCP_PIPER_BIN", "piper")

    async def synthesize(self, text: str, *, locale: str) -> bytes:
        del locale
        text = (text or "").strip()
        if not text:
            return b""
        if not self.voice_path or not Path(self.voice_path).exists():
            raise ImportError(
                "Set VOICE_MCP_PIPER_VOICE to an existing Piper .onnx voice "
                "(ru_RU). See docs/stt-tts-stack.md"
            )
        bin_path = shutil.which(self.piper_bin) or self.piper_bin
        if not shutil.which(self.piper_bin) and not Path(bin_path).exists():
            raise ImportError(
                f"Piper binary not found ({self.piper_bin}). Install Piper and set "
                "VOICE_MCP_PIPER_BIN, or use VOICE_MCP_TTS=silero"
            )

        loop = asyncio.get_running_loop()

        def _run() -> bytes:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as out:
                out_path = out.name
            try:
                proc = subprocess.run(
                    [
                        bin_path,
                        "--model",
                        self.voice_path,
                        "--output_file",
                        out_path,
                    ],
                    input=text.encode("utf-8"),
                    capture_output=True,
                    check=False,
                )
                if proc.returncode != 0:
                    err = proc.stderr.decode("utf-8", errors="replace")
                    raise RuntimeError(f"piper failed ({proc.returncode}): {err}")
                return Path(out_path).read_bytes()
            finally:
                Path(out_path).unlink(missing_ok=True)

        return await loop.run_in_executor(None, _run)
