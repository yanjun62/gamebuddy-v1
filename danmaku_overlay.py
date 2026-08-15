"""Game Buddy floating chat overlay with reliable queue and local voice input."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Optional

from PIL import Image, ImageOps, ImageTk

from bridge_protocol import BASE_DIR, DANMAKU_FILE, append_message, atomic_write_json
from game_knowledge import (
    SPOILER_LABELS,
    build_game_context,
    discover_profiles,
    load_credits,
    selected_profile_id,
)
from overlay_themes import (
    DEFAULT_THEME_ID,
    RoundIconButton,
    draw_message_bubble,
    get_theme,
    gradient_steps,
    theme_choices,
    ui_font_family,
)


CONFIG_FILE = BASE_DIR / "config.json"
HISTORY_FILE = BASE_DIR / "chat_history.txt"
STATUS_FILE = BASE_DIR / "direct_codex_status.json"
BRIDGE_FILE = BASE_DIR / "direct_codex_bridge.js"
HISTORY_TIMESTAMP_RE = re.compile(r"^\[\d{1,2}:\d{2}\]\s*")
DEFAULT_WINDOW_SIZE = (340, 520)
MIN_WINDOW_SIZE = (300, 380)
WINDOW_CORNER_RADIUS = 16
HEADER_HEIGHT = 44
HEADER_GRADIENT_HEIGHT = 4
WORDMARK_BY_THEME = {
    "pixel-farm": "gamebuddy-pixel-v1.png",
    "candlelit-codex": "gamebuddy-retro-v1.png",
    "crimson-memory": "gamebuddy-retro-v1.png",
    "gilded-court": "gamebuddy-retro-v1.png",
    "synthetic-detective": "gamebuddy-scifi-v1.png",
    "holographic-star-map": "gamebuddy-scifi-v1.png",
    "crystal-fantasy": "gamebuddy-scifi-v1.png",
    "elysian-world": "gamebuddy-retro-v1.png",
}
THEMES_WITH_BACKGROUND = frozenset(WORDMARK_BY_THEME)


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        value = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"config.json 无法读取: {exc}") from exc
    return value if isinstance(value, dict) else {}


def normalized_display_name(value: object, fallback: str) -> str:
    name = str(value or "").strip()
    return name or fallback


def update_display_names(config: dict, player_name: object, buddy_name: object) -> None:
    config["player_name"] = normalized_display_name(player_name, "我")
    config["buddy_name"] = normalized_display_name(buddy_name, "陪玩")


def strip_history_timestamp(text: str) -> str:
    return HISTORY_TIMESTAMP_RE.sub("", text, count=1)


def wordmark_name_for_theme(theme_id: str) -> str | None:
    return WORDMARK_BY_THEME.get(theme_id)


def effective_window_alpha(theme_id: str, requested: float) -> float:
    if theme_id in THEMES_WITH_BACKGROUND:
        return 1.0
    return max(0.25, min(1.0, requested))


def has_message_text(value: object) -> bool:
    return bool(str(value or "").strip())


def bounded_window_size(width: int, height: int) -> tuple[int, int]:
    return max(MIN_WINDOW_SIZE[0], width), max(MIN_WINDOW_SIZE[1], height)


def corner_ellipse_diameter(width: int, height: int) -> int:
    return max(2, min(WINDOW_CORNER_RADIUS * 2, width, height))


def bridge_status_presentation(status: str, previous: str | None = None) -> tuple[str, bool]:
    if status == "ready" and previous in {"starting", "retrying", "error"}:
        return "Codex 已恢复连接", False
    labels = {
        "starting": "Codex 连接中…",
        "ready": "Codex 已连接",
        "thinking": "Codex 正在回复…",
        "retrying": "Codex 连接波动，正在自动重试…",
        "error": "Codex 直连异常",
        "stopped": "Codex 直连已停止",
    }
    return labels.get(status, str(status)), status == "error"


class ChatOverlay:
    def __init__(self, config: dict):
        self.config = config
        self.font_size = int(config.get("overlay_font_size", 12))
        self.theme = get_theme(str(config.get("overlay_theme", DEFAULT_THEME_ID)))
        self._message_records: list[tuple[str, str]] = []
        self._running = True
        self._bridge_process: Optional[subprocess.Popen] = None
        self._voice_busy = False
        self._last_danmaku_mtime_ns = 0
        self._last_status_mtime_ns = 0
        self._last_bridge_status: str | None = None
        self._profile_rows = discover_profiles(config)

        self.root = tk.Tk()
        self.ui_font_family = ui_font_family(self.root)
        self.root.title("Game Buddy")
        if sys.platform == "win32":
            self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        requested_alpha = float(config.get("overlay_alpha", 0.85))
        self.root.attributes(
            "-alpha",
            1.0 if sys.platform == "darwin" else effective_window_alpha(self.theme.id, requested_alpha),
        )
        self.root.configure(bg=self.theme.window_bg)

        width, height = DEFAULT_WINDOW_SIZE
        self.root.geometry(f"{width}x{height}")
        self.root.resizable(True, True)
        self.root.minsize(*MIN_WINDOW_SIZE)
        self._window_drag_offset = (0, 0)
        self._resize_origin = (0, 0, width, height)
        self._rounding_after_id: Optional[str] = None
        self._rounded_window_key: Optional[tuple[int, int, int]] = None
        self._position_window(str(config.get("overlay_position", "tr")), width, height)
        self._build_header()

        self.input_frame = tk.Frame(self.root, bg=self.theme.input_bg, height=50)
        self.input_frame.pack(fill="x", side="bottom")
        self.input_frame.pack_propagate(False)

        self.entry_var = tk.StringVar()
        self.entry = tk.Entry(
            self.input_frame,
            textvariable=self.entry_var,
            font=(self.ui_font_family, 11),
            bg=self.theme.entry_bg,
            fg=self.theme.entry_fg,
            insertbackground=self.theme.accent,
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.theme.buddy_border,
            highlightcolor=self.theme.accent,
            bd=8,
        )
        self.entry.pack(fill="both", side="left", expand=True, padx=(10, 4), pady=7)
        self.entry.bind("<Return>", self._send_message)

        self.mic_button = RoundIconButton(
            self.input_frame,
            icon="mic",
            command=self._start_voice_input,
            size=28,
            background=self.theme.input_bg,
            fill=self.theme.entry_bg,
            foreground=self.theme.accent,
            border=self.theme.buddy_border,
            active_fill=self.theme.button_active,
        )

        self.menu_button = RoundIconButton(
            self.input_frame,
            icon="menu",
            command=self._open_settings,
            size=28,
            background=self.theme.input_bg,
            fill=self.theme.entry_bg,
            foreground=self.theme.accent,
            border=self.theme.buddy_border,
            active_fill=self.theme.button_active,
        )

        self.send_button = RoundIconButton(
            self.input_frame,
            icon="send",
            command=self._send_message,
            size=30,
            background=self.theme.input_bg,
            fill=self.theme.accent,
            foreground="#FFFFFF",
            border=self.theme.accent_alt,
            active_fill=self.theme.button_active,
        )
        self.send_button.pack(side="right", padx=(2, 10), pady=10)
        self.menu_button.pack(side="right", padx=2, pady=11)
        self.mic_button.pack(side="right", padx=2, pady=11)
        self.entry_var.trace_add("write", self._sync_send_button)
        self._sync_send_button()

        self.status_label = tk.Label(
            self.root,
            text="就绪",
            anchor="w",
            justify="left",
            wraplength=DEFAULT_WINDOW_SIZE[0] - 24,
            font=(self.ui_font_family, 9),
            bg=self.theme.status_bg,
            fg=self.theme.status_fg,
            padx=12,
            pady=4,
        )
        self.status_label.pack(fill="x", side="bottom")

        self.history = tk.Canvas(
            self.root,
            bg=self.theme.chat_bg,
            highlightthickness=0,
            bd=0,
            takefocus=0,
        )
        self.history.pack(fill="both", expand=True, side="top")
        self._load_background(self.theme.id)
        self.history.bind("<Configure>", lambda _event: self._draw_background())
        self.history.bind("<MouseWheel>", self._on_history_mousewheel)

        self.resize_grip = tk.Frame(self.root, width=12, height=12, bg=self.theme.input_bg, cursor="size_nw_se")
        self.resize_grip.place(relx=1.0, rely=1.0, anchor="se")
        self.resize_grip.bind("<ButtonPress-1>", self._begin_window_resize)
        self.resize_grip.bind("<B1-Motion>", self._resize_window)
        self.resize_grip.lift()
        self.root.bind("<Configure>", self._schedule_window_rounding, add="+")
        self.root.after_idle(self._apply_window_rounding)

        self._append("Game Buddy 已就绪。可打字、按 MIC 说话，或用 ☰ 切换游戏、词库、攻略和外观主题。", "system")
        self._load_history()
        self.root.bind("<Button-3>", lambda _event: self._on_close())
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.entry.focus_set()

        if config.get("direct_codex_enabled", False):
            self._start_direct_bridge()
        if DANMAKU_FILE.exists():
            self._last_danmaku_mtime_ns = DANMAKU_FILE.stat().st_mtime_ns
        self._show_active_settings()
        self.root.after(40, self._draw_header_gradient)

    def _load_background(self, theme_id: str) -> None:
        self._bg_image: Optional[Image.Image] = None
        self._bg_photo: Optional[ImageTk.PhotoImage] = None
        self._bg_draw_key: Optional[tuple[int, int, str]] = None
        self._header_background_key: Optional[tuple[int, int, str]] = None
        base = BASE_DIR / "assets" / "themes" / theme_id
        for name in ("background-v2.png", "background-v1.png"):
            path = base / name
            if path.exists():
                try:
                    with Image.open(path) as source:
                        self._bg_image = source.convert("RGBA")
                except OSError:
                    self._bg_image = None
                break

    def _draw_background(self) -> None:
        if self._bg_image is None:
            self.history.delete("bg")
            self._draw_header_background()
            return
        width = max(1, self.history.winfo_width())
        height = max(1, self.history.winfo_height())
        if width <= 1 or height <= 1:
            return
        draw_key = (width, height, self.theme.id)
        if self._bg_draw_key == draw_key:
            self._draw_header_background()
            return
        try:
            total_height = HEADER_HEIGHT + HEADER_GRADIENT_HEIGHT + height
            full_background = ImageOps.fit(
                self._bg_image,
                (width, total_height),
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )
            resized = full_background.crop((0, HEADER_HEIGHT + HEADER_GRADIENT_HEIGHT, width, total_height))
            self._bg_photo = ImageTk.PhotoImage(resized)
        except (OSError, ValueError):
            return
        self.history.delete("bg")
        self.history.create_image(
            self.history.canvasx(0),
            self.history.canvasy(0),
            image=self._bg_photo,
            anchor="nw",
            tags="bg",
        )
        self.history.tag_lower("bg")
        self._bg_draw_key = draw_key
        self._draw_header_background()

    def _draw_header_background(self) -> None:
        if not hasattr(self, "header_frame"):
            return
        self.header_frame.delete("header_bg")
        self._header_bg_photo = None
        if self._bg_image is None:
            return
        width = max(1, self.header_frame.winfo_width())
        history_height = max(1, self.history.winfo_height()) if hasattr(self, "history") else max(1, self.root.winfo_height() - HEADER_HEIGHT)
        if width <= 1:
            return
        draw_key = (width, history_height, self.theme.id)
        if self._header_background_key == draw_key and self.header_frame.find_withtag("header_bg"):
            return
        try:
            total_height = HEADER_HEIGHT + HEADER_GRADIENT_HEIGHT + history_height
            full_background = ImageOps.fit(
                self._bg_image,
                (width, total_height),
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )
            header = full_background.crop((0, 0, width, HEADER_HEIGHT))
            self._header_bg_photo = ImageTk.PhotoImage(header)
        except (OSError, ValueError):
            return
        self.header_frame.create_image(0, 0, image=self._header_bg_photo, anchor="nw", tags="header_bg")
        self.header_frame.tag_lower("header_bg")
        self._header_background_key = draw_key

    def _position_background(self) -> None:
        self.history.coords("bg", self.history.canvasx(0), self.history.canvasy(0))
        self.history.tag_lower("bg")

    def _on_history_mousewheel(self, event: tk.Event) -> str | None:
        delta = int(getattr(event, "delta", 0))
        if delta == 0:
            return None
        steps = max(1, abs(delta) // 120)
        self.history.yview_scroll(-steps if delta > 0 else steps, "units")
        self._position_background()
        return "break"

    def _build_header(self) -> None:
        self.header_frame = tk.Canvas(self.root, bg=self.theme.surface_bg, height=HEADER_HEIGHT, highlightthickness=0, bd=0, takefocus=0)
        self.header_frame.pack(fill="x", side="top")
        self._header_bg_photo: Optional[ImageTk.PhotoImage] = None
        self._header_wordmark_photo: Optional[ImageTk.PhotoImage] = None
        self._header_redraw_after_id: Optional[str] = None
        self._header_controls_key: Optional[tuple[int, str]] = None
        self._update_header_wordmark(self.theme.id)
        self._draw_header_controls()
        self.header_frame.bind("<ButtonPress-1>", self._begin_window_drag)
        self.header_frame.bind("<B1-Motion>", self._drag_window)
        self.header_frame.bind("<Configure>", self._schedule_header_redraw)
        self.header_frame.tag_bind("header_close", "<Button-1>", self._close_from_header)
        self.gradient_strip = tk.Canvas(self.root, height=HEADER_GRADIENT_HEIGHT, bg=self.theme.surface_bg, highlightthickness=0, bd=0)
        self.gradient_strip.pack(fill="x", side="top")

    def _close_from_header(self, _event: tk.Event) -> str:
        self._on_close()
        return "break"

    def _schedule_header_redraw(self, _event: Optional[tk.Event] = None) -> None:
        if self._header_redraw_after_id is not None:
            self.root.after_cancel(self._header_redraw_after_id)
        self._header_redraw_after_id = self.root.after(30, self._redraw_header)

    def _redraw_header(self) -> None:
        self._header_redraw_after_id = None
        self._draw_header_background()
        self._draw_header_controls()

    def _draw_header_controls(self) -> None:
        width = max(1, self.header_frame.winfo_width())
        controls_key = (width, self.theme.id)
        if self._header_controls_key == controls_key and self.header_frame.find_withtag("header_close"):
            return
        self.header_frame.delete("header_close")
        center_x, center_y = width - 17, HEADER_HEIGHT // 2
        self.header_frame.create_oval(
            center_x - 10,
            center_y - 10,
            center_x + 10,
            center_y + 10,
            fill=self.theme.surface_bg,
            outline=self.theme.buddy_border,
            width=1,
            tags="header_close",
        )
        for delta in (-1, 1):
            self.header_frame.create_line(
                center_x - 4,
                center_y + delta * 4,
                center_x + 4,
                center_y - delta * 4,
                fill=self.theme.status_fg,
                width=1.5,
                capstyle="round",
                tags="header_close",
            )
        self._header_controls_key = controls_key

    def _update_header_wordmark(self, theme_id: str) -> None:
        self.header_frame.delete("header_logo")
        filename = wordmark_name_for_theme(theme_id)
        path = BASE_DIR / "assets" / "wordmarks" / filename if filename else None
        if path and path.exists():
            try:
                with Image.open(path) as source:
                    fitted = ImageOps.fit(
                        source.convert("RGBA"),
                        (142, 28),
                        method=Image.Resampling.LANCZOS,
                        centering=(0.5, 0.5),
                    )
                self._header_wordmark_photo = ImageTk.PhotoImage(fitted)
            except (OSError, ValueError):
                self._header_wordmark_photo = None
        else:
            self._header_wordmark_photo = None
        if self._header_wordmark_photo is None:
            self.header_frame.create_text(
                10,
                HEADER_HEIGHT // 2,
                text="Game Buddy",
                font=(self.ui_font_family, 15, "bold"),
                fill=self.theme.entry_fg,
                anchor="w",
                tags="header_logo",
            )
        else:
            self.header_frame.create_image(8, 8, image=self._header_wordmark_photo, anchor="nw", tags="header_logo")

    def _draw_header_gradient(self) -> None:
        if not self._running:
            return
        self.gradient_strip.delete("all")
        width = max(1, self.gradient_strip.winfo_width())
        colors = gradient_steps(self.theme.gradient, 32)
        for index, color in enumerate(colors):
            left = round(width * index / len(colors))
            right = round(width * (index + 1) / len(colors))
            self.gradient_strip.create_rectangle(left, 0, max(left + 1, right), 5, fill=color, outline="")

    def _apply_theme(self, theme_id: str) -> None:
        self.theme = get_theme(theme_id)
        requested_alpha = float(self.config.get("overlay_alpha", 0.85))
        self.root.attributes(
            "-alpha",
            1.0 if sys.platform == "darwin" else effective_window_alpha(theme_id, requested_alpha),
        )
        self.root.configure(bg=self.theme.window_bg)
        self.header_frame.configure(bg=self.theme.surface_bg)
        self._update_header_wordmark(theme_id)
        self._draw_header_controls()
        self.gradient_strip.configure(bg=self.theme.surface_bg)
        self.input_frame.configure(bg=self.theme.input_bg)
        self.resize_grip.configure(bg=self.theme.input_bg)
        self.entry.configure(bg=self.theme.entry_bg, fg=self.theme.entry_fg, insertbackground=self.theme.accent, highlightbackground=self.theme.buddy_border, highlightcolor=self.theme.accent)
        for button in (self.mic_button, self.menu_button):
            button.set_theme(
                background=self.theme.input_bg,
                fill=self.theme.entry_bg,
                foreground=self.theme.accent,
                border=self.theme.buddy_border,
                active_fill=self.theme.button_active,
            )
        self.send_button.set_theme(
            background=self.theme.input_bg,
            fill=self.theme.accent,
            foreground="#FFFFFF",
            border=self.theme.accent_alt,
            active_fill=self.theme.button_active,
        )
        self.status_label.configure(bg=self.theme.status_bg, fg=self.theme.status_fg)
        self.history.configure(bg=self.theme.chat_bg)
        self._load_background(theme_id)
        self._draw_header_gradient()
        self._render_history()

    def _bubble_width(self) -> int:
        current = self.history.winfo_width()
        if current <= 1:
            current = self.root.winfo_width()
        return max(250, current)

    def _render_history(self) -> None:
        self.history.delete("all")
        self._bg_draw_key = None
        self._draw_background()
        y = 8
        width = self._bubble_width()
        player_name = normalized_display_name(self.config.get("player_name"), "我")
        buddy_name = normalized_display_name(self.config.get("buddy_name"), "陪玩")
        for text, tag in self._message_records[-50:]:
            if tag in {"buddy", "player"}:
                bubble_height = draw_message_bubble(
                    self.history,
                    text=text,
                    speaker=tag,
                    caption=player_name if tag == "player" else buddy_name,
                    theme=self.theme,
                    font_size=self.font_size,
                    max_width=width,
                    font_family=self.ui_font_family,
                    y=y,
                )
                y += bubble_height + 8
            else:
                item = self.history.create_text(
                    14, y + 4, anchor="nw", text=f"  {text}",
                    width=max(120, width - 28),
                    justify="left",
                    fill=self.theme.system_fg,
                    font=(self.ui_font_family, max(9, self.font_size - 1)),
                )
                bbox = self.history.bbox(item) or (0, y, width - 28, y + 18)
                y += max(26, bbox[3] - bbox[1] + 12)
        self.history.configure(
            scrollregion=(0, 0, max(1, self.history.winfo_width()), max(y, self.history.winfo_height()))
        )
        self.history.yview_moveto(1.0)
        self._position_background()

    def _settings_summary(self) -> str:
        profile_id = selected_profile_id(self.config)
        row = next((item for item in self._profile_rows if item["id"] == profile_id), None)
        game = row["display_name"] if row else "未选择游戏"
        knowledge = "词库开" if self.config.get("knowledge_enabled", True) and row else "词库关"
        mode = SPOILER_LABELS.get(str(self.config.get("spoiler_mode", "safe")), SPOILER_LABELS["safe"])
        return f"{game} · {knowledge} · {mode}"

    def _show_active_settings(self) -> None:
        self._set_status(self._settings_summary())

    def _open_settings(self) -> None:
        theme = self.theme
        dialog = tk.Toplevel(self.root)
        dialog.title("Game Buddy 设置")
        dialog.configure(bg=theme.surface_bg)
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        panel = tk.Frame(dialog, bg=theme.surface_bg, padx=16, pady=14)
        panel.pack(fill="both", expand=True)
        labels = {"不指定游戏": ""}
        labels.update({item["display_name"]: item["id"] for item in self._profile_rows})
        selected_id = selected_profile_id(self.config)
        selected_label = next((label for label, value in labels.items() if value == selected_id), "不指定游戏")
        theme_options = theme_choices()
        theme_labels = {item.display_name: item.id for item in theme_options}
        theme_descriptions = {item.display_name: item.description for item in theme_options}
        selected_theme = get_theme(str(self.config.get("overlay_theme", DEFAULT_THEME_ID)))

        def make_label(text: str) -> tk.Label:
            return tk.Label(panel, text=text, bg=theme.surface_bg, fg=theme.entry_fg, anchor="w", font=(self.ui_font_family, 10))

        player_name_var = tk.StringVar(value=normalized_display_name(self.config.get("player_name"), "我"))
        buddy_name_var = tk.StringVar(value=normalized_display_name(self.config.get("buddy_name"), "陪玩"))

        def make_entry(variable: tk.StringVar) -> tk.Entry:
            return tk.Entry(
                panel,
                textvariable=variable,
                width=38,
                bg=theme.entry_bg,
                fg=theme.entry_fg,
                insertbackground=theme.accent,
                relief="flat",
                highlightthickness=1,
                highlightbackground=theme.buddy_border,
                highlightcolor=theme.accent,
                font=(self.ui_font_family, 10),
            )

        make_label("你的称呼").grid(row=0, column=0, sticky="w", pady=5)
        make_entry(player_name_var).grid(row=0, column=1, sticky="ew", pady=5, padx=(10, 0), ipady=3)

        make_label("陪玩称呼").grid(row=1, column=0, sticky="w", pady=5)
        make_entry(buddy_name_var).grid(row=1, column=1, sticky="ew", pady=5, padx=(10, 0), ipady=3)

        make_label("游戏").grid(row=2, column=0, sticky="w", pady=5)
        game_var = tk.StringVar(value=selected_label)
        game_box = ttk.Combobox(panel, textvariable=game_var, values=list(labels), state="readonly", width=36)
        game_box.grid(row=2, column=1, sticky="ew", pady=5, padx=(10, 0))

        knowledge_var = tk.BooleanVar(value=bool(self.config.get("knowledge_enabled", True)))
        tk.Checkbutton(panel, text="启用词库（世界书、术语、语音热词和 OCR 校对）", variable=knowledge_var, bg=theme.surface_bg, fg=theme.entry_fg, activebackground=theme.surface_bg, activeforeground=theme.entry_fg, selectcolor=theme.entry_bg, font=(self.ui_font_family, 10)).grid(row=3, column=0, columnspan=2, sticky="w", pady=7)

        make_label("攻略/剧透").grid(row=4, column=0, sticky="w", pady=5)
        current_mode = str(self.config.get("spoiler_mode", "safe"))
        mode_var = tk.StringVar(value=SPOILER_LABELS.get(current_mode, SPOILER_LABELS["safe"]))
        mode_box = ttk.Combobox(panel, textvariable=mode_var, values=list(SPOILER_LABELS.values()), state="readonly", width=36)
        mode_box.grid(row=4, column=1, sticky="ew", pady=5, padx=(10, 0))

        make_label("外观主题").grid(row=5, column=0, sticky="w", pady=5)
        theme_var = tk.StringVar(value=selected_theme.display_name)
        theme_box = ttk.Combobox(panel, textvariable=theme_var, values=list(theme_labels), state="readonly", width=36)
        theme_box.grid(row=5, column=1, sticky="ew", pady=5, padx=(10, 0))
        theme_note = tk.Label(panel, text=selected_theme.description, bg=theme.surface_bg, fg=theme.status_fg, justify="left", wraplength=390, font=(self.ui_font_family, 9))
        theme_note.grid(row=6, column=0, columnspan=2, sticky="w", pady=(2, 5))
        theme_box.bind("<<ComboboxSelected>>", lambda _event: theme_note.configure(text=theme_descriptions.get(theme_var.get(), "")))

        hint = tk.Label(panel, text="完整剧透会允许结局、凶手、死亡与跨作后果；主题只改变本地外观，不影响语音、菜单、词库、截图或 Codex 直连。", bg=theme.surface_bg, fg=theme.status_fg, justify="left", wraplength=390, font=(self.ui_font_family, 9))
        hint.grid(row=7, column=0, columnspan=2, sticky="w", pady=(4, 10))
        buttons = tk.Frame(panel, bg=theme.surface_bg)
        buttons.grid(row=8, column=0, columnspan=2, sticky="e")

        def make_button(text: str, command) -> tk.Button:
            return tk.Button(buttons, text=text, command=command, font=(self.ui_font_family, 9), bg=theme.button_bg, fg=theme.button_fg, activebackground=theme.button_active, activeforeground=theme.button_fg, relief="flat", padx=8, pady=3)

        def show_credits() -> None:
            temp_config = dict(self.config)
            temp_config["game_profile"] = labels.get(game_var.get(), "")
            try:
                text = load_credits(temp_config)
            except RuntimeError as exc:
                text = str(exc)
            credits = tk.Toplevel(dialog)
            credits.title("致谢与来源")
            credits.geometry("620x480")
            credits.configure(bg=theme.surface_bg)
            viewer = tk.Text(credits, wrap="word", padx=12, pady=10, font=(self.ui_font_family, 10), bg=theme.entry_bg, fg=theme.entry_fg, relief="flat")
            viewer.insert("1.0", text)
            viewer.config(state="disabled")
            viewer.pack(fill="both", expand=True, padx=8, pady=8)

        make_button("致谢与来源", show_credits).pack(side="left", padx=4)

        def save() -> None:
            mode = next((key for key, label in SPOILER_LABELS.items() if label == mode_var.get()), "safe")
            if mode == "full" and current_mode != "full":
                confirmed = messagebox.askyesno("开启完整剧透攻略？", "这会允许 Game Buddy 直接说明结局、凶手、角色死亡和隐藏后果。确定开启吗？", parent=dialog)
                if not confirmed:
                    return
            profile_id = labels.get(game_var.get(), "")
            selected_theme_id = theme_labels.get(theme_var.get(), DEFAULT_THEME_ID)
            self.config["game_profile"] = profile_id
            self.config["voice_game_profile"] = profile_id
            self.config["current_game"] = profile_id
            self.config["knowledge_enabled"] = bool(knowledge_var.get() and profile_id)
            self.config["spoiler_mode"] = mode
            self.config["overlay_theme"] = selected_theme_id
            update_display_names(self.config, player_name_var.get(), buddy_name_var.get())
            try:
                atomic_write_json(CONFIG_FILE, self.config)
            except OSError as exc:
                messagebox.showerror("保存失败", str(exc), parent=dialog)
                return
            self._apply_theme(selected_theme_id)
            self._append(f"设置已更新：{self._settings_summary()} · {self.theme.display_name}", "system")
            self._show_active_settings()
            dialog.destroy()

        make_button("取消", dialog.destroy).pack(side="left", padx=4)
        make_button("保存", save).pack(side="left", padx=4)
        panel.columnconfigure(1, weight=1)
        dialog.update_idletasks()
        x = self.root.winfo_rootx() + 20
        y = self.root.winfo_rooty() + 40
        dialog.geometry(f"+{x}+{y}")

    def _position_window(self, position: str, width: int, height: int) -> None:
        self.root.update_idletasks()
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        positions = {
            "tr": (screen_width - width - 15, 20),
            "tl": (15, 20),
            "br": (screen_width - width - 15, screen_height - height - 50),
            "bl": (15, screen_height - height - 50),
        }
        x, y = positions.get(position, positions["tr"])
        self.root.geometry(f"+{x}+{y}")

    def _begin_window_drag(self, event: tk.Event) -> None:
        self._window_drag_offset = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def _drag_window(self, event: tk.Event) -> None:
        offset_x, offset_y = self._window_drag_offset
        self.root.geometry(f"+{event.x_root - offset_x}+{event.y_root - offset_y}")

    def _begin_window_resize(self, event: tk.Event) -> None:
        self._resize_origin = (event.x_root, event.y_root, self.root.winfo_width(), self.root.winfo_height())

    def _resize_window(self, event: tk.Event) -> None:
        start_x, start_y, start_width, start_height = self._resize_origin
        width, height = bounded_window_size(
            start_width + event.x_root - start_x,
            start_height + event.y_root - start_y,
        )
        self.root.geometry(f"{width}x{height}")

    def _schedule_window_rounding(self, _event: Optional[tk.Event] = None) -> None:
        if sys.platform != "win32" or self._rounding_after_id is not None:
            return
        self._rounding_after_id = self.root.after_idle(self._apply_window_rounding)

    def _apply_window_rounding(self) -> None:
        self._rounding_after_id = None
        if sys.platform != "win32" or not self._running:
            return
        try:
            import ctypes

            width = max(1, self.root.winfo_width())
            height = max(1, self.root.winfo_height())
            frame_id = self.root.wm_frame()
            hwnd = int(frame_id, 0) if isinstance(frame_id, str) else int(frame_id)
            window_key = (hwnd, width, height)
            if self._rounded_window_key == window_key:
                return
            self._rounded_window_key = window_key
            diameter = corner_ellipse_diameter(width, height)

            create_region = ctypes.windll.gdi32.CreateRoundRectRgn
            create_region.argtypes = [ctypes.c_int] * 6
            create_region.restype = ctypes.c_void_p
            set_region = ctypes.windll.user32.SetWindowRgn
            set_region.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
            set_region.restype = ctypes.c_int
            delete_object = ctypes.windll.gdi32.DeleteObject
            delete_object.argtypes = [ctypes.c_void_p]
            delete_object.restype = ctypes.c_int

            region = create_region(0, 0, width + 1, height + 1, diameter, diameter)
            if region and not set_region(hwnd, region, 1):
                self._rounded_window_key = None
                delete_object(region)
        except (AttributeError, OSError, ValueError, tk.TclError):
            self._rounded_window_key = None
            return

    def _append(self, text: str, tag: Optional[str] = None) -> None:
        clean = text.strip()
        if not clean:
            return
        self._message_records.append((clean, tag or "system"))
        self._message_records = self._message_records[-50:]
        self._render_history()

    def _load_history(self) -> None:
        if not HISTORY_FILE.exists():
            return
        try:
            lines = HISTORY_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return
        loaded = []
        for line in lines[-50:]:
            if line.startswith("[Buddy]"):
                loaded.append((strip_history_timestamp(line[7:].lstrip()), "buddy"))
            elif line.startswith("[Player]"):
                loaded.append((strip_history_timestamp(line[8:].lstrip()), "player"))
            elif line.startswith("[系统]"):
                loaded.append((strip_history_timestamp(line[4:].lstrip()), "system"))
        self._message_records.extend((text, tag) for text, tag in loaded if text)
        self._message_records = self._message_records[-50:]
        self._render_history()

    def _save_to_history(self, speaker: str, text: str) -> None:
        timestamp = time.strftime("%H:%M")
        lines = text.splitlines() or [text]
        payload = "".join(f"[{speaker}] [{timestamp}] {line}\n" for line in lines if line.strip())
        if not payload:
            return
        try:
            with HISTORY_FILE.open("a", encoding="utf-8", newline="") as handle:
                handle.write(payload)
        except OSError as exc:
            self._set_status(f"历史记录写入失败: {exc}", error=True)

    def _send_message(self, _event=None) -> None:
        text = self.entry.get().strip()
        if not text:
            return
        try:
            context = build_game_context(self.config, text)
            append_message(text, game_context=context)
        except (OSError, RuntimeError) as exc:
            self._set_status(f"消息写入失败: {exc}", error=True)
            return
        self.entry.delete(0, "end")
        self._append(f"{text}\n", "player")
        self._save_to_history("Player", text)
        self._set_status("消息已进入可靠队列")

    def _sync_send_button(self, *_args) -> None:
        self.send_button.set_enabled(has_message_text(self.entry_var.get()))

    def _set_status(self, text: str, *, error: bool = False) -> None:
        if not self._running:
            return
        self.status_label.config(text=text, fg=self.theme.error_fg if error else self.theme.status_fg)

    def _voice_status(self, text: str) -> None:
        if self._running:
            self.root.after(0, lambda: self._set_status(text))

    def _start_voice_input(self) -> None:
        if self._voice_busy:
            return
        self._voice_busy = True
        self.mic_button.set_enabled(False)

        def worker() -> None:
            try:
                from voice_input import transcribe_once

                text = transcribe_once(self.config, self._voice_status)
                if self._running:
                    self.root.after(0, lambda: self._finish_voice(text, None))
            except Exception as exc:
                if self._running:
                    error_text = str(exc)
                    self.root.after(0, lambda message=error_text: self._finish_voice(None, message))

        threading.Thread(target=worker, name="game-buddy-voice", daemon=True).start()

    def _finish_voice(self, text: Optional[str], error: Optional[str]) -> None:
        self._voice_busy = False
        self.mic_button.set_enabled(True)
        if error:
            self._set_status(error, error=True)
            return
        self.entry.delete(0, "end")
        self.entry.insert(0, text or "")
        self.entry.focus_set()

    def _start_direct_bridge(self) -> None:
        configured = str(self.config.get("node_executable", "")).strip()
        node = configured if configured and not configured.startswith("<") else shutil.which("node")
        if not node:
            self._set_status("找不到 Node.js，无法启动 Codex 直连", error=True)
            return
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            self._bridge_process = subprocess.Popen(
                [node, str(BRIDGE_FILE)],
                cwd=str(BASE_DIR),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
        except OSError as exc:
            self._set_status(f"直连桥启动失败: {exc}", error=True)

    def _read_bridge_status(self) -> None:
        if not STATUS_FILE.exists():
            return
        try:
            mtime = STATUS_FILE.stat().st_mtime_ns
            if mtime == self._last_status_mtime_ns:
                return
            self._last_status_mtime_ns = mtime
            value = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
            status = value.get("status", "unknown")
            text, is_error = bridge_status_presentation(status, self._last_bridge_status)
            self._last_bridge_status = status
            self._set_status(text, error=is_error)
        except (OSError, json.JSONDecodeError):
            return

    def _on_close(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._bridge_process and self._bridge_process.poll() is None:
            self._bridge_process.terminate()
            try:
                self._bridge_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._bridge_process.kill()
        self.root.destroy()

    def _tick(self) -> None:
        if not self._running:
            return
        try:
            if DANMAKU_FILE.exists():
                mtime = DANMAKU_FILE.stat().st_mtime_ns
                if mtime != self._last_danmaku_mtime_ns:
                    self._last_danmaku_mtime_ns = mtime
                    content = DANMAKU_FILE.read_text(encoding="utf-8", errors="replace").strip()
                    if content:
                        self._append(f"{content}\n", "buddy")
                        self._save_to_history("Buddy", content)
        except OSError as exc:
            self._set_status(f"回复读取失败: {exc}", error=True)
        self._read_bridge_status()
        self.root.after(750, self._tick)

    def start(self) -> None:
        self._tick()
        self.root.mainloop()


def main() -> int:
    try:
        config = load_config()
    except RuntimeError as exc:
        print(f"❌ {exc}")
        return 1
    overlay = ChatOverlay(config)
    print("🎬 Game Buddy 聊天气泡已启动")
    overlay.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
