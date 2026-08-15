"""GameBuddy Art Nouveau / Mucha-inspired visual concept.

This is a self-contained visual prototype. It never touches the production
message queue, screenshots, voice input, heartbeat, or bridge state.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def configure_tk() -> None:
    for root in dict.fromkeys((Path(sys.base_prefix), Path(sys.prefix), Path(sys.executable).resolve().parent)):
        tcl = root / "tcl" / "tcl8.6"
        tk = root / "tcl" / "tk8.6"
        if tcl.is_dir() and tk.is_dir():
            os.environ["TCL_LIBRARY"] = str(tcl)
            os.environ["TK_LIBRARY"] = str(tk)
            return


configure_tk()

import tkinter as tk  # noqa: E402


INK = "#342B26"
PAPER = "#EFE3C7"
PAPER_LIGHT = "#F8F0DC"
PAPER_DARK = "#D8C59E"
GOLD = "#A67B32"
GOLD_LIGHT = "#D4B66E"
SAGE = "#73836F"
SAGE_LIGHT = "#DCE0CB"
ROSE = "#9F5E64"
ROSE_LIGHT = "#E8CFCA"
TEAL = "#416E6A"
MUTED = "#74685C"


def arch_panel(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float,
               shoulder: float = 16, **kwargs: object) -> int:
    """A soft arched card with the characteristic Nouveau shoulder curve."""
    points = [
        x1, y1 + shoulder,
        x1 + 5, y1 + 5,
        x1 + shoulder, y1,
        x2 - shoulder, y1,
        x2 - 5, y1 + 5,
        x2, y1 + shoulder,
        x2, y2 - 8,
        x2 - 8, y2,
        x1 + 8, y2,
        x1, y2 - 8,
    ]
    return canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs)


class MuchaConcept:
    WIDTH = 460
    HEIGHT = 590
    MEDALLION = 86

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("GameBuddy · Art Nouveau Concept")
        self.root.geometry(f"{self.WIDTH}x{self.HEIGHT}+76+116")
        self.root.configure(bg=INK)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.98)
        self.root.overrideredirect(True)
        self.root.bind("<Escape>", lambda _event: self.root.destroy())
        self.drag_dx = 0
        self.drag_dy = 0
        self.compact = False

        self.shell = tk.Frame(root, bg=PAPER, highlightbackground=GOLD, highlightthickness=2)
        self.shell.pack(fill="both", expand=True)
        self._build_header()
        self._build_chat()
        self._build_composer()
        self._seed_messages()

    def _build_header(self) -> None:
        self.header = tk.Canvas(self.shell, height=112, bg=PAPER, highlightthickness=0)
        self.header.pack(fill="x")
        self._paper_texture(self.header, 112)

        # Poster arch and double-rule frame.
        self.header.create_arc(18, 7, 442, 190, start=0, extent=180,
                               style="arc", outline=GOLD, width=2)
        self.header.create_arc(24, 13, 436, 184, start=0, extent=180,
                               style="arc", outline=GOLD_LIGHT, width=1)
        self.header.create_line(18, 77, 18, 106, fill=GOLD, width=2)
        self.header.create_line(442, 77, 442, 106, fill=GOLD, width=2)
        self.header.create_line(28, 105, 432, 105, fill=GOLD)

        self._draw_flower(self.header, 52, 48, 1.0, ROSE)
        self._draw_flower(self.header, 408, 48, 1.0, TEAL)
        self._draw_monogram(self.header, 104, 54, 0.92)
        self.header.create_text(230, 39, text="GAME BUDDY", fill=INK,
                                font=("Georgia", 18, "bold"))
        self.header.create_text(230, 65, text="A COMPANION FOR STRANGE TALES",
                                fill=TEAL, font=("Georgia", 7, "bold"))
        self.header.create_text(230, 88, text="《苏丹的游戏》 · 三幕画面已阅",
                                fill=MUTED, font=("Microsoft YaHei UI", 8))

        minimize = tk.Button(self.header, text="—", command=self.toggle_compact,
                             bg=PAPER, fg=GOLD, activebackground=PAPER_LIGHT,
                             activeforeground=INK, bd=0, font=("Georgia", 11), cursor="hand2")
        close = tk.Button(self.header, text="×", command=self.root.destroy,
                          bg=PAPER, fg=ROSE, activebackground=ROSE_LIGHT,
                          activeforeground=INK, bd=0, font=("Georgia", 13), cursor="hand2")
        self.header.create_window(399, 88, width=28, height=25, window=minimize)
        self.header.create_window(428, 88, width=28, height=25, window=close)
        self.header.bind("<ButtonPress-1>", self._drag_start)
        self.header.bind("<B1-Motion>", self._drag_move)

    def _build_chat(self) -> None:
        self.chat_holder = tk.Frame(self.shell, bg=PAPER_LIGHT)
        self.chat_holder.pack(fill="both", expand=True)
        self.chat = tk.Canvas(self.chat_holder, bg=PAPER_LIGHT, highlightthickness=0)
        self.scroll = tk.Scrollbar(self.chat_holder, orient="vertical", command=self.chat.yview,
                                   width=8, bd=0, troughcolor=PAPER, bg=GOLD_LIGHT)
        self.chat.configure(yscrollcommand=self.scroll.set)
        self.chat.pack(side="left", fill="both", expand=True)
        self.scroll.pack(side="right", fill="y")
        self.chat.bind("<MouseWheel>", self._mousewheel)
        self._paper_texture(self.chat, 620)
        self.chat.create_line(14, 0, 14, 620, fill=GOLD_LIGHT)
        self.chat.create_line(20, 0, 20, 620, fill=PAPER_DARK)
        self.chat.create_line(434, 0, 434, 620, fill=GOLD_LIGHT)
        self.chat.create_line(440, 0, 440, 620, fill=PAPER_DARK)
        self.message_y = 18

    def _build_composer(self) -> None:
        self.composer = tk.Canvas(self.shell, height=82, bg=PAPER, highlightthickness=0)
        self.composer.pack(fill="x")
        self._paper_texture(self.composer, 82)
        self.composer.create_line(18, 2, 442, 2, fill=GOLD, width=2)
        self.composer.create_line(30, 7, 430, 7, fill=GOLD_LIGHT)
        arch_panel(self.composer, 18, 20, 354, 64, 11,
                   fill=PAPER_LIGHT, outline=GOLD_LIGHT, width=1)
        self.composer.create_text(36, 42, text="✦", fill=GOLD,
                                  font=("Georgia", 11))
        self.entry = tk.Entry(self.composer, bd=0, bg=PAPER_LIGHT, fg=INK,
                              insertbackground=ROSE, selectbackground=ROSE_LIGHT,
                              font=("Microsoft YaHei UI", 10))
        self.entry.insert(0, "命运会偏爱哪一种选择？")
        self.entry.bind("<Return>", self._send_local)
        self.composer.create_window(52, 42, width=244, height=28, anchor="w", window=self.entry)

        voice = tk.Button(self.composer, text="声", command=self._voice_hint,
                          bg=SAGE, fg=PAPER_LIGHT, activebackground=TEAL,
                          activeforeground="white", bd=0,
                          font=("Microsoft YaHei UI", 9, "bold"), cursor="hand2")
        send = tk.Button(self.composer, text="寄语", command=self._send_local,
                         bg=ROSE, fg=PAPER_LIGHT, activebackground=TEAL,
                         activeforeground="white", bd=0,
                         font=("Microsoft YaHei UI", 9, "bold"), cursor="hand2")
        self.composer.create_window(327, 42, width=36, height=28, window=voice)
        self.composer.create_window(405, 42, width=70, height=42, window=send)

    def _seed_messages(self) -> None:
        self.add_divider("第三幕 · 命运之牌")
        self.add_message("我看见牌面上的花纹变了。\n代价藏得很漂亮，也很危险。", "buddy")
        self.add_message("右边看起来更诱人。", "player")
        self.add_message("右边会得到更多财富，\n却也让下一回合蒙上两层阴影。\n今夜若求安稳，便选左边吧。", "buddy")
        self.add_divider("耳语通道已静候", accent=True)

    def add_divider(self, text: str, accent: bool = False) -> None:
        y = self.message_y + 9
        color = ROSE if accent else TEAL
        self.chat.create_line(56, y, 136, y, fill=GOLD_LIGHT)
        self.chat.create_line(300, y, 380, y, fill=GOLD_LIGHT)
        self.chat.create_oval(143, y - 3, 149, y + 3, fill=color, outline="")
        self.chat.create_oval(287, y - 3, 293, y + 3, fill=color, outline="")
        self.chat.create_text(218, y, text=text, fill=color,
                              font=("Microsoft YaHei UI", 8))
        self.message_y += 30
        self._scroll_bottom()

    def add_message(self, text: str, side: str) -> None:
        player = side == "player"
        top = self.message_y
        avatar_x = 407 if player else 47
        if player:
            self._draw_player_seal(self.chat, avatar_x, top + 23)
        else:
            self._draw_monogram(self.chat, avatar_x, top + 23, 0.58)

        text_x = 368 if player else 78
        anchor = "ne" if player else "nw"
        text_item = self.chat.create_text(text_x, top + 15, text=text, anchor=anchor,
                                          width=260, justify="left", fill=INK,
                                          font=("Microsoft YaHei UI", 10))
        bbox = self.chat.bbox(text_item)
        assert bbox is not None
        y1, y2 = bbox[1] - 11, bbox[3] + 12
        if player:
            x1, x2 = bbox[0] - 16, 382
            fill, border, sprig = ROSE_LIGHT, ROSE, ROSE
        else:
            x1, x2 = 68, bbox[2] + 16
            fill, border, sprig = SAGE_LIGHT, SAGE, TEAL
        card = arch_panel(self.chat, x1, y1, x2, y2, 13,
                          fill=fill, outline=border, width=1)
        self.chat.tag_lower(card, text_item)
        self.chat.create_line(x1 + 14, y2 - 5, x1 + 29, y2 - 5,
                              fill=sprig, width=2)
        self.chat.create_oval(x1 + 27, y2 - 8, x1 + 33, y2 - 2,
                              fill=sprig, outline="")
        self.message_y = max(y2, top + 46) + 18
        self._scroll_bottom()

    def _draw_monogram(self, canvas: tk.Canvas, cx: float, cy: float, scale: float) -> None:
        r1, r2 = 26 * scale, 21 * scale
        canvas.create_oval(cx - r1, cy - r1, cx + r1, cy + r1,
                           fill=PAPER_LIGHT, outline=GOLD, width=2)
        canvas.create_oval(cx - r2, cy - r2, cx + r2, cy + r2,
                           fill=TEAL, outline=GOLD_LIGHT)
        canvas.create_text(cx, cy, text="GB", fill=PAPER_LIGHT,
                           font=("Georgia", max(7, int(11 * scale)), "bold"))

    def _draw_player_seal(self, canvas: tk.Canvas, cx: float, cy: float) -> None:
        canvas.create_oval(cx - 19, cy - 19, cx + 19, cy + 19,
                           fill=ROSE_LIGHT, outline=ROSE, width=2)
        canvas.create_oval(cx - 14, cy - 14, cx + 14, cy + 14,
                           fill=ROSE, outline=GOLD_LIGHT)
        canvas.create_text(cx, cy, text="你", fill=PAPER_LIGHT,
                           font=("Microsoft YaHei UI", 8, "bold"))

    def _draw_flower(self, canvas: tk.Canvas, cx: float, cy: float,
                     scale: float, color: str) -> None:
        for dx, dy in ((0, -12), (11, -4), (7, 10), (-7, 10), (-11, -4)):
            canvas.create_oval(cx + (dx - 6) * scale, cy + (dy - 8) * scale,
                               cx + (dx + 6) * scale, cy + (dy + 8) * scale,
                               fill=PAPER_LIGHT, outline=color, width=1)
        canvas.create_oval(cx - 6 * scale, cy - 6 * scale,
                           cx + 6 * scale, cy + 6 * scale,
                           fill=GOLD_LIGHT, outline=GOLD)
        canvas.create_line(cx, cy + 15 * scale, cx - 9 * scale, cy + 35 * scale,
                           cx + 2 * scale, cy + 47 * scale,
                           smooth=True, fill=SAGE, width=2)

    def _paper_texture(self, canvas: tk.Canvas, height: int) -> None:
        for y in range(9, height, 17):
            canvas.create_line(0, y, self.WIDTH, y, fill="#EBDDCA")

    def _send_local(self, _event: tk.Event | None = None) -> str:
        text = self.entry.get().strip()
        if not text:
            return "break"
        self.entry.delete(0, "end")
        self.add_message(text, "player")
        self.root.after(550, lambda: self.add_message(
            "你的话语已落在纸上。\n这里只是原型，并未寄往真实弹幕。", "buddy"))
        return "break"

    def _voice_hint(self) -> None:
        self.add_divider("语音仅作陈列 · 尚未聆听", accent=True)

    def _scroll_bottom(self) -> None:
        self.chat.configure(scrollregion=(0, 0, self.WIDTH - 8, max(620, self.message_y + 14)))
        self.root.after_idle(lambda: self.chat.yview_moveto(1.0))

    def toggle_compact(self) -> None:
        x, y = self.root.winfo_x(), self.root.winfo_y()
        if not self.compact:
            self.compact = True
            self.header.pack_forget()
            self.chat_holder.pack_forget()
            self.composer.pack_forget()
            self.root.geometry(f"{self.MEDALLION}x{self.MEDALLION}+{x}+{y}")
            self.medallion = tk.Canvas(self.shell, bg=PAPER, highlightthickness=0, cursor="hand2")
            self.medallion.pack(fill="both", expand=True)
            self._draw_monogram(self.medallion, 43, 43, 1.35)
            self.medallion.create_oval(66, 9, 79, 22, fill=ROSE, outline=GOLD_LIGHT)
            self.medallion.create_text(72.5, 15.5, text="3", fill=PAPER_LIGHT,
                                        font=("Georgia", 7, "bold"))
            self.medallion.bind("<Button-1>", lambda _event: self.toggle_compact())
            self.medallion.bind("<ButtonPress-3>", self._drag_start)
            self.medallion.bind("<B3-Motion>", self._drag_move)
        else:
            self.compact = False
            self.medallion.destroy()
            self.root.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}")
            self.header.pack(fill="x")
            self.chat_holder.pack(fill="both", expand=True)
            self.composer.pack(fill="x")

    def _drag_start(self, event: tk.Event) -> None:
        self.drag_dx = event.x_root - self.root.winfo_x()
        self.drag_dy = event.y_root - self.root.winfo_y()

    def _drag_move(self, event: tk.Event) -> None:
        self.root.geometry(f"+{event.x_root - self.drag_dx}+{event.y_root - self.drag_dy}")

    def _mousewheel(self, event: tk.Event) -> None:
        self.chat.yview_scroll(int(-event.delta / 120), "units")


def main() -> None:
    root = tk.Tk()
    MuchaConcept(root)
    root.mainloop()


if __name__ == "__main__":
    main()
