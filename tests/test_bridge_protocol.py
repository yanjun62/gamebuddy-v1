import json
import tempfile
import unittest
from pathlib import Path

import bridge_protocol


class BridgeProtocolTests(unittest.TestCase):
    def test_append_message_keeps_every_entry_and_updates_legacy_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            queue = root / "queue.jsonl"
            legacy = root / "message.txt"
            first = bridge_protocol.append_message(
                "第一条", queue_path=queue, legacy_path=legacy, message_id="one", created_at="2026-01-01T00:00:00Z"
            )
            second = bridge_protocol.append_message(
                "第二条", queue_path=queue, legacy_path=legacy, message_id="two", created_at="2026-01-01T00:00:01Z"
            )

            self.assertEqual([first, second], bridge_protocol.read_messages(queue))
            self.assertEqual("第二条", legacy.read_text(encoding="utf-8"))

    def test_read_messages_ignores_damaged_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = Path(directory) / "queue.jsonl"
            queue.write_text(
                '{"id":"ok","created_at":"now","text":"hello"}\nnot json\n{"id":"missing-text"}\n',
                encoding="utf-8",
            )
            self.assertEqual(["ok"], [item["id"] for item in bridge_protocol.read_messages(queue)])

    def test_atomic_json_is_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "state.json"
            bridge_protocol.atomic_write_json(target, {"中文": True})
            self.assertEqual({"中文": True}, json.loads(target.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
