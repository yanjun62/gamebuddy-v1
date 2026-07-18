# Game Buddy v2

Game Buddy 是一个置顶游戏聊天气泡：支持文字输入、本地语音转文字、仅目标游戏窗口截图，以及把可靠消息队列桥接到 Codex。默认截图模式每 10 秒拍一帧，在本机滚动保留最近 6 帧，不调用远程视觉 API。

## 快速开始

1. 安装 Python 3.9+、Node.js 22+ 和 Codex CLI。
2. 安装依赖：`python -m pip install -r requirements.txt`。
3. 把 `config.example.json` 复制为 `config.json`，至少填写 `game_window_title`。
4. 启动截图：`python capture_daemon.py`。
5. 启动气泡：`pythonw overlay_launcher.py`。

`game_window_title` 必须能匹配到目标游戏窗口。找不到窗口时程序会跳过截图，绝不会退回主屏幕。

## 本地语音输入

点击气泡中的麦克风按钮。程序会录制配置时长的单声道音频，通过本地 `faster-whisper` 转成文字，再填入输入框供玩家修改。首次使用会把模型缓存到项目的 `models/` 目录；临时 WAV 会在识别结束后删除，音频不会上传。

主要配置：

```json
{
  "voice_input_device": "麦克风名称片段",
  "voice_record_seconds": 5,
  "voice_language": "zh-CN",
  "voice_model": "base",
  "voice_model_download_root": "models"
}
```

## Codex 直连

启用 `direct_codex_enabled` 后，气泡会启动 `direct_codex_bridge.js`。桥接程序会：

- 连接仅监听本机的 Codex app-server WebSocket；
- 完成 `initialize`，恢复指定任务或新建专用任务；
- 顺序消费 `message_queue.jsonl`，以消息 UUID 去重；
- 在截图更新时间不超过 15 秒时附加 `current_frame.jpg`；
- 只把最终助手消息写入 `danmaku.txt`；
- 把断线、处理中消息和已处理 ID 持久化，采用退避重连。

建议为气泡使用专用 Codex 任务，并保持 `direct_codex_read_only: true`。桥接实现按当前官方 app-server 协议使用 `thread/resume`、`turn/start`、`item/completed` 和 `turn/completed`。WebSocket 传输仍属实验能力，只应绑定回环地址。参见 [Codex App Server 官方文档](https://learn.chatgpt.com/docs/app-server.md)。

如果不让桥接程序自动启动 app-server，可设置 `direct_codex_spawn_server: false`，然后手动运行：

```powershell
codex app-server --listen ws://127.0.0.1:8766
```

## 心跳兼容层

心跳模式采用两阶段提交，避免事件在 AI 真正处理前就被标记为已读：

```powershell
python heartbeat_bridge.py poll
python heartbeat_bridge.py commit --token <poll 返回的 token> --reply "回复内容"
python heartbeat_bridge.py commit --token <poll 返回的 token> --silent
```

`poll` 会在没有变化时返回 `idle`。有变化时，它把最近 3 张图冻结到独立批次，并通过按时间排序的 `frame_paths` 返回；同一个 pending 会一直返回，直到用匹配 token 提交，随后自动清理冻结帧。这样 AI 读图期间不会被下一次截图覆盖。多句弹幕可在一次 `--reply` 中用换行分隔。直连启用时，心跳默认不重复消费玩家消息；如确有需要，可显式设置 `heartbeat_include_messages: true`。

## 文件协议

| 文件 | 写入方 | 读取方 | 用途 |
|---|---|---|---|
| `message_queue.jsonl` | 气泡 | 直连桥/心跳桥 | UUID + UTC 时间戳的可靠消息队列 |
| `message.txt` | 气泡 | 旧桥 | 最新单条消息兼容层 |
| `danmaku.txt` | AI 桥 | 气泡 | 最终助手回复 |
| `chat_history.txt` | 气泡 | 气泡 | 本地聊天历史 |
| `current_frame.jpg` | 截图进程 | AI 桥 | 最新目标窗口帧 |
| `frame_history/` | 截图进程 | 心跳桥 | 本地滚动截图历史，默认保留 6 帧 |
| `.heartbeat_frames/` | 心跳桥 | Codex Heartbeat | pending 期间冻结的最近 3 帧 |
| `description.txt` | 远程视觉/OCR | 心跳 | 可选画面描述 |
| `direct_codex_status.json` | 直连桥 | 气泡/调试者 | `starting`、`ready`、`thinking`、`error` |

运行产生的配置、聊天、截图、状态和消息文件均已加入 `.gitignore`。不要提交 API Key、真实任务 ID、个人路径、聊天历史或截图。

完整的本地启动、停止、验收与故障恢复步骤见 [OPERATIONS.md](OPERATIONS.md)；Codex 定时消费者的强制流程见 [CODEX_HEARTBEAT_RUNBOOK.md](CODEX_HEARTBEAT_RUNBOOK.md)。
