# Profile authoring

## Goal

Keep runtime speech hints, lore, and walkthrough guidance separate but linked by one stable profile ID.

## Files

For profile ID `example-game`, create:

- `assets/game-profiles/example-game.json`: machine-readable aliases and high-value speech terms.
- `references/games/example-game.md`: human-readable worldbook and guide.
- Optional `assets/glossaries/example-game.json`: a large term set loaded only by lookup.
- One catalog row in `references/catalog.md`.

Copy the supplied JSON and Markdown templates rather than inventing a new schema.

## Profile rules

- Use lowercase hyphen-case IDs.
- Include title aliases players actually say, including common abbreviations and localized names.
- Keep `prompt_prefix` short and neutral.
- Prefer names, places, factions, skills, and mission titles that are frequently spoken or often misrecognized.
- Add common transliterations as aliases without declaring one fan translation universally canonical.
- Assign higher `priority` to the title, protagonist, companions, central factions, and recurring mechanics.
- Keep the default prompt under roughly 700 characters. The exporter stops before the configured limit.
- Do not put plot revelations into speech aliases or the prompt prefix.
- Keep large or spoiler-sensitive term sets out of `stt.terms`. Link them through a profile-level `glossaries` list so they are queried only on demand.
- A glossary entry needs `canonical` and `aliases`; optional `scopes`, `category`, `confidence`, and `needs_review` fields preserve provenance and filtering hints.
- Do not store machine-local paths, credentials, full dialogue corpora, or unneeded source manifests in a glossary.

## Worldbook rules

- Separate spoiler-safe setting facts from revelations.
- Organize by player intent: current task, build, choice, character, faction, history, and completionism.
- Record edition or patch differences next to the affected mechanic.
- Cite sources for exact mission cutoffs, numeric requirements, and disputed translations.
- Write recommendations as guidance, not as a single canonical playthrough.
- Never assume protagonist identity, morality, romance, or prior choices when the game lets the player decide them.

## Validation

```powershell
python scripts/game_profile.py validate assets/game-profiles/example-game.json
python scripts/game_profile.py resolve "localized title"
python scripts/game_profile.py stt-prompt example-game --max-chars 700
python scripts/game_profile.py lookup example-game "a companion name"
python scripts/game_profile.py glossary-stats example-game
```

Check the exported prompt manually for spoilers, duplicates, and low-value item clutter.
