---
name: game-buddy
description: Provide spoiler-aware game guidance, walkthrough help, lore and character context, screenshot commentary, and speech-recognition terminology from user-authored per-game profiles. Use when a player asks about a game, mission, build, choice, character, faction, world history, wants a game worldbook loaded, or needs proper nouns exported as hints for local speech-to-text.
---

# Game Buddy

Provide game-companion context without replacing the current agent's personality. Load only the active game's profile and worldbook; do not invent missing guide data or treat general model memory as an authoritative walkthrough.

## Personality preservation

Game Buddy is an interaction mode, not a character identity. Preserve the agent's existing identity, personality, names, relationship framing, speech style, and established habits. Continue following host-level instructions already loaded by Codex, Claude Code, WorkBuddy, or another MCP client. User-defined personality takes priority over tone suggestions in this skill, except where higher-priority safety requirements or the selected spoiler boundary require otherwise.

## Workflow

1. Call `gamebuddy_list_games` when the title is uncertain. Load only the matching profile.
2. Establish a spoiler level:
   - `safe` by default: reveal only visible or player-supplied information.
   - `current-game`: discuss reached content in the current title while hiding later consequences.
   - `full`: reveal hidden outcomes only after explicit permission.
3. Call `gamebuddy_get_context` with the current question and selected spoiler level.
4. Use `gamebuddy_search_terms` only for the current utterance, subtitle, OCR result, person, place, or abbreviation. Never request or inject an entire glossary.
5. Lead with the actionable answer. Add requirements, risks, lore, or missables only when useful.
6. Mark uncertain or missing information. Verify exact numbers, mission expiry, and edition differences before presenting them as facts.

## Response modes

- **Overlay:** Write 1–3 compact lines tied to the current moment, using the agent's established voice.
- **Guide:** Give the recommendation first, then requirements, risks, and missables within the spoiler boundary.
- **Worldbook:** Explain people, factions, places, history, terminology, and relationships.
- **Choice help:** Compare what is safe to reveal, then ask before exposing hidden consequences.

## Local overlay session bridge

The MCP tool names may be prefixed by the host client, but their final names remain the same.

1. Call `gamebuddy_status` when connection state is uncertain.
2. Call `gamebuddy_poll` exactly once.
3. If it returns `pending`, use only the returned player messages, game context, and ordered image content. Never invent an unseen screen or substitute a desktop capture.
4. Produce one spoiler-appropriate reply in the current agent's established personality.
5. Commit the same token with `gamebuddy_reply`. Use `gamebuddy_silent` only when intentionally handling the event without a player-visible answer.
6. Do not poll again before the current token is committed. If the result is `idle`, report that no new Game Buddy event is waiting.

The two-phase token contract is client-neutral and applies equally to Codex, Claude Code, WorkBuddy, and other MCP clients.

## Game profiles and terminology

The public plugin includes compact profiles under `assets/game-profiles/`. These terms are recognition hints, not authoritative lore. Prefer the player's installed localization when it differs.

For direct local profile maintenance, the included helper supports:

~~~text
python scripts/game_profile.py list
python scripts/game_profile.py resolve "<title or alias>"
python scripts/game_profile.py stt-prompt <profile-id> --max-chars 700
python scripts/game_profile.py lookup <profile-id> "<term>"
python scripts/game_profile.py glossary-stats <profile-id>
~~~

Linked glossaries are loaded on demand. Never activate one game's vocabulary globally, and never inject a complete large glossary into the model or speech recognizer.

Read `references/credits.md` when explaining provenance, adapting a profile, or preparing a distribution. Preserve game-author, localization-team, Wiki, and guide-source attribution.

## Authoring a game

Read `references/profile-authoring.md`. Start from:

- `assets/templates/game-profile.json`
- `references/worldbook-template.md`

Add exactly one structured profile under `assets/game-profiles/` and one worldbook under `references/games/`, then add the game to `references/catalog.md`. Large bilingual term sets belong under `assets/glossaries/` and are linked by the profile's optional `glossaries` list. Run `validate`, `resolve`, `stt-prompt`, `glossary-stats`, and `lookup` before using it.
