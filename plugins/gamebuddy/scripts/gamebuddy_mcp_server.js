"use strict";

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const readline = require("node:readline");
const { spawnSync } = require("node:child_process");

const SERVER_INFO = { name: "gamebuddy-local", version: "0.1.0" };
const SUPPORTED_PROTOCOLS = [
  "2026-07-28",
  "2025-11-25",
  "2025-06-18",
  "2024-11-05"
];
const LEGACY_PROTOCOL = "2025-11-25";
const PLUGIN_ROOT = path.resolve(__dirname, "..");
const PUBLIC_SKILL_ROOT = path.join(PLUGIN_ROOT, "skills", "game-buddy");
const AUTHORING_SKILL_ROOT = path.join(
  PLUGIN_ROOT,
  "skills",
  "game-guide-authoring"
);
const MAX_JSON_BYTES = 4 * 1024 * 1024;
const MAX_FRAME_BYTES = 8 * 1024 * 1024;
const MAX_TOTAL_FRAME_BYTES = 20 * 1024 * 1024;
const MAX_RETURNED_FRAMES = 3;
const SPOILER_MODES = new Set(["safe", "current-game", "full"]);
const INSTRUCTIONS =
  "Use safe spoilers by default. Public profile tools work without a desktop connection. " +
  "For the overlay, call gamebuddy_poll once, answer from only that event and its images, " +
  "then commit the same token with gamebuddy_reply or gamebuddy_silent.";

let negotiatedProtocol = null;

class UserFacingError extends Error {}

function debug(message) {
  if (process.env.GAMEBUDDY_MCP_DEBUG === "1") {
    process.stderr.write("[gamebuddy-mcp] " + message + "\n");
  }
}

function hasOwn(value, key) {
  return Object.prototype.hasOwnProperty.call(value, key);
}

function normalizeKey(value) {
  return String(value || "")
    .normalize("NFKC")
    .toLocaleLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, "");
}

function clampInteger(value, minimum, maximum, fallback) {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return Math.max(minimum, Math.min(maximum, parsed));
}

const TRUNCATION_MARKER = "[Excerpt truncated by Game Buddy MCP.]";

// Worldbooks run past 20k characters, so a smaller budget silently cuts the
// late sections — including the full-spoiler block and the source credits —
// and makes every spoiler mode look identical. Keep the default above the
// largest bundled profile and leave the ceiling room to grow.
const CONTEXT_MAX_CHARS_DEFAULT = 24000;
const CONTEXT_MAX_CHARS_CEILING = 60000;

function truncateText(value, maximum) {
  const text = String(value || "");
  if (text.length <= maximum) {
    return text;
  }
  return text.slice(0, Math.max(0, maximum - 48)).trimEnd() +
    "\n\n" + TRUNCATION_MARKER;
}

function readJson(filePath, fallback = {}) {
  try {
    const stat = fs.statSync(filePath);
    if (!stat.isFile() || stat.size > MAX_JSON_BYTES) {
      return fallback;
    }
    const value = JSON.parse(fs.readFileSync(filePath, "utf8"));
    return value && typeof value === "object" && !Array.isArray(value)
      ? value
      : fallback;
  } catch {
    return fallback;
  }
}

function readText(filePath, maximumBytes = 2 * 1024 * 1024) {
  try {
    const stat = fs.statSync(filePath);
    if (!stat.isFile() || stat.size > maximumBytes) {
      return "";
    }
    return fs.readFileSync(filePath, "utf8").replace(/\r\n?/g, "\n");
  } catch {
    return "";
  }
}

function canonicalDirectory(candidate) {
  if (!candidate) {
    return null;
  }
  try {
    const resolved = fs.realpathSync(path.resolve(String(candidate)));
    return fs.statSync(resolved).isDirectory() ? resolved : null;
  } catch {
    return null;
  }
}

function isGameBuddyHome(candidate) {
  if (!candidate) {
    return false;
  }
  const required = [
    "heartbeat_bridge.py",
    "bridge_protocol.py",
    "config.example.json"
  ];
  return required.every((name) => fs.existsSync(path.join(candidate, name)));
}

function resolveGameBuddyHome(explicitHome) {
  const candidates = [];
  const add = (value, source, requireActiveState = false) => {
    if (typeof value === "string" && value.trim()) {
      candidates.push({
        value: value.trim(),
        source,
        requireActiveState
      });
    }
  };

  add(explicitHome, "tool-argument");
  add(process.env.GAMEBUDDY_HOME, "environment");
  if (process.env.GAMEBUDDY_DISABLE_AUTO_DISCOVERY !== "1") {
    add(process.cwd(), "working-directory");
    add(path.resolve(PLUGIN_ROOT, "..", ".."), "repository", true);
    add(
      path.resolve(PLUGIN_ROOT, "..", "..", ".."),
      "repository-parent",
      true
    );
  }

  const seen = new Set();
  for (const candidate of candidates) {
    const directory = canonicalDirectory(candidate.value);
    if (!directory) {
      continue;
    }
    const key = process.platform === "win32"
      ? directory.toLocaleLowerCase()
      : directory;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    const hasActiveState = [
      "config.json",
      "message_queue.jsonl",
      "current_frame.jpg"
    ].some((name) => fs.existsSync(path.join(directory, name)));
    if (
      isGameBuddyHome(directory) &&
      (!candidate.requireActiveState || hasActiveState)
    ) {
      return { path: directory, source: candidate.source };
    }
  }
  return null;
}

function expandUserPath(value) {
  const text = String(value || "").trim();
  if (text === "~") {
    return os.homedir();
  }
  if (text.startsWith("~/") || text.startsWith("~\\")) {
    return path.join(os.homedir(), text.slice(2));
  }
  return text;
}

function resolveConfiguredPath(home, value) {
  const expanded = expandUserPath(value);
  if (!expanded) {
    return null;
  }
  return path.isAbsolute(expanded)
    ? path.resolve(expanded)
    : path.resolve(home, expanded);
}

