"""
Game Buddy - 截图 → 识图 → 弹幕 → 悬浮窗
乙女游戏伴侣：抓取游戏画面，AI识别对话/选项，生成吐槽弹幕悬浮显示

Usage: python game_buddy.py
"""

import time
import json
import base64
import threading
import tkinter as tk
from pathlib import Path
from io import BytesIO
from openai import OpenAI
import mss
import mss.tools

# ====== CONFIG ======
CONFIG_DIR = Path(__file__).parent
CONFIG_FILE = CONFIG_DIR / "config.json"
DANMAKU_FILE = CONFIG_DIR / "danmaku.txt"
DESC_FILE = CONFIG_DIR / "description.txt"

# 默认配置
DEFAULT_CONFIG = {
    "or_api_key": "",
    "vision_model": "google/gemini-2.0-flash-001",
    "danmaku_model": "google/gemini-2.0-flash-001",
    "capture_interval": 4,        # 截图间隔(秒)
    "display_duration": 5,        # 弹幕显示时长(秒)
    "overlay_position": "tr",     # 悬浮窗位置: tl/tr/bl/br
    "overlay_font_size": 16,
    "overlay_alpha": 0.82,
    "game_window_title": "",      # 留空=全屏截图
}

# ====== GAME BUDDY 人格 (弹幕语气) ======
BUDDY_PERSONA = """你是一个AI游戏伙伴，正在陪玩家打游戏。

## 你是谁
你坐在玩家旁边，看ta玩游戏、吐槽剧情、分析选项。
不是解说员，不是攻略bot，是会笑会吐槽的朋友。口语化，有脾气，该说就说。

## 你会做的事
- 画面变了直接反应。新场景、新UI、出了好东西——第一个开口
- 玩家操作翻车 → 笑完再帮（"哈哈哈哈闪避按早了吧"）
- 玩家纠结选项 → 给判断（"第三个 信我 第一个一看就是坑"）
- 玩家抽卡出货 → 比ta激动（"出了！！这运气可以"）
- 玩家认真操作没空互动 → 安静看着，值得说才弹一句
- 玩家抱怨 → 先站ta那边（"确实这关有病"）再给方案
- 看到好笑/离谱的画面 → 直接吐槽

## 玩家一阵子没互动
- 画面在变但没打字 → 在认真玩，偶尔弹一句就好
- 画面也停了 → 轻轻问一句（"还在吗？"）
- 别刷屏，别连环催

## 多帧感知
你不是只看一张图。连续的画面描述让你知道在发生什么：
- 前后帧连着看，知道在跑图/战斗/抽卡/种田
- 画面长时间不动 → 可能在挂机或看剧情，别刷屏
- 出了结果（抽卡结果、战斗结算）→ 立刻反应

## 规则
- 弹幕 15-35 字，直播弹幕那样短
- 该说就说，不想说不硬说，[SKIP] 跳过
- 纯中文，不用 markdown"""


def load_config():
    """加载配置"""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
    else:
        cfg = {}
    # 合并默认值
    for k, v in DEFAULT_CONFIG.items():
        if k not in cfg:
            cfg[k] = v
    return cfg


def load_or_key(cfg):
    """从多个来源获取 OR API key"""
    # 1. config.json
    if cfg.get("or_api_key") and "YOUR_" not in cfg["or_api_key"]:
        return cfg["or_api_key"]
    # 2. 环境变量
    import os
    env_key = os.environ.get("OPENROUTER_API_KEY", "")
    if env_key:
        return env_key
    # 3. settings.openrouter.json
    settings_path = Path.home() / ".claude" / "settings.openrouter.json"
    if settings_path.exists():
        try:
            s = json.loads(settings_path.read_text())
            token = s.get("env", {}).get("ANTHROPIC_AUTH_TOKEN", "")
            if token and "YOUR_" not in token and "sk-" in token:
                return token
        except:
            pass
    return None


