# Game Buddy v2

Game Buddy 是一个置顶游戏聊天气泡：支持文字输入、本地语音转文字、仅目标游戏窗口截图，以及把可靠消息队列桥接到 Codex。直连模式默认只在玩家发送文字或语音消息时截取一张目标窗口画面；不说话时不会定时截图，也不调用远程视觉 API。

## 快速开始

1. 安装 Python 3.10+；需要 Codex 直连时再安装 Node.js 22+ 和 Codex CLI。Windows 使用 Tkinter 生产窗口；macOS 会通过系统 Swift 工具链自动编译并启动原生 AppKit 窗口。可先运行 `python3 overlay_launcher.py --check`。完整版本、模型和下载说明见 [ENVIRONMENT_AND_MODELS.md](ENVIRONMENT_AND_MODELS.md)。
2. 安装依赖：`python -m pip install -r requirements.txt`。
3. 把 `config.example.json` 复制为 `config.json`，至少填写 `game_window_title`。
4. 启动气泡：`pythonw overlay_launcher.py`。启用 Codex 直连后，发消息时会自动调用 `capture_once.py` 截一张图。
5. 只有使用心跳兼容模式时，才另开终端运行 `python capture_daemon.py` 做周期截图。

`game_window_title` 必须能匹配到目标游戏窗口。找不到窗口时程序会跳过截图，绝不会退回主屏幕。Windows 默认使用 `.venv\Scripts\python.exe` 执行按消息截图；未创建 venv 时回退到 PATH 中的 `python`。也可通过 `capture_python_executable` 明确指定。

## 游戏与词库菜单

点击聊天气泡输入栏旁的 `☰`：

- **游戏**：从本机已安装或仓库自带的 Game Buddy profile 中选择。
- **词库**：统一控制世界书、攻略、术语检索、语音热词和 OCR 校对。
- **攻略/剧透**：`安全（不剧透）`、`当前进度攻略`、`完整剧透攻略`。开启完整剧透前会再次确认。
- **致谢与来源**：显示所选 skill 中记录的游戏作者、汉化团队和 Wiki／攻略来源。

菜单会写入本机 `config.json`。术语检索每次只取当前最相关的 10～30 条；不会把整个大型词库塞进语音模型或 Codex 上下文。

## 外观主题

菜单里的“外观主题”提供三套多巴胺渐变（落日果冻、雪酪俱乐部、宇宙汽水）以及像素农场、烛火秘典、仿生侦探、绯色记忆、鎏金宫廷、全息星图、水晶幻想和极乐世界八套原创主题。每套使用圆角消息卡、主题背景与原创几何点缀；不使用任何官方素材。极乐世界以原创海港晨雾、油画拼贴和半调网点表达侦探手记气质，不含游戏截图、角色或官方标志。主题选择即时写入本机 config.json 的 overlay_theme，只改变外观，不影响语音、菜单、词库、截图或 Codex 直连。

Windows 主题层使用标准 Tkinter；macOS 使用原生 AppKit，避免系统 Tk 8.5 的白窗问题。两端共享同一个 config.json、消息队列、历史、回复文件和主题 ID；有背景图的主题会在两端延伸到无边框顶栏。完整色盘见 THEMES.md。

## 本地语音输入

点击气泡中的麦克风按钮。程序会录制配置时长的单声道音频，通过本地 `faster-whisper` 转成文字，再填入输入框供玩家修改。首次使用会把模型缓存到项目的 `models/` 目录；临时 WAV 会在识别结束后删除，音频不会上传。

主要配置：

```json
{
  "voice_input_device": "麦克风名称片段",
  "voice_record_seconds": 5,
  "voice_language": "zh-CN",
  "voice_model": "base",
  "voice_model_download_root": "models",
  "voice_game_profile": "",
  "voice_game_prompt_max_chars": 700
}
```

`voice_game_profile` 兼容手动配置；通常直接在 `☰` 菜单选择游戏即可。程序会优先从 `game_profile_root` / `voice_game_profile_root` 查找，其次查找仓库内的 `skill-package/game-buddy/assets/game-profiles/` 和已安装的 `$CODEX_HOME/skills/game-buddy/assets/game-profiles/`，再把按优先级截断的核心专有词传给 Whisper `initial_prompt`。大型词库只用于按需检索，不会全部传给 Whisper。

OCR 模式会用相同词库保守校对独立的人名、地点或缩写；模糊度不足时保留 OCR 原文。给 Codex 的每条消息只附加最多 `knowledge_context_term_limit` 条相关术语，默认 20，允许范围 10～30。

## 通用 MCP（Codex / Claude Code / WorkBuddy）

标准 MCP 是共享核心，Codex 插件、Claude Code 和 WorkBuddy 只是不同的导入入口；三者调用同一个本地 stdio 服务。公共轻量 profile 可独立使用，连接桌面气泡时再设置 `GAMEBUDDY_HOME`。完整配置、工具协议和隐私边界见 [mcp/README.md](mcp/README.md)。

发布到 GitHub 后可分别使用：

~~~text
# Codex 插件
codex plugin marketplace add yanjun62/gamebuddy-v1 --ref master
codex plugin add gamebuddy@gamebuddy-open-source

# Claude Code
claude mcp add --transport stdio --scope user gamebuddy -- npx -y github:yanjun62/gamebuddy-v1#master

# 任意支持 stdio MCP 的客户端
npx -y github:yanjun62/gamebuddy-v1#master
~~~

WorkBuddy 可在“连接器 → 自定义连接器”直接粘贴 [mcp/configs/workbuddy.json](mcp/configs/workbuddy.json)。这个 GitHub 入口只包含代码、公开的精简词库和来源说明，不包含本机完整攻略词库、聊天、截图、配置、模型或个人路径。

