import json
import tempfile
import unittest
from pathlib import Path

import game_knowledge


class GameKnowledgeTests(unittest.TestCase):
    def make_skill(self, root: Path) -> Path:
        skill = root / "game-buddy"
        profile_root = skill / "assets" / "game-profiles"
        glossary_root = skill / "assets" / "glossaries"
        profile_root.mkdir(parents=True)
        glossary_root.mkdir(parents=True)
        (skill / "SKILL.md").write_text("---\nname: game-buddy\ndescription: test\n---\n", encoding="utf-8")
        profile = {
            "id": "test-game",
            "display_name": "Test Game",
            "reference": "references/games/test-game.md",
            "credits_section": "Test Game",
            "glossaries": ["assets/glossaries/test-game.json"],
            "stt": {
                "prompt_prefix": "游戏术语：",
                "terms": [
                    {"canonical": "盖拉斯·瓦卡里安", "aliases": ["Garrus Vakarian", "Garrus"], "priority": 100},
                    {"canonical": "核心热词", "aliases": ["Core Hint"], "priority": 90},
                ],
            },
        }
        glossary = {
            "schema_version": 1,
            "id": "test-game-terms",
            "display_name": "Test terms",
            "entries": [
                {"canonical": "新奇骰子匠人", "aliases": ["Novelty Dicemaker"], "scopes": ["test"]},
                {"canonical": "埃莉亚", "aliases": ["Aria"], "scopes": ["test"]},
            ],
        }
        (profile_root / "test-game.json").write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")
        (glossary_root / "test-game.json").write_text(json.dumps(glossary, ensure_ascii=False), encoding="utf-8")
        reference = skill / "references" / "games" / "test-game.md"
        reference.parent.mkdir(parents=True)
        reference.write_text("# Test", encoding="utf-8")
        (skill / "references" / "credits.md").write_text(
            "# Credits\n\nShared introduction.\n\n"
            "## Test Game\n\nTest-only credit.\n\n"
            "## Other Game\n\nOther-only credit.\n",
            encoding="utf-8",
        )
        return profile_root

    def config(self, profile_root: Path) -> dict:
        return {
            "game_profile": "test-game",
            "game_profile_root": str(profile_root),
            "knowledge_enabled": True,
            "spoiler_mode": "safe",
        }

    def test_discovers_profile_and_keeps_large_glossary_out_of_whisper_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            profile_root = self.make_skill(Path(directory))
            config = self.config(profile_root)
            self.assertEqual("test-game", game_knowledge.discover_profiles(config)[0]["id"])
            prompt = game_knowledge.build_whisper_prompt(config, 300)
            self.assertIn("核心热词", prompt)
            self.assertNotIn("新奇骰子匠人", prompt)

    def test_retrieval_returns_relevant_terms_without_short_substring_collision(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self.config(self.make_skill(Path(directory)))
            matches = game_knowledge.retrieve_terms("Garrus Vakarian 在哪里？", config)
            names = [item["canonical"] for item in matches]
            self.assertIn("盖拉斯·瓦卡里安", names)
            self.assertNotIn("埃莉亚", names)

    def test_ocr_correction_is_conservative(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self.config(self.make_skill(Path(directory)))
            corrected, changes = game_knowledge.correct_ocr_text("盖拉思·瓦卡里安\n这是一整句普通对白", config)
            self.assertEqual("盖拉斯·瓦卡里安\n这是一整句普通对白", corrected)
            self.assertEqual([{"from": "盖拉思·瓦卡里安", "to": "盖拉斯·瓦卡里安"}], changes)

    def test_context_carries_menu_state_and_at_most_thirty_terms(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self.config(self.make_skill(Path(directory)))
            config["spoiler_mode"] = "current-game"
            config["knowledge_context_term_limit"] = 999
            context = game_knowledge.build_game_context(config, "Novelty Dicemaker")
            self.assertEqual("current-game", context["spoiler_mode"])
            self.assertTrue(context["knowledge_enabled"])
            self.assertLessEqual(len(context["terms"]), 30)
            self.assertIn("reference_path", context)

    def test_public_package_skills_directory_is_discovered(self):
        with tempfile.TemporaryDirectory() as directory:
            base_dir = Path(directory)
            profile_root = base_dir / "skills" / "game-buddy" / "assets" / "game-profiles"
            profile_root.mkdir(parents=True)
            (profile_root / "bundled-game.json").write_text(
                json.dumps({"id": "bundled-game", "display_name": "Bundled Game"}, ensure_ascii=False),
                encoding="utf-8",
            )
            rows = game_knowledge.discover_profiles({}, base_dir=base_dir)
            bundled = next(row for row in rows if row["id"] == "bundled-game")
            self.assertEqual((profile_root / "bundled-game.json").resolve(), Path(bundled["path"]).resolve())

    def test_disabled_knowledge_disables_hotwords_and_retrieval(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self.config(self.make_skill(Path(directory)))
            config["knowledge_enabled"] = False
            self.assertIsNone(game_knowledge.build_whisper_prompt(config))
            self.assertEqual([], game_knowledge.retrieve_terms("Garrus", config))

    def test_credits_only_show_the_selected_game_section(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self.config(self.make_skill(Path(directory)))
            credits = game_knowledge.load_credits(config)
            self.assertIn("Shared introduction.", credits)
            self.assertIn("Test-only credit.", credits)
            self.assertNotIn("Other-only credit.", credits)


if __name__ == "__main__":
    unittest.main()
