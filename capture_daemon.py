"""Capture only the configured game window into current_frame.jpg.

Modes:
- local_snapshot (default): keep the newest local JPEG; no image leaves the machine.
- remote_vision: also send the frame to an OpenAI-compatible vision endpoint and
  write description.txt.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from bridge_protocol import atomic_write_text
from game_knowledge import core_term_hint
from screen_capture import capture_region, find_game_window, image_as_base64, resize_image, save_jpeg_atomic


ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / "config.json"
FRAME_FILE = ROOT / "current_frame.jpg"
FRAME_HISTORY_DIR = ROOT / "frame_history"
DESCRIPTION_FILE = ROOT / "description.txt"


DEFAULT_VISION_PROMPT = """你正在看一个游戏截图。用中文简洁描述：
1. 当前场景、对话、战斗或菜单状态；
2. 可辨认的角色名和关键台词；
3. 所有可选项或按钮；
4. 画面情绪和氛围。
不要猜测看不清的内容。这段描述将用于生成实时游戏伙伴回复。"""


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    value = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def load_vision_prompt(config: dict) -> str:
    game = str(config.get("current_game", "")).strip()
    if game:
        prompt_file = ROOT / "knowledge" / game / "vision_prompt.txt"
        if prompt_file.exists():
            custom = prompt_file.read_text(encoding="utf-8").strip()
            if custom:
                prompt = f"{custom}\n\n---\n以下为通用要求：\n{DEFAULT_VISION_PROMPT}"
                hint = core_term_hint(config)
                return f"{prompt}\n\n当前游戏核心术语：{hint}" if hint else prompt
    hint = core_term_hint(config)
    return f"{DEFAULT_VISION_PROMPT}\n\n当前游戏核心术语：{hint}" if hint else DEFAULT_VISION_PROMPT


def get_api_client(config: dict):
    api_key = str(config.get("vision_api_key", ""))
    if not api_key or api_key.startswith("YOUR_"):
        raise RuntimeError("remote_vision 模式需要在本地 config.json 设置 vision_api_key")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("remote_vision 模式缺少 openai 包") from exc
    return OpenAI(
        base_url=str(config.get("vision_base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")),
        api_key=api_key,
    )


def describe_screen(client, model: str, image_b64: str, prompt: str) -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                ],
            }
        ],
        max_tokens=500,
    )
    return (response.choices[0].message.content or "").strip()


def save_history_frame(image, *, max_edge: int, quality: int, keep: int) -> Path:
    """Save one immutable frame and keep a small rolling local history."""
    FRAME_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    path = FRAME_HISTORY_DIR / f"frame_{time.time_ns()}.jpg"
    save_jpeg_atomic(image, path, max_edge=max_edge, quality=quality)
    frames = sorted(FRAME_HISTORY_DIR.glob("frame_*.jpg"))
    for old_path in frames[:-keep]:
        old_path.unlink(missing_ok=True)
    return path


def main() -> int:
    try:
        config = load_config()
    except (OSError, json.JSONDecodeError) as exc:
        print(f"❌ config.json 无法读取: {exc}")
        return 1

    mode = str(config.get("capture_mode", "local_snapshot"))
    if mode not in {"local_snapshot", "remote_vision"}:
        print("❌ capture_mode 只能是 local_snapshot 或 remote_vision")
        return 1
    title = str(config.get("game_window_title", "")).strip()
    if not title:
        print("❌ 请先在 config.json 设置 game_window_title；未截图，以免捕获桌面隐私")
        return 1

    interval = max(1.0, float(config.get("capture_interval", 10)))
    history_size = max(3, int(config.get("capture_history_size", 6)))
    max_edge = int(config.get("capture_max_edge", 1920))
    quality = int(config.get("capture_jpeg_quality", 82))
    try:
        client = get_api_client(config) if mode == "remote_vision" else None
    except RuntimeError as exc:
        print(f"❌ {exc}")
        return 1
    model = str(config.get("vision_model", "qwen3.5-omni-plus"))
    prompt = load_vision_prompt(config)

    print(
        f"[GameBuddy] 截图进程已启动：{mode}，目标窗口“{title}”，"
        f"间隔 {interval:g}s，保留最近 {history_size} 帧"
    )
    if mode == "local_snapshot":
        print("[Privacy] 仅保存本地最新帧，不调用视觉 API")

    frame = 0
    last_description = ""
    missing_reported = False
    try:
        while True:
            region = find_game_window(title)
            if region is None:
                if not missing_reported:
                    print("[Skip] 未找到目标游戏窗口；已跳过截图，不会退回主屏幕")
                    missing_reported = True
                time.sleep(interval)
                continue
            missing_reported = False

            try:
                image = resize_image(capture_region(region), max_edge)
                save_jpeg_atomic(image, FRAME_FILE, max_edge=max_edge, quality=quality)
                history_path = save_history_frame(
                    image,
                    max_edge=max_edge,
                    quality=quality,
                    keep=history_size,
                )
                frame += 1
                if mode == "remote_vision":
                    description = describe_screen(client, model, image_as_base64(image, quality=quality), prompt)
                    if description and description != last_description:
                        atomic_write_text(DESCRIPTION_FILE, description)
                        last_description = description
                print(
                    f"[Snap] #{frame} {image.width}x{image.height} → "
                    f"{FRAME_FILE.name} + {history_path.name}"
                )
            except Exception as exc:
                print(f"[Error] 截图失败: {exc}")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("👋 Capture Daemon 已停止")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