## Codex 直连

Game Buddy 只向现有代理补充游戏、剧透档位、词库和截图上下文，不创建或替换 AI 人格。代理已经加载的身份、称呼、关系和表达习惯应继续保留；例如 Claude Code 可沿用其 `CLAUDE.md`，Codex 可沿用其 `AGENTS.md`。这些文件只按各代理自身规则加载，Game Buddy 不会为了寻找人格文件而额外扫描目录。

启用 `direct_codex_enabled` 后，气泡会启动 `direct_codex_bridge.js`。桥接程序会：

- 连接仅监听本机的 Codex app-server WebSocket；
- 完成 `initialize`，恢复指定任务或新建专用任务；
- 顺序消费 `message_queue.jsonl`，以消息 UUID 去重；
- 玩家发送消息时先调用 `capture_once.py`，只截取匹配到的目标游戏窗口；
- 在截图更新时间不超过 15 秒时附加 `current_frame.jpg`；
- 只把最终助手消息写入 `danmaku.txt`；
- 把断线、处理中消息和已处理 ID 持久化，采用退避重连。
- 把可恢复的连接波动显示为“正在自动重试”，恢复后清除旧错误状态。
- 首次从心跳切换到直连时继承已处理消息 ID，避免把旧语音从头重放。

建议为气泡使用专用 Codex 任务，并保持 `direct_codex_read_only: true`。桥接实现按当前官方 app-server 协议使用 `thread/resume`、`turn/start`、`item/completed` 和 `turn/completed`。WebSocket 传输仍属实验能力，只应绑定回环地址。参见 [Codex App Server 官方文档](https://learn.chatgpt.com/docs/app-server.md)。

如果不让桥接程序自动启动 app-server，可设置 `direct_codex_spawn_server: false`，然后手动运行：

```powershell
codex app-server --listen ws://127.0.0.1:8766
```

## Claude Code 同会话连接

Claude Code 不需要 Codex app-server。把仓库内的 `skills/game-buddy/` 安装到 Claude Code 的项目级 `.claude/skills/game-buddy/` 或用户级 `~/.claude/skills/game-buddy/`，然后在 Game Buddy 项目目录打开同一个 Claude Code 会话，明确要求它使用 `game-buddy` 技能读取当前 Game Buddy 事件即可。

Claude 路径使用下方的心跳两阶段协议：同一会话执行一次 `heartbeat_bridge.py poll`，只读取返回的消息和 `frame_paths`，给出回复后再用同一个 token `commit`。它不会另开 WebSocket，也不会替换已有 `CLAUDE.md` 人格。首次配置、推荐提示词和完整操作见 [CLAUDE_CODE.md](CLAUDE_CODE.md)。使用此模式时设置 `direct_codex_enabled: false`、`heartbeat_include_messages: true`。

## 心跳兼容层

心跳模式采用两阶段提交，避免事件在 AI 真正处理前就被标记为已读：

```powershell
python heartbeat_bridge.py poll
python heartbeat_bridge.py commit --token <poll 返回的 token> --reply "回复内容"
python heartbeat_bridge.py commit --token <poll 返回的 token> --silent
```

`poll` 会在没有变化时返回 `idle`。有变化时，它把最近 3 张图冻结到独立批次，并通过按时间排序的 `frame_paths` 返回；同一个 pending 会一直返回，直到用匹配 token 提交，随后自动清理冻结帧。这样 AI 读图期间不会被下一次截图覆盖。多句弹幕可在一次 `--reply` 中用换行分隔。直连启用时，心跳默认不重复消费玩家消息；如确有需要，可显式设置 `heartbeat_include_messages: true`。

低延迟心跳可使用更短的调度间隔；`heartbeat_screenshot_min_interval_seconds` 只限制没有玩家消息时的纯画面事件。新文字或语音不受该限流影响，并仍会附带最新截图。这样能快速回答“选哪个”，又避免在玩家没说话时频繁调用模型。

## 文件协议

| 文件 | 写入方 | 读取方 | 用途 |
|---|---|---|---|
| `message_queue.jsonl` | 气泡 | 直连桥/心跳桥 | UUID + UTC 时间戳的可靠消息队列 |
| `message.txt` | 气泡 | 旧桥 | 最新单条消息兼容层 |
| `danmaku.txt` | AI 桥 | 气泡 | 最终助手回复 |
| `chat_history.txt` | 气泡 | 气泡 | 本地聊天历史 |
| `current_frame.jpg` | 按消息截图/截图进程 | AI 桥 | 最新目标窗口帧 |
| `frame_history/` | 截图进程 | 心跳桥 | 本地滚动截图历史，默认保留 6 帧 |
| `.heartbeat_frames/` | 心跳桥 | Codex Heartbeat | pending 期间冻结的最近 3 帧 |
| `description.txt` | 远程视觉/OCR | 心跳 | 可选画面描述 |
| `direct_codex_status.json` | 直连桥 | 气泡/调试者 | `starting`、`ready`、`thinking`、`retrying`、`error` |

运行产生的配置、聊天、截图、状态和消息文件均已加入 `.gitignore`。不要提交 API Key、真实任务 ID、个人路径、聊天历史或截图。

完整的本地启动、停止、验收与故障恢复步骤见 [OPERATIONS.md](OPERATIONS.md)；Codex 定时消费者的强制流程见 [CODEX_HEARTBEAT_RUNBOOK.md](CODEX_HEARTBEAT_RUNBOOK.md)。
