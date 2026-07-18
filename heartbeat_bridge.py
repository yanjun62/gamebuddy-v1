"""Two-phase file bridge for scheduled/heartbeat-based Game Buddy integrations."""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import shutil
import sys
from pathlib import Path
from typing import List, Optional

from bridge_protocol import (
    BASE_DIR,
    DANMAKU_FILE,
    MESSAGE_QUEUE_FILE,
    atomic_write_json,
    atomic_write_text,
    load_json,
    read_messages,
    utc_now_iso,
)


CONFIG_FILE = BASE_DIR / "config.json"
STATE_FILE = BASE_DIR / ".heartbeat_state.json"
DESCRIPTION_FILE = BASE_DIR / "description.txt"
FRAME_FILE = BASE_DIR / "current_frame.jpg"
FRAME_HISTORY_DIR = BASE_DIR / "frame_history"
FRAME_BATCH_DIR = BASE_DIR / ".heartbeat_frames"


def load_config() -> dict:
    value = load_json(CONFIG_FILE, {})
    return value if isinstance(value, dict) else {}


def load_state() -> dict:
    value = load_json(
        STATE_FILE,
        {
            "processed_message_ids": [],
            "last_description_mtime_ns": 0,
            "last_frame_sha256": "",
            "pending": None,
        },
    )
    return value if isinstance(value, dict) else {}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def recent_frame_paths(limit: int) -> list[Path]:
    """Return the newest immutable captures, with legacy single-frame fallback."""
    if FRAME_HISTORY_DIR.exists():
        frames = sorted(FRAME_HISTORY_DIR.glob("frame_*.jpg"))
        if frames:
            return frames[-limit:]
    return [FRAME_FILE] if FRAME_FILE.exists() else []


def freeze_frame_batch(token: str, sources: list[Path]) -> tuple[list[str], list[str]]:
    """Copy selected frames so a later capture cannot overwrite the pending event."""
    if not sources:
        return [], []
    batch_dir = FRAME_BATCH_DIR / token
    batch_dir.mkdir(parents=True, exist_ok=False)
    paths: list[str] = []
    hashes: list[str] = []
    try:
        for index, source in enumerate(sources, start=1):
            digest = file_sha256(source)
            destination = batch_dir / f"frame_{index:02d}.jpg"
            shutil.copyfile(source, destination)
            paths.append(str(destination.resolve()))
            hashes.append(digest)
    except OSError:
        for path in batch_dir.glob("*"):
            path.unlink(missing_ok=True)
        batch_dir.rmdir()
        raise
    return paths, hashes


def cleanup_frame_batch(frame_paths: list[str]) -> None:
    """Remove only bridge-owned frozen frames after their event is committed."""
    batch_root = FRAME_BATCH_DIR.resolve()
    batch_dirs: set[Path] = set()
    for raw_path in frame_paths:
        path = Path(raw_path).resolve()
        if path.parent.parent == batch_root:
            path.unlink(missing_ok=True)
            batch_dirs.add(path.parent)
    for batch_dir in batch_dirs:
        try:
            batch_dir.rmdir()
        except OSError:
            pass


def poll() -> dict:
    cfg = load_config()
    state = load_state()
    pending = state.get("pending")
    if isinstance(pending, dict):
        return {"status": "pending", **pending}

    processed = set(state.get("processed_message_ids", []))
    include_messages = bool(
        cfg.get("heartbeat_include_messages", not cfg.get("direct_codex_enabled", False))
    )
    messages = [item for item in read_messages(MESSAGE_QUEUE_FILE) if item["id"] not in processed]
    if not include_messages:
        messages = []

    description = None
    description_mtime_ns = 0
    if DESCRIPTION_FILE.exists():
        description_mtime_ns = DESCRIPTION_FILE.stat().st_mtime_ns
        if description_mtime_ns > int(state.get("last_description_mtime_ns", 0)):
            description = DESCRIPTION_FILE.read_text(encoding="utf-8", errors="replace").strip() or None

    frame_count = max(1, min(6, int(cfg.get("heartbeat_frame_count", 3))))
    recent_frames = recent_frame_paths(frame_count)
    newest_frame_sha256 = file_sha256(recent_frames[-1]) if recent_frames else ""
    frame_changed = bool(
        newest_frame_sha256
        and newest_frame_sha256 != state.get("last_frame_sha256", "")
    )
    should_attach_frames = bool(recent_frames and (frame_changed or messages))

    if not messages and description is None and not frame_changed:
        return {"status": "idle"}

    token = secrets.token_urlsafe(24)
    frame_paths, frame_sha256s = freeze_frame_batch(
        token,
        recent_frames if should_attach_frames else [],
    )
    event = {
        "token": token,
        "created_at": utc_now_iso(),
        "messages": messages,
        "description": description,
        "description_mtime_ns": description_mtime_ns,
        "frame_paths": frame_paths,
        "frame_sha256s": frame_sha256s,
        "frame_path": frame_paths[-1] if frame_paths else None,
        "frame_sha256": newest_frame_sha256,
        "frame_changed": frame_changed,
    }
    state["pending"] = event
    atomic_write_json(STATE_FILE, state)
    return {"status": "pending", **event}


def commit(token: str, reply: Optional[str], silent: bool) -> dict:
    state = load_state()
    pending = state.get("pending")
    if not isinstance(pending, dict):
        raise ValueError("没有等待提交的 heartbeat 事件")
    if not secrets.compare_digest(str(pending.get("token", "")), token):
        raise ValueError("heartbeat token 不匹配")
    if silent and reply:
        raise ValueError("--silent 与 --reply 不能同时使用")
    if not silent and not (reply or "").strip():
        raise ValueError("必须提供 --reply，或明确使用 --silent")

    if reply:
        atomic_write_text(DANMAKU_FILE, reply.strip())

    processed = list(dict.fromkeys(state.get("processed_message_ids", [])))
    processed.extend(item["id"] for item in pending.get("messages", []) if item.get("id"))
    state["processed_message_ids"] = list(dict.fromkeys(processed))[-10000:]
    if pending.get("description_mtime_ns"):
        state["last_description_mtime_ns"] = pending["description_mtime_ns"]
    if pending.get("frame_sha256"):
        state["last_frame_sha256"] = pending["frame_sha256"]
    state["pending"] = None
    state["last_commit_at"] = utc_now_iso()
    atomic_write_json(STATE_FILE, state)
    cleanup_frame_batch(list(pending.get("frame_paths", [])))
    return {"status": "committed", "silent": silent}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("poll", help="返回 idle 或一个需要处理的 pending 事件")
    commit_parser = subparsers.add_parser("commit", help="提交 pending 事件的处理结果")
    commit_parser.add_argument("--token", required=True)
    commit_parser.add_argument("--reply")
    commit_parser.add_argument("--silent", action="store_true")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "poll":
            result = poll()
        else:
            result = commit(args.token, args.reply, args.silent)
    except (OSError, ValueError) as exc:
        result = {"status": "error", "error": str(exc)}
        print(json.dumps(result, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
