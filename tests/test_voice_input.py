import json
import tempfile
import unittest
from pathlib import Path

import voice_input


class VoiceGameProfileTests(unittest.TestCase):
    def make_profile(self, root: Path) -> None:
        profile = {
            "stt": {
                "prompt_prefix": "游戏专有词：",
                "terms": [
                    {
                        "canonical": "低优先级词条名字非常长而且不应该挤掉重要角色",
                        "aliases": ["Long Low Priority Alias That Should Not Fit"],
                        "priority": 1,
                    },
                    {"canonical": "高优先级", "aliases": ["High Name"], "priority": 100},
                ],
            }
        }
        (root / "test-game.json").write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")

    def test_empty_profile_keeps_voice_prompt_disabled(self):
        self.assertIsNone(voice_input.load_game_initial_prompt({}))

    def test_manual_prompt_works_without_profile(self):
        self.assertEqual("玩家正在说中文", voice_input.load_game_initial_prompt({"voice_initial_prompt": "玩家正在说中文"}))

    def test_profile_prompt_prefers_high_priority_terms(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_profile(root)
            prompt = voice_input.load_game_initial_prompt(
                {
                    "voice_game_profile": "test-game",
                    "voice_game_profile_root": str(root),
                    "voice_game_prompt_max_chars": 80,
                }
            )
            self.assertIn("高优先级", prompt)
            self.assertIn("High Name", prompt)
            self.assertNotIn("低优先级", prompt)

    def test_missing_selected_profile_is_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "找不到游戏词库"):
                voice_input.load_game_initial_prompt(
                    {"voice_game_profile": "missing", "voice_game_profile_root": directory}
                )


if __name__ == "__main__":
    unittest.main()
