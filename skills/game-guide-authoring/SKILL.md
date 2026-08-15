---
name: game-guide-authoring
description: Create, audit, and maintain spoiler-aware game guides, worldbooks, game profiles, and terminology glossaries with traceable sources and safe redistribution boundaries. Use when a user asks to write or update a walkthrough, companion guide, game lore reference, missables checklist, game vocabulary list, or a reusable game-guide package.
---

# Game Guide Authoring

Build guides that help a player act at the current moment without pretending that incomplete notes are authoritative. Default to a spoiler-safe answer; make a fuller walkthrough an explicit opt-in.

## Workflow

1. Establish the exact game, edition, platform, language/mod state, current objective, and requested spoiler level.
2. Create a short evidence ledger before writing exact mechanics, cutoffs, check difficulties, achievement conditions, or translation claims. Mark each claim as primary, reliable secondary, community report, or unverified.
3. Write the guide in player order: immediate next action, prerequisites, risks/missables, then optional context. Keep hidden consequences in a clearly labelled Full section.
4. Create a profile from `assets/game-profile.json` only when speech/OCR support is needed. Put a short, high-value recognition list in `stt.terms`; keep large vocabularies optional and on-demand.
5. Record sources and rights in the finished guide. Read `references/source-and-release.md` before redistributing any game-derived data.
6. Validate the result: title aliases resolve, the default prompt is small and spoiler-safe, sources support exact claims, and no local paths, credentials, screenshots, subtitles, or dialogue dumps are included.

## Spoiler contract

- **safe:** discuss only the current screen, tutorial-level facts, and facts the player supplied.
- **current-game:** discuss reached material in the current title, but hide later missions and cross-title consequences.
- **full:** reveal hidden outcomes only after explicit permission.

State uncertainty instead of inventing a route. When a choice has a hidden permanent consequence, offer to explain it rather than revealing it by default.

## Deliverables

Use a stable hyphen-case game ID and produce only the pieces the task needs:

- `references/games/<game-id>.md` — worldbook and walkthrough, starting from `references/worldbook-template.md`.
- `assets/game-profiles/<game-id>.json` — optional recognition profile, starting from `assets/game-profile.json`.
- `assets/glossaries/<game-id>.json` — optional large vocabulary, queried only when relevant.
- `references/credits.md` or an equivalent provenance section — source links, localization credit, edition limits, and redistribution conditions.

Do not treat a terminology list as a lore authority or a full walkthrough. Do not call a terminology-only pack a completion guide.

## Release boundary

Do not place copyrighted dialogue, subtitle corpora, screenshots, maps, game bundles, user exports, or local installation artifacts into an open-source release without clear redistribution permission. Keep code and self-authored summaries under their stated license; keep third-party data under its own terms and credit. See `references/source-and-release.md`.
