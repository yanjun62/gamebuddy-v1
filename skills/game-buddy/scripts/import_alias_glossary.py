#!/usr/bin/env python3
"""Convert a compact bilingual alias export into a Game Buddy glossary."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def normalized(value: str) -> str:
    return "".join(value.casefold().split())


def unique_names(values: list[Any], canonical: str) -> list[str]:
    seen = {normalized(canonical)}
    result: list[str] = []
    for value in values:
        name = str(value or "").strip()
        key = normalized(name)
        if name and key not in seen:
            seen.add(key)
            result.append(name)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--id", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--source-kind", default="user-supplied-localization-export")
    args = parser.parse_args()

    source_bytes = args.source.read_bytes()
    source = json.loads(source_bytes.decode("utf-8-sig"))
    raw_entries = source.get("entries", [])
    if not isinstance(raw_entries, list):
        raise ValueError("source entries must be a list")

    entries: list[dict[str, Any]] = []
    for raw in raw_entries:
        canonical = str(raw.get("canonical_zh") or raw.get("canonical") or "").strip()
        if not canonical:
            continue
        aliases = unique_names(
            [raw.get("english"), *raw.get("aliases", [])],
            canonical,
        )
        entry: dict[str, Any] = {
            "canonical": canonical,
            "aliases": aliases,
            "scopes": [str(value) for value in raw.get("games", raw.get("scopes", []))],
        }
        if raw.get("category_hint"):
            entry["category"] = str(raw["category_hint"])
        if raw.get("confidence"):
            entry["confidence"] = str(raw["confidence"])
        if raw.get("needs_review"):
            entry["needs_review"] = True
        entries.append(entry)

    output = {
        "schema_version": 1,
        "id": args.id,
        "display_name": args.display_name,
        "source": {
            "kind": args.source_kind,
            "source_schema_version": source.get("schema_version"),
            "sha256": hashlib.sha256(source_bytes).hexdigest(),
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
