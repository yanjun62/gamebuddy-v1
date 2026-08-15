"""Original, asset-free visual themes for the GameBuddy Tk overlay."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Tuple
import tkinter as tk
from tkinter import font as tkfont


@dataclass(frozen=True)
class OverlayTheme:
    id: str
    display_name: str
    description: str
    badge: str
    window_bg: str
    surface_bg: str
    chat_bg: str
    input_bg: str
    entry_bg: str
    entry_fg: str
    button_bg: str
    button_fg: str
    button_active: str
    status_bg: str
    status_fg: str
    error_fg: str
    buddy_fill: str
    buddy_border: str
    buddy_text: str
    player_fill: str
    player_border: str
    player_text: str
    system_fg: str
    accent: str
    accent_alt: str
    gradient: Tuple[str, str, str]
    decoration: str


_THEME_LIST = (
    OverlayTheme("dopamine-sunset", "多巴胺 · 落日果冻", "莓粉、珊瑚与柠檬黄的快乐渐变", "POP", "#201225", "#301936", "#301936", "#2A1632", "#47214F", "#FFF8FC", "#FF5E98", "#24101E", "#FF83B2", "#24101E", "#B69CB9", "#FFB1C8", "#55234F", "#FF78AA", "#FFF8FC", "#D94178", "#FFB2CF", "#FFF8FC", "#D8A5CF", "#FF5E98", "#FFD35E", ("#FF5E98", "#FF8B5E", "#FFD35E"), "spark"),
    OverlayTheme("dopamine-sorbet", "多巴胺 · 雪酪俱乐部", "树莓、青柠与薰衣草的轻甜撞色", "JOY", "#FFF7F2", "#FFF0F6", "#FFF0F6", "#FFF7FB", "#FFFFFF", "#331929", "#7C5CFF", "#FFFFFF", "#A08BFF", "#FFF0F6", "#775E70", "#C85B7C", "#FFFFFF", "#FF78AB", "#3A1631", "#92D66E", "#63B751", "#17361B", "#A24C6D", "#FF5A99", "#9EE870", ("#FF5A99", "#9EE870", "#8065FF"), "pill"),
    OverlayTheme("dopamine-cosmic", "多巴胺 · 宇宙汽水", "电蓝、葡萄紫与橘光的夜航霓虹", "WAVE", "#11152B", "#181D3B", "#181D3B", "#151A34", "#252C56", "#F7F8FF", "#58D7FF", "#0B1730", "#99E8FF", "#101633", "#A1ABD1", "#FF9D7B", "#252D5A", "#6EE4FF", "#071B2B", "#824BCE", "#BC8CFF", "#FFF9FF", "#AAB4D7", "#45D7FF", "#FF9D5B", ("#45D7FF", "#A777FF", "#FF9D5B"), "orbit"),
    OverlayTheme("pixel-farm", "像素农场", "土壤棕、麦穗金与菜园绿的像素农场", "FARM", "#2B2019", "#47301F", "#47301F", "#382518", "#5B3A22", "#FFF7D7", "#F4C95D", "#3A250F", "#FFE29A", "#382518", "#D7C18D", "#F6C96B", "#F2DC9B", "#A86B35", "#342516", "#478A62", "#75BD77", "#F6FFE8", "#E6C876", "#F3C557", "#72C373", ("#F3C557", "#8FCF67", "#65B6C8"), "pixel"),
    OverlayTheme("candlelit-codex", "烛火秘典", "深木、古金与烛火橙的秘典卷轴质感", "TOME", "#15110E", "#241C15", "#241C15", "#1C1612", "#34271B", "#F5E9CF", "#B78A46", "#17110C", "#E4B96C", "#1C1612", "#B7A88C", "#D86D45", "#392817", "#C99B52", "#FFF5DF", "#552E22", "#D1794A", "#FFF4E1", "#C8B38D", "#CBA156", "#D96D45", ("#CBA156", "#E7BE7B", "#B8603D"), "rune"),
    OverlayTheme("synthetic-detective", "仿生侦探", "冷白、扫描蓝与单一蓝色光环的分析界面", "SCAN", "#EAF6FC", "#F7FBFE", "#EDF8FD", "#E3F1F8", "#FFFFFF", "#153446", "#2AABD2", "#FFFFFF", "#78D8EF", "#E3F1F8", "#51798B", "#D85E78", "#FFFFFF", "#77CDE7", "#153446", "#DDF4FC", "#4DB9DE", "#123847", "#5F8493", "#31B7DE", "#7DDCF1", ("#31B7DE", "#9EEAF7", "#DDF7FD"), "scan"),
    OverlayTheme("crimson-memory", "绯色记忆", "文艺复兴象牙白、暗炭与绯红", "MEMORY", "#2A1B1C", "#F5F0E7", "#F5F0E7", "#EEE8DE", "#FFFFFF", "#2D2020", "#B72F3E", "#FFFDFC", "#D7515E", "#E9E2D7", "#685B58", "#B72F3E", "#FFFDFC", "#C9B69D", "#302324", "#B72F3E", "#D05059", "#FFFDFC", "#796C67", "#B72F3E", "#D8B765", ("#B72F3E", "#E1685D", "#D8B765"), "ribbon"),
    OverlayTheme("gilded-court", "鎏金宫廷", "朱红挂毯、靛青夜色与鎏金描边", "COURT", "#180C15", "#32111F", "#32111F", "#260D19", "#4A1A2A", "#FFF1D1", "#C99536", "#24100F", "#F3C96C", "#260D19", "#C0A282", "#F2A2A2", "#4A1726", "#E8B950", "#321019", "#40265E", "#7965A8", "#FFF5DD", "#D6B492", "#D7A83F", "#7B6AE3", ("#C7403E", "#D7A83F", "#4651A6"), "ornament"),
    OverlayTheme("holographic-star-map", "全息星图", "舰桥深蓝、全息青与信号红的科幻 HUD", "STAR", "#06131D", "#0B202D", "#0B202D", "#071923", "#102F40", "#EAFBFF", "#2FD6F3", "#041118", "#8DEEFF", "#071923", "#8AAEBC", "#FF7777", "#102F40", "#49DDF4", "#061824", "#2B3F72", "#6D95EB", "#F2FBFF", "#A8C6CE", "#39D7F0", "#E35B62", ("#39D7F0", "#5D8FFF", "#E35B62"), "signal"),
    OverlayTheme("crystal-fantasy", "水晶幻想", "夜海青、晶能绿与花火粉的柔光界面", "CRYSTAL", "#08161A", "#10262A", "#10262A", "#0B1D20", "#17363A", "#F2FFFF", "#5EDCC0", "#062021", "#A3F9E3", "#0B1D20", "#A0C5C5", "#FF9BB4", "#173A3B", "#75F0D2", "#062A29", "#363C7A", "#8089E7", "#FBF8FF", "#B3CDCC", "#68E4C6", "#E68CC1", ("#68E4C6", "#7BC9EA", "#E68CC1"), "crystal"),
    OverlayTheme("elysian-world", "极乐世界", "冷暖油画、拼贴网点与海港晨雾的侦探手记", "CASE", "#0D2028", "#142C34", "#D9D7C8", "#10262E", "#1B3941", "#F6ECD4", "#D99A53", "#162229", "#F0B56E", "#11272F", "#C8D3C8", "#E77A5C", "#F0E5C8", "#D08A4B", "#24363A", "#244C55", "#73B8AE", "#FFF4D7", "#C0C7B8", "#E77A3D", "#74B9AF", ("#234B55", "#E77A3D", "#EADCB8"), "case"),
)

THEMES = {theme.id: theme for theme in _THEME_LIST}
DEFAULT_THEME_ID = "dopamine-sunset"


def get_theme(theme_id: Optional[str]) -> OverlayTheme:
    return THEMES.get(str(theme_id or ""), THEMES[DEFAULT_THEME_ID])


def theme_choices() -> Tuple[OverlayTheme, ...]:
    return _THEME_LIST


def ui_font_family(widget: tk.Misc) -> str:
    candidates = ("Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC", "Arial")
    try:
        installed = set(tkfont.families(widget))
    except tk.TclError:
        return "Arial"
    return next((name for name in candidates if name in installed), "Arial")


def _mix(first: str, second: str, ratio: float) -> str:
    first_values = tuple(int(first[index:index + 2], 16) for index in (1, 3, 5))
    second_values = tuple(int(second[index:index + 2], 16) for index in (1, 3, 5))
    values = tuple(round(start + (end - start) * ratio) for start, end in zip(first_values, second_values))
    return "#{:02X}{:02X}{:02X}".format(*values)


def _relative_luminance(color: str) -> float:
    values = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in values]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(first: str, second: str) -> float:
    first_luminance = _relative_luminance(first)
    second_luminance = _relative_luminance(second)
    lighter, darker = max(first_luminance, second_luminance), min(first_luminance, second_luminance)
    return (lighter + 0.05) / (darker + 0.05)


def readable_text_color(background: str, preferred: str) -> str:
    """Match the macOS renderer's WCAG fallback for low-contrast theme text."""
    if contrast_ratio(background, preferred) >= 4.5:
        return preferred
    return "#F6F8FC" if _relative_luminance(background) < 0.45 else "#1B1620"


