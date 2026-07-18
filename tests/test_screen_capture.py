import unittest

from screen_capture import GameWindowNotFound, capture_region, find_game_window


class ScreenCapturePrivacyTests(unittest.TestCase):
    def test_empty_title_never_selects_a_screen_or_window(self):
        self.assertIsNone(find_game_window(""))

    def test_missing_region_never_falls_back_to_primary_monitor(self):
        with self.assertRaises(GameWindowNotFound):
            capture_region(None)


if __name__ == "__main__":
    unittest.main()