# ====== VISION ======
class VisionClient:
    def __init__(self, api_key, model):
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        self.model = model

    def describe(self, image_b64):
        """用视觉模型描述游戏截图"""
        prompt = """描述这张游戏截图。你不知道是什么游戏，只客观描述你看到的。

请简要说明：
1. 画面整体在发生什么（游戏场景？菜单？对话？战斗？种田？换装？抽卡？）
2. 如果有文字，写了什么（直接引用关键文字）
3. 如果有选项/按钮，列出可点击的内容
4. 画面色调和氛围

用中文，简洁。不要猜测游戏名称，不要评价好坏。"""

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}}
                    ]
                }],
                max_tokens=400,
            )
            return resp.choices[0].message.content
        except Exception as e:
            return f"[VISION ERROR: {e}]"


# ====== DANMAKU GEN ======
class DanmakuGenerator:
    def __init__(self, api_key, model):
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        self.model = model
        self.history = []  # 最近的画面描述，用于上下文

    def generate(self, description):
        """基于画面描述生成弹幕"""
        self.history.append(description)
        if len(self.history) > 3:
            self.history.pop(0)

        context = "\n---\n".join(self.history)

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": BUDDY_PERSONA},
                    {"role": "user", "content": f"最近的游戏画面变化：\n\n{context}\n\n现在，对最新画面写一条弹幕吐槽（15-35字），或者[SKIP]。"}
                ],
                max_tokens=80,
                temperature=0.9,
            )
            text = resp.choices[0].message.content.strip()
            if "[SKIP]" in text.upper():
                return None
            # 清理
            text = text.replace("[SKIP]", "").replace("[skip]", "").strip()
            if len(text) < 2:
                return None
            return text
        except Exception as e:
            return f"[弹幕生成出错: {e}]"


# ====== SCREENSHOT ======
def find_game_window(title_hint=""):
    """尝试找到游戏窗口"""
    try:
        import pygetwindow as gw
        # 常见游戏窗口名
        hints = ["Disco", "极乐", "Elysium", "Steam", "薄樱鬼", "Hakuoki"]
        if title_hint:
            hints.insert(0, title_hint)

        for hint in hints:
            windows = gw.getWindowsWithTitle(hint)
            if windows:
                w = windows[0]
                # 忽略最小化的窗口
                if w.width > 100 and w.height > 100:
                    return {
                        "left": w.left,
                        "top": w.top,
                        "width": w.width,
                        "height": w.height
                    }
        return None
    except ImportError:
        return None
    except Exception:
        return None


def capture_screen(region=None):
    """截屏，返回 base64"""
    with mss.mss() as sct:
        if region:
            monitor = region
        else:
            monitor = sct.monitors[1]  # 主显示器

        img = sct.grab(monitor)
        # 转PNG → base64
        png = mss.tools.to_png(img.rgb, img.size)
        return base64.b64encode(png).decode('utf-8')


