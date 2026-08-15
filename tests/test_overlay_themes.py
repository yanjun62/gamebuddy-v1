import unittest
from unittest.mock import patch

from overlay_themes import DEFAULT_THEME_ID, THEMES, _rounded_rect, draw_button_icon, draw_message_bubble, get_theme, gradient_steps, readable_text_color, theme_choices


class RecordingCanvas:
    def __init__(self):
        self.calls = []

    def create_polygon(self, points, **kwargs):
        self.calls.append((points, kwargs))


class BubbleCanvas(RecordingCanvas):
    def __init__(self):
        super().__init__()
        self.text_calls = []
        self.deleted = []

    def create_text(self, *args, **kwargs):
        self.text_calls.append((args, kwargs))
        return len(self.text_calls)

    def bbox(self, _item):
        return (0, 0, 96, 22)

    def delete(self, item):
        self.deleted.append(item)


class FakeFont:
    def measure(self, text):
        return len(text) * 9

    def metrics(self, key):
        return 12 if key == "linespace" else 0


class IconCanvas:
    def __init__(self):
        self.lines = []
        self.polygons = []

    def create_line(self, *args, **kwargs):
        self.lines.append((args, kwargs))

    def create_polygon(self, *args, **kwargs):
        self.polygons.append((args, kwargs))


class OverlayThemeTests(unittest.TestCase):
    def test_default_theme_is_registered(self):
        self.assertIn(DEFAULT_THEME_ID, THEMES)
        self.assertEqual(get_theme(None).id, DEFAULT_THEME_ID)

    def test_requested_game_and_dopamine_themes_exist(self):
        expected = {
            "dopamine-sunset", "dopamine-sorbet", "dopamine-cosmic", "pixel-farm",
            "candlelit-codex", "synthetic-detective", "crimson-memory",
            "gilded-court", "holographic-star-map", "crystal-fantasy",
            "elysian-world",
        }
        self.assertTrue(expected.issubset(THEMES))
        self.assertEqual(len(theme_choices()), len(THEMES))

    def test_unknown_theme_falls_back_without_breaking_overlay(self):
        self.assertEqual(get_theme("does-not-exist").id, DEFAULT_THEME_ID)

    def test_gradient_steps_are_hex_colors(self):
        steps = gradient_steps(get_theme("holographic-star-map").gradient, 9)
        self.assertEqual(len(steps), 9)
        self.assertTrue(all(value.startswith("#") and len(value) == 7 for value in steps))

    def test_low_contrast_theme_text_gets_same_fallback_as_macos(self):
        self.assertEqual(readable_text_color("#102F40", "#061824"), "#F6F8FC")
        self.assertEqual(readable_text_color("#FFFFFF", "#153446"), "#153446")

    def test_macos_style_composer_icons_are_vector_drawn(self):
        mic = IconCanvas()
        menu = IconCanvas()
        send = IconCanvas()
        close = IconCanvas()

        draw_button_icon(mic, "mic", 28, "#FFFFFF")
        draw_button_icon(menu, "menu", 28, "#FFFFFF")
        draw_button_icon(send, "send", 30, "#FFFFFF")
        draw_button_icon(close, "close", 22, "#FFFFFF")

        self.assertEqual(len(mic.lines), 4)
        self.assertEqual(len(menu.lines), 3)
        self.assertEqual(len(send.polygons), 1)
        self.assertEqual(len(close.lines), 2)

    def test_rounded_rect_uses_one_outline_without_internal_seams(self):
        canvas = RecordingCanvas()

        _rounded_rect(canvas, 2, 2, 202, 62, 16, fill="#eef", outline="#09f", width=1)

        self.assertEqual(len(canvas.calls), 1)
        points, options = canvas.calls[0]
        self.assertEqual(len(points), 24)
        self.assertTrue(options["smooth"])
        self.assertEqual(options["splinesteps"], 24)
        self.assertEqual(options["outline"], "#09f")

    @patch("overlay_themes.tkfont.Font", return_value=FakeFont())
    def test_message_bubble_is_drawn_directly_and_hugs_short_content(self, _font):
        canvas = BubbleCanvas()

        height = draw_message_bubble(
            canvas,
            text="短消息",
            speaker="buddy",
            caption="陪玩",
            theme=get_theme("synthetic-detective"),
            font_size=12,
            max_width=360,
            font_family="test",
            y=8,
        )

        self.assertEqual(height, 50)
        self.assertEqual(len(canvas.calls), 1)
        points, _options = canvas.calls[0]
        self.assertLess(max(points[::2]), 180)
        self.assertEqual(canvas.deleted, [1])
        self.assertEqual(canvas.text_calls[-2][1]["text"], "陪玩")
        self.assertEqual(canvas.text_calls[-1][1]["text"], "短消息")

    @patch("overlay_themes.tkfont.Font", return_value=FakeFont())
    def test_player_bubble_keeps_same_sixteen_pixel_outer_margin(self, _font):
        canvas = BubbleCanvas()

        draw_message_bubble(
            canvas,
            text="收到",
            speaker="player",
            caption="我",
            theme=get_theme("gilded-court"),
            font_size=12,
            max_width=360,
            font_family="test",
        )

        points, _options = canvas.calls[0]
        self.assertEqual(max(points[::2]), 344)


if __name__ == "__main__":
    unittest.main()
