"""GUI app orchestration: status hub client/host + tray + panel.

Launch:
  voice-mcp-gui                 # standalone stub demo (hub + tray + panel)
  voice-mcp --gui --stub        # MCP stdio + status hub + tray in one process
  voice-mcp-gui --attach        # tray/panel only, attach to existing hub
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import threading
import time
from typing import Any

from voice_mcp.presence import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    PresenceState,
    StatusHub,
    fetch_status,
    post_control,
)

log = logging.getLogger("voice_mcp.gui")


class GuiRuntime:
    def __init__(
        self,
        *,
        attach_url: str | None = None,
        stub: bool = True,
        host_hub: bool = True,
        with_demo: bool = True,
    ) -> None:
        self.attach_url = attach_url
        self.stub = stub
        self.host_hub = host_hub and not attach_url
        self.with_demo = with_demo
        self.state = PresenceState()
        self.hub: StatusHub | None = None
        self._sm = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._tray = None
        self._panel = None
        self._base_url = attach_url or f"http://{DEFAULT_HOST}:{DEFAULT_PORT}"

    def _status(self) -> dict[str, Any]:
        if self.attach_url:
            remote = fetch_status(self.attach_url)
            if remote:
                return remote
            return {"state": "stopped", "stub": True, "ok": False, "last_transcript": "(hub offline)"}
        return self.state.snapshot()

    def _control(self, action: str) -> None:
        if self.attach_url:
            try:
                post_control(self.attach_url, action)
            except Exception as e:
                log.warning("control %s failed: %s", action, e)
            return
        self.state.control(action)

    def _start_local_backend(self) -> None:
        from voice_mcp import __version__
        from voice_mcp.audio import build_audio_stack
        from voice_mcp.config import load_settings
        from voice_mcp.session import SessionManager

        settings = load_settings(stub=self.stub)
        self.state.update(version=__version__, stub=settings.stub)
        audio = build_audio_stack(settings)
        self._sm = SessionManager(audio, presence=self.state)
        self._sm.publish_presence()

        self._loop = asyncio.new_event_loop()

        def _run_loop() -> None:
            assert self._loop is not None
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()

        self._loop_thread = threading.Thread(target=_run_loop, name="voice-mcp-async", daemon=True)
        self._loop_thread.start()

        def _run_coro(coro: Any) -> Any:
            assert self._loop is not None
            fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
            return fut.result(timeout=120)

        def mute() -> Any:
            self.state.update(muted=True)
            snap = self.state.snapshot()
            sid = snap.get("session_id")
            if sid and self._sm and snap.get("state") == "speak":
                return _run_coro(self._sm.cancel(sid, reason="agent_stop"))
            return {"muted": True}

        def unmute() -> Any:
            self.state.update(muted=False)
            return {"muted": False}

        def stop() -> Any:
            snap = self.state.snapshot()
            sid = snap.get("session_id")
            if sid and self._sm:
                return _run_coro(self._sm.stop(sid))
            return {"stopped": True}

        def ptt() -> Any:
            """Push-to-talk style: ensure session + one listen (stub works offline)."""
            assert self._sm is not None
            snap = self.state.snapshot()
            sid = snap.get("session_id")
            if not sid or not snap.get("session_active"):
                started = _run_coro(self._sm.start(locale="ru-RU"))
                sid = started["session_id"]
            # Fake mic level pulse for panel demo
            self.state.update(mic_level=0.7, ptt_armed=True)
            out = _run_coro(self._sm.listen(sid, timeout_ms=3000))
            self.state.update(mic_level=0.0, ptt_armed=False)
            return out

        def demo_turn() -> Any:
            assert self._sm is not None
            snap = self.state.snapshot()
            if snap.get("session_active") and snap.get("session_id"):
                _run_coro(self._sm.stop(snap["session_id"]))
            started = _run_coro(self._sm.start())
            sid = started["session_id"]
            self.state.update(mic_level=0.55)
            listened = _run_coro(self._sm.listen(sid, timeout_ms=3000))
            self.state.update(mic_level=0.0)
            spoken = None
            if not self.state.snapshot().get("muted"):
                spoken = _run_coro(
                    self._sm.speak(sid, text="Демо: короткий голосовой ответ.")
                )
            return {"listen": listened, "speak": spoken}

        self.state.set_control_handler("mute", mute)
        self.state.set_control_handler("unmute", unmute)
        self.state.set_control_handler("stop", stop)
        self.state.set_control_handler("ptt", ptt)
        if self.with_demo:
            self.state.set_control_handler("demo_turn", demo_turn)

        if self.host_hub:
            self.hub = StatusHub(self.state, host=DEFAULT_HOST, port=DEFAULT_PORT)
            self.hub.start()
            self._base_url = self.hub.base_url

    def run(self) -> None:
        # Import GUI deps lazily so headless/MCP-only installs stay light
        try:
            import tkinter  # noqa: F401
        except ImportError as e:
            raise SystemExit(
                "GUI: tkinter missing.\n"
                "  Linux:   sudo apt install python3-tk\n"
                "  macOS:   python.org installer with Tcl/Tk\n"
                "  Windows: reinstall from python.org (Tcl/Tk included)\n"
                "  Docs:    docs/pc-runbook.md\n"
                f"  detail: {e}"
            ) from e
        try:
            import PIL  # noqa: F401
        except ImportError as e:
            raise SystemExit(
                "GUI: Pillow missing — pip install -e '.[gui]'\n"
                f"  detail: {e}"
            ) from e

        if not self.attach_url:
            self._start_local_backend()
        else:
            self._base_url = self.attach_url

        from voice_mcp.gui.panel import ControlPanel
        from voice_mcp.gui.tray import TrayApp

        def open_panel() -> None:
            assert self._panel is not None
            self._panel.show()

        def toggle_mute() -> None:
            s = self._status()
            self._control("unmute" if s.get("muted") else "mute")

        def quit_app() -> None:
            self._stop.set()
            if self._tray:
                self._tray.stop()
            if self._panel:
                self._panel.destroy()
            if self.hub:
                self.hub.stop()
            if self._loop:
                self._loop.call_soon_threadsafe(self._loop.stop)

        self._panel = ControlPanel(
            on_mute=lambda: self._control("mute"),
            on_unmute=lambda: self._control("unmute"),
            on_stop=lambda: self._control("stop"),
            on_ptt=lambda: threading.Thread(
                target=lambda: self._control("ptt"), daemon=True
            ).start(),
            on_demo_turn=(
                (
                    lambda: threading.Thread(
                        target=lambda: self._control("demo_turn"), daemon=True
                    ).start()
                )
                if self.with_demo and not self.attach_url
                else None
            ),
        )
        # Build withdrawn panel so tk is ready
        self._panel.ensure()
        self._panel.hide()

        try:
            self._tray = TrayApp(
                get_status=self._status,
                on_open_panel=open_panel,
                on_toggle_mute=toggle_mute,
                on_quit=quit_app,
            )
            self._tray.start()
        except RuntimeError as e:
            log.warning("%s — continuing with panel only", e)
            self._panel.show()

        log.info("GUI companion ready (hub=%s)", self._base_url)
        # Main thread: tk event pump + poll status
        while not self._stop.is_set():
            st = self._status()
            self._panel.apply_status(st)
            if self._tray:
                self._tray.update_icon()
            self._panel.tick()
            time.sleep(0.15)


def run_gui(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    p = argparse.ArgumentParser(description="voice-mcp GUI companion (tray + panel)")
    p.add_argument("--attach", nargs="?", const=f"http://{DEFAULT_HOST}:{DEFAULT_PORT}",
                   default=None, help="Attach to existing status hub URL")
    p.add_argument("--stub", action="store_true", default=True)
    p.add_argument("--real", action="store_true")
    p.add_argument("--no-demo", action="store_true", help="Hide Demo turn button")
    args = p.parse_args(argv)

    if args.real:
        os.environ["VOICE_MCP_STUB"] = "0"
        stub = False
    else:
        os.environ.setdefault("VOICE_MCP_STUB", "1")
        stub = True

    GuiRuntime(
        attach_url=args.attach,
        stub=stub,
        host_hub=args.attach is None,
        with_demo=not args.no_demo,
    ).run()


def start_status_hub_for_mcp(sessions: Any, settings: Any) -> tuple[PresenceState, StatusHub]:
    """Called from MCP process to publish SessionManager state for an external/embedded GUI."""
    from voice_mcp import __version__

    state = PresenceState()
    state.update(version=__version__, stub=settings.stub)
    sessions.set_presence(state)

    def mute() -> Any:
        state.update(muted=True)
        snap = sessions.snapshot()
        sid = snap.get("session_id")
        if sid and snap.get("state") == "speak":
            # best-effort; MCP process has its own event loop via anyio/asyncio
            return {"muted": True, "note": "cancel via voice_cancel if speak in flight"}
        return {"muted": True}

    def unmute() -> Any:
        state.update(muted=False)
        return {"muted": False}

    def stop() -> Any:
        return {"ok": False, "error": "stop_via_mcp_or_gui_standalone"}

    state.set_control_handler("mute", mute)
    state.set_control_handler("unmute", unmute)
    state.set_control_handler("stop", stop)
    hub = StatusHub(state)
    hub.start()
    sessions.publish_presence()
    return state, hub
