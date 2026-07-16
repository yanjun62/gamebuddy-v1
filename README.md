# Game Buddy

AI 游戏伙伴：截图 → 识图 → AI 弹幕悬浮窗，边玩边吐槽，支持打字和语音聊天。

## 快速开始

```bash
pip install -r requirements.txt
# 复制 config.example.json 为 config.json，填入 API key
```

一键启动（截图脚本 + 弹幕悬浮窗一起拉起）：

```bash
python start_buddy.py          # 视觉模型识图
python start_buddy.py --ocr    # Windows OCR 识图（免费）
```

Windows 直接双击 `start.bat` 也可以。右键关闭悬浮窗，截图脚本会一起退出。

## 语音输入

悬浮窗输入框旁有 🎤 按钮（快捷键 F2）：按一下开始录音，再按一下结束，
识别出的文字会填进输入框，回车发送。想跳过确认直接发送，把 config.json 里
`voice_auto_send` 设为 `true`。

语音识别走 OpenAI 兼容的 `audio/transcriptions` 接口，在 config.json 配置：

```json
"stt_api_key": "sk-...",
"stt_base_url": "https://api.siliconflow.cn/v1",
"stt_model": "FunAudioLLM/SenseVoiceSmall"
```

不填 `stt_api_key` 时自动复用 `vision_api_key`（同一家 API 时省事）。

## 文件协议

组件之间靠 txt 文件传话（最土也最通用）：

| 文件 | 写入方 | 读取方 | 模式 |
|---|---|---|---|
| `description.txt` | 截图脚本 | AI | 覆盖写 |
| `message.txt` | 悬浮窗（玩家消息，一行一条） | AI | 追加写，AI 读完清空 |
| `danmaku.txt` | AI（一行一条） | 悬浮窗 | 追加写，悬浮窗显示后清空 |

追加+消费模式保证连发多条消息不会丢——玩家快速发几条、AI 连回几条都能收到。

## 组件

- `start_buddy.py` — 一键启动器
- `capture_daemon.py` — 截图 + 视觉模型识图 → description.txt
- `snap_ocr.py` — Windows OCR 版识图（免费替代）
- `danmaku_overlay.py` — 弹幕悬浮窗：聊天历史 + 输入框 + 语音输入
- `game_buddy.py` — 独立全家桶版（自带识图+弹幕生成，不依赖 AI 对话端）
- `knowledge/<game>/` — 每个游戏的攻略知识库，见 SKILL.md
