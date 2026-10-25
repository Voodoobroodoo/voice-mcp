"""PCM / WAV helpers shared by capture, STT, TTS, playback."""

from __future__ import annotations

import io
import wave
from pathlib import Path

import numpy as np

CACHE_DIR = Path.home() / ".cache" / "voice-mcp"


def ensure_cache_dir() -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR


def float32_mono(audio: np.ndarray) -> np.ndarray:
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    return np.asarray(audio, dtype=np.float32).reshape(-1)


def float_to_int16(audio: np.ndarray) -> np.ndarray:
    audio = float32_mono(audio)
    audio = np.clip(audio, -1.0, 1.0)
    return (audio * 32767.0).astype(np.int16)


def int16_to_float(audio: np.ndarray) -> np.ndarray:
    return np.asarray(audio, dtype=np.float32) / 32768.0


def wav_bytes_from_float32(audio: np.ndarray, *, sample_rate: int) -> bytes:
    pcm = float_to_int16(audio)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


def float32_from_wav_bytes(data: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(data), "rb") as wf:
        sr = wf.getframerate()
        frames = wf.readframes(wf.getnframes())
        sampwidth = wf.getsampwidth()
        channels = wf.getnchannels()
    if sampwidth == 2:
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    else:
        raise ValueError(f"Unsupported sample width: {sampwidth}")
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    return audio, sr


def download_file(url: str, dest: Path, *, timeout: float = 120.0) -> Path:
    """Download url to dest if missing. Uses urllib (no extra deps)."""
    import urllib.request

    ensure_cache_dir()
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    urllib.request.urlretrieve(url, tmp)  # noqa: S310 — pinned model URLs
    tmp.replace(dest)
    return dest
