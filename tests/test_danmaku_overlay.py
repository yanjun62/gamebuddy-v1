import unittest
from types import SimpleNamespace
from unittest.mock import patch

from danmaku_overlay import DEFAULT_WINDOW_SIZE, ChatOverlay, bounded_window_size, bridge_status_presentation, corner_ellipse_diameter, effective_window_alpha, has_message_text, normalized_display_name, strip_history_timestamp, update_display_names, wordmark_name_for_theme
from overlay_themes import get_theme


class RecordingHistory:
    def __init__(self):
        self.scroll_calls = []
        self.coord_calls = []
        self.lower_calls = []

    def canvasx(self, value):
        return value + 11

    def canvasy(self, value):
        return value + 37

    def coords(self, tag, x, y):
        self.coord_calls.append((tag, x, y))

    def tag_lower(self, tag):
        self.lower_calls.append(tag)

    def yview_scroll(self, steps, units):
        self.scroll_calls.append((steps, units))


class RenderHistory(RecordingHistory):
    def __init__(self):
        super().__init__()
        self.text_calls = []
        self.config_calls = []
        self.view_calls = []
        self.height = 300

    def delete(self, _tag):
        pass

    def winfo_width(self):
        return 420

    def winfo_height(self):
        return self.height

    def create_text(self, *args, **kwargs):
        self.text_calls.append((args, kwargs))
        return len(self.text_calls)

    def bbox(self, _item):
        return (0, 0, 280, 44)

    def configure(self, **kwargs):
        self.config_calls.append(kwargs)

    def yview_moveto(self, position):
        self.view_calls.append(position)


class ChatOverlayCanvasTests(unittest.TestCase):
    def make_overlay(self):
        overlay = ChatOverlay.__new__(ChatOverlay)
        overlay.history = RecordingHistory()
        return overlay

    def test_background_tracks_visible_canvas_origin(self):
        overlay = self.make_overlay()

        overlay._position_background()

        self.assertEqual(overlay.history.coord_calls, [("bg", 11, 37)])
        self.assertEqual(overlay.history.lower_calls, ["bg"])

    def test_mousewheel_scrolls_and_repositions_background(self):
        overlay = self.make_overlay()

        result = overlay._on_history_mousewheel(SimpleNamespace(delta=-240))

        self.assertEqual(result, "break")
        self.assertEqual(overlay.history.scroll_calls, [(2, "units")])
        self.assertEqual(overlay.history.coord_calls, [("bg", 11, 37)])

    def test_high_resolution_mousewheel_delta_still_scrolls(self):
        overlay = self.make_overlay()

        overlay._on_history_mousewheel(SimpleNamespace(delta=30))

        self.assertEqual(overlay.history.scroll_calls, [(-1, "units")])

    def test_display_names_are_trimmed_and_blank_values_use_defaults(self):
        config = {}

        update_display_names(config, "  Kate  ", "   ")

        self.assertEqual(config["player_name"], "Kate")
        self.assertEqual(config["buddy_name"], "陪玩")
        self.assertEqual(normalized_display_name(None, "我"), "我")

    def test_history_timestamp_is_hidden_from_bubble_text(self):
        self.assertEqual(strip_history_timestamp("[16:35] 你好"), "你好")
        self.assertEqual(strip_history_timestamp("没有时间的正文"), "没有时间的正文")

    def test_windows_default_size_and_wordmarks_match_macos(self):
        self.assertEqual(DEFAULT_WINDOW_SIZE, (340, 520))
        self.assertEqual(wordmark_name_for_theme("crystal-fantasy"), "gamebuddy-scifi-v1.png")
        self.assertEqual(wordmark_name_for_theme("gilded-court"), "gamebuddy-retro-v1.png")
        self.assertEqual(wordmark_name_for_theme("elysian-world"), "gamebuddy-retro-v1.png")
        self.assertIsNone(wordmark_name_for_theme("dopamine-sunset"))
        self.assertEqual(effective_window_alpha("crystal-fantasy", 0.86), 1.0)
        self.assertEqual(effective_window_alpha("dopamine-sunset", 0.86), 0.86)

    def test_send_button_enablement_ignores_whitespace(self):
        self.assertFalse(has_message_text("   "))
        self.assertTrue(has_message_text("你好"))

    def test_frameless_resize_keeps_window_usable(self):
        self.assertEqual(bounded_window_size(120, 200), (300, 380))
        self.assertEqual(bounded_window_size(420, 600), (420, 600))

    def test_outer_window_corner_diameter_matches_macos_radius(self):
        self.assertEqual(corner_ellipse_diameter(340, 520), 32)
        self.assertEqual(corner_ellipse_diameter(20, 20), 20)

    def test_retry_status_is_not_shown_as_a_permanent_error(self):
        self.assertEqual(bridge_status_presentation("retrying"), ("Codex 连接波动，正在自动重试…", False))

    def test_ready_status_announces_recovery_after_retry(self):
        self.assertEqual(bridge_status_presentation("ready", "retrying"), ("Codex 已恢复连接", False))
        self.assertEqual(bridge_status_presentation("ready", "ready"), ("Codex 已连接", False))

    def test_system_notice_wraps_and_uses_measured_height(self):
        overlay = ChatOverlay.__new__(ChatOverlay)
        overlay.history = RenderHistory()
        overlay.history.height = 40
        overlay.root = SimpleNamespace(winfo_width=lambda: 340)
        overlay.config = {}
        overlay.theme = get_theme("synthetic-detective")
        overlay.font_size = 12
        overlay.ui_font_family = "test"
        overlay._message_records = [("设置已更新：这是一条需要自动换行的很长提示", "system")]
        overlay._draw_background = lambda: None

        overlay._render_history()

        _args, options = overlay.history.text_calls[0]
        self.assertGreater(options["width"], 120)
        self.assertGreater(overlay.history.config_calls[-1]["scrollregion"][3], 40)

    @patch("danmaku_overlay.draw_message_bubble", return_value=54)
    def test_history_draws_bubbles_on_shared_canvas_with_saved_names(self, draw_bubble):
        overlay = ChatOverlay.__new__(ChatOverlay)
        overlay.history = RenderHistory()
        overlay.root = SimpleNamespace(winfo_width=lambda: 420)
        overlay.config = {"player_name": "Kate", "buddy_name": "小陪玩"}
        overlay.theme = get_theme("synthetic-detective")
        overlay.font_size = 12
        overlay.ui_font_family = "test"
        overlay._message_records = [("你好", "buddy"), ("收到", "player")]
        overlay._draw_background = lambda: None

        overlay._render_history()

        self.assertEqual(draw_bubble.call_count, 2)
        self.assertEqual(draw_bubble.call_args_list[0].kwargs["caption"], "小陪玩")
        self.assertEqual(draw_bubble.call_args_list[1].kwargs["caption"], "Kate")
        self.assertEqual(overlay.history.view_calls, [1.0])


if __name__ == "__main__":
    unittest.main()
