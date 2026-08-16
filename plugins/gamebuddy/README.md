# Game Buddy Codex plugin and MCP

This plugin adds spoiler-aware Game Buddy guidance and a dependency-free local MCP server to Codex. The public profile bundle works immediately after installation. Connecting the MCP server to the desktop overlay is optional and remains entirely local.

## Install from GitHub

After this repository is published, run:

~~~text
codex plugin marketplace add yanjun62/gamebuddy-v2 --ref master
codex plugin add gamebuddy@gamebuddy-open-source
~~~

Start a new Codex task after installation so the skill and MCP tools are loaded.

## What works without desktop setup

- List the bundled public game profiles.
- Load a spoiler-filtered worldbook for the selected game.
- Search only the 10 to 30 most relevant names and terms.
- Read source and localization credits.

The public bundle currently includes compact profiles for *Disco Elysium — The Final Cut* and *Mass Effect Legendary Edition* LE2/LE3. It does not include extracted dialogue, screenshots, maps, save data, the private 424-entry Disco Elysium actor export, or the private 3,205-entry Mass Effect localization glossary.

## Connect a local Game Buddy overlay

The MCP server automatically connects when Codex is running from a Game Buddy checkout. Otherwise, set `GAMEBUDDY_HOME` to the extracted or cloned Game Buddy folder before starting Codex.

macOS or Linux:

~~~text
export GAMEBUDDY_HOME="/path/to/gamebuddy-v2"
codex
~~~

Windows PowerShell:

~~~text
$env:GAMEBUDDY_HOME = "C:\\path\\to\\gamebuddy-v2"
codex
~~~

`GAMEBUDDY_PYTHON` is optional. Set it only when the overlay must use a specific Python executable for its heartbeat bridge.

## MCP tools

| Tool | Effect |
|---|---|
| `gamebuddy_list_games` | Lists available public and locally installed profiles without revealing file paths. |
| `gamebuddy_get_context` | Returns a spoiler-filtered worldbook excerpt for one game. |
| `gamebuddy_search_terms` | Retrieves 10 to 30 relevant terms instead of loading a whole glossary. |
| `gamebuddy_get_credits` | Returns source, localization, Wiki, and guide acknowledgements. |
| `gamebuddy_get_authoring_kit` | Returns the generic profile/worldbook templates and release rules to every MCP client. |
| `gamebuddy_status` | Reports sanitized local overlay status; it never returns task IDs or private paths. |
| `gamebuddy_poll` | Reads one pending overlay event and returns its target-game frames as MCP image content. |
| `gamebuddy_reply` | Commits a reply using the event token returned by `gamebuddy_poll`. |
| `gamebuddy_silent` | Explicitly commits an event without a visible reply. |

`gamebuddy_poll` and both commit tools require a connected desktop checkout. The token makes the read/reply sequence two-phase: the event remains pending until the matching token is committed.

## Privacy and safety

- The MCP transport is local stdio. It opens no listening port and makes no network request.
- It does not scan the home directory. It checks only an explicit `gamebuddy_home`, `GAMEBUDDY_HOME`, the current working directory, and the repository location around the plugin.
- Local status output omits absolute paths, Codex task IDs, credentials, raw config, and prior chat history.
- Game frames are returned only after an explicit poll and only when the desktop bridge produced paths inside the selected Game Buddy folder.
- `safe` is the default spoiler mode. Full-spoiler worldbook sections are removed unless `full` is explicitly requested.

See `THIRD_PARTY_NOTICES.md` and `skills/game-buddy/references/credits.md` before redistributing or extending game-derived data.
