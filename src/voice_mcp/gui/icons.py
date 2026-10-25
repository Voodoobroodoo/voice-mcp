"""Generate small tray icons colored by session state."""

from __future__ import annotations

STATE_COLORS = {
    "stopped": (120, 120, 120),
    "idle": (70, 160, 90),
    "listen": (50, 130, 220),
    "think": (200, 160, 40),
    "speak": (200, 80, 60),
    "barge_in": (220, 100, 200),
}


def make_icon(state: str = "idle", *, size: int = 64, muted: bool = False):
    try:
        from PIL import Image, ImageDraw
    except ImportError as e:
        raise ImportError(
            "Pillow missing — pip install -e '.[gui]' (pillow>=10)"
        ) from e

    color = STATE_COLORS.get(state, STATE_COLORS["idle"])
    if muted:
        color = (90, 90, 90)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = size // 8
    draw.ellipse([pad, pad, size - pad, size - pad], fill=color + (255,))
    draw.ellipse(
        [pad + 2, pad + 2, size - pad - 2, size - pad - 2],
        outline=(255, 255, 255, 180),
        width=max(1, size // 32),
    )
    if muted:
        draw.line(
            [(pad, size - pad), (size - pad, pad)],
            fill=(240, 240, 240, 230),
            width=max(2, size // 16),
        )
    return img
