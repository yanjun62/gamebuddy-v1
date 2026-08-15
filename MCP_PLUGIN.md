# Game Buddy as a GitHub-installable Codex plugin

The repository contains a repo marketplace at `.agents/plugins/marketplace.json` and the installable plugin at `plugins/gamebuddy/`. Once these files are published to GitHub, Codex can import the marketplace and install the MCP without copying local configuration files.

~~~text
codex plugin marketplace add yanjun62/gamebuddy-v1 --ref master
codex plugin add gamebuddy@gamebuddy-open-source
~~~

Open a new Codex task after installation. Public, compact game profiles work immediately. To connect the optional desktop overlay bridge, run Codex from the Game Buddy checkout or set `GAMEBUDDY_HOME` before launching Codex. Full local guides and localization-derived glossaries stay outside the public plugin unless their redistribution rights are independently confirmed.

The server uses local stdio, has no network listener, and exposes a two-phase `poll` then `reply`/`silent` workflow for overlay events. See `plugins/gamebuddy/README.md` for the tool list and Windows/macOS setup.
