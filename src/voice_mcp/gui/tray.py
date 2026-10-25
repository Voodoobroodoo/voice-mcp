"""System tray icon (pystray) — always-on companion."""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Callable

log = logging.getLogger("voice_mcp.gui.tray")


def _pick_backend() -> None:
    if "PYSTRAY_BACKEND" not in os.environ:
        # Prefer appindicator on Linux desktops; fall back left to pystray
        if os.name == "posix" and os.environ.get("XDG_CURRENT_DESKTOP"):
            os.environ.setdefault("PYSTRAY_BACKEND", "appindicator")


class TrayApp:
    def __init__(
        self,
        *,
        get_status: Callable[[], dict[str, Any]],
        on_open_panel: Callable[[], None],
        on_toggle_mute: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        self._get_status = get_status
        self._on_open_panel = on_open_panel
        self._on_toggle_mute = on_toggle_mute
        self._on_quit = on_quit
        self._icon = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        _pick_backend()
        try:
            import pystray
            from pystray import MenuItem as Item
        except Exception as e:
            raise RuntimeError(
                "pystray unavailable — pip install 'voice-mcp[gui]' "
                "(Linux may need gir1.2-ayatanaappindicator3 / gtk). "
                f"detail: {e}"
            ) from e

        from voice_mcp.gui.icons import make_icon

        status = self._get_status()
        image = make_icon(str(status.get("state") or "idle"), muted=bool(status.get("muted")))

        def _title() -> str:
            s = self._get_status()
            mode = "stub" if s.get("stub") else "real"
            return f"voice-mcp · {s.get('state', '?')} · {mode}"

        menu = pystray.Menu(
            Item("Open panel", lambda: self._on_open_panel(), default=True),
            Item(
                lambda item: "Unmute" if self._get_status().get("muted") else "Mute",
                lambda: self._on_toggle_mute(),
            ),
            Item(
                lambda item: f"Mode: {'stub' if self._get_status().get('stub') else 'real'}",
                None,
                enabled=False,
            ),
            Item("Quit", lambda: self._on_quit()),
        )

        self._icon = pystray.Icon("voice-mcp", image, _title(), menu)

        def _run() -> None:
            assert self._icon is not None
            self._icon.run()

        self._thread = threading.Thread(target=_run, name="voice-mcp-tray", daemon=True)
        self._thread.start()
        log.info("tray started (backend=%s)", os.environ.get("PYSTRAY_BACKEND", "auto"))

    def update_icon(self) -> None:
        if self._icon is None:
            return
        from voice_mcp.gui.icons import make_icon

        s = self._get_status()
        try:
            self._icon.icon = make_icon(str(s.get("state") or "idle"), muted=bool(s.get("muted")))
            self._icon.title = (
                f"voice-mcp · {s.get('state', '?')} · "
                f"{'stub' if s.get('stub') else 'real'}"
            )
        except Exception as e:
            log.debug("tray icon update failed: %s", e)

    def stop(self) -> None:
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None
