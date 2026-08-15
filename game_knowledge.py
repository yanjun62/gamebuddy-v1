"""Discover Game Buddy profiles and retrieve a small, relevant terminology set."""

from __future__ import annotations

import json
import os
import re
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from bridge_protocol import BASE_DIR


SPOILER_LABELS = {
    "safe": "安全（不剧透）",
    "current-game": "当前进度攻略",
    "full": "完整剧透攻略",
}
DEFAULT_CONTEXT_TERM_LIMIT = 20


def _normalized(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _profile_roots(config: dict, base_dir: Path = BASE_DIR) -> list[Path]:
    roots: list[Path] = []
    for key in ("game_profile_root", "voice_game_profile_root"):
        configured = str(config.get(key, "")).strip()
        if configured:
            path = Path(configured).expanduser()
            roots.append(path if path.is_absolute() else base_dir / path)

    roots.append(base_dir / "skill-package" / "game-buddy" / "assets" / "game-profiles")
    roots.append(base_dir / "skills" / "game-buddy" / "assets" / "game-profiles")
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
    roots.append(codex_home / "skills" / "game-buddy" / "assets" / "game-profiles")

    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root.resolve()).casefold()
        if key not in seen:
            seen.add(key)
            unique.append(root)
    return unique


def _skill_root(profile_path: Path) -> Path:
    for parent in profile_path.resolve().parents:
        if (parent / "SKILL.md").is_file():
            return parent
    return profile_path.resolve().parent


