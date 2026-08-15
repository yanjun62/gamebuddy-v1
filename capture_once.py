"""Capture one frame from the configured game window, then exit."""

from __future__ import annotations

import json
from pathlib import Path

from screen_capture import capture_region, find_game_window, resize_image, save_jpeg_atomic


ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / "config.json"
FRAME_FILE = ROOT / "current_frame.jpg"


def main() -> int:
    try:
        config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"config.json 无法读取: {exc}")
        return 1

    title = str(config.get("game_window_title", "")).strip()
    if not title:
        print("未设置 game_window_title；为保护隐私，不截图")
        return 2

    region = find_game_window(title)
    if region is None:
        print(f"未找到目标游戏窗口：{title}；不会退回桌面截图")
        return 3

    try:
        max_edge = int(config.get("capture_max_edge", 1920))
        quality = int(config.get("capture_jpeg_quality", 82))
        image = resize_image(capture_region(region), max_edge)
        save_jpeg_atomic(image, FRAME_FILE, max_edge=max_edge, quality=quality)
    except Exception as exc:
        print(f"截图失败: {exc}")
        return 4


    print(f"captured {image.width}x{image.height} -> {FRAME_FILE.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
