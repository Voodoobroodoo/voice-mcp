"""Compact control panel (tkinter) — opens from tray click."""

from __future__ import annotations

from typing import Any, Callable


def _require_tk():
    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError as e:
        raise ImportError(
            "tkinter missing — Linux: sudo apt install python3-tk; "
            "macOS/Windows: use official python.org build with Tcl/Tk"
        ) from e
    return tk, ttk


class ControlPanel:
    def __init__(
        self,
        *,
        on_mute: Callable[[], None],
        on_unmute: Callable[[], None],
        on_stop: Callable[[], None],
        on_ptt: Callable[[], None],
        on_demo_turn: Callable[[], None] | None = None,
    ) -> None:
        self._on_mute = on_mute
        self._on_unmute = on_unmute
        self._on_stop = on_stop
        self._on_ptt = on_ptt
        self._on_demo_turn = on_demo_turn
        self._root = None
        self._built = False
        self._muted = False
        self._tk = None
        self._ttk = None

    def ensure(self):
        if self._root is not None:
            return self._root
        tk, ttk = _require_tk()
        self._tk = tk
        self._ttk = ttk
        root = tk.Tk()
        root.title("voice-mcp")
        root.geometry("360x280")
        root.minsize(320, 240)
        root.protocol("WM_DELETE_WINDOW", self.hide)

        frm = ttk.Frame(root, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)

        self._state_var = tk.StringVar(value="stopped")
        self._meta_var = tk.StringVar(value="engines: —")
        self._transcript_var = tk.StringVar(value="(нет transcript)")
        self._level_var = tk.DoubleVar(value=0.0)

        top = ttk.Frame(frm)
        top.pack(fill=tk.X)
        ttk.Label(top, text="State").pack(side=tk.LEFT)
        self._pill = ttk.Label(
            top,
            textvariable=self._state_var,
            relief=tk.SOLID,
            padding=(8, 2),
            font=("Segoe UI", 10, "bold"),
        )
        self._pill.pack(side=tk.RIGHT)

        ttk.Label(frm, textvariable=self._meta_var, wraplength=330).pack(fill=tk.X, pady=(8, 4))

        ttk.Label(frm, text="Mic level").pack(anchor=tk.W)
        self._level = ttk.Progressbar(frm, maximum=1.0, variable=self._level_var)
        self._level.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(frm, text="Last transcript").pack(anchor=tk.W)
        self._transcript = ttk.Label(
            frm,
            textvariable=self._transcript_var,
            wraplength=330,
            relief=tk.GROOVE,
            padding=6,
        )
        self._transcript.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        btns = ttk.Frame(frm)
        btns.pack(fill=tk.X)
        self._mute_btn = ttk.Button(btns, text="Mute", command=self._toggle_mute)
        self._mute_btn.pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(btns, text="PTT", command=self._on_ptt).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Stop session", command=self._on_stop).pack(side=tk.LEFT, padx=4)
        if self._on_demo_turn:
            ttk.Button(btns, text="Demo turn", command=self._on_demo_turn).pack(side=tk.RIGHT)

        self._root = root
        self._built = True
        return root

    def _toggle_mute(self) -> None:
        if self._muted:
            self._on_unmute()
        else:
            self._on_mute()

    def show(self) -> None:
        root = self.ensure()
        root.deiconify()
        root.lift()
        root.focus_force()

    def hide(self) -> None:
        if self._root is not None:
            self._root.withdraw()

    def destroy(self) -> None:
        if self._root is not None:
            try:
                self._root.destroy()
            except Exception:
                pass
            self._root = None

    def apply_status(self, status: dict[str, Any]) -> None:
        if not self._built or self._root is None:
            return
        state = str(status.get("state") or "stopped")
        muted = bool(status.get("muted"))
        self._muted = muted
        self._state_var.set(f"{state}" + (" · muted" if muted else ""))
        self._mute_btn.configure(text="Unmute" if muted else "Mute")

        engines = status.get("engines") or {}
        eng = "/".join(str(engines.get(k, "?")) for k in ("vad", "stt", "tts"))
        mode = "stub" if status.get("stub") else "real"
        lat_l = status.get("last_listen_latency_ms")
        lat_t = status.get("last_ttfa_ms")
        lat = []
        if lat_l is not None:
            lat.append(f"listen {lat_l}ms")
        if lat_t is not None:
            lat.append(f"ttfa {lat_t}ms")
        lat_s = (" · ".join(lat)) if lat else "latency —"
        sid = status.get("session_id") or "—"
        self._meta_var.set(f"{mode} · {eng}\n{lat_s} · session {sid}")

        tr = status.get("last_transcript") or ""
        self._transcript_var.set(tr if tr else "(нет transcript)")
        try:
            self._level_var.set(float(status.get("mic_level") or 0.0))
        except (TypeError, ValueError):
            self._level_var.set(0.0)

    def tick(self) -> None:
        if self._root is None or self._tk is None:
            return
        try:
            self._root.update_idletasks()
            self._root.update()
        except Exception:
            self._root = None