function isInside(root, candidate) {
  const relative = path.relative(root, candidate);
  return relative === "" ||
    (!relative.startsWith(".." + path.sep) &&
      relative !== ".." &&
      !path.isAbsolute(relative));
}

function findSkillRoot(profilePath) {
  let current = path.dirname(profilePath);
  for (let index = 0; index < 10; index += 1) {
    if (fs.existsSync(path.join(current, "SKILL.md"))) {
      return current;
    }
    const parent = path.dirname(current);
    if (parent === current) {
      break;
    }
    current = parent;
  }
  return path.dirname(profilePath);
}

function profileRoots(connection, config) {
  const roots = [];
  const add = (value, source) => {
    const directory = canonicalDirectory(value);
    if (directory) {
      roots.push({ path: directory, source });
    }
  };

  if (connection) {
    for (const key of ["game_profile_root", "voice_game_profile_root"]) {
      const configured = resolveConfiguredPath(connection.path, config[key]);
      if (configured) {
        add(configured, "local");
      }
    }
    add(
      path.join(
        connection.path,
        "skill-package",
        "game-buddy",
        "assets",
        "game-profiles"
      ),
      "local"
    );
    add(
      path.join(
        connection.path,
        "skills",
        "game-buddy",
        "assets",
        "game-profiles"
      ),
      "local"
    );
  }

  add(path.join(PUBLIC_SKILL_ROOT, "assets", "game-profiles"), "bundled");

  const unique = [];
  const seen = new Set();
  for (const root of roots) {
    const key = process.platform === "win32"
      ? root.path.toLocaleLowerCase()
      : root.path;
    if (!seen.has(key)) {
      seen.add(key);
      unique.push(root);
    }
  }
  return unique;
}

function discoverProfiles(options = {}) {
  const connection = resolveGameBuddyHome(options.gamebuddy_home);
  const config = connection
    ? readJson(path.join(connection.path, "config.json"), {})
    : {};
  const profiles = [];
  const seen = new Set();

  for (const root of profileRoots(connection, config)) {
    let names = [];
    try {
      names = fs.readdirSync(root.path)
        .filter((name) => name.toLocaleLowerCase().endsWith(".json"))
        .sort();
    } catch {
      continue;
    }

    for (const name of names) {
      const profilePath = path.join(root.path, name);
      const value = readJson(profilePath, null);
      if (!value) {
        continue;
      }
      const id = String(value.id || path.basename(name, ".json")).trim();
      if (!id) {
        continue;
      }
      const key = normalizeKey(id);
      if (!key || seen.has(key)) {
        continue;
      }
      seen.add(key);
      profiles.push({
        id,
        displayName: String(value.display_name || id).trim() || id,
        aliases: Array.isArray(value.aliases)
          ? value.aliases.map(String).map((item) => item.trim()).filter(Boolean)
          : [],
        source: root.source,
        path: profilePath,
        skillRoot: findSkillRoot(profilePath),
        data: value
      });
    }
  }

  return { connection, config, profiles };
}

function selectedProfileId(config) {
  return String(
    config.game_profile || config.voice_game_profile || ""
  ).trim();
}

function resolveProfile(discovery, requestedId) {
  const requested = String(
    requestedId || selectedProfileId(discovery.config)
  ).trim();
  if (!requested) {
    if (discovery.profiles.length === 1) {
      return discovery.profiles[0];
    }
    return null;
  }

  const wanted = normalizeKey(requested);
  return discovery.profiles.find((profile) => {
    const names = [
      profile.id,
      profile.displayName,
      ...profile.aliases
    ];
    return names.some((name) => normalizeKey(name) === wanted);
  }) || null;
}

function publicProfile(profile) {
  return {
    id: profile.id,
    display_name: profile.displayName,
    aliases: profile.aliases,
    source: profile.source,
    has_extended_glossary:
      Array.isArray(profile.data.glossaries) &&
      profile.data.glossaries.length > 0
  };
}

function safeLinkedFile(root, relativePath) {
  if (typeof relativePath !== "string" || !relativePath.trim()) {
    return null;
  }
  const rootReal = canonicalDirectory(root);
  if (!rootReal) {
    return null;
  }
  const candidate = path.resolve(rootReal, relativePath);
  if (!isInside(rootReal, candidate)) {
    return null;
  }
  try {
    const real = fs.realpathSync(candidate);
    return isInside(rootReal, real) && fs.statSync(real).isFile()
      ? real
      : null;
  } catch {
    return null;
  }
}

function collectTerms(profile, includeGlossaries = true) {
  const terms = [];
  const core = profile.data &&
    profile.data.stt &&
    Array.isArray(profile.data.stt.terms)
    ? profile.data.stt.terms
    : [];

  for (const term of core) {
    if (!term || typeof term !== "object") {
      continue;
    }
    const canonical = String(term.canonical || "").trim();
    if (canonical) {
      terms.push({ ...term, canonical, source: "core-stt" });
    }
  }

  if (!includeGlossaries || !Array.isArray(profile.data.glossaries)) {
    return terms;
  }

  for (const relative of profile.data.glossaries) {
    const glossaryPath = safeLinkedFile(profile.skillRoot, String(relative));
    if (!glossaryPath) {
      continue;
    }
    const glossary = readJson(glossaryPath, null);
    if (!glossary || !Array.isArray(glossary.entries)) {
      continue;
    }
    const glossaryId = String(
      glossary.id || path.basename(glossaryPath, ".json")
    );
    for (const entry of glossary.entries) {
      if (!entry || typeof entry !== "object") {
        continue;
      }
      const canonical = String(entry.canonical || "").trim();
      if (canonical) {
        terms.push({
          ...entry,
          canonical,
          source: "glossary:" + glossaryId
        });
      }
    }
  }

  return terms;
}

