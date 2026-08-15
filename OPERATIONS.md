# GameBuddy 本地使用与维护

## 推荐模式：直连时按消息截图

启用 `direct_codex_enabled: true` 与 `capture_on_message: true` 后，只需要启动聊天气泡。玩家发送文字或语音消息时，直连桥会先调用 `capture_once.py` 截取一张目标游戏窗口，再把新鲜画面附给 Codex；玩家不说话时不会定时截图。Windows 会优先使用项目 `.venv\Scripts\python.exe`，找不到时回退到 PATH 中的 `python`。

`game_window_title` 为空、窗口未找到或窗口已最小化时都会安全跳过，不会回退到桌面截图。

## 心跳兼容模式

2026-07-18 已用 *Sultan's Game* 完整验证以下链路：

`目标游戏窗口 → 每 10 秒截图 → 最近三帧冻结 → Codex Heartbeat 看图/读玩家消息 → 2–3 行弹幕 → Game Buddy 窗口显示`

当前推荐配置：

- `capture_mode: local_snapshot`：截图仅保存在本机，不调用远程视觉 API。
- `capture_interval: 10`：每 10 秒截图一次。
- `capture_history_size: 6`：滚动保留最近 6 帧。
- `heartbeat_frame_count: 3`：每次 heartbeat 冻结并读取最近 3 帧。
- `heartbeat_include_messages: true`：heartbeat 同时可靠消费文字和语音转写后的玩家消息。

## 首次准备

在项目目录打开 PowerShell：

```powershell
Copy-Item .\config.example.json .\config.json
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
```

编辑本机的 `config.json`，至少设置 `game_window_title`。`config.json`、截图、聊天记录、模型和运行状态均已忽略，不应提交到 Git。

检查弹幕窗口所需 Tcl/Tk：

```powershell
.\.venv\Scripts\python.exe .\overlay_launcher.py --check
```

## 启动顺序（心跳兼容模式）

1. 先启动游戏，并让窗口标题与 `game_window_title` 匹配。
2. 启动截图进程。调试时建议在可见终端运行，确认每 10 秒出现一条 `[Snap]`：

   ```powershell
   .\.venv\Scripts\python.exe .\capture_daemon.py
   ```

3. 启动置顶弹幕窗口：

   ```powershell
   .\.venv\Scripts\pythonw.exe .\overlay_launcher.py
   ```

4. 在 Codex 的“已安排”中启用现有的 `GameBuddy 心跳`。它必须读取仓库内的 `CODEX_HEARTBEAT_RUNBOOK.md`。
5. 不要同时运行 `heartbeat_loop.ps1`；它只是旧的本地轮询器，会与 Codex Heartbeat 抢同一个 pending。

## 日常使用

- 文字：在 Game Buddy 底部输入框输入并回车，状态栏出现“消息已进入可靠队列”。
- 语音：点麦克风，等待本地模型转写；文字会先填入输入框，确认或修改后再回车发送。
- 画面：直连模式在每次发送消息时截一张；心跳模式由截图进程周期抓取。两者都只抓匹配到的目标游戏窗口，找不到时会跳过，不会退回桌面截图。
- 回复：主 heartbeat 会按时间读取三帧并发送 2–3 行；第一次提交后的额外 poll 只负责排空被 pending 挡住的消息，截图-only 事件会静默提交。

## 正确停止

按此顺序停止，避免留下无法提交的 pending：

1. 先在 Codex 的“已安排”中暂停 `GameBuddy 心跳`。
2. 如果当时已有 heartbeat 正在处理，让它完成当前 reply/silent commit；检查 `.heartbeat_state.json` 中 `pending` 为 `null`。
3. 关闭 Game Buddy 窗口。
4. 在截图终端按 `Ctrl+C` 停止 `capture_daemon.py`。
5. 确认没有单独运行的 `heartbeat_loop.ps1`。

若进程是在后台启动、没有可见终端，可在管理员 PowerShell 中只停止 GameBuddy 的 Python 进程：

```powershell
$targets = Get-CimInstance Win32_Process | Where-Object {
  $_.Name -in @('python.exe', 'pythonw.exe') -and
  ($_.CommandLine -like '*capture_daemon.py*' -or $_.CommandLine -like '*overlay_launcher.py*')
}
$targets | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

## 验收清单

1. `frame_history/` 中最多保留配置数量的图片，时间间隔约 10 秒。
2. `heartbeat_bridge.py poll` 返回按时间排序的 3 个 `frame_paths` 和不同的 `frame_sha256s`。
3. 拿到 `pending` 后必须用同一 token commit；commit 后 `.heartbeat_state.json` 的 `pending` 为 `null`。
4. `danmaku.txt` 的多行回复能显示在 Game Buddy 窗口。
5. 玩家连续发消息时，第一事件 commit 后的额外 poll 能接到被挡住的消息。
6. 运行测试：

   ```powershell
   .\.venv\Scripts\python.exe -m unittest discover -s tests -v
   ```

## 常见问题

- 心跳反复拿到同一 token：说明上一次 pending 尚未 commit；不要继续 poll，先提交该 token。
- 玩家消息没出现：确认 `heartbeat_include_messages` 为 `true`，并检查 `message_queue.jsonl`。
- 弹幕窗口不启动：先运行 `overlay_launcher.py --check`，不要直接绕过启动器。
- 语音首次较慢：本地 Whisper 模型需要首次下载并缓存到 `models/`。
- 截图没有更新：确认游戏窗口标题匹配，且游戏窗口没有关闭。
- 同一分钟刷两次：确认额外 poll 的截图-only 事件使用 silent commit。
