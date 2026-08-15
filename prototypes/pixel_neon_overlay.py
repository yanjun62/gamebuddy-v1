"""GameBuddy pixel-neon cyberpunk UI concept.

The prototype is deliberately disconnected from every production subsystem.
Typed messages and simulated replies live in memory only.
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


VOID = "#070711"
DEEP = "#0D0B1B"
PANEL = "#121025"
PANEL_2 = "#181332"
CYAN = "#27F2FF"
CYAN_DIM = "#116A78"
PINK = "#FF3BC8"
PINK_DIM = "#7B236B"
VIOLET = "#886BFF"
GOLD = "#FFC857"
TEXT = "#EAFBFF"
MUTED = "#8293AA"
GREEN = "#51FF9A"

PIXEL_FONT = ("Cascadia Mono", 9, "bold")
BODY_FONT = ("Microsoft YaHei UI", 10)


def cut_panel(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float,
              cut: float = 8, **kwargs: object) -> int:
    points = [x1 + cut, y1, x2, y1, x2, y2 - cut, x2 - cut, y2, x1, y2, x1, y1 + cut]
    return canvas.create_polygon(points, **kwargs)


class PixelNeonConcept:
    WIDTH = 460
    HEIGHT = 560
    ORB = 82

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("GameBuddy // PIXEL NEON CONCEPT")
        self.root.geometry(f"{self.WIDTH}x{self.HEIGHT}+72+120")
        self.root.configure(bg=VOID)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.97)
        self.root.overrideredirect(True)
        self.root.bind("<Escape>", lambda _event: self.root.destroy())
        self.drag_dx = 0
        self.drag_dy = 0
        self.compact = False

        self.shell = tk.Frame(root, bg=VOID, highlightbackground=CYAN_DIM, highlightthickness=1)
        self.shell.pack(fill="both", expand=True)
        self._build_header()
        self._build_chat()
        self._build_composer()
        self._seed_messages()

    def _build_header(self) -> None:
        self.header = tk.Canvas(self.shell, height=66, bg=DEEP, highlightthickness=0)
        self.header.pack(fill="x")
        self.header.create_rectangle(0, 0, 7, 65, fill=CYAN, outline="")
        self.header.create_rectangle(7, 0, 12, 65, fill=PINK, outline="")
        self._draw_pixel_bot(self.header, 38, 33, 1.05)
        self.header.create_text(72, 22, anchor="w", text="GAME//BUDDY",
                                fill=TEXT, font=("Cascadia Mono", 12, "bold"))
        self.header.create_text(72, 45, anchor="w", text="SULTAN_LINK  /  LIVE",
                                fill=CYAN, font=("Cascadia Mono", 8, "bold"))
        self.header.create_rectangle(254, 18, 260, 24, fill=GREEN, outline="")
        self.header.create_text(268, 21, anchor="w", text="SYNC 03/03",
                                fill=MUTED, font=("Cascadia Mono", 8))
        self.header.create_line(12, 64, self.WIDTH, 64, fill=CYAN_DIM)
        self.header.create_line(316, 64, 388, 64, fill=PINK, width=2)

        minimize = tk.Button(self.header, text="_", command=self.toggle_compact,
                             bg=DEEP, fg=CYAN, activebackground=PANEL_2,
                             activeforeground=TEXT, bd=0,
                             font=("Cascadia Mono", 12, "bold"), cursor="hand2")
        close = tk.Button(self.header, text="X", command=self.root.destroy,
                          bg=DEEP, fg=PINK, activebackground=PINK_DIM,
                          activeforeground=TEXT, bd=0,
                          font=("Cascadia Mono", 10, "bold"), cursor="hand2")
        self.header.create_window(396, 28, width=30, height=30, window=minimize)
        self.header.create_window(432, 28, width=30, height=30, window=close)
        self.header.bind("<ButtonPress-1>", self._drag_start)
        self.header.bind("<B1-Motion>", self._drag_move)

    def _build_chat(self) -> None:
        self.chat_holder = tk.Frame(self.shell, bg=VOID)
        self.chat_holder.pack(fill="both", expand=True)
        self.chat = tk.Canvas(self.chat_holder, bg=VOID, highlightthickness=0)
        self.scroll = tk.Scrollbar(self.chat_holder, orient="vertical", command=self.chat.yview,
                                   bd=0, width=7, troughcolor=VOID, bg=CYAN_DIM)
        self.chat.configure(yscrollcommand=self.scroll.set)
        self.chat.pack(side="left", fill="both", expand=True)
        self.scroll.pack(side="right", fill="y")
        self.chat.bind("<MouseWheel>", self._mousewheel)
        self.message_y = 18

        # Sparse CRT scanlines; kept subtle so Chinese text stays readable.
        for y in range(10, 440, 8):
            self.chat.create_line(0, y, self.WIDTH, y, fill="#0A0916")

    def _build_composer(self) -> None:
        self.composer = tk.Canvas(self.shell, height=78, bg=DEEP, highlightthickness=0)
        self.composer.pack(fill="x")
        self.composer.create_line(0, 1, 330, 1, fill=CYAN_DIM)
        self.composer.create_line(330, 1, self.WIDTH, 1, fill=PINK_DIM)
        cut_panel(self.composer, 15, 17, 357, 61, 7, fill=PANEL, outline=CYAN_DIM, width=1)
        self.composer.create_text(28, 39, text=">", fill=CYAN,
                                  font=("Cascadia Mono", 11, "bold"))
        self.entry = tk.Entry(self.composer, bd=0, bg=PANEL, fg=TEXT,
                              insertbackground=PINK, selectbackground=PINK_DIM,
                              font=BODY_FONT)
        self.entry.insert(0, "这张牌右边是不是有诈？")
        self.entry.bind("<Return>", self._send_local)
        self.composer.create_window(42, 39, width=254, height=28, anchor="w", window=self.entry)

        mic = tk.Button(self.composer, text="VOX", command=self._voice_hint,
                        bg=PANEL_2, fg=GOLD, activebackground="#2C2346",
                        activeforeground=TEXT, bd=0, font=PIXEL_FONT, cursor="hand2")
        send = tk.Button(self.composer, text="SEND", command=self._send_local,
                         bg=CYAN, fg=VOID, activebackground=PINK,
                         activeforeground=VOID, bd=0, font=PIXEL_FONT, cursor="hand2")
        self.composer.create_window(329, 39, width=46, height=28, window=mic)
        self.composer.create_window(405, 39, width=72, height=42, window=send)

    def _seed_messages(self) -> None:
        self.add_signal("FRAME BUFFER 03  //  MOTION DETECTED", CYAN)
        self.add_message("哦？这张牌的代价藏在第二行。\n先别点，我放大看看。", "buddy")
        self.add_message("我就知道右边有诈！", "player")
        self.add_message("抓到了。右边会多拿资源，\n但下一回合风险会叠两层。\n想稳住局面就选左边。", "buddy")
        self.add_signal("VOICE CHANNEL  //  READY", GOLD)

    def add_signal(self, text: str, color: str) -> None:
        y = self.message_y
        self.chat.create_line(24, y + 8, 44, y + 8, fill=color, width=2)
        self.chat.create_rectangle(48, y + 3, 54, y + 13, fill=color, outline="")
        self.chat.create_text(62, y + 8, anchor="w", text=text, fill=color,
                              font=("Cascadia Mono", 7, "bold"))
        self.message_y += 29
        self._scroll_bottom()

    def add_message(self, text: str, side: str) -> None:
        player = side == "player"
        top = self.message_y
        avatar_x = 420 if player else 30
        self._draw_player(self.chat, avatar_x, top + 18) if player else self._draw_pixel_bot(
            self.chat, avatar_x, top + 18, 0.72)

        text_x = 371 if player else 72
        anchor = "ne" if player else "nw"
        item = self.chat.create_text(text_x, top + 14, text=text, anchor=anchor,
                                     width=266, justify="left", fill=TEXT, font=BODY_FONT)
        bbox = self.chat.bbox(item)
        assert bbox is not None
        y1, y2 = bbox[1] - 10, bbox[3] + 11
        if player:
            x1, x2 = bbox[0] - 15, 386
            panel_fill, border, edge = "#25113A", PINK_DIM, PINK
        else:
            x1, x2 = 60, bbox[2] + 15
            panel_fill, border, edge = PANEL, CYAN_DIM, CYAN
        bubble = cut_panel(self.chat, x1, y1, x2, y2, 9,
                           fill=panel_fill, outline=border, width=1)
        self.chat.tag_lower(bubble, item)
        self.chat.create_rectangle(x1, y1 + 8, x1 + 3, y2 - 3, fill=edge, outline="")
        self.chat.create_rectangle(x2 - 19, y2 - 3, x2 - 5, y2, fill=edge, outline="")
        self.message_y = max(y2, top + 38) + 18
        self._scroll_bottom()

    def _draw_pixel_bot(self, canvas: tk.Canvas, cx: float, cy: float, scale: float) -> None:
        def rect(dx1: float, dy1: float, dx2: float, dy2: float, color: str) -> None:
            canvas.create_rectangle(cx + dx1 * scale, cy + dy1 * scale,
                                    cx + dx2 * scale, cy + dy2 * scale,
                                    fill=color, outline="")

        rect(-15, -14, 15, 14, PANEL_2)
        rect(-11, -10, 11, 9, "#211B43")
        rect(-7, -4, -2, 2, CYAN)
        rect(3, -4, 8, 2, PINK)
        rect(-4, 6, 5, 8, VIOLET)
        rect(-19, -6, -15, 7, CYAN_DIM)
        rect(15, -6, 19, 7, PINK_DIM)
        rect(-2, -19, 2, -14, GOLD)

    def _draw_player(self, canvas: tk.Canvas, cx: float, cy: float) -> None:
        canvas.create_rectangle(cx - 14, cy - 14, cx + 14, cy + 14,
                                fill="#38224F", outline=PINK_DIM)
        canvas.create_text(cx, cy, text="YOU", fill=PINK,
                           font=("Cascadia Mono", 6, "bold"))

    def _send_local(self, _event: tk.Event | None = None) -> str:
        text = self.entry.get().strip()
        if not text:
            return "break"
        self.entry.delete(0, "end")
        self.add_message(text, "player")
        self.root.after(500, lambda: self.add_message(
            "信号收到。这是本地模拟回复，\n真实弹幕链路仍处于断开状态。", "buddy"))
        return "break"

    def _voice_hint(self) -> None:
        self.add_signal("VOX DEMO ONLY  //  MIC DISCONNECTED", GOLD)

    def _scroll_bottom(self) -> None:
        self.chat.configure(scrollregion=(0, 0, self.WIDTH - 8, self.message_y + 12))
        self.root.after_idle(lambda: self.chat.yview_moveto(1.0))

    def toggle_compact(self) -> None:
        x, y = self.root.winfo_x(), self.root.winfo_y()
        if not self.compact:
            self.compact = True
            self.header.pack_forget()
            self.chat_holder.pack_forget()
            self.composer.pack_forget()
            self.root.geometry(f"{self.ORB}x{self.ORB}+{x}+{y}")
            self.orb = tk.Canvas(self.shell, bg=VOID, highlightthickness=0, cursor="hand2")
            self.orb.pack(fill="both", expand=True)
            cut_panel(self.orb, 7, 7, 75, 75, 12, fill=PANEL, outline=CYAN, width=2)
            self._draw_pixel_bot(self.orb, 41, 41, 1.25)
            self.orb.create_rectangle(62, 10, 72, 20, fill=PINK, outline="")
            self.orb.create_text(67, 15, text="3", fill=VOID,
                                 font=("Cascadia Mono", 6, "bold"))
            self.orb.bind("<Button-1>", lambda _event: self.toggle_compact())
            self.orb.bind("<ButtonPress-3>", self._drag_start)
            self.orb.bind("<B3-Motion>", self._drag_move)
        else:
            self.compact = False
            self.orb.destroy()
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
    PixelNeonConcept(root)
    root.mainloop()


if __name__ == "__main__":
    main()