function mergedTerms(profile) {
  const merged = new Map();
  for (const term of collectTerms(profile, true)) {
    const key = normalizeKey(term.canonical);
    if (!key) {
      continue;
    }
    let current = merged.get(key);
    if (!current) {
      current = {
        canonical: term.canonical,
        aliases: [],
        priority: Number(term.priority || 0),
        source: term.source || "unknown",
        scopes: Array.isArray(term.scopes) ? term.scopes : []
      };
      merged.set(key, current);
    }
    const aliases = Array.isArray(term.aliases)
      ? term.aliases.map(String).map((item) => item.trim()).filter(Boolean)
      : [];
    current.aliases = [...new Set([...current.aliases, ...aliases])];
    current.priority = Math.max(
      Number(current.priority || 0),
      Number(term.priority || 0)
    );
    if (String(term.source || "").startsWith("core-")) {
      current.source = term.source;
    }
    if (Array.isArray(term.scopes) && term.scopes.length) {
      current.scopes = [...new Set([...current.scopes, ...term.scopes])];
    }
  }
  return [...merged.values()];
}

function queryParts(value) {
  const text = String(value || "").trim();
  if (!text) {
    return [];
  }
  const matches = text.match(
    /[A-Za-z][A-Za-z0-9'’ .:_-]{1,48}|[\p{Script=Han}]{2,24}/gu
  ) || [];
  return [...new Set([text, ...matches.map((item) => item.trim())])]
    .filter(Boolean);
}

function directMatchScore(query, name) {
  const queryKey = normalizeKey(query);
  const nameKey = normalizeKey(name);
  if (!queryKey || !nameKey) {
    return 0;
  }
  if (queryKey === nameKey) {
    return 1;
  }
  if (nameKey.length >= 2 && queryKey.includes(nameKey)) {
    const hasHan = /[\p{Script=Han}]/u.test(String(name));
    if (
      hasHan ||
      nameKey.length >= 6 ||
      nameKey.length / queryKey.length >= 0.45
    ) {
      return 0.98;
    }
  }
  if (queryKey.length >= 2 && nameKey.includes(queryKey)) {
    return 0.9;
  }
  return 0;
}

function levenshteinSimilarity(left, right) {
  if (left === right) {
    return 1;
  }
  if (!left.length || !right.length) {
    return 0;
  }
  let previous = Array.from(
    { length: right.length + 1 },
    (_, index) => index
  );
  for (let row = 1; row <= left.length; row += 1) {
    const current = [row];
    for (let column = 1; column <= right.length; column += 1) {
      const cost = left[row - 1] === right[column - 1] ? 0 : 1;
      current[column] = Math.min(
        current[column - 1] + 1,
        previous[column] + 1,
        previous[column - 1] + cost
      );
    }
    previous = current;
  }
  const distance = previous[right.length];
  return 1 - distance / Math.max(left.length, right.length);
}

function fuzzyMatchScore(query, name) {
  const queryKey = normalizeKey(query);
  const nameKey = normalizeKey(name);
  if (Math.min(queryKey.length, nameKey.length) < 3) {
    return 0;
  }
  const lengthRatio = queryKey.length / nameKey.length;
  if (lengthRatio < 0.6 || lengthRatio > 1.5) {
    return 0;
  }
  if (queryKey[0] !== nameKey[0]) {
    return 0;
  }
  const score = levenshteinSimilarity(queryKey, nameKey);
  return score >= 0.72 ? score : 0;
}

function retrieveTerms(profile, query, limit) {
  const parts = queryParts(query);
  if (!parts.length) {
    return [];
  }
  const terms = mergedTerms(profile);

  const rank = (scorer) => {
    const ranked = [];
    for (const term of terms) {
      const names = [term.canonical, ...term.aliases];
      let best = 0;
      let matched = "";
      for (const part of parts) {
        for (const name of names) {
          const score = scorer(part, name);
          if (score > best) {
            best = score;
            matched = name;
          }
        }
      }
      if (best > 0) {
        ranked.push({
          score: best,
          priority: Number(term.priority || 0),
          value: {
            canonical: term.canonical,
            aliases: term.aliases.slice(0, 12),
            source: term.source,
            matched,
            score: Number(best.toFixed(3)),
            ...(term.scopes.length ? { scopes: term.scopes } : {})
          }
        });
      }
    }
    return ranked;
  };

  let ranked = rank(directMatchScore);
  if (!ranked.length) {
    ranked = rank(fuzzyMatchScore);
  }
  ranked.sort((left, right) =>
    right.score - left.score ||
    right.priority - left.priority ||
    left.value.canonical.localeCompare(right.value.canonical)
  );
  return ranked.slice(0, limit).map((item) => item.value);
}

function splitH2Sections(document) {
  const regex = /^##[ \t]+(.+?)[ \t]*$/gm;
  const matches = [...document.matchAll(regex)];
  if (!matches.length) {
    return [{ title: "", body: document, index: 0 }];
  }
  const sections = [];
  if (matches[0].index > 0) {
    sections.push({
      title: "",
      body: document.slice(0, matches[0].index).trim(),
      index: 0
    });
  }
  for (let index = 0; index < matches.length; index += 1) {
    const start = matches[index].index;
    const end = index + 1 < matches.length
      ? matches[index + 1].index
      : document.length;
    sections.push({
      title: matches[index][1].trim(),
      body: document.slice(start, end).trim(),
      index: index + 1
    });
  }
  return sections.filter((section) => section.body);
}

function filterSpoilers(document, mode) {
  if (mode === "full") {
    return document;
  }
  const forbidden = /(full[- ]?spoiler|完整剧透|全剧透|完全剧透)/i;
  return splitH2Sections(document)
    .filter((section) => !forbidden.test(section.title))
    .map((section) => section.body)
    .join("\n\n");
}

function sectionScore(section, query) {
  const pieces = queryParts(query)
    .map(normalizeKey)
    .filter((piece) => piece.length >= 2);
  if (!pieces.length) {
    return 0;
  }
  const heading = normalizeKey(section.title);
  const body = normalizeKey(section.body);
  let score = 0;
  for (const piece of pieces) {
    if (heading.includes(piece) || piece.includes(heading)) {
      score += 12;
    }
    if (body.includes(piece)) {
      score += 3;
    }
  }
  return score;
}

function relevantExcerpt(document, query, maximum) {
  if (!String(query || "").trim()) {
    return truncateText(document, maximum);
  }
  const sections = splitH2Sections(document);
  const selected = new Map();
  const always = /(companion contract|player-state|spoiler boundaries|scope|使用约定|剧透边界)/i;

  for (const section of sections) {
    if (!section.title || always.test(section.title)) {
      selected.set(section.index, section);
    }
  }

  const ranked = sections
    .map((section) => ({
      section,
      score: sectionScore(section, query)
    }))
    .filter((item) => item.score > 0)
    .sort((left, right) =>
      right.score - left.score ||
      left.section.index - right.section.index
    )
    .slice(0, 6);

  for (const item of ranked) {
    selected.set(item.section.index, item.section);
  }

  if (!ranked.length) {
    for (const section of sections.slice(0, 4)) {
      selected.set(section.index, section);
    }
  }

  const ordered = [...selected.values()]
    .sort((left, right) => left.index - right.index)
    .map((section) => section.body)
    .join("\n\n");
  return truncateText(ordered || document, maximum);
}

function profileReference(profile) {
  const relative = String(profile.data.reference || "").trim();
  return safeLinkedFile(profile.skillRoot, relative);
}

function profileCredits(profile) {
  return safeLinkedFile(
    profile.skillRoot,
    path.join("references", "credits.md")
  );
}

function selectCreditsSection(document, heading) {
  const wanted = normalizeKey(heading);
  if (!wanted) {
    return document;
  }
  const sections = splitH2Sections(document);
  const preamble = sections.find((section) => !section.title);
  const matched = sections.find(
    (section) => normalizeKey(section.title) === wanted
  );
  if (!matched) {
    return document;
  }
  return [preamble && preamble.body, matched.body]
    .filter(Boolean)
    .join("\n\n");
}

function requireProfile(argumentsObject) {
  const discovery = discoverProfiles(argumentsObject);
  const profile = resolveProfile(discovery, argumentsObject.profile_id);
  if (!profile) {
    const available = discovery.profiles.map((item) => item.id);
    throw new UserFacingError(
      "Choose profile_id first. Available profiles: " +
      (available.join(", ") || "none")
    );
  }
  return { discovery, profile };
}

function listGames(argumentsObject) {
  const discovery = discoverProfiles(argumentsObject);
  const selected = selectedProfileId(discovery.config);
  return {
    connected_to_desktop: Boolean(discovery.connection),
    selected_profile_id: selected || null,
    games: discovery.profiles.map(publicProfile)
  };
}

function getContext(argumentsObject) {
  const { discovery, profile } = requireProfile(argumentsObject);
  const configuredMode = String(discovery.config.spoiler_mode || "safe");
  const requestedMode = String(
    argumentsObject.spoiler_mode || configuredMode || "safe"
  );
  const mode = SPOILER_MODES.has(requestedMode)
    ? requestedMode
    : "safe";
  const maximum = clampInteger(
    argumentsObject.max_chars,
    2000,
    CONTEXT_MAX_CHARS_CEILING,
    CONTEXT_MAX_CHARS_DEFAULT
  );
  const referencePath = profileReference(profile);
  const raw = referencePath ? readText(referencePath) : "";
  const filtered = filterSpoilers(raw, mode);
  const worldbook = relevantExcerpt(
    filtered,
    String(argumentsObject.query || ""),
    maximum
  );
  const truncated = worldbook.endsWith(TRUNCATION_MARKER);

  return {
    profile: publicProfile(profile),
    spoiler_mode: mode,
    full_spoiler_sections_included: mode === "full",
    worldbook_truncated: truncated,
    worldbook_max_chars: maximum,
    desktop_connected: Boolean(discovery.connection),
    worldbook: worldbook ||
      "This profile has no readable worldbook. Use the compact terminology only."
  };
}

function searchTerms(argumentsObject) {
  const query = String(argumentsObject.query || "").trim();
  if (!query) {
    throw new UserFacingError("query must not be empty");
  }
  const { profile } = requireProfile(argumentsObject);
  const limit = clampInteger(argumentsObject.limit, 10, 30, 20);
  return {
    profile_id: profile.id,
    query,
    limit,
    terms: retrieveTerms(profile, query, limit)
  };
}

function getCredits(argumentsObject) {
  const { profile } = requireProfile(argumentsObject);
  const creditsPath = profileCredits(profile);
  const document = creditsPath ? readText(creditsPath) : "";
  const heading = String(profile.data.credits_section || "").trim();
  const credits = truncateText(
    selectCreditsSection(document, heading),
    16000
  );
  return {
    profile_id: profile.id,
    credits: credits ||
      "No source and localization credits are bundled for this profile."
  };
}

function getAuthoringKit() {
  const profileTemplate = readJson(
    path.join(AUTHORING_SKILL_ROOT, "assets", "game-profile.json"),
    null
  );
  const worldbookTemplate = readText(
    path.join(
      AUTHORING_SKILL_ROOT,
      "references",
      "worldbook-template.md"
    )
  );
  const sourceAndRelease = readText(
    path.join(
      AUTHORING_SKILL_ROOT,
      "references",
      "source-and-release.md"
    )
  );
  const workflow = readText(
    path.join(AUTHORING_SKILL_ROOT, "SKILL.md")
  );

  if (!profileTemplate || !worldbookTemplate || !sourceAndRelease) {
    throw new UserFacingError(
      "The public Game Buddy authoring kit is incomplete."
    );
  }

  return {
    purpose:
      "Create one spoiler-aware, source-attributed Game Buddy profile and worldbook without redistributing protected game data.",
    profile_template: profileTemplate,
    worldbook_template: truncateText(worldbookTemplate, 16000),
    source_and_release_rules: truncateText(sourceAndRelease, 16000),
    workflow: truncateText(workflow, 12000)
  };
}

function countNonBlankLines(filePath) {
  let descriptor;
  try {
    descriptor = fs.openSync(filePath, "r");
    const buffer = Buffer.allocUnsafe(64 * 1024);
    let leftover = "";
    let count = 0;
    let bytes = 0;
    while ((bytes = fs.readSync(descriptor, buffer, 0, buffer.length, null)) > 0) {
      const chunk = leftover + buffer.subarray(0, bytes).toString("utf8");
      const lines = chunk.split(/\r?\n/);
      leftover = lines.pop() || "";
      count += lines.filter((line) => line.trim()).length;
    }
    if (leftover.trim()) {
      count += 1;
    }
    return count;
  } catch {
    return 0;
  } finally {
    if (descriptor !== undefined) {
      try {
        fs.closeSync(descriptor);
      } catch {
        // Ignore close errors in a read-only status helper.
      }
    }
  }
}

function fileAgeSeconds(filePath) {
  try {
    const stat = fs.statSync(filePath);
    return Math.max(
      0,
      Math.round((Date.now() - stat.mtimeMs) / 100) / 10
    );
  } catch {
    return null;
  }
}

function sanitizedStatus(argumentsObject) {
  const connection = resolveGameBuddyHome(argumentsObject.gamebuddy_home);
  if (!connection) {
    return {
      connected: false,
      knowledge_only: true,
      message:
        "Public profiles are available. To use the desktop bridge, run Codex " +
        "from the Game Buddy checkout or set GAMEBUDDY_HOME before launch."
    };
  }

  const config = readJson(path.join(connection.path, "config.json"), {});
  const direct = readJson(
    path.join(connection.path, "direct_codex_status.json"),
    {}
  );
  const heartbeat = readJson(
    path.join(connection.path, ".heartbeat_state.json"),
    {}
  );
  const discovery = discoverProfiles({
    gamebuddy_home: connection.path
  });
  const profile = resolveProfile(discovery, null);
  const rawDirectStatus = String(direct.status || "unknown").trim();
  const allowedStatuses = new Set([
    "starting",
    "ready",
    "thinking",
    "retrying",
    "error",
    "stopped",
    "unknown"
  ]);
  const directStatus = allowedStatuses.has(rawDirectStatus)
    ? rawDirectStatus
    : "unknown";
  const framePath = path.join(connection.path, "current_frame.jpg");

  return {
    connected: true,
    connection_source: connection.source,
    config_present: fs.existsSync(path.join(connection.path, "config.json")),
    game: profile ? publicProfile(profile) : null,
    knowledge_enabled: config.knowledge_enabled !== false,
    spoiler_mode: SPOILER_MODES.has(String(config.spoiler_mode || ""))
      ? String(config.spoiler_mode)
      : "safe",
    bridge: {
      direct_codex_enabled: Boolean(config.direct_codex_enabled),
      capture_on_message: config.capture_on_message !== false,
      heartbeat_include_messages: Boolean(config.heartbeat_include_messages),
      queued_messages: countNonBlankLines(
        path.join(connection.path, "message_queue.jsonl")
      ),
      pending_event: Boolean(
        heartbeat.pending && typeof heartbeat.pending === "object"
      ),
      direct_status: directStatus,
      frame_available: fs.existsSync(framePath),
      frame_age_seconds: fileAgeSeconds(framePath)
    }
  };
}

function redactLocalText(value, home) {
  let text = String(value || "");
  if (home) {
    const variants = [
      home,
      home.replace(/\\/g, "/"),
      home.replace(/\//g, "\\")
    ];
    for (const variant of variants) {
      if (variant) {
        text = text.split(variant).join("[GAMEBUDDY_HOME]");
      }
    }
  }
  return truncateText(text, 2000);
}

function pythonCandidates(home) {
  const candidates = [];
  const add = (command, prefix = []) => {
    if (!command) {
      return;
    }
    const key = command + "\u0000" + prefix.join("\u0000");
    if (!candidates.some((candidate) => candidate.key === key)) {
      candidates.push({ command, prefix, key });
    }
  };

  add(process.env.GAMEBUDDY_PYTHON);
  const windowsVenv = path.join(home, ".venv", "Scripts", "python.exe");
  const unixVenv = path.join(home, ".venv", "bin", "python");
  if (fs.existsSync(windowsVenv)) {
    add(windowsVenv);
  }
  if (fs.existsSync(unixVenv)) {
    add(unixVenv);
  }
  if (process.platform === "win32") {
    add("py", ["-3"]);
    add("python");
    add("python3");
  } else {
    add("python3");
    add("python");
  }
  return candidates;
}

function parseLastJsonLine(output) {
  const lines = String(output || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  for (let index = lines.length - 1; index >= 0; index -= 1) {
    try {
      const value = JSON.parse(lines[index]);
      if (value && typeof value === "object" && !Array.isArray(value)) {
        return value;
      }
    } catch {
      // Continue searching earlier lines.
    }
  }
  return null;
}

function invokeHeartbeat(home, bridgeArguments) {
  const script = path.join(home, "heartbeat_bridge.py");
  if (!fs.existsSync(script)) {
    throw new UserFacingError(
      "The selected Game Buddy folder has no heartbeat bridge."
    );
  }

  for (const candidate of pythonCandidates(home)) {
    const result = spawnSync(
      candidate.command,
      [...candidate.prefix, script, ...bridgeArguments],
      {
        cwd: home,
        encoding: "utf8",
        timeout: 30000,
        maxBuffer: MAX_JSON_BYTES,
        windowsHide: true,
        env: process.env
      }
    );
    if (result.error && result.error.code === "ENOENT") {
      continue;
    }
    if (result.error) {
      const message = result.error.code === "ETIMEDOUT"
        ? "The Game Buddy heartbeat bridge timed out."
        : "The Game Buddy heartbeat bridge could not start.";
      throw new UserFacingError(message);
    }

    const payload = parseLastJsonLine(result.stdout);
    if (!payload) {
      debug(redactLocalText(result.stderr, home));
      throw new UserFacingError(
        "The Game Buddy heartbeat bridge returned no valid JSON."
      );
    }
    if (result.status !== 0 || payload.status === "error") {
      throw new UserFacingError(
        redactLocalText(
          payload.error || "The Game Buddy heartbeat bridge reported an error.",
          home
        )
      );
    }
    return payload;
  }

  throw new UserFacingError(
    "No usable Python executable was found. Install Python 3.10+ or set GAMEBUDDY_PYTHON."
  );
}

function sanitizedGameContext(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return {
    profile_id: value.profile_id || "",
    display_name: value.display_name || "",
    knowledge_enabled: Boolean(value.knowledge_enabled),
    spoiler_mode: SPOILER_MODES.has(String(value.spoiler_mode || ""))
      ? String(value.spoiler_mode)
      : "safe",
    spoiler_label: String(value.spoiler_label || ""),
    terms: Array.isArray(value.terms)
      ? value.terms.slice(0, 30).map((term) => ({
        canonical: String(term.canonical || ""),
        aliases: Array.isArray(term.aliases)
          ? term.aliases.slice(0, 12).map(String)
          : [],
        matched: String(term.matched || ""),
        score: Number(term.score || 0)
      }))
      : []
  };
}

function sanitizeEvent(payload) {
  if (payload.status !== "pending") {
    return { status: String(payload.status || "idle") };
  }
  const framePaths = Array.isArray(payload.frame_paths)
    ? payload.frame_paths
    : payload.frame_path
      ? [payload.frame_path]
      : [];
  return {
    status: "pending",
    token: String(payload.token || ""),
    created_at: String(payload.created_at || ""),
    messages: Array.isArray(payload.messages)
      ? payload.messages.slice(0, 50).map((message) => ({
        created_at: String(message.created_at || ""),
        text: truncateText(message.text, 12000)
      }))
      : [],
    description: payload.description
      ? truncateText(payload.description, 12000)
      : null,
    game_context: sanitizedGameContext(payload.game_context),
    frame_count: framePaths.length,
    frame_changed: Boolean(payload.frame_changed)
  };
}

function mimeTypeForFrame(filePath) {
  const extension = path.extname(filePath).toLocaleLowerCase();
  if (extension === ".png") {
    return "image/png";
  }
  if (extension === ".webp") {
    return "image/webp";
  }
  return "image/jpeg";
}

function frameContent(home, payload) {
  const rawPaths = Array.isArray(payload.frame_paths)
    ? payload.frame_paths
    : payload.frame_path
      ? [payload.frame_path]
      : [];
  const selected = rawPaths.slice(-MAX_RETURNED_FRAMES);
  const blocks = [];
  let totalBytes = 0;
  let omitted = 0;
  const homeReal = canonicalDirectory(home);
  if (!homeReal) {
    return { blocks, omitted: selected.length };
  }

  for (const rawPath of selected) {
    try {
      const real = fs.realpathSync(String(rawPath));
      const stat = fs.statSync(real);
      if (
        !isInside(homeReal, real) ||
        !stat.isFile() ||
        stat.size > MAX_FRAME_BYTES ||
        totalBytes + stat.size > MAX_TOTAL_FRAME_BYTES
      ) {
        omitted += 1;
        continue;
      }
      const data = fs.readFileSync(real).toString("base64");
      totalBytes += stat.size;
      blocks.push({
        type: "image",
        data,
        mimeType: mimeTypeForFrame(real)
      });
    } catch {
      omitted += 1;
    }
  }
  return { blocks, omitted };
}

function pollOverlay(argumentsObject) {
  const connection = resolveGameBuddyHome(argumentsObject.gamebuddy_home);
  if (!connection) {
    throw new UserFacingError(
      "No local Game Buddy desktop checkout is connected. Set GAMEBUDDY_HOME or pass gamebuddy_home."
    );
  }
  const payload = invokeHeartbeat(connection.path, ["poll"]);
  const sanitized = sanitizeEvent(payload);
  const frames = frameContent(connection.path, payload);
  if (frames.omitted) {
    sanitized.omitted_frame_count = frames.omitted;
  }
  return { data: sanitized, extraContent: frames.blocks };
}

function requireToken(value) {
  const token = String(value || "").trim();
  if (!token || token.length > 512) {
    throw new UserFacingError(
      "A valid pending-event token from gamebuddy_poll is required."
    );
  }
  return token;
}

function replyOverlay(argumentsObject) {
  const connection = resolveGameBuddyHome(argumentsObject.gamebuddy_home);
  if (!connection) {
    throw new UserFacingError(
      "No local Game Buddy desktop checkout is connected. Set GAMEBUDDY_HOME or pass gamebuddy_home."
    );
  }
  const token = requireToken(argumentsObject.token);
  const reply = String(argumentsObject.reply || "").trim();
  if (!reply) {
    throw new UserFacingError("reply must not be empty");
  }
  if (reply.length > 8000) {
    throw new UserFacingError("reply must be 8,000 characters or fewer");
  }
  const payload = invokeHeartbeat(
    connection.path,
    ["commit", "--token", token, "--reply", reply]
  );
  return {
    status: String(payload.status || "committed"),
    silent: false
  };
}

function silentOverlay(argumentsObject) {
  const connection = resolveGameBuddyHome(argumentsObject.gamebuddy_home);
  if (!connection) {
    throw new UserFacingError(
      "No local Game Buddy desktop checkout is connected. Set GAMEBUDDY_HOME or pass gamebuddy_home."
    );
  }
  const token = requireToken(argumentsObject.token);
  const payload = invokeHeartbeat(
    connection.path,
    ["commit", "--token", token, "--silent"]
  );
  return {
    status: String(payload.status || "committed"),
    silent: true
  };
}

const HOME_PROPERTY = {
  type: "string",
  description:
    "Optional path to a local Game Buddy checkout. Usually omit it and use GAMEBUDDY_HOME or the current working directory."
};

const TOOL_DEFINITIONS = [
  {
    name: "gamebuddy_list_games",
    title: "List Game Buddy games",
    description:
      "List bundled public and locally installed Game Buddy profiles without returning their filesystem paths.",
    inputSchema: {
      type: "object",
      properties: { gamebuddy_home: HOME_PROPERTY },
      additionalProperties: false
    },
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: false
    }
  },
  {
    name: "gamebuddy_get_context",
    title: "Load spoiler-aware game context",
    description:
      "Load a compact worldbook excerpt. Use safe unless the user explicitly selected current-game or full spoilers. Full-spoiler sections are physically removed in non-full modes.",
    inputSchema: {
      type: "object",
      properties: {
        profile_id: {
          type: "string",
          description:
            "Game profile id or exact alias. Omit only when the desktop config already selects a game."
        },
        spoiler_mode: {
          type: "string",
          enum: ["safe", "current-game", "full"],
          description:
            "Spoiler boundary. Choose full only after explicit user permission."
        },
        query: {
          type: "string",
          description:
            "Current mission, person, place, choice, or navigation question used to select relevant sections."
        },
        max_chars: {
          type: "integer",
          minimum: 2000,
          maximum: CONTEXT_MAX_CHARS_CEILING,
          description:
            "Maximum worldbook characters to return. Defaults to " +
            CONTEXT_MAX_CHARS_DEFAULT +
            ", which holds the largest bundled profile in full. Lowering it can cut late sections; check worldbook_truncated in the result."
        },
        gamebuddy_home: HOME_PROPERTY
      },
      additionalProperties: false
    },
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: false
    }
  },
  {
    name: "gamebuddy_search_terms",
    title: "Search Game Buddy terminology",
    description:
      "Retrieve only the 10 to 30 most relevant names, places, factions, abbreviations, or localization aliases for the current utterance or OCR text.",
    inputSchema: {
      type: "object",
      properties: {
        profile_id: {
          type: "string",
          description:
            "Game profile id or exact alias. Omit only when the desktop config already selects a game."
        },
        query: {
          type: "string",
          minLength: 1,
          description: "Speech, OCR text, or a possibly misheard term."
        },
        limit: {
          type: "integer",
          minimum: 10,
          maximum: 30,
          description: "Bounded result count; defaults to 20."
        },
        gamebuddy_home: HOME_PROPERTY
      },
      required: ["query"],
      additionalProperties: false
    },
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: false
    }
  },
  {
    name: "gamebuddy_get_credits",
    title: "Read Game Buddy credits",
    description:
      "Read source, game-author, localization-team, Wiki, and guide acknowledgements for one profile.",
    inputSchema: {
      type: "object",
      properties: {
        profile_id: {
          type: "string",
          description:
            "Game profile id or exact alias. Omit only when the desktop config already selects a game."
        },
        gamebuddy_home: HOME_PROPERTY
      },
      additionalProperties: false
    },
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: false
    }
  },
  {
    name: "gamebuddy_get_authoring_kit",
    title: "Read the Game Buddy authoring kit",
    description:
      "Return the client-neutral profile template, worldbook template, workflow, and source/release rules for creating a new spoiler-aware game guide. This is read-only and does not create or publish files.",
    inputSchema: {
      type: "object",
      properties: {},
      additionalProperties: false
    },
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: false
    }
  },
  {
    name: "gamebuddy_status",
    title: "Check local Game Buddy status",
    description:
      "Return sanitized desktop bridge state without absolute paths, Codex task ids, credentials, config contents, or chat history.",
    inputSchema: {
      type: "object",
      properties: { gamebuddy_home: HOME_PROPERTY },
      additionalProperties: false
    },
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: false
    }
  },
  {
    name: "gamebuddy_poll",
    title: "Read one pending Game Buddy event",
    description:
      "Poll exactly once for a pending overlay event. It freezes the event until its token is committed and returns up to three target-game frames as MCP images. Do not poll again before replying or committing silent.",
    inputSchema: {
      type: "object",
      properties: { gamebuddy_home: HOME_PROPERTY },
      additionalProperties: false
    },
    annotations: {
      readOnlyHint: false,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: false
    }
  },
  {
    name: "gamebuddy_reply",
    title: "Reply to a Game Buddy event",
    description:
      "Write one visible overlay reply and commit the matching pending event token returned by gamebuddy_poll.",
    inputSchema: {
      type: "object",
      properties: {
        token: {
          type: "string",
          minLength: 1,
          description: "Pending event token returned by gamebuddy_poll."
        },
        reply: {
          type: "string",
          minLength: 1,
          maxLength: 8000,
          description: "Player-visible reply."
        },
        gamebuddy_home: HOME_PROPERTY
      },
      required: ["token", "reply"],
      additionalProperties: false
    },
    annotations: {
      readOnlyHint: false,
      destructiveHint: false,
      idempotentHint: false,
      openWorldHint: false
    }
  },
  {
    name: "gamebuddy_silent",
    title: "Commit a Game Buddy event silently",
    description:
      "Explicitly mark the matching pending event handled without writing a visible overlay reply. Use only when silence is intentional.",
    inputSchema: {
      type: "object",
      properties: {
        token: {
          type: "string",
          minLength: 1,
          description: "Pending event token returned by gamebuddy_poll."
        },
        gamebuddy_home: HOME_PROPERTY
      },
      required: ["token"],
      additionalProperties: false
    },
    annotations: {
      readOnlyHint: false,
      destructiveHint: false,
      idempotentHint: false,
      openWorldHint: false
    }
  }
];