def draw_button_icon(canvas: tk.Canvas, icon: str, size: int, color: str) -> None:
    center = size / 2
    if icon == "mic":
        canvas.create_line(center, 7, center, 15, fill=color, width=5, capstyle="round")
        canvas.create_line(
            center - 6, 12, center - 6, 15, center - 4, 18, center, 19,
            center + 4, 18, center + 6, 15, center + 6, 12,
            fill=color, width=1.8, smooth=True, capstyle="round", joinstyle="round",
        )
        canvas.create_line(center, 19, center, 22, fill=color, width=1.8, capstyle="round")
        canvas.create_line(center - 3, 22, center + 3, 22, fill=color, width=1.8, capstyle="round")
    elif icon == "menu":
        for y in (10, 14, 18):
            canvas.create_line(9, y, size - 9, y, fill=color, width=2, capstyle="round")
    elif icon == "send":
        canvas.create_polygon(
            7, 8, size - 6, center, 7, size - 8,
            10.5, center + 1.5, size - 12, center, 10.5, center - 1.5,
            fill=color, outline=color, joinstyle="round",
        )
    elif icon == "close":
        canvas.create_line(8, 8, size - 8, size - 8, fill=color, width=1.8, capstyle="round")
        canvas.create_line(size - 8, 8, 8, size - 8, fill=color, width=1.8, capstyle="round")
    else:
        raise ValueError(f"Unknown button icon: {icon}")


