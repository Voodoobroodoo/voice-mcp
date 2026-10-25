"""CLI / MCP / GUI entry: `python -m voice_mcp` and console script `voice-mcp`."""

from __future__ import annotations

import argparse
import logging
import os
import sys


def _parse_mcp(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Local MCP voice presence server (stdio) or GUI companion"
    )
    p.add_argument(
        "--stub",
        action="store_true",
        default=None,
        help="Use stub VAD/STT/TTS (no model downloads). Default if VOICE_MCP_STUB unset.",
    )
    p.add_argument(
        "--real",
        action="store_true",
        help="Use real engine imports (Silero VAD, faster-whisper, Silero/Piper TTS).",
    )
    p.add_argument(
        "--tts",
        choices=["silero", "piper"],
        default=None,
        help="TTS backend when not stub (default: silero; piper = license fallback).",
    )
    p.add_argument(
        "--gui",
        action="store_true",
        help="Launch tray+panel companion (does not start MCP stdio). Same as voice-mcp-gui.",
    )
    p.add_argument(
        "--status",
        action="store_true",
        help="Expose localhost presence status hub for GUI attach (with MCP stdio).",
    )
    p.add_argument(
        "--status-port",
        type=int,
        default=None,
        help="Status hub port (default 8765 / VOICE_MCP_STATUS_PORT).",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Entry used by console_scripts and `python -m voice_mcp`."""
    raw = list(sys.argv[1:] if argv is None else argv)
    cli_cmds = {
        "session-start",
        "session-stop",
        "listen",
        "speak",
        "cancel",
        "health",
        "turn",
        "gui",
    }
    if "gui" in raw:
        from voice_mcp.gui.app import run_gui

        idx = raw.index("gui")
        run_gui(raw[idx + 1 :])
        return

    if any(a in cli_cmds - {"gui"} for a in raw):
        from voice_mcp.cli import main as cli_main

        cli_main(raw)
        return

    args = _parse_mcp(raw)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)

    if args.gui:
        from voice_mcp.gui.app import run_gui

        gui_argv: list[str] = []
        if args.real:
            gui_argv.append("--real")
        elif args.stub:
            gui_argv.append("--stub")
        run_gui(gui_argv)
        return

    if args.real and args.stub:
        print("Choose either --stub or --real", file=sys.stderr)
        sys.exit(2)

    if args.real:
        stub: bool | None = False
        os.environ["VOICE_MCP_STUB"] = "0"
    elif args.stub:
        stub = True
        os.environ["VOICE_MCP_STUB"] = "1"
    else:
        stub = None

    if args.tts:
        os.environ["VOICE_MCP_TTS"] = args.tts
    if args.status_port is not None:
        os.environ["VOICE_MCP_STATUS_PORT"] = str(args.status_port)

    want_status = args.status or os.environ.get("VOICE_MCP_STATUS", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )

    from voice_mcp.config import load_settings
    from voice_mcp.server import create_server

    settings = load_settings(stub=stub)
    if want_status:
        from voice_mcp.gui.app import start_status_hub_for_mcp

        # create_server without presence first, then wire hub (single PresenceState)
        server = create_server(settings)
        sessions = server._voice_sessions  # type: ignore[attr-defined]
        _state, hub = start_status_hub_for_mcp(sessions, settings)
        print(f"presence status hub: {hub.base_url}", file=sys.stderr)
    else:
        server = create_server(settings)

    server.run(transport="stdio")


if __name__ == "__main__":
    main()