function textResult(data, extraContent = [], renderedText = null) {
  const text = renderedText === null
    ? JSON.stringify(data, null, 2)
    : renderedText;
  return {
    content: [
      { type: "text", text },
      ...extraContent
    ],
    structuredContent: data
  };
}

function errorToolResult(message) {
  const data = {
    status: "error",
    error: truncateText(message, 2000)
  };
  return {
    content: [{ type: "text", text: JSON.stringify(data, null, 2) }],
    structuredContent: data,
    isError: true
  };
}

function dispatchTool(name, rawArguments) {
  const args = rawArguments &&
    typeof rawArguments === "object" &&
    !Array.isArray(rawArguments)
    ? rawArguments
    : {};

  switch (name) {
    case "gamebuddy_list_games":
      return textResult(listGames(args));
    case "gamebuddy_get_context": {
      const data = getContext(args);
      const truncationNote = data.worldbook_truncated
        ? "Note: this excerpt hit the " + data.worldbook_max_chars +
          " character budget, so later sections are missing for length " +
          "reasons, not because of spoiler filtering. Raise max_chars or " +
          "pass a query to focus the excerpt.\n"
        : "";
      const rendered =
        "Game: " + data.profile.display_name + "\n" +
        "Spoiler mode: " + data.spoiler_mode + "\n" +
        truncationNote + "\n" +
        data.worldbook;
      return textResult(data, [], rendered);
    }
    case "gamebuddy_search_terms":
      return textResult(searchTerms(args));
    case "gamebuddy_get_credits": {
      const data = getCredits(args);
      return textResult(data, [], data.credits);
    }
    case "gamebuddy_get_authoring_kit":
      return textResult(getAuthoringKit());
    case "gamebuddy_status":
      return textResult(sanitizedStatus(args));
    case "gamebuddy_poll": {
      const result = pollOverlay(args);
      return textResult(result.data, result.extraContent);
    }
    case "gamebuddy_reply":
      return textResult(replyOverlay(args));
    case "gamebuddy_silent":
      return textResult(silentOverlay(args));
    default:
      return null;
  }
}

