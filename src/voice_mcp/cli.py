"""Thin CLI secondary surface — same SessionManager ops as MCP (not a second architecture)."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

from voice_mcp.audio import build_audio_stack
from voice_mcp.config import load_settings
from voice_mcp.errors import VoiceError
from voice_mcp.session import SessionManager


def _print(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _die(exc: VoiceError) -> None:
    _print(exc.to_dict())
    raise SystemExit(1)


def _extract_globals(argv: list[str]) -> tuple[list[str], bool | None, str | None]:
    """Allow `voice-mcp health --stub` and `voice-mcp --stub health`."""
    stub: bool | None = None
    tts: str | None = None
    out: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--stub":
            stub = True
        elif a == "--real":
            stub = False
        elif a == "--tts" and i + 1 < len(argv):
            tts = argv[i + 1]
            i += 1
        elif a.startswith("--tts="):
            tts = a.split("=", 1)[1]
        else:
            out.append(a)
        i += 1
    return out, stub, tts


async def _run(args: argparse.Namespace, *, stub: bool, tts: str | None) -> None:
    if tts:
        os.environ["VOICE_MCP_TTS"] = tts
    settings = load_settings(stub=stub)
    sm = SessionManager(build_audio_stack(settings))

    try:
        if args.cmd == "health":
            _print(
                {
                    "ok": True,
                    "stub": settings.stub,
                    "session": sm.snapshot(),
                    "capabilities": sm.audio.capabilities(),
                }
            )
            return

        if args.cmd == "session-start":
            _print(await sm.start(locale=args.locale, mode=args.mode))
            return

        if args.cmd == "session-stop":
            _print(await sm.stop(args.session_id))
            return

        if args.cmd == "listen":
            _print(
                await sm.listen(
                    args.session_id,
                    timeout_ms=args.timeout_ms,
                    max_duration_ms=args.max_duration_ms,
                    language=args.language,
                )
            )
            return

        if args.cmd == "speak":
            text = args.text
            if text is None and not sys.stdin.isatty():
                text = sys.stdin.read()
            if not text:
                raise VoiceError("empty_text", "provide --text or stdin")
            _print(
                await sm.speak(
                    args.session_id,
                    text=text,
                    allow_barge_in=not args.no_barge_in,
                )
            )
            return

        if args.cmd == "cancel":
            _print(await sm.cancel(args.session_id, reason=args.reason))
            return

        if args.cmd == "turn":
            # One-process duplex helper (CLI is process-local; MCP is long-lived)
            started = await sm.start(locale=args.locale, mode=args.mode)
            sid = started["session_id"]
            listened = await sm.listen(
                sid,
                timeout_ms=args.timeout_ms,
                max_duration_ms=args.max_duration_ms,
                language=args.language,
            )
            spoken = None
            if args.speak_text:
                spoken = await sm.speak(
                    sid,
                    text=args.speak_text,
                    allow_barge_in=not args.no_barge_in,
                )
            stopped = await sm.stop(sid)
            _print(
                {
                    "session_start": started,
                    "listen": listened,
                    "speak": spoken,
                    "session_stop": stopped,
                }
            )
            return

        raise SystemExit(f"unknown command: {args.cmd}")
    except VoiceError as e:
        _die(e)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="voice-mcp",
        description="Thin CLI over the same session ops as the MCP server",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("session-start", help="voice_session_start")
    s.add_argument("--locale", default="ru-RU")
    s.add_argument("--mode", default="open_mic", choices=["open_mic", "push_to_talk"])

    s = sub.add_parser("session-stop", help="voice_session_stop")
    s.add_argument("session_id")

    s = sub.add_parser("listen", help="voice_listen")
    s.add_argument("session_id")
    s.add_argument("--timeout-ms", type=int, default=15000)
    s.add_argument("--max-duration-ms", type=int, default=30000)
    s.add_argument("--language", default=None)

    s = sub.add_parser("speak", help="voice_speak")
    s.add_argument("session_id")
    s.add_argument("--text", default=None)
    s.add_argument("--no-barge-in", action="store_true")

    s = sub.add_parser("cancel", help="voice_cancel")
    s.add_argument("session_id")
    s.add_argument(
        "--reason",
        default="agent_stop",
        choices=["user_barge_in", "agent_stop", "timeout", "other"],
    )

    sub.add_parser("health", help="health snapshot (stub/real + capabilities)")

    s = sub.add_parser(
        "turn",
        help="One-process: session-start → listen → optional speak → stop",
    )
    s.add_argument("--locale", default="ru-RU")
    s.add_argument("--mode", default="open_mic", choices=["open_mic", "push_to_talk"])
    s.add_argument("--timeout-ms", type=int, default=15000)
    s.add_argument("--max-duration-ms", type=int, default=30000)
    s.add_argument("--language", default=None)
    s.add_argument("--speak-text", default=None, help="If set, speak after listen")
    s.add_argument("--no-barge-in", action="store_true")
    return p


def main(argv: list[str] | None = None) -> None:
    raw = list(sys.argv[1:] if argv is None else argv)
    rest, stub_flag, tts = _extract_globals(raw)
    if stub_flag is True:
        os.environ["VOICE_MCP_STUB"] = "1"
    elif stub_flag is False:
        os.environ["VOICE_MCP_STUB"] = "0"
    stub = True if stub_flag is None else stub_flag
    # default stub for CLI unless --real
    if stub_flag is None:
        stub = load_settings(stub=None).stub

    parser = build_parser()
    args = parser.parse_args(rest)
    asyncio.run(_run(args, stub=stub, tts=tts))


if __name__ == "__main__":
    main()