class RoundIconButton(tk.Canvas):
    """Small themed vector button matching the macOS composer controls."""

    def __init__(self, master: tk.Misc, *, icon: str, command: Callable[[], object], size: int,
                 background: str, fill: str, foreground: str, border: str, active_fill: str) -> None:
        super().__init__(master, width=size, height=size, bg=background, highlightthickness=0,
                         bd=0, takefocus=1, cursor="hand2")
        self.icon = icon
        self.command = command
        self.size = size
        self._background = background
        self._fill = fill
        self._foreground = foreground
        self._border = border
        self._active_fill = active_fill
        self._enabled = True
        self._hovered = False
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._invoke)
        self.bind("<Return>", self._invoke)
        self.bind("<space>", self._invoke)
        self._draw()

    def set_theme(self, *, background: str, fill: str, foreground: str, border: str, active_fill: str) -> None:
        self._background = background
        self._fill = fill
        self._foreground = foreground
        self._border = border
        self._active_fill = active_fill
        super().configure(bg=background)
        self._draw()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)
        self.configure(cursor="hand2" if self._enabled else "arrow")
        self._draw()

    def _on_enter(self, _event: tk.Event) -> None:
        self._hovered = True
        self._draw()

    def _on_leave(self, _event: tk.Event) -> None:
        self._hovered = False
        self._draw()

    def _invoke(self, _event: Optional[tk.Event] = None) -> str:
        if self._enabled:
            self.command()
        return "break"

    def _draw(self) -> None:
        self.delete("all")
        if self._enabled:
            fill = self._active_fill if self._hovered else self._fill
            foreground = self._foreground
            border = self._border
        else:
            fill = _mix(self._background, self._fill, 0.45)
            foreground = _mix(fill, self._foreground, 0.45)
            border = _mix(self._background, self._border, 0.45)
        self.create_oval(1, 1, self.size - 1, self.size - 1, fill=fill, outline=border, width=1)
        draw_button_icon(self, self.icon, self.size, foreground)


