"""
Capture Daemon - 截图 + 视觉模型识图 → description.txt
支持硅基流动 / OpenRouter 等 OpenAI 兼容 API。

Usage: python capture_daemon.py
"""

import time
import json
import base64
from pathlib import Path
from openai import OpenAI
import mss
import mss.tools

CONFIG_DIR = Path(__file__).parent
CONFIG_FILE = CONFIG_DIR / "config.json"
DESC_FILE = CONFIG_DIR / "description.txt"


def load_config():
    cfg = {}
    if CONFIG_FILE.exists():
        cfg = json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
    return cfg


def get_api_client(cfg):
    """从配置初始化 OpenAI client"""
    api_key = cfg.get("vision_api_key", "")
    base_url = cfg.get("vision_base_url", "https://api.siliconflow.cn/v1")
    model = cfg.get("vision_model", "Qwen/Qwen3.5-9B")

    if not api_key or "YOUR_" in api_key:
        # 兼容旧配置
        api_key = cfg.get("or_api_key", "")
        base_url = "https://openrouter.ai/api/v1"
        model = cfg.get("vision_model", "google/gemini-2.0-flash-001")

    if not api_key or "YOUR_" in api_key:
        return None, model

    client = OpenAI(base_url=base_url, api_key=api_key)
    return client, model


def find_game_window(title_hint=""):
    try:
        import pygetwindow as gw
        hints = ["Disco", "极乐", "Elysium", "Hakuoki", "薄樱鬼", "Steam"]
        if title_hint:
            hints.insert(0, title_hint)

        for hint in hints:
            windows = gw.getWindowsWithTitle(hint)
            if windows:
                w = windows[0]
                if w.width > 100 and w.height > 100:
                    return {"left": w.left, "top": w.top,
                            "width": w.width, "height": w.height}
        return None
    except Exception:
        return None


def capture_screen(region=None):
    with mss.mss() as sct:
        monitor = region if region else sct.monitors[1]
        img = sct.grab(monitor)
        png = mss.tools.to_png(img.rgb, img.size)
        return base64.b64encode(png).decode('utf-8')


def load_vision_prompt(cfg):
    """Load game-specific vision prompt from knowledge/<game>/vision_prompt.txt"""
    game = cfg.get("current_game", "")
    if game:
        prompt_file = CONFIG_DIR / "knowledge" / game / "vision_prompt.txt"
        if prompt_file.exists():
            extra = prompt_file.read_text(encoding="utf-8").strip()
            if extra:
                return extra
    return ""


DEFAULT_VISION_PROMPT = """你正在看一个文字RPG游戏（极乐迪斯科或类似的文字RPG）的截图。用中文描述。

请覆盖：
1. 当前在发生什么？对话？选项？菜单？场景描述？
2. 如果有对话，角色名+说了什么（直接引用关键台词）
3. 如果有选项，列出所有选项编号和文字
4. 画面情绪/氛围

简洁但不要遗漏。这段描述将用于生成实时弹幕吐槽。"""


def describe_screen(client, model, image_b64, game_prompt=""):
    if game_prompt:
        prompt = game_prompt + "\n\n---\n以下为通用要求：\n" + DEFAULT_VISION_PROMPT
    else:
        prompt = DEFAULT_VISION_PROMPT

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/png;base64,{image_b64}"}}
                ]
            }],
            max_tokens=500,
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"[识图失败: {e}]"


def main():
    cfg = load_config()
    client, model = get_api_client(cfg)

    if client is None:
        print("❌ 没找到 API Key！填 vision_api_key 到 config.json")
        return

    interval = cfg.get("capture_interval", 4)

    game_prompt = load_vision_prompt(cfg)
    game_name = cfg.get("current_game", "无")
    print(f"[GameBuddy] Capture Daemon 启动")
    print(f"   游戏: {game_name}")
    print(f"   API: {cfg.get('vision_base_url', 'siliconflow')}")
    print(f"   模型: {model}")
    print(f"   间隔: {interval}s → {DESC_FILE}")
    if game_prompt:
        print(f"   [OK] 已加载 {game_name} 专属 vision prompt")
    print(f"   [Paused]  默认暂停 | [回车] 拍一张 | 再按[回车]切换自动 | [Ctrl+C] 退出")
    print()

    last_desc = ""
    frame = 0
    paused = True  # 默认暂停，按回车才截一张

    def check_input():
        """非阻塞检查键盘输入"""
        import sys
        if sys.platform == 'win32':
            import msvcrt
            while msvcrt.kbhit():
                ch = msvcrt.getch()
                if ch == b'\r':
                    return True
        else:
            import select
            if select.select([sys.stdin], [], [], 0)[0]:
                sys.stdin.readline()
                return True
        return False

    try:
        while True:
            # 检查暂停切换
            if check_input():
                paused = not paused
                # 清空输入缓冲，防止 Enter 残留字符导致连续触发
                import sys
                if sys.platform == 'win32':
                    import msvcrt
                    while msvcrt.kbhit():
                        msvcrt.getch()
                if paused:
                    print("[Paused]  已暂停。按回车继续截图。")
                else:
                    print("▶️  已恢复自动截图")

            if paused:
                time.sleep(0.3)
                continue

            frame += 1
            region = find_game_window(cfg.get("game_window_title", ""))
            img_b64 = capture_screen(region)
            desc = describe_screen(client, model, img_b64, game_prompt)

            if desc == last_desc:
                time.sleep(interval)
                continue

            last_desc = desc
            DESC_FILE.write_text(desc, encoding='utf-8')

            print(f"[Snap] #{frame} 已更新")
            print(f"   {desc[:150]}...\n")

            time.sleep(interval)

    except KeyboardInterrupt:
        print("👋 Capture Daemon 已停止")


if __name__ == "__main__":
    main()
