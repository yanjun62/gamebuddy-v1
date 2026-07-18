import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import heartbeat_bridge


class HeartbeatBridgeTests(unittest.TestCase):
    def test_pending_event_requires_matching_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {
                "CONFIG_FILE": root / "config.json",
                "STATE_FILE": root / "state.json",
                "DESCRIPTION_FILE": root / "description.txt",
                "FRAME_FILE": root / "frame.jpg",
                "FRAME_HISTORY_DIR": root / "frame_history",
                "FRAME_BATCH_DIR": root / "heartbeat_frames",
                "MESSAGE_QUEUE_FILE": root / "queue.jsonl",
                "DANMAKU_FILE": root / "danmaku.txt",
            }
            files["CONFIG_FILE"].write_text('{"direct_codex_enabled": false}', encoding="utf-8")
            files["MESSAGE_QUEUE_FILE"].write_text(
                '{"id":"m1","created_at":"now","text":"你好"}\n', encoding="utf-8"
            )

            patchers = [patch.object(heartbeat_bridge, name, value) for name, value in files.items()]
            for patcher in patchers:
                patcher.start()
            try:
                first = heartbeat_bridge.poll()
                second = heartbeat_bridge.poll()
                self.assertEqual("pending", first["status"])
                self.assertEqual(first["token"], second["token"])
                with self.assertRaises(ValueError):
                    heartbeat_bridge.commit("wrong", "不会写入", False)

                result = heartbeat_bridge.commit(first["token"], "收到", False)
                self.assertEqual("committed", result["status"])
                self.assertEqual("收到", files["DANMAKU_FILE"].read_text(encoding="utf-8"))
                self.assertEqual("idle", heartbeat_bridge.poll()["status"])
                state = json.loads(files["STATE_FILE"].read_text(encoding="utf-8"))
                self.assertIn("m1", state["processed_message_ids"])
            finally:
                for patcher in reversed(patchers):
                    patcher.stop()

    def test_direct_mode_does_not_duplicate_player_messages_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {
                "CONFIG_FILE": root / "config.json",
                "STATE_FILE": root / "state.json",
                "DESCRIPTION_FILE": root / "description.txt",
                "FRAME_FILE": root / "frame.jpg",
                "FRAME_HISTORY_DIR": root / "frame_history",
                "FRAME_BATCH_DIR": root / "heartbeat_frames",
                "MESSAGE_QUEUE_FILE": root / "queue.jsonl",
                "DANMAKU_FILE": root / "danmaku.txt",
            }
            files["CONFIG_FILE"].write_text('{"direct_codex_enabled": true}', encoding="utf-8")
            files["MESSAGE_QUEUE_FILE"].write_text(
                '{"id":"m1","created_at":"now","text":"你好"}\n', encoding="utf-8"
            )
            patchers = [patch.object(heartbeat_bridge, name, value) for name, value in files.items()]
            for patcher in patchers:
                patcher.start()
            try:
                self.assertEqual("idle", heartbeat_bridge.poll()["status"])
            finally:
                for patcher in reversed(patchers):
                    patcher.stop()

    def test_poll_freezes_the_three_newest_history_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            history = root / "frame_history"
            history.mkdir()
            for index in range(1, 5):
                (history / f"frame_{index:02d}.jpg").write_bytes(f"frame-{index}".encode())

            files = {
                "CONFIG_FILE": root / "config.json",
                "STATE_FILE": root / "state.json",
                "DESCRIPTION_FILE": root / "description.txt",
                "FRAME_FILE": root / "frame.jpg",
                "FRAME_HISTORY_DIR": history,
                "FRAME_BATCH_DIR": root / "heartbeat_frames",
                "MESSAGE_QUEUE_FILE": root / "queue.jsonl",
                "DANMAKU_FILE": root / "danmaku.txt",
            }
            files["CONFIG_FILE"].write_text('{"heartbeat_frame_count": 3}', encoding="utf-8")
            patchers = [patch.object(heartbeat_bridge, name, value) for name, value in files.items()]
            for patcher in patchers:
                patcher.start()
            try:
                event = heartbeat_bridge.poll()
                self.assertEqual("pending", event["status"])
                self.assertEqual(3, len(event["frame_paths"]))
                self.assertEqual(
                    [b"frame-2", b"frame-3", b"frame-4"],
                    [Path(path).read_bytes() for path in event["frame_paths"]],
                )

                (history / "frame_04.jpg").write_bytes(b"overwritten")
                self.assertEqual(b"frame-4", Path(event["frame_paths"][-1]).read_bytes())

                frozen_paths = [Path(path) for path in event["frame_paths"]]
                heartbeat_bridge.commit(event["token"], "第一句\n第二句\n第三句", False)
                self.assertTrue(all(not path.exists() for path in frozen_paths))
                self.assertEqual(
                    "第一句\n第二句\n第三句",
                    files["DANMAKU_FILE"].read_text(encoding="utf-8"),
                )
            finally:
                for patcher in reversed(patchers):
                    patcher.stop()


if __name__ == "__main__":
    unittest.main()