def gradient_steps(colors: Tuple[str, str, str], count: int = 30) -> Tuple[str, ...]:
    if count < 2:
        return (colors[0],)
    result = []
    for index in range(count):
        position = index / (count - 1)
        segment = min(int(position * 2), 1)
        local_position = position * 2 - segment
        result.append(_mix(colors[segment], colors[segment + 1], local_position))
    return tuple(result)


def _rounded_rect(canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, radius: int, **kwargs) -> None:
    radius = max(2, min(radius, (x2 - x1) // 2, (y2 - y1) // 2))
    points = (
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
    )
    canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs)


def draw_message_bubble(
    canvas: tk.Canvas,
    *,
    text: str,
    speaker: str,
    caption: str,
    theme: OverlayTheme,
    font_size: int,
    max_width: int,
    font_family: str,
    x_offset: int = 0,
    y: int = 0,
) -> int:
    """Draw a content-sized bubble directly on the shared history canvas."""
    player = speaker == "player"
    fill = theme.player_fill if player else theme.buddy_fill
    border = theme.player_border if player else theme.buddy_border
    preferred_text = theme.player_text if player else theme.buddy_text
    text_color = readable_text_color(fill, preferred_text)
    caption_color = _mix(fill, text_color, 0.62)
    body_font = tkfont.Font(family=font_family, size=font_size)
    caption_font = tkfont.Font(family=font_family, size=max(8, font_size - 3), weight="bold")

    horizontal_inset = 16
    horizontal_padding = 10
    vertical_padding = 7
    max_bubble_width = max(150, max_width - horizontal_inset * 2)
    max_body_width = max(120, max_bubble_width - horizontal_padding * 2)
    temporary = canvas.create_text(
        0,
        0,
        anchor="nw",
        text=text,
        width=max_body_width,
        justify="right" if player else "left",
        font=body_font,
    )
    bbox = canvas.bbox(temporary) or (0, 0, max_body_width, font_size + 8)
    canvas.delete(temporary)
    body_width = max(1, bbox[2] - bbox[0])
    body_height = max(font_size + 4, bbox[3] - bbox[1])
    caption_height = max(10, int(caption_font.metrics("linespace")))
    content_width = max(body_width, caption_font.measure(caption))
    bubble_width = min(max_bubble_width, max(72, content_width + horizontal_padding * 2))
    bubble_height = max(42, vertical_padding * 2 + caption_height + 2 + body_height)

    if player:
        x2 = x_offset + max_width - horizontal_inset
        x1 = x2 - bubble_width
        text_x = x2 - horizontal_padding
        anchor = "ne"
        justify = "right"
    else:
        x1 = x_offset + horizontal_inset
        x2 = x1 + bubble_width
        text_x = x1 + horizontal_padding
        anchor = "nw"
        justify = "left"

    _rounded_rect(canvas, x1, y, x2, y + bubble_height, 12, fill=fill, outline=border, width=1)
    canvas.create_text(text_x, y + vertical_padding, anchor=anchor, text=caption, fill=caption_color, font=caption_font)
    canvas.create_text(
        text_x,
        y + vertical_padding + caption_height + 2,
        anchor=anchor,
        text=text,
        width=max(48, bubble_width - horizontal_padding * 2),
        justify=justify,
        fill=text_color,
        font=body_font,
    )
    return bubble_height


class RoundedMessageBubble(tk.Canvas):
    """Canvas-backed message card used by the production overlay, with no external assets."""

    def __init__(self, master: tk.Misc, *, text: str, speaker: str, theme: OverlayTheme, font_size: int, max_width: int, font_family: str) -> None:
        self.text = text
        self.speaker = speaker
        self.theme = theme
        self.font_size = font_size
        self.max_width = max(220, max_width)
        self.font_family = font_family
        super().__init__(master, width=self.max_width, height=64, bg=theme.chat_bg, highlightthickness=0, bd=0, takefocus=0)
        self._draw()

    def _draw_gradient_strip(self, x1: int, x2: int, y: int) -> None:
        colors = gradient_steps(self.theme.gradient, 18)
        width = max(1, x2 - x1)
        for index, color in enumerate(colors):
            left = x1 + round(width * index / len(colors))
            right = x1 + round(width * (index + 1) / len(colors))
            self.create_rectangle(left, y, max(left + 1, right), y + 2, fill=color, outline="")

    def _draw_decoration(self, x2: int, y1: int) -> None:
        accent, alternate = self.theme.accent, self.theme.accent_alt
        if self.theme.decoration == "pixel":
            for dx, dy, color in ((0, 0, accent), (5, 0, "#FFF2A6"), (5, 5, accent), (10, 5, alternate)):
                self.create_rectangle(x2 - 24 + dx, y1 + 11 + dy, x2 - 20 + dx, y1 + 15 + dy, fill=color, outline="")
        elif self.theme.decoration in {"orbit", "scan", "signal"}:
            for index in range(3):
                x = x2 - 16 - index * 5
                self.create_line(x, y1 + 10 + index * 3, x, y1 + 18 + index * 3, fill=accent, width=1)
        elif self.theme.decoration in {"ornament", "rune"}:
            self.create_arc(x2 - 30, y1 + 8, x2 - 10, y1 + 28, start=180, extent=110, outline=accent, style="arc", width=1)
            self.create_arc(x2 - 24, y1 + 14, x2 - 6, y1 + 32, start=180, extent=110, outline=alternate, style="arc", width=1)
        elif self.theme.decoration in {"ribbon", "crystal"}:
            self.create_line(x2 - 26, y1 + 9, x2 - 9, y1 + 26, fill=accent, width=2)
            self.create_line(x2 - 20, y1 + 9, x2 - 5, y1 + 24, fill=alternate, width=1)
        else:
            self.create_oval(x2 - 19, y1 + 11, x2 - 13, y1 + 17, fill=accent, outline="")
            self.create_line(x2 - 23, y1 + 14, x2 - 9, y1 + 14, fill=alternate, width=1)

    def _draw(self) -> None:
        self.delete("all")
        player = self.speaker == "player"
        x1 = 30 if player else 2
        x2 = self.max_width - 2 if player else self.max_width - 30
        fill = self.theme.player_fill if player else self.theme.buddy_fill
        border = self.theme.player_border if player else self.theme.buddy_border
        preferred_text = self.theme.player_text if player else self.theme.buddy_text
        text_color = readable_text_color(fill, preferred_text)
        caption = "YOU" if player else "BUDDY"
        caption_color = self.theme.accent_alt if player else self.theme.accent
        body_font = tkfont.Font(family=self.font_family, size=self.font_size)
        caption_font = tkfont.Font(family=self.font_family, size=max(8, self.font_size - 3), weight="bold")
        temporary = self.create_text(x1 + 14, 30, anchor="nw", text=self.text, width=max(140, x2 - x1 - 28), justify="left", fill=text_color, font=body_font)
        bbox = self.bbox(temporary) or (0, 0, self.max_width, 36)
        self.delete(temporary)
        height = max(58, bbox[3] + 14)
        self.configure(height=height)
        _rounded_rect(self, x1, 2, x2, height - 2, 16, fill=fill, outline=border, width=1)
        self.create_text(x1 + 14, 12, anchor="nw", text=caption, fill=caption_color, font=caption_font)
        self.create_text(x1 + 14, 30, anchor="nw", text=self.text, width=max(140, x2 - x1 - 28), justify="left", fill=text_color, font=body_font)
