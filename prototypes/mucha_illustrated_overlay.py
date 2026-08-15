"""Illustrated Art Nouveau GameBuddy prototype using a generated lithograph asset.

This concept intentionally displays only the three most recent messages and is
disconnected from all production queues, capture, voice, heartbeat, and bridge
state. Local input is never persisted.
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
from PIL import Image, ImageOps, ImageTk  # noqa: E402


ASSET_ROOT = Path(__file__).resolve().parent / "assets"


def load_project_fonts() -> bool:
    """Register bundled OFL fonts privately for this Windows process only."""
    if sys.platform != "win32":
        return False
    import ctypes

    font_paths = (
        ASSET_ROOT / "fonts" / "great-vibes" / "GreatVibes-Regular.ttf",
        ASSET_ROOT / "fonts" / "lxgw-wenkai" / "LXGWWenKai-Regular.ttf",
    )
    return all(
        path.is_file() and ctypes.windll.gdi32.AddFontResourceExW(str(path), 0x10, 0)
        for path in font_paths
    )


PROJECT_FONTS_READY = load_project_fonts()
TITLE_FAMILY = "Great Vibes" if PROJECT_FONTS_READY else "Gabriola"
BODY_FAMILY = "LXGW WenKai" if PROJECT_FONTS_READY else "KaiTi"


INK = "#35291F"
PAPER = "#F0E0BC"
PAPER_LIGHT = "#F7ECD2"
GOLD = "#9D732D"
GOLD_LIGHT = "#CCAA62"
SAGE = "#596F60"
SAGE_CARD = "#D8DCC3"
ROSE = "#98565C"
ROSE_CARD = "#E5C7BD"
TEAL = "#345F5B"
MUTED = "#716354"


def arch_card(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float,
              fill: str, outline: str, tag: str) -> int:
    shoulder = 12
    points = [
        x1, y1 + shoulder,
        x1 + 5, y1 + 5,
        x1 + shoulder, y1,
        x2 - shoulder, y1,
        x2 - 5, y1 + 5,
        x2, y1 + shoulder,
        x2, y2 - 7,
        x2 - 7, y2,
        x1 + 7, y2,
        x1, y2 - 7,
    ]
    return canvas.create_polygon(points, smooth=True, splinesteps=24,
                                 fill=fill, outline=outline, width=1, tags=tag)


class IllustratedMuchaConcept:
    WIDTH = 448
    HEIGHT = 672
    ORB = 90

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("GameBuddy · Illustrated Art Nouveau")
        self.root.geometry(f"{self.WIDTH}x{self.HEIGHT}+76+82")
        self.root.configure(bg=INK)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.985)
        self.root.overrideredirect(True)
        self.root.bind("<Escape>", lambda _event: self.root.destroy())
        self.drag_dx = 0
        self.drag_dy = 0
        self.compact = False

        asset = ASSET_ROOT / "mucha-frame-v1.png"
        self.source = Image.open(asset).convert("RGB")
        fitted = ImageOps.fit(self.source, (self.WIDTH, self.HEIGHT), method=Image.Resampling.LANCZOS)
        self.background = ImageTk.PhotoImage(fitted)

        self.canvas = tk.Canvas(root, width=self.WIDTH, height=self.HEIGHT,
                                highlightthickness=0, bg=PAPER)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_image(0, 0, anchor="nw", image=self.background, tags="base")
        self._build_chrome()
        self._build_composer()

        self.messages: list[tuple[str, str]] = [
            ("花纹已经替你揭开了一点秘密。\n那张牌并不像表面那样温顺。", "buddy"),
            ("右边的奖励实在很诱人。", "player"),
            ("它会带来更多财富，\n也会让下一回合蒙上两重阴影。\n若今夜求稳，便选择左边吧。", "buddy"),
        ]
        self.render_messages()

    def _build_chrome(self) -> None:
        # The generated empty medallion becomes the companion identity.
        self.canvas.create_text(75, 116, text="GB", fill=TEAL,
                                font=(TITLE_FAMILY, 24), tags="chrome")
        self.canvas.create_text(75, 137, text="COMPANION", fill=GOLD,
                                font=("Georgia", 6, "bold"), tags="chrome")

        self.canvas.create_text(224, 199, text="Game Buddy",
                                fill=INK, font=(TITLE_FAMILY, 30), tags="chrome")
        self.canvas.create_line(88, 228, 175, 228, fill=GOLD_LIGHT, tags="chrome")
        self.canvas.create_oval(181, 225, 187, 231, fill=TEAL, outline="", tags="chrome")
        self.canvas.create_text(224, 228, text="命 运 旁 白", fill=TEAL,
                                font=(BODY_FAMILY, 9), tags="chrome")
        self.canvas.create_oval(261, 225, 267, 231, fill=TEAL, outline="", tags="chrome")
        self.canvas.create_line(273, 228, 360, 228, fill=GOLD_LIGHT, tags="chrome")

        minimize = tk.Button(self.canvas, text="—", command=self.toggle_compact,
                             bg="#E8D4AA", fg=GOLD, activebackground=PAPER_LIGHT,
                             activeforeground=INK, bd=0, font=("Georgia", 10), cursor="hand2")
        close = tk.Button(self.canvas, text="×", command=self.root.destroy,
                          bg="#E8D4AA", fg=ROSE, activebackground=ROSE_CARD,
                          activeforeground=INK, bd=0, font=("Georgia", 12), cursor="hand2")
        self.canvas.create_window(402, 17, width=25, height=22, window=minimize, tags="chrome")
        self.canvas.create_window(429, 17, width=25, height=22, window=close, tags="chrome")

        self.canvas.bind("<ButtonPress-1>", self._drag_start)
        self.canvas.bind("<B1-Motion>", self._drag_move)

    def _build_composer(self) -> None:
        self.entry = tk.Entry(self.canvas, bd=0, bg="#F2E3BF", fg=INK,
                              insertbackground=ROSE, selectbackground=ROSE_CARD,
                              font=(BODY_FAMILY, 10))
        self.entry.insert(0, "命运会偏爱哪一种选择？")
        self.entry.bind("<Return>", self._send_local)
        self.canvas.create_window(88, 611, width=225, height=28,
                                  anchor="w", window=self.entry, tags="composer")

        voice = tk.Button(self.canvas, text="耳语", command=self._voice_hint,
                          bg=SAGE, fg=PAPER_LIGHT, activebackground=TEAL,
                          activeforeground="white", bd=0,
                          font=(BODY_FAMILY, 9, "bold"), cursor="hand2")
        send = tk.Button(self.canvas, text="寄语", command=self._send_local,
                         bg=ROSE, fg=PAPER_LIGHT, activebackground=TEAL,
                         activeforeground="white", bd=0,
                         font=(BODY_FAMILY, 9, "bold"), cursor="hand2")
        self.canvas.create_window(332, 611, width=44, height=27, window=voice, tags="composer")
        self.canvas.create_window(386, 611, width=52, height=31, window=send, tags="composer")
        self.canvas.create_text(224, 647, text="THREE VISIONS REMEMBERED  ·  LOCAL CONCEPT",
                                fill=MUTED, font=("Georgia", 5, "italic"), tags="composer")

    def render_messages(self) -> None:
        self.canvas.delete("message")
        visible = self.messages[-3:]
        if not self._draw_message_set(visible):
            self.canvas.delete("message")
            self._draw_message_set(self.messages[-2:])

    def _draw_message_set(self, messages: list[tuple[str, str]]) -> bool:
        y = 247
        for text, side in messages:
            player = side == "player"
            avatar_x = 386 if player else 62
            text_x = 348 if player else 95
            anchor = "ne" if player else "nw"
            item = self.canvas.create_text(text_x, y + 14, text=text, anchor=anchor,
                                           width=235, justify="left", fill=INK,
                                           font=(BODY_FAMILY, 10), tags="message")
            bbox = self.canvas.bbox(item)
            assert bbox is not None
            y1, y2 = bbox[1] - 10, bbox[3] + 11
            if player:
                x1, x2 = bbox[0] - 14, 364
                fill, border = ROSE_CARD, ROSE
            else:
                x1, x2 = 82, bbox[2] + 14
                fill, border = SAGE_CARD, SAGE
            card = arch_card(self.canvas, x1, y1, x2, y2, fill, border, "message")
            self.canvas.tag_lower(card, item)
            self._draw_seal(avatar_x, y1 + 20, player)
            self.canvas.create_line(x1 + 13, y2 - 4, x1 + 27, y2 - 4,
                                    fill=border, width=2, tags="message")
            self.canvas.create_oval(x1 + 25, y2 - 7, x1 + 31, y2 - 1,
                                    fill=border, outline="", tags="message")
            y = max(y2, y + 40) + 15
        return y <= 555

    def _draw_seal(self, cx: float, cy: float, player: bool) -> None:
        outer = ROSE if player else GOLD
        inner = ROSE if player else TEAL
        self.canvas.create_oval(cx - 16, cy - 16, cx + 16, cy + 16,
                                fill=PAPER_LIGHT, outline=outer, width=2, tags="message")
        self.canvas.create_oval(cx - 12, cy - 12, cx + 12, cy + 12,
                                fill=inner, outline=GOLD_LIGHT, tags="message")
        self.canvas.create_text(cx, cy, text="你" if player else "GB",
                                fill=PAPER_LIGHT,
                                font=((BODY_FAMILY, 8, "bold") if player
                                      else (TITLE_FAMILY, 11)), tags="message")

    def _send_local(self, _event: tk.Event | None = None) -> str:
        text = self.entry.get().strip()
        if not text:
            return "break"
        self.entry.delete(0, "end")
        self.messages.append((text, "player"))
        self.render_messages()
        self.root.after(550, self._fake_reply)
        return "break"

    def _fake_reply(self) -> None:
        self.messages.append(("我听见了。这句话只停留在原型中，\n尚未寄往真实弹幕。", "buddy"))
        self.render_messages()

    def _voice_hint(self) -> None:
        self.messages.append(("耳语通道尚在沉睡；这里只展示它醒来后的模样。", "buddy"))
        self.render_messages()

    def toggle_compact(self) -> None:
        x, y = self.root.winfo_x(), self.root.winfo_y()
        if not self.compact:
            self.compact = True
            self.canvas.pack_forget()
            self.root.geometry(f"{self.ORB}x{self.ORB}+{x}+{y}")
            crop = self.source.crop((48, 180, 340, 472))
            crop = ImageOps.fit(crop, (self.ORB, self.ORB), method=Image.Resampling.LANCZOS)
            self.orb_image = ImageTk.PhotoImage(crop)
            self.orb = tk.Canvas(self.root, width=self.ORB, height=self.ORB,
                                 highlightthickness=1, highlightbackground=GOLD, cursor="hand2")
            self.orb.pack(fill="both", expand=True)
            self.orb.create_image(0, 0, anchor="nw", image=self.orb_image)
            self.orb.create_text(45, 45, text="GB", fill=TEAL,
                                 font=(TITLE_FAMILY, 20))
            self.orb.create_oval(68, 7, 84, 23, fill=ROSE, outline=GOLD_LIGHT)
            self.orb.create_text(76, 15, text="3", fill=PAPER_LIGHT,
                                 font=("Georgia", 8, "bold"))
            self.orb.bind("<Button-1>", lambda _event: self.toggle_compact())
            self.orb.bind("<ButtonPress-3>", self._drag_start)
            self.orb.bind("<B3-Motion>", self._drag_move)
        else:
            self.compact = False
            self.orb.destroy()
            self.root.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}")
            self.canvas.pack(fill="both", expand=True)

    def _drag_start(self, event: tk.Event) -> None:
        # Buttons and the entry retain their own click behavior.
        if isinstance(event.widget, (tk.Button, tk.Entry)):
            return
        self.drag_dx = event.x_root - self.root.winfo_x()
        self.drag_dy = event.y_root - self.root.winfo_y()

    def _drag_move(self, event: tk.Event) -> None:
        if self.drag_dx or self.drag_dy:
            self.root.geometry(f"+{event.x_root - self.drag_dx}+{event.y_root - self.drag_dy}")


def main() -> None:
    root = tk.Tk()
    IllustratedMuchaConcept(root)
    root.mainloop()


if __name__ == "__main__":
    main()
