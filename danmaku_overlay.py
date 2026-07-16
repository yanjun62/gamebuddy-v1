"""
Danmaku Overlay - 悬浮弹幕 + 聊天输入 + 语音输入
上方聊天历史，底部输入框，🎤/F2 语音说话，右键关闭。

文件协议：
- danmaku.txt  AI 追加写入（一行一条），悬浮窗读取显示后清空
- message.txt  玩家消息追加写入（一行一条），AI 读取后清空

Usage: python danmaku_overlay.py
"""

import io
import time
import wave
import threading
import tkinter as tk
from pathlib import Path

CONFIG_DIR = Path(__file__).parent
DANMAKU_FILE = CONFIG_DIR / "danmaku.txt"
MESSAGE_FILE = CONFIG_DIR / "message.txt"
HISTORY_FILE = CONFIG_DIR / "chat_history.txt"


def load_config():
    import json
    cfg_file = CONFIG_DIR / "config.json"
    if cfg_file.exists():
        return json.loads(cfg_file.read_text(encoding='utf-8'))
    return {}


class ChatOverlay:
    def __init__(self, position="tr", font_size=12, alpha=0.85, duration=6, cfg=None):
        cfg = cfg or {}
        self.font_size = font_size
        self.alpha = alpha
        self.duration = duration

        # 语音转文字配置（OpenAI 兼容 API，复用识图 key 兜底）
        self.stt_api_key = (cfg.get("stt_api_key") or cfg.get("vision_api_key")
                            or cfg.get("or_api_key") or "")
        if "YOUR_" in self.stt_api_key:
            self.stt_api_key = ""
        self.stt_base_url = cfg.get("stt_base_url") or cfg.get(
            "vision_base_url", "https://api.siliconflow.cn/v1")
        self.stt_model = cfg.get("stt_model", "FunAudioLLM/SenseVoiceSmall")
        self.voice_auto_send = cfg.get("voice_auto_send", False)
        self.recording = False
        self._stt_client = None

        self.root = tk.Tk()
        self.root.title("Game Buddy")
        self.root.attributes('-topmost', True)
        self.root.attributes('-alpha', alpha)
        self.root.configure(bg='#0d0d0d')

        w, h = 400, 380
        self.root.geometry(f"{w}x{h}")
        self.root.resizable(True, True)
        self.root.minsize(300, 200)

        # 定位
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        positions = {
            "tr": (sw - w - 15, 20),
            "tl": (15, 20),
            "br": (sw - w - 15, sh - h - 50),
            "bl": (15, sh - h - 50),
        }
        x, y = positions.get(position, positions["tr"])
        self.root.geometry(f"+{x}+{y}")

        # === 输入框（先 pack，锁定底部空间） ===
        input_frame = tk.Frame(self.root, bg='#1a1a1a', height=36)
        input_frame.pack(fill='x', side='bottom', before=None)
        input_frame.pack_propagate(False)

        self.entry = tk.Entry(
            input_frame,
            font=('Microsoft YaHei', 11),
            bg='#2a2a2a',
            fg='#ffffff',
            insertbackground='#ffffff',
            relief='flat',
            bd=8
        )
        self.entry.pack(fill='both', side='left', expand=True, padx=(6, 2), pady=3)
        self.entry.bind('<Return>', self._send_message)
        self.entry.focus_set()

        send_btn = tk.Button(
            input_frame,
            text='→',
            command=self._send_message,
            font=('Microsoft YaHei', 10, 'bold'),
            bg='#3a3a3a',
            fg='#ffffff',
            relief='flat',
            padx=10,
            bd=0,
            activebackground='#555555',
            activeforeground='#ffffff',
            cursor='hand2'
        )
        send_btn.pack(fill='y', side='right', padx=(2, 6), pady=3)

        self.mic_btn = tk.Button(
            input_frame,
            text='🎤',
            command=self._toggle_voice,
            font=('Microsoft YaHei', 10),
            bg='#3a3a3a',
            fg='#ffffff',
            relief='flat',
            padx=8,
            bd=0,
            activebackground='#555555',
            activeforeground='#ffffff',
            cursor='hand2'
        )
        self.mic_btn.pack(fill='y', side='right', padx=(2, 0), pady=3)
        self.root.bind('<F2>', self._toggle_voice)

        # === 聊天历史区（填充剩余空间） ===
        self.history = tk.Text(
            self.root,
            font=('Microsoft YaHei', font_size),
            bg='#0d0d0d',
            fg='#d0d0d0',
            wrap='word',
            relief='flat',
            padx=10,
            pady=6,
            state='disabled',
            cursor='arrow'
        )
        self.history.pack(fill='both', expand=True, side='top')

        # 配置标签样式
        self.history.tag_config('buddy', foreground='#a8d8ea', font=('Microsoft YaHei', font_size, 'bold'))
        self.history.tag_config('player', foreground='#f0c0c0', font=('Microsoft YaHei', font_size))
        self.history.tag_config('system', foreground='#888888', font=('Microsoft YaHei', font_size - 1))
        self.history.tag_config('timestamp', foreground='#555555', font=('Microsoft YaHei', 9))

        # 初始内容
        self._append("🐾 Game Buddy 已就绪。打字聊天，🎤/F2 语音，右键关闭。\n", 'system')

        # 加载历史
        self._load_history()

        # 右键退出
        self.root.bind("<Button-3>", lambda e: self.root.destroy())
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._running = True

    def _append(self, text, tag=None):
        """追加文字到历史区"""
        self.history.config(state='normal')
        if tag:
            self.history.insert('end', text, tag)
        else:
            self.history.insert('end', text)
        self.history.see('end')
        self.history.config(state='disabled')

    def _load_history(self):
        """加载已有聊天记录"""
        if HISTORY_FILE.exists():
            try:
                lines = HISTORY_FILE.read_text(encoding='utf-8').strip().split('\n')
                for line in lines[-50:]:  # 最近50条
                    if line.startswith('[Buddy]'):
                        self._append(line[7:] + '\n', 'buddy')
                    elif line.startswith('[Player]'):
                        self._append(line[8:] + '\n', 'player')
                    elif line.startswith('[系统]'):
                        self._append(line[4:] + '\n', 'system')
            except:
                pass

    def _save_to_history(self, speaker, text):
        """追加一条到历史文件"""
        ts = time.strftime('%H:%M')
        line = f"[{speaker}] [{ts}] {text}\n"
        try:
            with open(HISTORY_FILE, 'a', encoding='utf-8') as f:
                f.write(line)
        except:
            pass

    def _send_message(self, event=None):
        """发送消息 → message.txt（追加，一行一条，连发不丢）"""
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, 'end')

        # 显示自己的消息
        self._append(f'{text}\n', 'player')
        self._save_to_history('Player', text)

        # 追加到 message.txt 给 AI 读（AI 读完后清空文件）
        ts = time.strftime('%H:%M:%S')
        with open(MESSAGE_FILE, 'a', encoding='utf-8') as f:
            f.write(f"[{ts}] {text}\n")

    # ====== 语音输入 ======
    def _toggle_voice(self, event=None):
        """🎤/F2 开始录音，再按一次结束并转文字"""
        if self.recording:
            self.recording = False  # 录音线程会自行收尾
            return
        try:
            import sounddevice  # noqa: F401
            import numpy  # noqa: F401
        except ImportError:
            self._append("⚠ 语音需要先安装: pip install sounddevice numpy\n", 'system')
            return
        if not self.stt_api_key:
            self._append("⚠ 未配置语音识别 API，在 config.json 填 stt_api_key\n", 'system')
            return
        self.recording = True
        self.mic_btn.config(text='⏹', bg='#8b2222')
        threading.Thread(target=self._record_worker, daemon=True).start()

    def _record_worker(self):
        """后台线程：录音 → WAV → 语音识别 API"""
        import sounddevice as sd
        import numpy as np
        sr = 16000
        chunks = []
        try:
            with sd.InputStream(samplerate=sr, channels=1, dtype='int16') as stream:
                while self.recording:
                    data, _ = stream.read(int(sr * 0.1))
                    chunks.append(data.copy())
        except Exception as e:
            self.recording = False
            self.root.after(0, self._voice_done, None, f"录音失败: {e}")
            return

        if not chunks:
            self.root.after(0, self._voice_done, None, None)
            return
        audio = np.concatenate(chunks)
        if len(audio) < sr * 0.4:  # 少于0.4秒当误触
            self.root.after(0, self._voice_done, None, None)
            return

        self.root.after(0, lambda: self.mic_btn.config(text='…'))
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(audio.tobytes())

        try:
            text = self._transcribe(buf.getvalue())
        except Exception as e:
            self.root.after(0, self._voice_done, None, f"识别失败: {e}")
            return
        self.root.after(0, self._voice_done, text, None)

    def _transcribe(self, wav_bytes):
        """调用 OpenAI 兼容的 audio/transcriptions 接口"""
        if self._stt_client is None:
            from openai import OpenAI
            self._stt_client = OpenAI(base_url=self.stt_base_url,
                                      api_key=self.stt_api_key)
        resp = self._stt_client.audio.transcriptions.create(
            model=self.stt_model,
            file=("voice.wav", wav_bytes, "audio/wav"),
        )
        return (resp.text or "").strip()

    def _voice_done(self, text, error):
        """录音/识别结束，回到主线程更新 UI"""
        self.recording = False
        self.mic_btn.config(text='🎤', bg='#3a3a3a')
        if error:
            self._append(f"⚠ {error}\n", 'system')
            return
        if not text:
            return
        if self.voice_auto_send:
            self.entry.delete(0, 'end')
            self.entry.insert(0, text)
            self._send_message()
        else:
            # 填进输入框，玩家确认/修改后回车发送
            self.entry.insert('end', text)
            self.entry.focus_set()

    def _on_close(self):
        self._running = False
        self.root.destroy()

    def _tick(self):
        if not self._running:
            return

        # 检查 danmaku.txt（AI 回复）：读出所有行后清空文件。
        # 追加+消费模式，AI 连发多条或重复内容都不会丢。
        try:
            if DANMAKU_FILE.exists() and DANMAKU_FILE.stat().st_size > 0:
                with open(DANMAKU_FILE, 'r+', encoding='utf-8') as f:
                    content = f.read()
                    f.seek(0)
                    f.truncate()
                for line in content.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    self._append(f'{line}\n', 'buddy')
                    self._save_to_history('Buddy', line)
        except OSError:
            pass

        self.root.after(1500, self._tick)

    def start(self):
        self._tick()
        self.root.mainloop()


def main():
    cfg = load_config()
    overlay = ChatOverlay(
        position=cfg.get("overlay_position", "tr"),
        font_size=cfg.get("overlay_font_size", 12),
        alpha=cfg.get("overlay_alpha", 0.85),
        duration=cfg.get("display_duration", 6),
        cfg=cfg,
    )
    print("🎬 聊天弹幕窗已启动（右键关闭，🎤/F2 语音输入，可拖动调整大小）")
    overlay.start()


if __name__ == "__main__":
    main()
