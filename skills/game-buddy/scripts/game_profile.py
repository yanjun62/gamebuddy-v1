#!/usr/bin/env python3
"""Validate, resolve, query, and export Game Buddy profile data."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROFILE_ROOT = SKILL_ROOT / "assets" / "game-profiles"
ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def normalized(value: str) -> str:
    return "".join(value.casefold().split()).replace("：", ":")


def term_match_quality(needle: str, candidate: str) -> int:
    value = normalized(candidate)
    if needle == value:
        return 2
    if len(needle) < 2 or len(value) < 2:
        return 0
    if needle in value:
        return 1
    if value in needle and len(value) / len(needle) >= 0.6:
        return 1
    return 0


def read_profile(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_profile(data, path)
    data["_path"] = str(path.resolve())
    data["_skill_root"] = str(find_skill_root(path))
    validate_linked_glossaries(data)
    return data


def find_skill_root(path: Path) -> Path:
    resolved = path.resolve()
    for parent in resolved.parents:
        if (parent / "SKILL.md").is_file():
            return parent
    raise ValueError(f"{path}: could not find containing SKILL.md")


def validate_profile(data: dict[str, Any], path: Path | None = None) -> None:
    where = str(path or "profile")
    required = ("schema_version", "id", "display_name", "aliases", "reference", "stt")
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"{where}: missing keys: {', '.join(missing)}")
    if data["schema_version"] != 1:
        raise ValueError(f"{where}: unsupported schema_version {data['schema_version']!r}")
    if not ID_PATTERN.fullmatch(str(data["id"])):
        raise ValueError(f"{where}: id must use lowercase hyphen-case")
    if not isinstance(data["aliases"], list) or not data["aliases"]:
        raise ValueError(f"{where}: aliases must be a non-empty list")
    glossaries = data.get("glossaries", [])
    if not isinstance(glossaries, list) or any(
        not isinstance(value, str) or not value.strip() for value in glossaries
    ):
        raise ValueError(f"{where}: glossaries must be a list of relative paths")
    stt = data["stt"]
    if not isinstance(stt, dict) or not isinstance(stt.get("terms"), list):
        raise ValueError(f"{where}: stt.terms must be a list")
    for index, term in enumerate(stt["terms"]):
        if not isinstance(term, dict) or not str(term.get("canonical", "")).strip():
            raise ValueError(f"{where}: stt.terms[{index}] needs canonical")
        if not isinstance(term.get("aliases", []), list):
            raise ValueError(f"{where}: stt.terms[{index}].aliases must be a list")
        priority = term.get("priority", 0)
        if not isinstance(priority, int) or not 0 <= priority <= 100:
            raise ValueError(f"{where}: stt.terms[{index}].priority must be 0..100")


def glossary_path(profile: dict[str, Any], relative_path: str) -> Path:
    root = Path(profile["_skill_root"]).resolve()
    path = (root / relative_path).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"glossary path escapes skill root: {relative_path}") from exc
    return path


def read_glossary(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    where = str(path)
    required = ("schema_version", "id", "display_name", "entries")
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"{where}: missing keys: {', '.join(missing)}")
    if data["schema_version"] != 1:
        raise ValueError(f"{where}: unsupported schema_version {data['schema_version']!r}")
    if not ID_PATTERN.fullmatch(str(data["id"])):
        raise ValueError(f"{where}: id must use lowercase hyphen-case")
    if not isinstance(data["entries"], list):
        raise ValueError(f"{where}: entries must be a list")
    for index, entry in enumerate(data["entries"]):
        if not isinstance(entry, dict) or not str(entry.get("canonical", "")).strip():
            raise ValueError(f"{where}: entries[{index}] needs canonical")
        if not isinstance(entry.get("aliases", []), list):
            raise ValueError(f"{where}: entries[{index}].aliases must be a list")
        if not isinstance(entry.get("scopes", []), list):
            raise ValueError(f"{where}: entries[{index}].scopes must be a list")
    data["_path"] = str(path.resolve())
    return data


def validate_linked_glossaries(profile: dict[str, Any]) -> None:
    for relative_path in profile.get("glossaries", []):
        read_glossary(glossary_path(profile, relative_path))


def load_glossaries(profile: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        read_glossary(glossary_path(profile, relative_path))
        for relative_path in profile.get("glossaries", [])
    ]


def load_profiles(profile_root: Path) -> list[dict[str, Any]]:
    return [read_profile(path) for path in sorted(profile_root.glob("*.json"))]


def resolve_profile(query: str, profiles: list[dict[str, Any]]) -> dict[str, Any] | None:
    needle = normalized(query)
    exact: list[dict[str, Any]] = []
    partial: list[dict[str, Any]] = []
    for profile in profiles:
        names = [profile["id"], profile["display_name"], *profile.get("aliases", [])]
        normalized_names = [normalized(str(name)) for name in names]
        if needle in normalized_names:
            exact.append(profile)
        elif needle and any(needle in name or name in needle for name in normalized_names):
            partial.append(profile)
    matches = exact or partial
    return matches[0] if len(matches) == 1 else None


def require_profile(query: str, profiles: list[dict[str, Any]]) -> dict[str, Any]:
    profile = resolve_profile(query, profiles)
    if profile is None:
        known = ", ".join(item["id"] for item in profiles) or "none"
        raise ValueError(f"could not resolve one profile from {query!r}; known: {known}")
    return profile


def build_stt_prompt(profile: dict[str, Any], max_chars: int) -> str:
    stt = profile["stt"]
    prefix = str(stt.get("prompt_prefix", "")).strip()
    terms = sorted(stt["terms"], key=lambda item: -int(item.get("priority", 0)))
    chunks: list[str] = []
    for term in terms:
        names = [str(term["canonical"]), *[str(value) for value in term.get("aliases", [])]]
        chunk = " / ".join(dict.fromkeys(name.strip() for name in names if name.strip()))
        body = "；".join([*chunks, chunk])
        candidate = prefix + (" " if prefix and body else "") + body
        if len(candidate) > max_chars:
            break
        chunks.append(chunk)
    body = "；".join(chunks)
    return prefix + (" " if prefix and body else "") + body


def lookup(
    profile: dict[str, Any], query: str, scope: str | None = None
) -> list[dict[str, Any]]:
    needle = normalized(query)
    if not needle:
        raise ValueError("lookup query cannot be empty")
    ranked_matches: list[tuple[int, dict[str, Any]]] = []
    for term in profile["stt"]["terms"]:
        names = [str(term["canonical"]), *[str(value) for value in term.get("aliases", [])]]
        quality = max(term_match_quality(needle, name) for name in names)
        if quality:
            result = dict(term)
            result["source"] = "core-stt"
            ranked_matches.append((quality, result))
    for glossary in load_glossaries(profile):
        for entry in glossary["entries"]:
            scopes = [str(value) for value in entry.get("scopes", [])]
            if scope and scopes and normalized(scope) not in {normalized(value) for value in scopes}:
                continue
            names = [
                str(entry["canonical"]),
                *[str(value) for value in entry.get("aliases", [])],
            ]
            quality = max(term_match_quality(needle, name) for name in names)
            if quality:
                result = dict(entry)
                result["source"] = f"glossary:{glossary['id']}"
                ranked_matches.append((quality, result))
    if not ranked_matches:
        return []
    best = max(quality for quality, _ in ranked_matches)
    return [result for quality, result in ranked_matches if quality == best]


def glossary_stats(profile: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": glossary["id"],
            "display_name": glossary["display_name"],
            "entries": len(glossary["entries"]),
            "path": str(Path(glossary["_path"]).relative_to(Path(profile["_skill_root"]))),
        }
        for glossary in load_glossaries(profile)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile-root", type=Path, default=DEFAULT_PROFILE_ROOT)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List profiles")
    validate_parser = commands.add_parser("validate", help="Validate a profile JSON file")
    validate_parser.add_argument("path", type=Path)
    resolve_parser = commands.add_parser("resolve", help="Resolve a title or alias")
    resolve_parser.add_argument("query")
    prompt_parser = commands.add_parser("stt-prompt", help="Export a compact STT prompt")
    prompt_parser.add_argument("profile")
    prompt_parser.add_argument("--max-chars", type=int, default=700)
    lookup_parser = commands.add_parser("lookup", help="Find a term or alias")
    lookup_parser.add_argument("profile")
    lookup_parser.add_argument("query")
    lookup_parser.add_argument("--scope", help="Limit glossary matches to one game or edition")
    glossary_parser = commands.add_parser("glossary-stats", help="Show linked glossary counts")
    glossary_parser.add_argument("profile")
    args = parser.parse_args()

    try:
        if args.command == "validate":
            profile = read_profile(args.path)
            print(f"OK\t{profile['id']}\t{profile['display_name']}")
            return 0

        profiles = load_profiles(args.profile_root)
        if args.command == "list":
            for profile in profiles:
                print(f"{profile['id']}\t{profile['display_name']}\t{profile['reference']}")
            return 0

        if args.command == "resolve":
            print(require_profile(args.query, profiles)["id"])
            return 0

        profile = require_profile(args.profile, profiles)
        if args.command == "stt-prompt":
            if args.max_chars < 80:
                raise ValueError("--max-chars must be at least 80")
            print(build_stt_prompt(profile, args.max_chars))
            return 0
        if args.command == "lookup":
            print(json.dumps(lookup(profile, args.query, args.scope), ensure_ascii=False, indent=2))
            return 0
        if args.command == "glossary-stats":
            print(json.dumps(glossary_stats(profile), ensure_ascii=False, indent=2))
            return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
