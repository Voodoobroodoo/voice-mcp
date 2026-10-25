"""Mic-free presence hub tests."""

from __future__ import annotations

import os
import sys

os.environ["VOICE_MCP_STUB"] = "1"
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from voice_mcp.presence import PresenceState, StatusHub, fetch_status, post_control


def test_status_hub_get_and_control() -> None:
    state = PresenceState()
    state.update(state="think", stub=True, last_transcript="привет")
    hub = StatusHub(state, host="127.0.0.1", port=18766)
    hub.start()
    try:
        snap = fetch_status(hub.base_url)
        assert snap is not None
        assert snap["state"] == "think"
        assert snap["last_transcript"] == "привет"

        state.set_control_handler("mute", lambda: state.update(muted=True))
        assert post_control(hub.base_url, "mute")["ok"] is True
        assert state.snapshot()["muted"] is True
    finally:
        hub.stop()
