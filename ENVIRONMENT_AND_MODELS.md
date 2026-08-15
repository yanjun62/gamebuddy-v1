# Game Buddy 环境与模型说明

这份开源包包含源代码、原创主题资源、示例配置、游戏 profile／世界书和测试，不包含虚拟环境、模型权重、API Key、登录信息、聊天记录或截图。模型在用户明确启用对应功能后，由用户自己的环境下载或调用。

## 推荐环境

| 项目 | 最低要求 | 推荐 / 本次验证 |
|---|---|---|
| Windows | Windows 10/11、Python 3.10+、Tk 8.6 | Windows 11；Python 3.14.3；Tk 8.6 |
| macOS | 可运行 Python 3.10+；Xcode Command Line Tools 提供 Swift 5 | 原生 AppKit 前端会在首次启动时本地编译；本次发布未在 macOS 实机复测 |
| Node.js | 仅 Codex 直连需要，22+ | Node.js 24.13.0 |
| Codex CLI | 仅 Codex 直连需要；应能在终端完成登录并运行 `codex app-server` | 不锁定 CLI 版本；app-server 仍是实验能力 |
| Claude Code | 仅 Claude 同会话模式需要 | 安装 `game-buddy` 技能后使用本地心跳协议，不需要 Node.js app-server |

Python 依赖以 `requirements.txt` 为准。本次 Windows 环境已验证 `numpy 2.5.2`、`Pillow 12.3.0`、`mss 10.2.0`、`sounddevice 0.5.5`、`faster-whisper 1.2.1`。这些是验证快照，不是强制锁版本；全新安装建议使用 Python 3.11 或 3.12，以获得更稳妥的第三方 wheel 覆盖。

推荐安装：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe overlay_launcher.py --check
```

Windows 启动器发现项目 `.venv` 中已安装 `sounddevice` 与 `faster-whisper` 后，会自动切换到该环境，避免从其他 Python 启动而出现“缺少语音组件”。项目路径可以包含空格。

## 本地语音模型

- 引擎：`faster-whisper`，本地推理，不把录音上传。
- 默认模型：`base`。
- 默认设备：`cpu`；默认计算类型：`int8`，无需独立显卡。
- 默认缓存：项目 `models/`。首次点击麦克风时按 `voice_model` 下载；模型目录不会进入公开压缩包。
- 可选模型：可把 `voice_model` 改为 faster-whisper 支持的其他 Whisper 模型名。模型越大通常越慢、占用越高；开源版不替用户自动改档位。
- 临时音频：识别完成后删除。

如果首次下载失败，检查网络代理和磁盘空间后重试。若完全不需要语音，其他文字、主题、截图和词库功能仍可使用。

## Codex 使用的模型

Game Buddy 不内置、不下载、也不强制指定某个 Codex 大模型。`direct_codex_bridge.js` 连接用户本机已登录的 Codex CLI，并沿用专用任务或当前 Codex 配置所选择的模型、人格与项目规则。Game Buddy 只补充玩家消息、剧透档位、相关术语和一张新鲜的目标窗口截图。

Codex 直连需要：

```powershell
node --version
codex app-server --listen ws://127.0.0.1:8766
```

默认只绑定 `127.0.0.1`，并建议保持 `direct_codex_read_only: true`。app-server WebSocket 属于实验接口，升级 Codex CLI 后应先运行测试并做一次短消息验收。

## Claude Code 使用的模型

Claude 同会话模式同样不锁定 Claude 模型。它沿用用户当前 Claude Code 会话、`CLAUDE.md` 和账户配置；`game-buddy` 技能只是教当前会话如何按剧透边界读取 profile、世界书、消息和截图。详细步骤见 `CLAUDE_CODE.md`。

## 可选远程视觉模型

默认 `capture_mode: local_snapshot` 只保存本地目标窗口截图，不调用远程视觉 API。只有用户主动改成 `remote_vision` 时，`snap.py` 才会读取 `vision_base_url`、`vision_model` 和用户自己的 `vision_api_key`。示例配置当前写有 DashScope 兼容接口和 `qwen3.5-omni-plus`，它只是可选示例，不是运行必需项，也不随包提供 Key。

## 发布包明确不包含

- `.venv/`、`models/`、`__pycache__/`、编译产物；
- `config.json`、任何 API Key、Codex/Claude 登录状态或任务 ID；
- `chat_history.txt`、消息队列、回复、状态文件；
- `current_frame.jpg`、录屏截图、临时音频和冻结帧；
- 私有大型双语词库、游戏资源、官方截图或官方标志；
- 开发备份、`.bak`、临时补丁和本机绝对路径。
