"""Game Buddy floating chat overlay with reliable queue and local voice input."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from typing import Optional

from bridge_protocol import BASE_DIR, DANMAKU_FILE, append_message


CONFIG_FILE = BASE_DIR / "config.json"
HISTORY_FILE = BASE_DIR / "chat_history.txt"
STATUS_FILE = BASE_DIR / "direct_codex_status.json"
BRIDGE_FILE = BASE_DIR / "direct_codex_bridge.js"


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        value = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"config.json 无法读取: {exc}") from exc
    return value if isinstance(value, dict) else {}


class ChatOverlay:
    def __init__(self, config: dict):
        self.config = config
        self.font_size = int(config.get("overlay_font_size", 12))
        self._running = True
        self._bridge_process: Optional[subprocess.Popen] = None
        self._voice_busy = False
        self._last_danmaku_mtime_ns = 0
        self._last_status_mtime_ns = 0

        self.root = tk.Tk()
        self.root.title("Game Buddy")
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", float(config.get("overlay_alpha", 0.85)))
        self.root.configure(bg="#0d0d0d")

        width, height = 420, 400
        self.root.geometry(f"{width}x{height}")
        self.root.resizable(True, True)
        self.root.minsize(320, 220)
        self._position_window(str(config.get("overlay_position", "tr")), width, height)

        input_frame = tk.Frame(self.root, bg="#1a1a1a", height=42)
        input_frame.pack(fill="x", side="bottom")
        input_frame.pack_propagate(False)

        self.entry = tk.Entry(
            input_frame,
            font=("Microsoft YaHei", 11),
            bg="#2a2a2a",
            fg="#ffffff",
            insertbackground="#ffffff",
            relief="flat",
            bd=8,
        )
        self.entry.pack(fill="both", side="left", expand=True, padx=(6, 2), pady=4)
        self.entry.bind("<Return>", self._send_message)

        self.mic_button = tk.Button(
            input_frame,
            text="🎙",
            command=self._start_voice_input,
            font=("Segoe UI Emoji", 10),
            bg="#3a3a3a",
            fg="#ffffff",
            relief="flat",
            padx=8,
            bd=0,
            cursor="hand2",
        )
        self.mic_button.pack(fill="y", side="right", padx=2, pady=4)

        send_button = tk.Button(
            input_frame,
            text="→",
            command=self._send_message,
            font=("Microsoft YaHei", 10, "bold"),
            bg="#3a3a3a",
            fg="#ffffff",
            relief="flat",
            padx=10,
            bd=0,
            cursor="hand2",
        )
        send_button.pack(fill="y", side="right", padx=(2, 6), pady=4)

        self.status_label = tk.Label(
            self.root,
            text="就绪",
            anchor="w",
            font=("Microsoft YaHei", 9),
            bg="#171717",
            fg="#888888",
            padx=8,
            pady=2,
        )
        self.status_label.pack(fill="x", side="bottom")

        self.history = tk.Text(
            self.root,
            font=("Microsoft YaHei", self.font_size),
            bg="#0d0d0d",
            fg="#d0d0d0",
            wrap="word",
            relief="flat",
            padx=10,
            pady=6,
            state="disabled",
            cursor="arrow",
        )
        self.history.pack(fill="both", expand=True, side="top")
        self.history.tag_config("buddy", foreground="#a8d8ea", font=("Microsoft YaHei", self.font_size, "bold"))
        self.history.tag_config("player", foreground="#f0c0c0", font=("Microsoft YaHei", self.font_size))
        self.history.tag_config("system", foreground="#888888", font=("Microsoft YaHei", max(9, self.font_size - 1)))

        self._append("🐾 Game Buddy 已就绪。打字聊天或按麦克风说话。\n", "system")
        self._load_history()
        self.root.bind("<Button-3>", lambda _event: self._on_close())
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.entry.focus_set()

        if config.get("direct_codex_enabled", False):
            self._start_direct_bridge()
        if DANMAKU_FILE.exists():
            self._last_danmaku_mtime_ns = DANMAKU_FILE.stat().st_mtime_ns

    def _position_window(self, position: str, width: int, height: int) -> None:
        self.root.update_idletasks()
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        positions = {
            "tr": (screen_width - width - 15, 20),
            "tl": (15, 20),
            "br": (screen_width - width - 15, screen_height - height - 50),
            "bl": (15, screen_height - height - 50),
        }
        x, y = positions.get(position, positions["tr"])
        self.root.geometry(f"+{x}+{y}")

    def _append(self, text: str, tag: Optional[str] = None) -> None:
        self.history.config(state="normal")
        self.history.insert("end", text, tag or ())
        self.history.see("end")
        self.history.config(state="disabled")

    def _load_history(self) -> None:
        if not HISTORY_FILE.exists():
            return
        try:
            lines = HISTORY_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return
        for line in lines[-50:]:
            if line.startswith("[Buddy]"):
                self._append(line[7:].lstrip() + "\n", "buddy")
            elif line.startswith("[Player]"):
                self._append(line[8:].lstrip() + "\n", "player")
            elif line.startswith("[系统]"):
                self._append(line[4:].lstrip() + "\n", "system")

    def _save_to_history(self, speaker: str, text: str) -> None:
        timestamp = time.strftime("%H:%M")
        lines = text.splitlines() or [text]
        payload = "".join(f"[{speaker}] [{timestamp}] {line}\n" for line in lines if line.strip())
        if not payload:
            return
        try:
            with HISTORY_FILE.open("a", encoding="utf-8", newline="") as handle:
                handle.write(payload)
        except OSError as exc:
            self._set_status(f"历史记录写入失败: {exc}", error=True)

    def _send_message(self, _event=None) -> None:
        text = self.entry.get().strip()
        if not text:
            return
        try:
            append_message(text)
        except OSError as exc:
            self._set_status(f"消息写入失败: {exc}", error=True)
            return
        self.entry.delete(0, "end")
        self._append(f"{text}\n", "player")
        self._save_to_history("Player", text)
        self._set_status("消息已进入可靠队列")

    def _set_status(self, text: str, *, error: bool = False) -> None:
        if not self._running:
            return
        self.status_label.config(text=text, fg="#d88c8c" if error else "#888888")

    def _voice_status(self, text: str) -> None:
        if self._running:
            self.root.after(0, lambda: self._set_status(text))

    def _start_voice_input(self) -> None:
        if self._voice_busy:
            return
        self._voice_busy = True
        self.mic_button.config(state="disabled")

        def worker() -> None:
            try:
                from voice_input import transcribe_once

                text = transcribe_once(self.config, self._voice_status)
                if self._running:
                    self.root.after(0, lambda: self._finish_voice(text, None))
            except Exception as exc:
                if self._running:
                    self.root.after(0, lambda: self._finish_voice(None, str(exc)))

        threading.Thread(target=worker, name="game-buddy-voice", daemon=True).start()

    def _finish_voice(self, text: Optional[str], error: Optional[str]) -> None:
        self._voice_busy = False
        self.mic_button.config(state="normal")
        if error:
            self._set_status(error, error=True)
            return
        self.entry.delete(0, "end")
        self.entry.insert(0, text or "")
        self.entry.focus_set()

    def _start_direct_bridge(self) -> None:
        configured = str(self.config.get("node_executable", "")).strip()
        node = configured if configured and not configured.startswith("<") else shutil.which("node")
        if not node:
            self._set_status("找不到 Node.js，无法启动 Codex 直连", error=True)
            return
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            self._bridge_process = subprocess.Popen(
                [node, str(BRIDGE_FILE)],
                cwd=str(BASE_DIR),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
        except OSError as exc:
            self._set_status(f"直连桥启动失败: {exc}", error=True)

    def _read_bridge_status(self) -> None:
        if not STATUS_FILE.exists():
            return
        try:
            mtime = STATUS_FILE.stat().st_mtime_ns
            if mtime == self._last_status_mtime_ns:
                return
            self._last_status_mtime_ns = mtime
            value = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
            status = value.get("status", "unknown")
            labels = {"starting": "Codex 连接中…", "ready": "Codex 已连接", "thinking": "Codex 正在回复…", "error": "Codex 直连异常", "stopped": "Codex 直连已停止"}
            self._set_status(labels.get(status, str(status)), error=status == "error")
        except (OSError, json.JSONDecodeError):
            return

    def _on_close(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._bridge_process and self._bridge_process.poll() is None:
            self._bridge_process.terminate()
            try:
                self._bridge_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._bridge_process.kill()
        self.root.destroy()

    def _tick(self) -> None:
        if not self._running:
            return
        try:
            if DANMAKU_FILE.exists():
                mtime = DANMAKU_FILE.stat().st_mtime_ns
                if mtime != self._last_danmaku_mtime_ns:
                    self._last_danmaku_mtime_ns = mtime
                    content = DANMAKU_FILE.read_text(encoding="utf-8", errors="replace").strip()
                    if content:
                        self._append(f"{content}\n", "buddy")
                        self._save_to_history("Buddy", content)
        except OSError as exc:
            self._set_status(f"回复读取失败: {exc}", error=True)
        self._read_bridge_status()
        self.root.after(750, self._tick)

    def start(self) -> None:
        self._tick()
        self.root.mainloop()


def main() -> int:
    try:
        config = load_config()
    except RuntimeError as exc:
        print(f"❌ {exc}")
        return 1
    overlay = ChatOverlay(config)
    print("🎬 Game Buddy 聊天气泡已启动")
    overlay.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
