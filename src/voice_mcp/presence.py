"""Shared presence state + localhost status hub for GUI companion.

Architecture (A+C GUI):
  MCP / SessionManager owns the session and publishes snapshots here.
  Tray + compact panel are human-facing companions — they poll/control via
  http://127.0.0.1:<port> and do NOT replace MCP tools for the Agent.

Env: VOICE_MCP_STATUS_HOST (default 127.0.0.1), VOICE_MCP_STATUS_PORT (default 8765)
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import urlparse

log = logging.getLogger("voice_mcp.presence")

DEFAULT_HOST = os.environ.get("VOICE_MCP_STATUS_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("VOICE_MCP_STATUS_PORT", "8765"))


class PresenceState:
    """Thread-safe snapshot consumed by tray/panel."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._data: dict[str, Any] = {
            "ok": True,
            "version": None,
            "stub": True,
            "session_active": False,
            "session_id": None,
            "state": "stopped",
            "locale": "ru-RU",
            "mode": "open_mic",
            "muted": False,
            "ptt_armed": False,
            "mic_level": 0.0,
            "last_transcript": "",
            "last_listen_latency_ms": None,
            "last_ttfa_ms": None,
            "engines": {},
            "updated_at": time.time(),
        }
        self._listeners: list[Callable[[dict[str, Any]], None]] = []
        self._control_handlers: dict[str, Callable[[], Any]] = {}

    def set_control_handler(self, action: str, fn: Callable[[], Any]) -> None:
        with self._lock:
            self._control_handlers[action] = fn

    def on_change(self, fn: Callable[[dict[str, Any]], None]) -> None:
        with self._lock:
            self._listeners.append(fn)

    def update(self, **kwargs: Any) -> dict[str, Any]:
        with self._lock:
            self._data.update(kwargs)
            self._data["updated_at"] = time.time()
            snap = dict(self._data)
            listeners = list(self._listeners)
        for fn in listeners:
            try:
                fn(snap)
            except Exception as e:
                log.debug("presence listener error: %s", e)
        return snap

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._data)

    def control(self, action: str) -> dict[str, Any]:
        with self._lock:
            fn = self._control_handlers.get(action)
        if not fn:
            return {"ok": False, "error": f"unknown_action:{action}"}
        try:
            result = fn()
            return {"ok": True, "action": action, "result": result}
        except Exception as e:
            return {"ok": False, "action": action, "error": str(e)}


class StatusHub:
    """Minimal localhost JSON API for GUI."""

    def __init__(
        self,
        state: PresenceState,
        *,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
    ) -> None:
        self.state = state
        self.host = host
        self.port = port
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        state = self.state

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: Any) -> None:
                log.debug("status_hub: " + fmt, *args)

            def _send(self, code: int, payload: dict[str, Any]) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:  # noqa: N802
                path = urlparse(self.path).path
                if path in ("/", "/status", "/health"):
                    self._send(200, state.snapshot())
                else:
                    self._send(404, {"ok": False, "error": "not_found"})

            def do_POST(self) -> None:  # noqa: N802
                path = urlparse(self.path).path
                length = int(self.headers.get("Content-Length", "0") or 0)
                raw = self.rfile.read(length) if length else b"{}"
                try:
                    data = json.loads(raw.decode("utf-8") or "{}")
                except json.JSONDecodeError:
                    self._send(400, {"ok": False, "error": "bad_json"})
                    return
                if path == "/control":
                    action = str(data.get("action", ""))
                    self._send(200, state.control(action))
                elif path == "/update":
                    # Internal/demo publish (GUI demo loop may push mic_level etc.)
                    if not isinstance(data, dict):
                        self._send(400, {"ok": False, "error": "bad_body"})
                        return
                    snap = state.update(**{k: v for k, v in data.items() if k != "action"})
                    self._send(200, snap)
                else:
                    self._send(404, {"ok": False, "error": "not_found"})

        # Bind may fail if port busy — try a few ports
        last_err: Exception | None = None
        for offset in range(0, 8):
            port = self.port + offset
            try:
                self._httpd = ThreadingHTTPServer((self.host, port), Handler)
                self.port = port
                break
            except OSError as e:
                last_err = e
                self._httpd = None
        if self._httpd is None:
            raise RuntimeError(f"status hub bind failed: {last_err}")

        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        log.info("presence status hub at %s", self.base_url)

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd = None


def fetch_status(base_url: str, timeout: float = 0.5) -> dict[str, Any] | None:
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(f"{base_url.rstrip('/')}/status", timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def post_control(base_url: str, action: str, timeout: float = 1.0) -> dict[str, Any]:
    import urllib.request

    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/control",
        data=json.dumps({"action": action}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))