@lru_cache(maxsize=64)
def _read_json_cached(path_text: str, mtime_ns: int) -> dict[str, Any]:
    del mtime_ns
    value = json.loads(Path(path_text).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON root must be an object")
    return value


def _read_json(path: Path) -> dict[str, Any]:
    return _read_json_cached(str(path.resolve()), path.stat().st_mtime_ns)


def discover_profiles(config: dict, base_dir: Path = BASE_DIR) -> list[dict[str, str]]:
    """Return one UI row per available profile, preferring configured/local roots."""
    profiles: list[dict[str, str]] = []
    seen: set[str] = set()
    for root in _profile_roots(config, base_dir):
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*.json")):
            try:
                value = _read_json(path)
                profile_id = str(value.get("id") or path.stem).strip()
                display_name = str(value.get("display_name") or profile_id).strip()
            except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
            if profile_id and profile_id.casefold() not in seen:
                seen.add(profile_id.casefold())
                profiles.append(
                    {
                        "id": profile_id,
                        "display_name": display_name or profile_id,
                        "path": str(path.resolve()),
                    }
                )
    return profiles


def selected_profile_id(config: dict) -> str:
    return str(config.get("game_profile") or config.get("voice_game_profile") or "").strip()


def load_profile(config: dict, base_dir: Path = BASE_DIR) -> Optional[dict[str, Any]]:
    profile_id = selected_profile_id(config)
    if not profile_id:
        return None
    row = next(
        (item for item in discover_profiles(config, base_dir) if item["id"].casefold() == profile_id.casefold()),
        None,
    )
    if row is None:
        raise RuntimeError(f"找不到游戏词库 {profile_id!r}")
    path = Path(row["path"])
    value = dict(_read_json(path))
    value["_path"] = str(path)
    value["_skill_root"] = str(_skill_root(path))
    return value


def _iter_terms(profile: dict[str, Any], *, include_glossaries: bool) -> list[dict[str, Any]]:
    terms: list[dict[str, Any]] = []
    for term in profile.get("stt", {}).get("terms", []):
        if isinstance(term, dict) and str(term.get("canonical", "")).strip():
            value = dict(term)
            value["source"] = "core-stt"
            terms.append(value)
    if not include_glossaries:
        return terms

    root = Path(profile["_skill_root"])
    for relative in profile.get("glossaries", []):
        path = (root / str(relative)).resolve()
        try:
            path.relative_to(root.resolve())
            glossary = _read_json(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        glossary_id = str(glossary.get("id", path.stem))
        for entry in glossary.get("entries", []):
            if isinstance(entry, dict) and str(entry.get("canonical", "")).strip():
                value = dict(entry)
                value["source"] = f"glossary:{glossary_id}"
                terms.append(value)
    return terms


def build_whisper_prompt(config: dict, max_chars: Optional[int] = None) -> Optional[str]:
    """Build a bounded hot-word prompt from core terms only."""
    manual = str(config.get("voice_initial_prompt", "")).strip()
    if config.get("knowledge_enabled", True) is False:
        return manual or None
    profile = load_profile(config)
    limit = max(80, min(2000, int(max_chars or config.get("voice_game_prompt_max_chars", 700))))
    if profile is None:
        return manual[:limit] or None
    prefix = str(profile.get("stt", {}).get("prompt_prefix", "")).strip()
    terms = sorted(
        _iter_terms(profile, include_glossaries=False),
        key=lambda item: -int(item.get("priority", 0)),
    )
    chunks: list[str] = []
    for term in terms:
        names = [str(term["canonical"]), *[str(value) for value in term.get("aliases", [])]]
        chunk = " / ".join(dict.fromkeys(name.strip() for name in names if name.strip()))
        body = "；".join([*chunks, chunk])
        candidate = " ".join(part for part in (manual, prefix, body) if part)
        if len(candidate) > limit:
            break
        chunks.append(chunk)
    return " ".join(part for part in (manual, prefix, "；".join(chunks)) if part)[:limit] or None


def _query_parts(text: str) -> list[str]:
    parts = [text]
    parts.extend(re.findall(r"[A-Za-z][A-Za-z0-9'’ .:_-]{1,48}|[\u3400-\u9fff]{2,24}", text))
    return list(dict.fromkeys(part.strip() for part in parts if part.strip()))


def _direct_match_score(query: str, name: str) -> float:
    query_key = _normalized(query)
    name_key = _normalized(name)
    if not query_key or not name_key:
        return 0.0
    if query_key == name_key:
        return 1.0
    if len(name_key) >= 2 and name_key in query_key:
        has_cjk = any("\u3400" <= character <= "\u9fff" for character in name)
        if has_cjk or len(name_key) >= 6 or len(name_key) / len(query_key) >= 0.45:
            return 0.98
    if len(query_key) >= 2 and query_key in name_key:
        return 0.9
    return 0.0


def _fuzzy_match_score(query: str, name: str) -> float:
    query_key = _normalized(query)
    name_key = _normalized(name)
    if min(len(query_key), len(name_key)) < 3:
        return 0.0
    length_ratio = len(query_key) / len(name_key)
    if not 0.6 <= length_ratio <= 1.5:
        return 0.0
    if query_key[0] != name_key[0]:
        return 0.0
    ratio = SequenceMatcher(None, query_key, name_key).ratio()
    return ratio if ratio >= 0.72 else 0.0


def _merged_terms(profile: dict[str, Any]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for term in _iter_terms(profile, include_glossaries=True):
        canonical = str(term.get("canonical", "")).strip()
        key = _normalized(canonical)
        if not key:
            continue
        current = merged.get(key)
        if current is None:
            current = dict(term)
            current["aliases"] = []
            merged[key] = current
        aliases = [str(value).strip() for value in term.get("aliases", []) if str(value).strip()]
        current["aliases"] = list(dict.fromkeys([*current.get("aliases", []), *aliases]))
        current["priority"] = max(int(current.get("priority", 0)), int(term.get("priority", 0)))
        if str(term.get("source", "")).startswith("core-"):
            current["source"] = term["source"]
    return list(merged.values())


def retrieve_terms(text: str, config: dict, limit: Optional[int] = None) -> list[dict[str, Any]]:
    """Retrieve only the 10–30 most relevant terms for the current text."""
    if config.get("knowledge_enabled", True) is False:
        return []
    profile = load_profile(config)
    if profile is None or not text.strip():
        return []
    bounded_limit = max(10, min(30, int(limit or config.get("knowledge_context_term_limit", 20))))
    parts = _query_parts(text)
    terms = _merged_terms(profile)

    def rank(use_fuzzy: bool) -> list[tuple[float, int, dict[str, Any]]]:
        ranked: list[tuple[float, int, dict[str, Any]]] = []
        scorer = _fuzzy_match_score if use_fuzzy else _direct_match_score
        for term in terms:
            canonical = str(term.get("canonical", "")).strip()
            aliases = [str(value).strip() for value in term.get("aliases", []) if str(value).strip()]
            names = [canonical, *aliases]
            best = 0.0
            matched = ""
            for part in parts:
                for name in names:
                    score = scorer(part, name)
                    if score > best:
                        best, matched = score, name
            if best:
                result = {
                    "canonical": canonical,
                    "aliases": aliases,
                    "source": term.get("source", "unknown"),
                    "matched": matched,
                    "score": round(best, 3),
                }
                if term.get("scopes"):
                    result["scopes"] = term["scopes"]
                ranked.append((best, int(term.get("priority", 0)), result))
        return ranked

    ranked = rank(use_fuzzy=False)
    if not ranked:
        ranked = rank(use_fuzzy=True)
    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]["canonical"].casefold()))
    return [result for _, _, result in ranked[:bounded_limit]]


