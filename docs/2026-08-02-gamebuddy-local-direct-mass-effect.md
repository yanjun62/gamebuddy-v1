# 2026-08-02：GameBuddy 本地直连与《质量效应》词库

今天完成了 GameBuddy 的一轮本地能力闭环，并保留这一份简短记录：

- 接通本地语音输入与 Codex app-server 直连；
- 改为玩家说话时抓取一张已配置的游戏窗口，静默时不定时截图、不主动回复；
- 接入 3,205 条《质量效应》传奇版 LE2/LE3 术语；
- 同时保留 `terms.csv`、`aliases.json` 与运行时使用的 JSON 词库；
- 增加《质量效应》profile、世界书、词库检索和安全剧透模式；
- 补充游戏作者、中文汉化项目与社区 Wiki／攻略来源致谢。

本记录只描述今天完成的能力，不包含本地配置、凭据、聊天记录、截图、线程状态或完整字幕数据。可分享的本地压缩包仍在本机保存。

## 来源

游戏与原作版权归 BioWare、Electronic Arts 及相关创作者所有。术语来自 LE2/LE3 英文 TLK 与 Simplified Chinese Localization 社区汉化 TLK 的 String ID 对齐；汉化项目与社区资料来源见仓库内的 `CREDITS.md`。
