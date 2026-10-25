"""Optional real-engine smoke.

Exits 0 with SKIP when PortAudio/mic missing or heavy models not requested.
Does NOT claim live duplex works without devices.

Env:
  VOICE_MCP_REAL_SMOKE_MODELS=1  — load faster-whisper (+ Silero TTS if torch)
  VOICE_MCP_WHISPER_MODEL=base     — smaller model for optional STT probe
"""

from __future__ import annotations

import asyncio
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ["VOICE_MCP_STUB"] = "0"


def _have_audio_devices() -> tuple[bool, str]:
    try:
        import sounddevice as sd

        devices = sd.query_devices()
        if not devices:
            return False, "sounddevice returned no devices"
        ins = any(d.get("max_input_channels", 0) > 0 for d in devices)
        outs = any(d.get("max_output_channels", 0) > 0 for d in devices)
        if not ins and not outs:
            return False, "no input/output channels"
        return True, f"devices ok (in={ins}, out={outs})"
    except Exception as e:
        return False, f"device probe failed: {e}"


async def main() -> int:
    print("=== voice-mcp real smoke (optional) ===")

    missing = []
    for mod in ("numpy", "onnxruntime", "faster_whisper"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        print("SKIP: missing packages:", ", ".join(missing))
        print("Install: pip install -r requirements-real.txt")
        return 0

    try:
        import sounddevice  # noqa: F401
    except Exception as e:
        print(f"NOTE: sounddevice/PortAudio unavailable ({e})")
        print("Mic/playback will not work until PortAudio is installed.")

    from voice_mcp.audio import build_audio_stack
    from voice_mcp.audio.vad_silero import SileroVAD
    from voice_mcp.config import load_settings

    settings = load_settings(stub=False)
    stack = build_audio_stack(settings)
    assert stack.stub is False
    print("stack engines:", stack.capabilities()["engines"])

    import numpy as np

    vad = SileroVAD()
    # Load ONNX without opening mic
    try:
        # Bypass sounddevice ensure by calling _ensure after patching? 
        # speech_probability needs onnx only — but _ensure also imports sounddevice.
        # If sounddevice failed above, still try onnx-only path:
        from voice_mcp.audio.pcmutil import CACHE_DIR, download_file
        from voice_mcp.audio.vad_silero import SILERO_VAD_ONNX_URL
        import onnxruntime as ort

        model_path = download_file(SILERO_VAD_ONNX_URL, CACHE_DIR / "silero_vad.onnx")
        sess = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
        state = np.zeros((2, 1, 128), dtype=np.float32)
        out, _ = sess.run(
            None,
            {
                "input": np.zeros((1, 512), dtype=np.float32),
                "state": state,
                "sr": np.array(16000, dtype=np.int64),
            },
        )
        print(f"Silero VAD ONNX OK (silent chunk prob={float(out.squeeze()):.4f})")
        del sess, vad
    except Exception as e:
        print(f"FAIL: Silero VAD ONNX: {e}")
        return 1

    have_dev, reason = _have_audio_devices()
    print("audio devices:", reason)

    want_models = os.environ.get("VOICE_MCP_REAL_SMOKE_MODELS", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if want_models:
        from voice_mcp.audio.pcmutil import wav_bytes_from_float32
        from voice_mcp.audio.stt_faster_whisper import FasterWhisperSTT

        stt = FasterWhisperSTT(
            model_size=os.environ.get("VOICE_MCP_WHISPER_MODEL", "base"),
            compute_type=os.environ.get("VOICE_MCP_WHISPER_COMPUTE", "int8"),
        )
        silence = wav_bytes_from_float32(np.zeros(16000, dtype=np.float32), sample_rate=16000)
        text = await stt.transcribe(silence, locale="ru-RU")
        print(f"faster-whisper OK (silence transcript={text!r})")

        try:
            import torch  # noqa: F401

            from voice_mcp.audio.tts_silero import SileroTTS

            tts = SileroTTS()
            wav = await tts.synthesize("Проверка синтеза.", locale="ru-RU")
            print(f"Silero TTS OK (wav bytes={len(wav)}) — remember CC BY-NC for many RU voices")
        except Exception as e:
            print(f"Silero TTS skipped/failed: {e}")
    else:
        print(
            "SKIP models: set VOICE_MCP_REAL_SMOKE_MODELS=1 to download/load "
            "faster-whisper / Silero TTS (large)."
        )

    if not have_dev:
        print(
            "SKIP live duplex: no usable mic/speaker here — "
            "wiring is present; run --real on a desktop with devices."
        )
        print("PARTIAL OK")
        return 0

    print("Devices present; live listen/speak not auto-driven in this smoke.")
    print("PARTIAL OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
