# GameBuddy Codex Heartbeat Runbook

本文件所在目录就是 GameBuddy 项目目录。所有命令都应在该目录执行，Python 使用 `.venv\Scripts\python.exe`。

## 每次定时运行必须执行

1. 运行 `heartbeat_bridge.py poll` 恰好一次并解析 JSON。
2. `status` 为 `idle`：安静结束。
3. `status` 为 `error`：报告原始错误并停止，不得编造 token。
4. `status` 为 `pending`：保存 token，并在本次运行内完成该事件。
   - 读取 `messages` 中的全部玩家消息；有消息时必须回答最新一条。
   - `frame_paths` 存在时，按数组顺序查看全部图片。它们是桥接器冻结的最近三帧，不会在读图时被覆盖。
   - 兼容旧事件：没有 `frame_paths` 时才使用 `frame_path`。
   - 主事件的 `frame_changed` 为 `true` 时，只要图片可读，就必须结合三帧变化发送弹幕；菜单、地图和纯动画变化也不能静默丢弃。
   - 任一冻结帧无法打开或不可读：静默提交该事件，并在本次运行中报告准确错误。
   - 通常发送 2–3 行自然中文短句，每行约 12–30 个汉字，用换行分隔。各行要互补、不重复；语气俏皮、稍毒舌但偏心玩家。
   - 结束前必须执行 `commit --token <token> --reply <text>`，或明确执行 `commit --token <token> --silent`。
5. 第一次 commit 后额外 poll 恰好一次，用于接住被旧 pending 挡住的玩家消息。
   - `idle`：停止。
   - 有玩家消息：正常看图、回复并 commit。
   - 只有截图：silent commit 后停止；这是排空队列，不是同一分钟的第二次截图吐槽。
6. 任何成功 poll 到的 pending 都不得遗留。拿到 token 后绝不能跳过 commit 继续 poll。

## 互斥规则

Codex Heartbeat 是唯一轮询器。它启用时不得同时运行旧的 `heartbeat_loop.ps1`。
