"""
Auto-snap — 每分钟自动截图+识图 → description.txt
Ctrl+C 退出。

Usage: python snap.py
"""

import time
import json
from pathlib import Path
from openai import OpenAI
from screen_capture import capture_region, find_game_window as find_configured_window, image_as_base64

CONFIG_DIR = Path(__file__).parent
DESC_FILE = CONFIG_DIR / "description.txt"


def main():
    cfg = json.loads((CONFIG_DIR / "config.json").read_text(encoding='utf-8'))
    client = OpenAI(
        base_url=cfg.get("vision_base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        api_key=cfg["vision_api_key"],
    )
    model = cfg.get("vision_model", "qwen3.5-omni-plus")
    interval = cfg.get("capture_interval", 5)
    title = str(cfg.get("game_window_title", "")).strip()
    if not title:
        print("❌ 请先设置 game_window_title；未截图，以免捕获桌面隐私")
        return

    print(f"🎮 Auto-snap 启动（每{interval}秒）→ {DESC_FILE}")
    print("   Ctrl+C 退出\n")

    # Load game-specific vision prompt
    game = cfg.get("current_game", "")
    game_prompt = ""
    if game:
        prompt_file = CONFIG_DIR / "knowledge" / game / "vision_prompt.txt"
        if prompt_file.exists():
            game_prompt = prompt_file.read_text(encoding="utf-8").strip()
            if game_prompt:
                print(f"   ✅ 已加载 {cfg['current_game']} 专属 vision prompt")

    DEFAULT_PROMPT = """用中文描述这个文字RPG游戏截图：
1. 当前场景/对话/选项？
2. 角色和台词（引述关键对话）
3. 可选选项的文字
4. 氛围情绪
简洁，200字以内。这段描述将用于生成实时弹幕。"""

    if game_prompt:
        prompt = game_prompt + "\n\n---\n以下为通用要求：\n" + DEFAULT_PROMPT
    else:
        prompt = DEFAULT_PROMPT

    last_desc = ""
    frame = 0

    try:
        while True:
            frame += 1
            region = find_configured_window(title)
            if region is None:
                print("⚠️ 未找到目标游戏窗口；跳过截图")
                time.sleep(interval)
                continue
            img_b64 = image_as_base64(capture_region(region), image_format="PNG")

            resp = client.chat.completions.create(
                model=model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
                    ]
                }],
                max_tokens=400,
            )
            desc = resp.choices[0].message.content

            if desc == last_desc:
                time.sleep(interval)
                continue

            last_desc = desc
            DESC_FILE.write_text(desc, encoding='utf-8')
            print(f"📸 #{frame} {desc[:100]}...")

            time.sleep(interval)

    except KeyboardInterrupt:
        print("👋 Auto-snap 已停止")


if __name__ == "__main__":
    main()
