"""Import/build smoke for GUI modules — no display/tray required.

Exit 0 always:
  - SMOKE_GUI_IMPORT OK when deps present
  - SKIP when pillow/tkinter/pystray missing (clear message, not a crash)
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ["VOICE_MCP_STUB"] = "1"


def main() -> int:
    missing: list[str] = []
    try:
        import PIL  # noqa: F401
    except ImportError:
        missing.append("pillow (pip install -e '.[gui]')")
    try:
        import tkinter  # noqa: F401
    except ImportError:
        missing.append("tkinter (Linux: apt install python3-tk)")
    # pystray import may need display backends — probe softly
    try:
        os.environ.setdefault("PYSTRAY_BACKEND", "xorg")
        import pystray  # noqa: F401
    except Exception as e:
        missing.append(f"pystray ({e})")

    if missing:
        print("SKIP: GUI deps missing — " + "; ".join(missing))
        print("Install: pip install -e '.[gui]' + OS notes in docs/pc-runbook.md")
        # Still verify presence hub (no GUI deps)
        from voice_mcp.presence import PresenceState, StatusHub, fetch_status

        state = PresenceState()
        state.update(state="idle", stub=True)
        hub = StatusHub(state, host="127.0.0.1", port=18767)
        hub.start()
        assert fetch_status(hub.base_url) is not None
        hub.stop()
        print("presence hub OK (GUI skipped)")
        return 0

    from voice_mcp.gui.icons import make_icon
    from voice_mcp.presence import PresenceState, StatusHub, fetch_status, post_control

    img = make_icon("listen", muted=False)
    assert img.size[0] >= 16
    assert make_icon("speak", muted=True).size[0] >= 16

    state = PresenceState()
    state.update(state="idle", stub=True, last_transcript="ping")
    hub = StatusHub(state, host="127.0.0.1", port=18765)
    hub.start()
    snap = fetch_status(hub.base_url)
    assert snap is not None and snap["last_transcript"] == "ping"
    state.set_control_handler("mute", lambda: state.update(muted=True) or {"muted": True})
    assert post_control(hub.base_url, "mute")["ok"] is True
    hub.stop()

    import voice_mcp.gui.app as app_mod
    import voice_mcp.gui.panel as panel_mod
    import voice_mcp.gui.tray as tray_mod

    assert hasattr(panel_mod, "ControlPanel")
    assert hasattr(tray_mod, "TrayApp")
    assert hasattr(app_mod, "run_gui")
    print("SMOKE_GUI_IMPORT OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