def correct_ocr_text(text: str, config: dict) -> tuple[str, list[dict[str, str]]]:
    """Conservatively replace standalone OCR lines that closely match a known term."""
    if config.get("knowledge_enabled", True) is False:
        return text, []
    corrected_lines: list[str] = []
    corrections: list[dict[str, str]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        matches = retrieve_terms(line, config, limit=10) if line else []
        best = matches[0] if matches else None
        if best and float(best["score"]) >= 0.86:
            matched = str(best["matched"])
            source_length = max(1, len(_normalized(line)))
            matched_length = max(1, len(_normalized(matched)))
            comparable = 0.65 <= source_length / matched_length <= 1.45
            canonical = str(best["canonical"])
            if comparable and _normalized(line) != _normalized(canonical):
                corrected_lines.append(canonical)
                corrections.append({"from": line, "to": canonical})
                continue
        corrected_lines.append(raw_line)
    return "\n".join(corrected_lines), corrections


def build_game_context(config: dict, query: str = "") -> dict[str, Any]:
    """Build compact per-message state for the Codex/heartbeat bridges."""
    profile = load_profile(config)
    profile_id = selected_profile_id(config)
    enabled = bool(config.get("knowledge_enabled", True) and profile is not None)
    spoiler_mode = str(config.get("spoiler_mode", "safe"))
    if spoiler_mode not in SPOILER_LABELS:
        spoiler_mode = "safe"
    context: dict[str, Any] = {
        "profile_id": profile_id,
        "display_name": str(profile.get("display_name", profile_id)) if profile else profile_id,
        "knowledge_enabled": enabled,
        "spoiler_mode": spoiler_mode,
        "spoiler_label": SPOILER_LABELS[spoiler_mode],
        "terms": retrieve_terms(query, config) if enabled and query else [],
    }
    if enabled and profile:
        root = Path(profile["_skill_root"])
        reference = (root / str(profile.get("reference", ""))).resolve()
        context["profile_path"] = profile["_path"]
        if reference.is_file():
            context["reference_path"] = str(reference)
        context["credits_path"] = str(root / "references" / "credits.md")
    return context


def core_term_hint(config: dict, limit: int = 20) -> str:
    """Return a compact core-name hint for explicit remote-vision mode."""
    if config.get("knowledge_enabled", True) is False:
        return ""
    profile = load_profile(config)
    if profile is None:
        return ""
    terms = sorted(
        _iter_terms(profile, include_glossaries=False),
        key=lambda item: -int(item.get("priority", 0)),
    )[: max(1, min(30, limit))]
    return "；".join(str(term["canonical"]) for term in terms)


def _select_credits_section(document: str, heading: str) -> str:
    """Keep the document preamble and one matching level-two game section."""
    sections = list(re.finditer(r"(?m)^##[ \t]+(.+?)[ \t]*$", document))
    wanted = _normalized(heading)
    for index, match in enumerate(sections):
        if _normalized(match.group(1)) != wanted:
            continue
        end = sections[index + 1].start() if index + 1 < len(sections) else len(document)
        preamble = document[: sections[0].start()].strip()
        selected = document[match.start() : end].strip()
        return "\n\n".join(part for part in (preamble, selected) if part)
    return ""


def load_credits(config: dict) -> str:
    """Load the selected skill's attribution reference for the local UI."""
    profile = load_profile(config)
    if profile is None:
        return "请先选择游戏，再查看对应的致谢与来源。"
    path = Path(profile["_skill_root"]) / "references" / "credits.md"
    if not path.is_file():
        return "当前词库还没有附带致谢与来源说明。"
    document = path.read_text(encoding="utf-8")
    section_heading = str(profile.get("credits_section", "")).strip()
    if not section_heading:
        return document
    selected = _select_credits_section(document, section_heading)
    if not selected:
        return f"当前游戏的致谢章节（{section_heading}）不存在，请检查词库资料。"
    return selected
