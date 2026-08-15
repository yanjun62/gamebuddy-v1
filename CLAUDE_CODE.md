# Claude Code 同会话接入 Game Buddy

Claude Code 走“当前会话 + 本地技能 + 心跳文件协议”，不使用 Codex 的 app-server WebSocket。这样 Claude 自己已有的性格、称呼和 `CLAUDE.md` 会继续生效，Game Buddy 只增加游戏上下文与剧透边界。

## 1. 安装技能

项目级安装：把本包的 `skills/game-buddy/` 整个复制到目标项目：

```text
<你的项目>/.claude/skills/game-buddy/
```

用户级安装：

```text
Windows: %USERPROFILE%\.claude\skills\game-buddy\
macOS/Linux: ~/.claude/skills/game-buddy/
```

目录中应直接存在 `SKILL.md`、`assets/`、`references/` 和 `scripts/`，不要多套一层目录。安装后重新进入 Claude Code 会话，让它重新发现技能。

## 2. 配置 Game Buddy

在 `config.json` 中使用：

```json
{
  "direct_codex_enabled": false,
  "heartbeat_include_messages": true,
  "spoiler_mode": "safe"
}
```

再设置准确的 `game_window_title`，并在气泡菜单选择当前游戏、词库与剧透档位。

## 3. 启动

```powershell
pythonw overlay_launcher.py
python capture_daemon.py
```

第二条只用于希望 Claude 同时读取周期画面时。若只处理玩家发出的消息，也可以按需运行 `capture_once.py`，避免后台持续截图。

## 4. 在同一个 Claude 窗口开始

从 Game Buddy 根目录打开 Claude Code，然后发送：

> 请使用 game-buddy 技能，在当前会话按 heartbeat_bridge.py 的两阶段协议读取 Game Buddy。保持你已有的性格和 CLAUDE.md，默认安全不剧透；每次只处理一个 pending，并在回复后用同一个 token commit。

之后玩家在气泡输入或说话，Claude 在当前会话中执行：

```powershell
python heartbeat_bridge.py poll
```

返回 `pending` 后，它只读取返回的消息、游戏上下文和 `frame_paths`，组织回复，再提交：

```powershell
python heartbeat_bridge.py commit --token <token> --reply "回复内容"
```

如果是无需发言的纯截图事件，可以使用 `--silent`。同一个 pending 在提交前会反复出现，所以不能跳过 commit，也不要让两个 Claude/Codex 消费者同时抢同一队列。

## 5. 它与 Codex 直连的差别

| Claude Code 同会话 | Codex 直连 |
|---|---|
| 当前 Claude 会话主动执行技能和心跳命令 | Node 桥自动连接 Codex app-server |
| 不需要 WebSocket 或 Node.js | 需要 Node.js 22+ 与 Codex CLI |
| 沿用当前 Claude 模型与 `CLAUDE.md` | 沿用 Codex 任务模型与 `AGENTS.md` |
| 适合边聊边玩、手动或会话内循环 | 适合气泡自动排队与回复 |

两种模式共享同一套本地 profile、世界书、截图隐私规则和剧透档位，但不要同时消费同一条玩家消息。
