"""Runtime configuration (stub vs real engines)."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    stub: bool = True
    tts_backend: str = "silero"  # silero | piper
    whisper_model: str = "small"
    whisper_compute: str = "int8"
    locale_default: str = "ru-RU"
    route: str = "local"


def load_settings(*, stub: bool | None = None) -> Settings:
    """Resolve settings from CLI override and env.

    Env:
      VOICE_MCP_STUB=1|0|true|false
      VOICE_MCP_TTS=silero|piper
      VOICE_MCP_WHISPER_MODEL=small|base|...
      VOICE_MCP_WHISPER_COMPUTE=int8|float16|...
    """
    if stub is None:
        raw = os.environ.get("VOICE_MCP_STUB", "1").strip().lower()
        stub = raw in ("1", "true", "yes", "on")
    tts = os.environ.get("VOICE_MCP_TTS", "silero").strip().lower()
    if tts not in ("silero", "piper"):
        tts = "silero"
    return Settings(
        stub=stub,
        tts_backend=tts,
        whisper_model=os.environ.get("VOICE_MCP_WHISPER_MODEL", "small"),
        whisper_compute=os.environ.get("VOICE_MCP_WHISPER_COMPUTE", "int8"),
        locale_default=os.environ.get("VOICE_MCP_LOCALE", "ru-RU"),
        route="local",
    )
