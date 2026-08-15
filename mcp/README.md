# Universal Game Buddy MCP

The MCP server is the shared core. Codex, Claude Code, WorkBuddy, and other MCP clients all launch the same dependency-free stdio process:

~~~text
plugins/gamebuddy/scripts/gamebuddy_mcp_server.js
~~~

It implements newline-delimited JSON-RPC over stdio, supports legacy `initialize` clients and the 2026 `server/discover` flow, writes diagnostics only to stderr, opens no network port, and has no runtime package dependencies.

## GitHub install for generic MCP clients

Use the checked-in GitHub package through `npx`:

~~~json
{
  "mcpServers": {
    "gamebuddy": {
      "type": "stdio",
      "command": "npx",
      "args": [
        "-y",
        "github:yanjun62/gamebuddy-v2#master"
      ]
    }
  }
}
~~~

Clients that do not accept `type` can omit it. A ready-to-paste WorkBuddy variant is in `mcp/configs/workbuddy.json`.

This GitHub command installs only the public MCP, compact profiles, documentation, and license files selected by `package.json`. It does not contain local chat, screenshots, configuration, model files, or private localization-derived glossaries.

## Claude Code

Install from GitHub for the current user:

~~~text
claude mcp add --transport stdio --scope user gamebuddy -- npx -y github:yanjun62/gamebuddy-v2#master
~~~

Or clone the repository and keep the root `.mcp.json` as a project-scoped configuration. Claude Code asks for approval before first using a project MCP. Run `claude mcp get gamebuddy` or use `/mcp` to verify the connection.

## Codex

Native plugin install:

~~~text
codex plugin marketplace add yanjun62/gamebuddy-v2 --ref master
codex plugin add gamebuddy@gamebuddy-open-source
~~~

Standalone MCP install without the skill/plugin wrapper:

~~~text
codex mcp add gamebuddy -- npx -y github:yanjun62/gamebuddy-v2#master
~~~

Start a new Codex task after installing the plugin.

## WorkBuddy

Open **连接器 → 自定义连接器**, paste `mcp/configs/workbuddy.json`, save it, enable `gamebuddy`, and restart WorkBuddy if its tool list does not refresh. WorkBuddy uses the same local stdio process; no HTTP address or token is required.

## Connect the desktop overlay

Public game profiles and spoiler-aware worldbooks work immediately. Overlay event tools need the separate Game Buddy desktop checkout. Set `GAMEBUDDY_HOME` before launching the client, or pass `gamebuddy_home` to a tool.

macOS or Linux:

~~~text
export GAMEBUDDY_HOME="/path/to/gamebuddy-v2"
~~~

Windows PowerShell:

~~~text
$env:GAMEBUDDY_HOME = "C:\\path\\to\\gamebuddy-v2"
~~~

The server checks only that explicit location, the client working directory, and its nearby repository folder. It never crawls the user home directory. Status results omit the resolved path.

## Client-neutral tool contract

- Knowledge calls are read-only and work from the bundled profiles.
- `gamebuddy_get_authoring_kit` exposes the same profile, worldbook, source, and release templates to every MCP client, even when that client does not load Codex skills.
- `gamebuddy_poll` creates or reuses one pending event and returns up to three target-game images.
- The client must finish that event with the same token via `gamebuddy_reply` or `gamebuddy_silent`.
- `safe` is the default. `full` must represent explicit user permission.
- The 10 to 30 result bound is enforced by the terminology search tool itself, not by client prompting.
- `gamebuddy_get_context` returns a whole worldbook when no `query` is given, so its default `max_chars` budget holds the largest bundled profile in full. Lowering it can drop late sections; the result reports `worldbook_truncated` and `worldbook_max_chars` so a short excerpt is never mistaken for spoiler filtering.