function requestProtocol(request) {
  const paramsMeta = request &&
    request.params &&
    request.params._meta &&
    typeof request.params._meta === "object"
    ? request.params._meta
    : {};
  const topMeta = request &&
    request._meta &&
    typeof request._meta === "object"
    ? request._meta
    : {};
  return String(
    paramsMeta["io.modelcontextprotocol/protocolVersion"] ||
    topMeta["io.modelcontextprotocol/protocolVersion"] ||
    ""
  );
}

function isModernRequest(request) {
  return requestProtocol(request) === "2026-07-28";
}

function completeResult(request, result, options = {}) {
  if (!isModernRequest(request)) {
    return result;
  }
  const modern = { resultType: "complete", ...result };
  if (options.cacheable) {
    modern.ttlMs = options.ttlMs || 60000;
    modern.cacheScope = options.cacheScope || "private";
  }
  return modern;
}

function rpcResult(request, result, options = {}) {
  return {
    jsonrpc: "2.0",
    id: request.id,
    result: completeResult(request, result, options)
  };
}

function rpcError(request, code, message, data) {
  const error = { code, message };
  if (data !== undefined) {
    error.data = data;
  }
  return {
    jsonrpc: "2.0",
    id: hasOwn(request || {}, "id") ? request.id : null,
    error
  };
}

