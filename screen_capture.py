"""Privacy-preserving game-window capture helpers."""

from __future__ import annotations

import base64
import io
import os
import uuid
from pathlib import Path
from typing import Any, Dict, Optional


class GameWindowNotFound(RuntimeError):
    pass


def find_game_window(title_hint: str) -> Optional[Dict[str, int]]:
    """Find a visible, non-trivial window matching the configured title."""
    title_hint = title_hint.strip()
    if not title_hint:
        return None
    try:
        import pygetwindow as gw

        windows = gw.getWindowsWithTitle(title_hint)
    except Exception:
        return None

    candidates = []
    for window in windows:
        if getattr(window, "isMinimized", False):
            continue
        width = int(getattr(window, "width", 0))
        height = int(getattr(window, "height", 0))
        if width <= 100 or height <= 100:
            continue
        candidates.append(
            {
                "left": int(window.left),
                "top": int(window.top),
                "width": width,
                "height": height,
            }
        )
    return max(candidates, key=lambda item: item["width"] * item["height"], default=None)


def capture_region(region: dict[str, int]):
    """Capture an explicit region and return a Pillow RGB image."""
    if not region:
        raise GameWindowNotFound("未找到目标游戏窗口；为保护隐私，已跳过截图")
    import mss
    from PIL import Image

    with mss.mss() as sct:
        shot = sct.grab(region)
    return Image.frombytes("RGB", shot.size, shot.rgb)


def resize_image(image, max_edge: int = 1920):
    max_edge = max(320, int(max_edge))
    if max(image.size) <= max_edge:
        return image
    from PIL import Image

    scale = max_edge / max(image.size)
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    return image.resize(size, Image.Resampling.LANCZOS)


def save_jpeg_atomic(image, path: Path, *, max_edge: int = 1920, quality: int = 82) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    image = resize_image(image, max_edge)
    temp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        image.save(temp, format="JPEG", quality=max(40, min(95, int(quality))), optimize=True)
        os.replace(temp, path)
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
    return path


def image_as_base64(image, *, image_format: str = "JPEG", quality: int = 82) -> str:
    buffer = io.BytesIO()
    kwargs: dict[str, Any] = {}
    if image_format.upper() == "JPEG":
        kwargs["quality"] = max(40, min(95, int(quality)))
    image.save(buffer, format=image_format, **kwargs)
    return base64.b64encode(buffer.getvalue()).decode("ascii")