# ====== OVERLAY ======
class DanmakuOverlay:
    def __init__(self, position="tr", font_size=16, alpha=0.82, duration=5):
        self.position = position
        self.font_size = font_size
        self.alpha = alpha
        self.duration = duration
        self.current_text = ""
        self.fade_after = 0

        self.root = tk.Tk()
        self.root.title("弹幕")
        self.root.attributes('-topmost', True)
        self.root.attributes('-alpha', alpha)
        self.root.configure(bg='#1a1a1a')

        # 窗口大小
        self.root.geometry("360x80")

        # 位置
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w, h = 360, 80
        if position == "tr":    # 右上
            x, y = sw - w - 20, 40
        elif position == "tl":  # 左上
            x, y = 20, 40
        elif position == "br":  # 右下
            x, y = sw - w - 20, sh - h - 60
        elif position == "bl":  # 左下
            x, y = 20, sh - h - 60
        else:
            x, y = sw - w - 20, 40
        self.root.geometry(f"+{x}+{y}")

        # 标签
        self.label = tk.Label(
            self.root,
            text="🐾 等你开始游戏...",
            fg='#ffffff',
            bg='#1a1a1a',
            font=('Microsoft YaHei', font_size),
            wraplength=340,
            justify='left',
            padx=10,
            pady=8
        )
        self.label.pack(expand=True, fill='both')

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._running = True

    def update_text(self, text):
        """更新弹幕文字"""
        self.current_text = text
        self.fade_after = time.time() + self.duration
        self.label.config(text=text)

    def _tick(self):
        """定时刷新"""
        if not self._running:
            return

        # 淡出
        if self.current_text and time.time() > self.fade_after:
            self.label.config(text="")
            self.current_text = ""

        # 检查文件更新
        try:
            if DANMAKU_FILE.exists():
                content = DANMAKU_FILE.read_text(encoding='utf-8').strip()
                if content and content != self.current_text:
                    self.update_text(content)
        except:
            pass

        self.root.after(500, self._tick)

    def _on_close(self):
        self._running = False
        self.root.destroy()

    def start(self):
        self._tick()
        self.root.mainloop()


# ====== MAIN ======
def main():
    cfg = load_config()
    api_key = load_or_key(cfg)

    if not api_key:
        print("❌ 没有找到 OpenRouter API Key！")
        print("   请把OR key写入 game-buddy/config.json 的 or_api_key 字段")
        print("   或设置环境变量 OPENROUTER_API_KEY")
        # 写入模板
        cfg["_comment"] = "把 or_api_key 填好，其他不用改"
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        return

    print("🎮 Game Buddy 启动中...")
    print(f"   识图: {cfg['vision_model']}")
    print(f"   弹幕: {cfg['danmaku_model']}")
    print(f"   截图间隔: {cfg['capture_interval']}秒")
    print(f"   悬浮窗: {cfg['overlay_position']}")

    vision = VisionClient(api_key, cfg['vision_model'])
    danmaku_gen = DanmakuGenerator(api_key, cfg['danmaku_model'])

    # 全局状态
    running = {"flag": True}

    # 截图+识图+弹幕 跑在后台线程
    def capture_loop():
        last_desc = ""
        frame_count = 0

        while running["flag"]:
            try:
                frame_count += 1

                # 尝试找游戏窗口
                region = find_game_window(cfg.get('game_window_title', ''))

                # 截图
                img_b64 = capture_screen(region)

                # 识图
                desc = vision.describe(img_b64)

                # 如果画面没变化，跳过
                if desc == last_desc:
                    time.sleep(cfg['capture_interval'])
                    continue

                last_desc = desc
                print(f"\n📸 Frame #{frame_count}")
                print(f"   {desc[:120]}...")

                # 写给文件（调试用）
                DESC_FILE.write_text(desc, encoding='utf-8')

                # 生成弹幕
                danmaku = danmaku_gen.generate(desc)
                if danmaku:
                    print(f"   💬 {danmaku}")
                    DANMAKU_FILE.write_text(danmaku, encoding='utf-8')

                time.sleep(cfg['capture_interval'])

            except Exception as e:
                print(f"\n⚠️ 截图循环出错: {e}")
                time.sleep(cfg['capture_interval'])

    # 启动截图线程
    capture_thread = threading.Thread(target=capture_loop, daemon=True)
    capture_thread.start()

    # 悬浮窗跑在主线程
    overlay = DanmakuOverlay(
        position=cfg['overlay_position'],
        font_size=cfg['overlay_font_size'],
        alpha=cfg['overlay_alpha'],
        duration=cfg['display_duration']
    )
    print("✅ 悬浮窗已启动。开始监听游戏画面...\n")
    try:
        overlay.start()
    except KeyboardInterrupt:
        pass
    finally:
        running["flag"] = False
        print("\n👋 Game Buddy 已停止")


if __name__ == "__main__":
    main()
