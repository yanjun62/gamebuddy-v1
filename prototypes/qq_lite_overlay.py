"""Standalone QQ-lite visual concept for GameBuddy.

This prototype is intentionally isolated from the production queue, heartbeat,
voice input, and screenshot pipeline. Messages typed here stay in memory only.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _configure_tk_runtime() -> None:
    """Help the checked-in Windows venv locate its bundled Tcl/Tk runtime."""
    roots = [Path(sys.base_prefix), Path(sys.prefix)]
    for root in roots:
        tcl = root / "tcl" / "tcl8.6"
        tk = root / "tcl" / "tk8.6"
        if tcl.is_dir() and tk.is_dir():
            os.environ["TCL_LIBRARY"] = str(tcl)
            os.environ["TK_LIBRARY"] = str(tk)
            return


_configure_tk_runtime()

import tkinter as tk  # noqa: E402  (runtime must be configured first)


BG = "#F3F6FA"
PANEL = "#FFFFFF"
LINE = "#E7ECF3"
TEXT = "#1E2732"
MUTED = "#7D8998"
BLUE = "#2E7CF6"
BLUE_DARK = "#1767DF"
INPUT_BG = "#EEF2F7"
BUDDY_BUBBLE = "#FFFFFF"
GREEN = "#36C66A"


def rounded_rect(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float,
                 radius: float, **kwargs: object) -> int:
    radius = min(radius, (x2 - x1) / 2, (y2 - y1) / 2)
    points = [
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs)


class GameBuddyConcept:
    WIDTH = 440
    FULL_HEIGHT = 590
    COMPACT_SIZE = 76

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("GameBuddy · QQ-lite Concept")
        self.root.geometry(f"{self.WIDTH}x{self.FULL_HEIGHT}+70+120")
        self.root.configure(bg=BG)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.98)
        self.root.overrideredirect(True)
        self.compact = False
        self.drag_x = 0
        self.drag_y = 0

        self.shell = tk.Frame(root, bg=BG, highlightbackground="#D9E1EC", highlightthickness=1)
        self.shell.pack(fill="both", expand=True)
        self._build_header()
        self._build_chat()
        self._build_composer()
        self._seed_demo()

        self.root.bind("<Escape>", lambda _event: self.root.destroy())

    def _build_header(self) -> None:
        self.header = tk.Canvas(self.shell, height=76, bg=PANEL, highlightthickness=0)
        self.header.pack(fill="x")
        self.header.create_line(0, 75, self.WIDTH, 75, fill=LINE)
        self.header.create_oval(18, 15, 64, 61, fill=BLUE, outline="")
        self.header.create_text(41, 38, text="G", fill="white", font=("Segoe UI", 18, "bold"))
        self.header.create_text(78, 29, text="GameBuddy", anchor="w", fill=TEXT,
                                font=("Microsoft YaHei UI", 12, "bold"))
        self.header.create_oval(79, 47, 87, 55, fill=GREEN, outline="")
        self.header.create_text(93, 51, text="正在陪玩 · 本地概念版", anchor="w", fill=MUTED,
                                font=("Microsoft YaHei UI", 8))

        self.min_button = tk.Button(self.header, text="—", command=self.toggle_compact,
                                    bg=PANEL, fg=MUTED, activebackground=INPUT_BG,
                                    bd=0, font=("Segoe UI", 13), cursor="hand2")
        self.header.create_window(365, 27, width=34, height=30, window=self.min_button)
        self.close_button = tk.Button(self.header, text="×", command=self.root.destroy,
                                      bg=PANEL, fg=MUTED, activebackground="#FFE8E8",
                                      activeforeground="#DD3B3B", bd=0,
                                      font=("Segoe UI", 15), cursor="hand2")
        self.header.create_window(407, 27, width=34, height=30, window=self.close_button)

        for widget in (self.header,):
            widget.bind("<ButtonPress-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._drag)

    def _build_chat(self) -> None:
        holder = tk.Frame(self.shell, bg=BG)
        holder.pack(fill="both", expand=True)
        self.chat_holder = holder
        self.chat = tk.Canvas(holder, bg=BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(holder, orient="vertical", command=self.chat.yview,
                                 bd=0, width=8)
        self.scrollbar = scrollbar
        self.chat.configure(yscrollcommand=scrollbar.set)
        self.chat.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.chat.bind("<MouseWheel>", self._on_mousewheel)
        self.message_y = 18

    def _build_composer(self) -> None:
        self.composer = tk.Canvas(self.shell, height=82, bg=PANEL, highlightthickness=0)
        self.composer.pack(fill="x")
        self.composer.create_line(0, 0, self.WIDTH, 0, fill=LINE)
        rounded_rect(self.composer, 16, 16, 356, 64, 22, fill=INPUT_BG, outline="")
        self.entry = tk.Entry(self.composer, bd=0, bg=INPUT_BG, fg=TEXT,
                              insertbackground=TEXT, font=("Microsoft YaHei UI", 10))
        self.entry.insert(0, "这个选择会影响后面吗？")
        self.entry.bind("<Return>", self._send_local)
        self.composer.create_window(32, 40, width=258, height=30, anchor="w", window=self.entry)

        mic = tk.Button(self.composer, text="MIC", command=self._show_mic_hint,
                        bg=INPUT_BG, fg=BLUE, activebackground="#E1E9F5", bd=0,
                        font=("Segoe UI", 7, "bold"), cursor="hand2")
        self.composer.create_window(326, 40, width=40, height=34, window=mic)
        send = tk.Button(self.composer, text="发送", command=self._send_local,
                         bg=BLUE, fg="white", activebackground=BLUE_DARK,
                         activeforeground="white", bd=0,
                         font=("Microsoft YaHei UI", 9, "bold"), cursor="hand2")
        self.composer.create_window(397, 40, width=62, height=42, window=send)

    def _seed_demo(self) -> None:
        self.add_chip("今天 16:07 · Sultan's Game")
        self.add_message("我看到你打开了苏丹的游戏。现在是事件选择界面，先别急着点。", "buddy")
        self.add_message("这张牌应该怎么选？", "player")
        self.add_message(
            "左边偏稳，能保住资源。\n右边收益更高，但会增加风险。\n如果这轮求稳，我会选左边。",
            "buddy",
        )
        self.add_chip("画面已更新 · 已读取最近 3 张截图", accent=True)

    def add_chip(self, text: str, accent: bool = False) -> None:
        fill = "#E7F0FF" if accent else "#E8EDF4"
        color = BLUE_DARK if accent else MUTED
        item = self.chat.create_text(self.WIDTH / 2 - 4, self.message_y + 12, text=text,
                                     fill=color, font=("Microsoft YaHei UI", 8))
        bbox = self.chat.bbox(item)
        assert bbox is not None
        pad_x, pad_y = 12, 6
        bg = rounded_rect(self.chat, bbox[0] - pad_x, bbox[1] - pad_y,
                          bbox[2] + pad_x, bbox[3] + pad_y, 12,
                          fill=fill, outline="")
        self.chat.tag_lower(bg, item)
        self.message_y = bbox[3] + pad_y + 18
        self._refresh_scroll()

    def add_message(self, text: str, side: str) -> None:
        is_player = side == "player"
        avatar_x = 398 if is_player else 34
        bubble_right = 378 if is_player else 330
        bubble_left = 110 if is_player else 62
        anchor = "ne" if is_player else "nw"
        text_x = bubble_right - 15 if is_player else bubble_left + 15
        fill = "white" if is_player else TEXT
        bubble_fill = BLUE if is_player else BUDDY_BUBBLE

        self.chat.create_oval(avatar_x - 18, self.message_y, avatar_x + 18, self.message_y + 36,
                              fill="#AAB6C5" if is_player else BLUE, outline="")
        self.chat.create_text(avatar_x, self.message_y + 18, text="你" if is_player else "G",
                              fill="white", font=("Microsoft YaHei UI", 9, "bold"))

        text_item = self.chat.create_text(text_x, self.message_y + 13, text=text, anchor=anchor,
                                          width=238, justify="left", fill=fill,
                                          font=("Microsoft YaHei UI", 10))
        bbox = self.chat.bbox(text_item)
        assert bbox is not None
        y1, y2 = bbox[1] - 11, bbox[3] + 11
        if is_player:
            x1, x2 = bbox[0] - 15, bubble_right
        else:
            x1, x2 = bubble_left, bbox[2] + 15
        bubble = rounded_rect(self.chat, x1, y1, x2, y2, 16,
                              fill=bubble_fill, outline="#E8EDF3" if not is_player else "",
                              width=1)
        self.chat.tag_lower(bubble, text_item)
        self.message_y = max(y2, self.message_y + 36) + 17
        self._refresh_scroll()

    def _refresh_scroll(self) -> None:
        self.chat.configure(scrollregion=(0, 0, self.WIDTH - 10, self.message_y + 12))
        self.root.after_idle(lambda: self.chat.yview_moveto(1.0))

    def _send_local(self, _event: tk.Event | None = None) -> str:
        text = self.entry.get().strip()
        if not text:
            return "break"
        self.entry.delete(0, "end")
        self.add_message(text, "player")
        self.root.after(450, lambda: self.add_message(
            "收到。这条只是原型里的本地假回复，不会写入真实消息队列。", "buddy"))
        return "break"

    def _show_mic_hint(self) -> None:
        self.add_chip("语音按钮仅作视觉演示 · 未连接麦克风")

    def toggle_compact(self) -> None:
        if not self.compact:
            self.compact = True
            x, y = self.root.winfo_x(), self.root.winfo_y()
            self.chat_holder.pack_forget()
            self.composer.pack_forget()
            self.header.pack_forget()
            self.root.geometry(f"{self.COMPACT_SIZE}x{self.COMPACT_SIZE}+{x}+{y}")
            self.shell.configure(bg=BLUE, highlightbackground="#B9D2FA")
            self.compact_canvas = tk.Canvas(self.shell, bg=BLUE, highlightthickness=0,
                                            cursor="hand2")
            self.compact_canvas.pack(fill="both", expand=True)
            self.compact_canvas.create_oval(9, 9, 67, 67, fill="white", outline="")
            self.compact_canvas.create_text(38, 38, text="G", fill=BLUE,
                                            font=("Segoe UI", 23, "bold"))
            self.compact_canvas.create_oval(56, 54, 68, 66, fill=GREEN,
                                            outline=BLUE, width=2)
            self.compact_canvas.bind("<Button-1>", lambda _event: self.toggle_compact())
            self.compact_canvas.bind("<ButtonPress-3>", self._start_drag)
            self.compact_canvas.bind("<B3-Motion>", self._drag)
        else:
            self.compact = False
            x, y = self.root.winfo_x(), self.root.winfo_y()
            self.compact_canvas.destroy()
            self.root.geometry(f"{self.WIDTH}x{self.FULL_HEIGHT}+{x}+{y}")
            self.shell.configure(bg=BG, highlightbackground="#D9E1EC")
            self.header.pack(fill="x", before=self.chat_holder)
            self.chat_holder.pack(fill="both", expand=True, before=self.composer)
            self.composer.pack(fill="x")

    def _start_drag(self, event: tk.Event) -> None:
        self.drag_x = event.x_root - self.root.winfo_x()
        self.drag_y = event.y_root - self.root.winfo_y()

    def _drag(self, event: tk.Event) -> None:
        self.root.geometry(f"+{event.x_root - self.drag_x}+{event.y_root - self.drag_y}")

    def _on_mousewheel(self, event: tk.Event) -> None:
        self.chat.yview_scroll(int(-event.delta / 120), "units")


def main() -> None:
    root = tk.Tk()
    GameBuddyConcept(root)
    root.mainloop()


if __name__ == "__main__":
    main()
