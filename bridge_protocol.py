"""Shared, dependency-free file protocol helpers for Game Buddy."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional


BASE_DIR = Path(__file__).resolve().parent
MESSAGE_QUEUE_FILE = BASE_DIR / "message_queue.jsonl"
LEGACY_MESSAGE_FILE = BASE_DIR / "message.txt"
DANMAKU_FILE = BASE_DIR / "danmaku.txt"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def atomic_write_text(path: Path, text: str) -> None:
    """Replace a UTF-8 text file without exposing a partially-written value."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with temp.open("w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def append_message(
    text: str,
    *,
    queue_path: Path = MESSAGE_QUEUE_FILE,
    legacy_path: Optional[Path] = LEGACY_MESSAGE_FILE,
    message_id: Optional[str] = None,
    created_at: Optional[str] = None,
) -> dict[str, str]:
    """Durably append one message and update the legacy single-message file."""
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("message text cannot be empty")

    record = {
        "id": message_id or str(uuid.uuid4()),
        "created_at": created_at or utc_now_iso(),
        "text": cleaned,
    }
    payload = (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    queue_path = Path(queue_path)
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    fd = os.open(queue_path, flags, 0o600)
    try:
        remaining = memoryview(payload)
        while remaining:
            written = os.write(fd, remaining)
            if written <= 0:
                raise OSError("message queue write made no progress")
            remaining = remaining[written:]
        os.fsync(fd)
    finally:
        os.close(fd)

    if legacy_path is not None:
        atomic_write_text(Path(legacy_path), cleaned)
    return record


def read_messages(path: Path = MESSAGE_QUEUE_FILE) -> list[dict[str, str]]:
    """Read valid queue entries, ignoring damaged or incomplete trailing lines."""
    path = Path(path)
    if not path.exists():
        return []
    records: list[dict[str, str]] = []
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not raw_line.strip():
            continue
        try:
            value = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict):
            continue
        message_id = value.get("id")
        text = value.get("text")
        if isinstance(message_id, str) and message_id and isinstance(text, str) and text.strip():
            records.append(
                {
                    "id": message_id,
                    "created_at": str(value.get("created_at", "")),
                    "text": text.strip(),
                }
            )
    return records


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def unique_message_ids(records: Iterable[dict[str, str]]) -> list[str]:
    return list(dict.fromkeys(record["id"] for record in records if record.get("id")))
