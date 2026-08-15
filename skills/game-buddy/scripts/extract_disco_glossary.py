#!/usr/bin/env python3
"""Read official Disco Elysium bundles and export only bilingual actor names."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def load_named_tree(path: Path, name: str) -> dict[str, Any]:
    try:
        import UnityPy
    except ImportError as exc:
        raise SystemExit(
            "UnityPy is required for this optional read-only extractor. "
            "Install it in a temporary environment and retry."
        ) from exc

    environment = UnityPy.load(str(path))
    for obj in environment.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        tree = obj.read_typetree()
        if tree.get("m_Name") == name:
            return tree
    raise ValueError(f"{name!r} not found in {path}")


def term_map(tree: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for term in tree["mSource"]["mTerms"]:
        values = term.get("Languages", [])
        if values:
            result[str(term.get("Term", ""))] = str(values[0])
    return result


def field_map(fields: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        str(field.get("title", "")): field.get("value")
        for field in fields
        if isinstance(field, dict)
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chinese-bundle", required=True, type=Path)
    parser.add_argument("--dialogue-bundle", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--build-id", default="unknown")
    args = parser.parse_args()

    general = term_map(load_named_tree(args.chinese_bundle, "GeneralLockitChinese"))
    database = load_named_tree(args.dialogue_bundle, "Disco Elysium")
    entries: list[dict[str, Any]] = []
    for actor in database.get("actors", []):
        fields = field_map(actor.get("fields", []))
        articy_id = str(fields.get("Articy Id", "")).strip()
        english = str(fields.get("Name", "")).strip()
        chinese = general.get(f"Actors/{articy_id}/Name", "").strip()
        if not english or not chinese or chinese == '"':
            continue
        aliases = [] if english.casefold() == chinese.casefold() else [english]
        entries.append(
            {
                "canonical": chinese,
                "aliases": aliases,
                "scopes": ["The Final Cut"],
                "category": "角色/说话者",
                "source_id": articy_id,
            }
        )

    entries.sort(key=lambda entry: (entry["canonical"].casefold(), entry["source_id"]))
    output = {
        "schema_version": 1,
        "id": "disco-elysium-official-actors-schinese",
        "display_name": "Disco Elysium official Simplified Chinese actor names",
        "source": {
            "kind": "installed-game-localization",
            "steam_app_id": 632470,
            "build_id": str(args.build_id),
            "language": "schinese",
            "policy": "actor names only; dialogue text is not exported",
            "chinese_bundle_sha256": sha256(args.chinese_bundle),
            "dialogue_bundle_sha256": sha256(args.dialogue_bundle),
        },
        "entries": entries,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"WROTE\t{args.output}\t{len(entries)} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
