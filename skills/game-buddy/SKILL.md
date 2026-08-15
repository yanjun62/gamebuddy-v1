---
name: game-buddy
description: Provide spoiler-aware game guidance, walkthrough help, lore and character context, screenshot commentary, and speech-recognition terminology from user-authored per-game profiles. Use when a player asks about a game, mission, build, choice, character, faction, world history, wants a game worldbook loaded, or needs proper nouns exported as hints for local speech-to-text.
---

# Game Buddy

Provide game-companion context without replacing the current agent's personality. Load only the active game's profile and worldbook; do not invent missing guide data or treat general model memory as an authoritative walkthrough.

## Personality preservation

Game Buddy is an interaction mode, not a character identity. Preserve the agent's existing identity, personality, names, relationship framing, speech style, and established habits. If the host agent has already loaded personality or project instructions such as Claude Code's `CLAUDE.md` or Codex's `AGENTS.md`, continue following them; do not search for those files merely because they are named here. User-defined personality takes priority over tone suggestions in this skill, except where higher-priority safety requirements or the selected spoiler boundary require otherwise.

## Workflow

1. Identify the game and edition from the request, screenshot, window title, or configured profile.
2. Run `python scripts/game_profile.py resolve "<game name>"` when the title or alias is uncertain.
3. Read [references/catalog.md](references/catalog.md), then load only the matching worldbook.
4. Establish a spoiler level:
   - `safe` by default: reveal only visible or player-supplied information.
   - `current-game`: discuss the current title, but hide sequels and imported-save consequences.
   - `full`: reveal hidden outcomes only after explicit permission.
5. Lead with an actionable answer. Add lore only when it helps the current decision.
6. Mark uncertain or missing information. Verify exact numbers, mission expiry, and edition differences before presenting them as facts.

## Response modes

- **Overlay:** Write 1–3 compact lines tied to the current moment, using the agent's established voice.
- **Guide:** Give the recommendation first, then requirements, risks, and missables within the spoiler boundary.
- **Worldbook:** Explain people, factions, places, history, terminology, and relationships.
- **Choice help:** Compare what is safe to reveal, then ask before exposing hidden consequences.

## Local overlay session bridge

When this skill is running inside a Game Buddy project and the player asks to read the current overlay event or game frame, use the repository's two-phase heartbeat protocol instead of inventing unseen state:

1. Run `python heartbeat_bridge.py poll` exactly once and parse its JSON.
2. If it returns `pending`, use only the returned player messages, game context, and ordered `frame_paths`. Never substitute a desktop or unrelated window capture.
3. Produce one spoiler-appropriate reply in the current agent's established personality.
4. Commit the same token with `python heartbeat_bridge.py commit --token <token> --reply "<reply>"`. Use `--silent` only when intentionally draining a screenshot-only event without a player-visible reply.
5. Do not poll again before the current token is committed. If the result is `idle`, report that no new Game Buddy event is waiting.

Claude Code can use this route directly in the same terminal conversation after the skill is installed under `.claude/skills/game-buddy/` or `~/.claude/skills/game-buddy/`; it does not need the Codex WebSocket bridge. Continue honoring any already-loaded `CLAUDE.md` instructions.

## Game profiles

List and resolve installed profiles:

```powershell
python scripts/game_profile.py list
python scripts/game_profile.py resolve "<title or alias>"
```

Export a compact Whisper `initial_prompt` from the active profile:

```powershell
python scripts/game_profile.py stt-prompt <profile-id> --max-chars 700
```

Look up a possibly misheard term:

```powershell
python scripts/game_profile.py lookup <profile-id> "<term>"
python scripts/game_profile.py lookup <profile-id> "<term>" --scope <game-or-edition>
python scripts/game_profile.py glossary-stats <profile-id>
```

The compact `stt.terms` list is the only vocabulary exported into the speech prompt. Linked glossaries are loaded on demand by `lookup`; never inject an entire glossary into a model or speech recognizer.

Do not activate a game's vocabulary globally. Select a profile only while that game is active. Speech terms and glossary matches are recognition hints, not authoritative lore. Prefer the player's on-screen localization when it differs.

Read [references/credits.md](references/credits.md) when explaining data provenance, adapting a profile, or preparing any distribution. Preserve game-author, localization-team, Wiki, and guide-source attribution.

## Authoring a game

Read [references/profile-authoring.md](references/profile-authoring.md). Start from:

- `assets/templates/game-profile.json`
- `references/worldbook-template.md`

Add exactly one structured profile under `assets/game-profiles/` and one worldbook under `references/games/`, then add the game to `references/catalog.md`. Large bilingual term sets belong under `assets/glossaries/` and are linked by the profile's optional `glossaries` list. Run `validate`, `resolve`, `stt-prompt`, `glossary-stats`, and `lookup` before using it.
