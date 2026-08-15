# GameBuddy theme assets

Original generated UI assets for the local GameBuddy theme system. These files
use thematic visual language only; they do not reproduce game logos, characters,
or official interface artwork.

## Theme files

Each directory under `themes/` contains a vertical overlay background. The app
prefers `background-v2.png` when present, then falls back to `background-v1.png`.
Backgrounds use aspect-fill in the panel with a readability wash when needed.

Legacy `bubble-frame-v1.png` and `chat-frame-v1.png` experiments are kept locally
but are intentionally not loaded. Production themes use backgrounds, rounded
message cards, and title wordmarks only.

Included themes:

- `pixel-farm`
- `candlelit-codex`
- `synthetic-detective`
- `crimson-memory`
- `gilded-court`
- `holographic-star-map`
- `crystal-fantasy`

## GameBuddy wordmarks

- `wordmarks/gamebuddy-pixel-v1.png`
- `wordmarks/gamebuddy-retro-v1.png`
- `wordmarks/gamebuddy-scifi-v1.png`

These are transparent title wordmarks, not font files. Keep normal UI and chat
copy as real text for accessibility and localization. Choose the pixel wordmark
for cozy/pixel themes, retro for historical/fantasy themes, and sci-fi for HUD
themes.

## Integration notes

- Do not bake chat text into the frame asset.
- Keep current voice, menu, send, game selector, glossary, and spoiler controls.
- On Windows use Pillow/Tk image support; on macOS use SwiftUI `Image` with
  aspect-fill for theme backgrounds.
- Generated source prompts are recorded in the Codex task that produced this
  asset pack. Final PNGs are local project files and have not been uploaded.