function initializeResult(request) {
  const requested = String(
    request.params && request.params.protocolVersion || ""
  );
  negotiatedProtocol = SUPPORTED_PROTOCOLS.includes(requested)
    ? requested
    : LEGACY_PROTOCOL;
  return {
    protocolVersion: negotiatedProtocol,
    capabilities: {
      tools: { listChanged: false }
    },
    serverInfo: SERVER_INFO,
    instructions: INSTRUCTIONS
  };
}

function handleRequest(request) {
  if (!request || typeof request !== "object" || Array.isArray(request)) {
    return rpcError({}, -32600, "Invalid Request");
  }
  const hasId = hasOwn(request, "id");
  const method = String(request.method || "");

  if (!hasId) {
    if (method === "exit") {
      process.exitCode = 0;
    }
    return null;
  }

  if (request.jsonrpc !== "2.0" || !method) {
    return rpcError(request, -32600, "Invalid Request");
  }

  try {
    switch (method) {
      case "server/discover":
        return rpcResult(request, {
          supportedVersions: SUPPORTED_PROTOCOLS,
          capabilities: { tools: {} },
          serverInfo: SERVER_INFO,
          instructions: INSTRUCTIONS
        }, {
          cacheable: true,
          ttlMs: 300000,
          cacheScope: "public"
        });
      case "initialize":
        return {
          jsonrpc: "2.0",
          id: request.id,
          result: initializeResult(request)
        };
      case "ping":
      case "shutdown":
      case "logging/setLevel":
        return rpcResult(request, {});
      case "tools/list":
        return rpcResult(request, {
          tools: TOOL_DEFINITIONS
        }, {
          cacheable: true,
          ttlMs: 300000,
          cacheScope: "public"
        });
      case "tools/call": {
        const params = request.params &&
          typeof request.params === "object"
          ? request.params
          : {};
        const name = String(params.name || "");
        const result = dispatchTool(name, params.arguments);
        if (!result) {
          return rpcError(
            request,
            -32602,
            "Unknown Game Buddy tool: " + name
          );
        }
        return rpcResult(request, result);
      }
      case "resources/list":
        return rpcResult(request, { resources: [] });
      case "prompts/list":
        return rpcResult(request, { prompts: [] });
      default:
        return rpcError(request, -32601, "Method not found");
    }
  } catch (error) {
    if (method === "tools/call" && error instanceof UserFacingError) {
      return rpcResult(request, errorToolResult(error.message));
    }
    debug(error && error.stack ? error.stack : String(error));
    if (method === "tools/call") {
      return rpcResult(
        request,
        errorToolResult("Game Buddy MCP could not complete this local operation.")
      );
    }
    return rpcError(request, -32603, "Internal error");
  }
}

function send(message) {
  if (message === null || message === undefined) {
    return;
  }
  process.stdout.write(JSON.stringify(message) + "\n");
}

const input = readline.createInterface({
  input: process.stdin,
  crlfDelay: Infinity,
  terminal: false
});

input.on("line", (line) => {
  const trimmed = line.trim();
  if (!trimmed) {
    return;
  }
  let message;
  try {
    message = JSON.parse(trimmed);
  } catch {
    send({
      jsonrpc: "2.0",
      id: null,
      error: { code: -32700, message: "Parse error" }
    });
    return;
  }

  if (Array.isArray(message)) {
    if (!message.length) {
      send({
        jsonrpc: "2.0",
        id: null,
        error: { code: -32600, message: "Invalid Request" }
      });
      return;
    }
    const responses = message
      .map(handleRequest)
      .filter((item) => item !== null);
    if (responses.length) {
      send(responses);
    }
    return;
  }

  send(handleRequest(message));
});

input.on("close", () => {
  debug(
    "stdin closed" +
    (negotiatedProtocol ? " after " + negotiatedProtocol : "")
  );
});
