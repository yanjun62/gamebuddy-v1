"""
Danmaku Overlay - 悬浮弹幕 + 聊天输入
上方聊天历史，底部输入框，右键关闭。

Usage: python danmaku_overlay.py
"""

import time
import tkinter as tk
from pathlib import Path

CONFIG_DIR = Path(__file__).parent
DANMAKU_FILE = CONFIG_DIR / "danmaku.txt"
MESSAGE_FILE = CONFIG_DIR / "message.txt"
HISTORY_FILE = CONFIG_DIR / "chat_history.txt"


def load_config():
    import json
    cfg_file = CONFIG_DIR / "config.json"
    if cfg_file.exists():
        return json.loads(cfg_file.read_text(encoding='utf-8'))
    return {}


class ChatOverlay:
    def __init__(self, position="tr", font_size=12, alpha=0.85, duration=6):
        self.font_size = font_size
        self.alpha = alpha
        self.duration = duration
        self.last_danmaku = ""
        self.last_message = ""

        self.root = tk.Tk()
        self.root.title("Ash")
        self.root.attributes('-topmost', True)
        self.root.attributes('-alpha', alpha)
        self.root.configure(bg='#0d0d0d')

        w, h = 400, 380
        self.root.geometry(f"{w}x{h}")
        self.root.resizable(True, True)
        self.root.minsize(300, 200)

        # 定位
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        positions = {
            "tr": (sw - w - 15, 20),
            "tl": (15, 20),
            "br": (sw - w - 15, sh - h - 50),
            "bl": (15, sh - h - 50),
        }
        x, y = positions.get(position, positions["tr"])
        self.root.geometry(f"+{x}+{y}")

        # === 输入框（先 pack，锁定底部空间） ===
        input_frame = tk.Frame(self.root, bg='#1a1a1a', height=36)
        input_frame.pack(fill='x', side='bottom', before=None)
        input_frame.pack_propagate(False)

        self.entry = tk.Entry(
            input_frame,
            font=('Microsoft YaHei', 11),
            bg='#2a2a2a',
            fg='#ffffff',
            insertbackground='#ffffff',
            relief='flat',
            bd=8
        )
        self.entry.pack(fill='both', side='left', expand=True, padx=(6, 2), pady=3)
        self.entry.bind('<Return>', self._send_message)
        self.entry.focus_set()

        send_btn = tk.Button(
            input_frame,
            text='→',
            command=self._send_message,
            font=('Microsoft YaHei', 10, 'bold'),
            bg='#3a3a3a',
            fg='#ffffff',
            relief='flat',
            padx=10,
            bd=0,
            activebackground='#555555',
            activeforeground='#ffffff',
            cursor='hand2'
        )
        send_btn.pack(fill='y', side='right', padx=(2, 6), pady=3)

        # === 聊天历史区（填充剩余空间） ===
        self.history = tk.Text(
            self.root,
            font=('Microsoft YaHei', font_size),
            bg='#0d0d0d',
            fg='#d0d0d0',
            wrap='word',
            relief='flat',
            padx=10,
            pady=6,
            state='disabled',
            cursor='arrow'
        )
        self.history.pack(fill='both', expand=True, side='top')

        # 配置标签样式
        self.history.tag_config('ash', foreground='#a8d8ea', font=('Microsoft YaHei', font_size, 'bold'))
        self.history.tag_config('kate', foreground='#f0c0c0', font=('Microsoft YaHei', font_size))
        self.history.tag_config('system', foreground='#888888', font=('Microsoft YaHei', font_size - 1))
        self.history.tag_config('timestamp', foreground='#555555', font=('Microsoft YaHei', 9))

        # 初始内容
        self._append("🐾 Ash 在看你玩。打字聊天，右键关闭。\n", 'system')

        # 加载历史
        self._load_history()

        # 右键退出
        self.root.bind("<Button-3>", lambda e: self.root.destroy())
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._running = True

    def _append(self, text, tag=None):
        """追加文字到历史区"""
        self.history.config(state='normal')
        if tag:
            self.history.insert('end', text, tag)
        else:
            self.history.insert('end', text)
        self.history.see('end')
        self.history.config(state='disabled')

    def _load_history(self):
        """加载已有聊天记录"""
        if HISTORY_FILE.exists():
            try:
                lines = HISTORY_FILE.read_text(encoding='utf-8').strip().split('\n')
                for line in lines[-50:]:  # 最近50条
                    if line.startswith('[Ash]'):
                        self._append(line[5:] + '\n', 'ash')
                    elif line.startswith('[Kate]'):
                        self._append(line[6:] + '\n', 'kate')
                    elif line.startswith('[系统]'):
                        self._append(line[4:] + '\n', 'system')
            except:
                pass

    def _save_to_history(self, speaker, text):
        """追加一条到历史文件"""
        ts = time.strftime('%H:%M')
        line = f"[{speaker}] [{ts}] {text}\n"
        try:
            with open(HISTORY_FILE, 'a', encoding='utf-8') as f:
                f.write(line)
        except:
            pass

    def _send_message(self, event=None):
        """发送消息 → message.txt"""
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, 'end')

        # 显示自己的消息
        self._append(f'{text}\n', 'kate')
        self._save_to_history('Kate', text)

        # 写入 message.txt 给 Ash 读
        MESSAGE_FILE.write_text(text, encoding='utf-8')

    def _on_close(self):
        self._running = False
        self.root.destroy()

    def _tick(self):
        if not self._running:
            return

        # 检查 danmaku.txt（Ash 回复）
        try:
            if DANMAKU_FILE.exists():
                content = DANMAKU_FILE.read_text(encoding='utf-8').strip()
                if content and content != self.last_danmaku:
                    self.last_danmaku = content
                    # 延迟写入历史，避免卡UI
                    self.root.after(200, lambda c=content: self._save_to_history('Ash', c))
                    self._append(f'{content}\n', 'ash')
        except:
            pass

        self.root.after(1500, self._tick)

    def start(self):
        self._tick()
        self.root.mainloop()


def main():
    cfg = load_config()
    overlay = ChatOverlay(
        position=cfg.get("overlay_position", "tr"),
        font_size=cfg.get("overlay_font_size", 12),
        alpha=cfg.get("overlay_alpha", 0.85),
        duration=cfg.get("display_duration", 6),
    )
    print("🎬 聊天弹幕窗已启动（右键关闭，可拖动调整大小）")
    overlay.start()


if __name__ == "__main__":
    main()
