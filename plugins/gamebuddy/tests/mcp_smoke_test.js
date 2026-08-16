"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const readline = require("node:readline");
const { spawn } = require("node:child_process");

const PLUGIN_ROOT = path.resolve(__dirname, "..");
const REPO_ROOT = path.resolve(PLUGIN_ROOT, "..", "..");
const MCP_CONFIG = JSON.parse(
  fs.readFileSync(path.join(PLUGIN_ROOT, ".mcp.json"), "utf8")
).mcpServers.gamebuddy;

class McpClient {
  constructor() {
    this.nextId = 1;
    this.pending = new Map();
    this.stderr = "";
    this.process = spawn(
      MCP_CONFIG.command,
      MCP_CONFIG.args,
      {
        cwd: path.resolve(PLUGIN_ROOT, MCP_CONFIG.cwd || "."),
        stdio: ["pipe", "pipe", "pipe"],
        windowsHide: true,
        env: {
          ...process.env,
          GAMEBUDDY_PYTHON:
            process.env.GAMEBUDDY_PYTHON ||
            (process.platform === "win32" ? "python" : "python3"),
          GAMEBUDDY_DISABLE_AUTO_DISCOVERY: "1"
        }
      }
    );
    this.process.stderr.setEncoding("utf8");
    this.process.stderr.on("data", (chunk) => {
      this.stderr += chunk;
    });
    const lines = readline.createInterface({
      input: this.process.stdout,
      crlfDelay: Infinity
    });
    lines.on("line", (line) => {
      const message = JSON.parse(line);
      const responseList = Array.isArray(message) ? message : [message];
      for (const response of responseList) {
        const waiter = this.pending.get(response.id);
        if (waiter) {
          this.pending.delete(response.id);
          waiter.resolve(response);
        }
      }
    });
    this.process.on("exit", (code) => {
      for (const waiter of this.pending.values()) {
        waiter.reject(
          new Error(
            "MCP server exited early with code " + code + ": " + this.stderr
          )
        );
      }
      this.pending.clear();
    });
  }

  request(method, params) {
    const id = this.nextId;
    this.nextId += 1;
    const request = {
      jsonrpc: "2.0",
      id,
      method
    };
    if (params !== undefined) {
      request.params = params;
    }
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error("Timed out waiting for " + method));
      }, 10000);
      this.pending.set(id, {
        resolve: (response) => {
          clearTimeout(timer);
          resolve(response);
        },
        reject: (error) => {
          clearTimeout(timer);
          reject(error);
        }
      });
      this.process.stdin.write(JSON.stringify(request) + "\n");
    });
  }

  call(name, args = {}, modern = false) {
    const params = { name, arguments: args };
    if (modern) {
      params._meta = {
        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientInfo": {
          name: "gamebuddy-test",
          version: "1.0.0"
        },
        "io.modelcontextprotocol/clientCapabilities": {}
      };
    }
    return this.request("tools/call", params);
  }

  async close() {
    this.process.stdin.end();
    await new Promise((resolve) => {
      const timer = setTimeout(() => {
        this.process.kill();
        resolve();
      }, 3000);
      this.process.once("exit", () => {
        clearTimeout(timer);
        resolve();
      });
    });
  }
}

function writeJson(filePath, value) {
  fs.writeFileSync(filePath, JSON.stringify(value, null, 2) + "\n");
}

function makeFixture() {
  const root = fs.mkdtempSync(
    path.join(os.tmpdir(), "gamebuddy-mcp-test-")
  );
  const skillRoot = path.join(root, "local-skill");
  const profileRoot = path.join(skillRoot, "assets", "game-profiles");
  const referenceRoot = path.join(skillRoot, "references", "games");
  fs.mkdirSync(profileRoot, { recursive: true });
  fs.mkdirSync(referenceRoot, { recursive: true });
  fs.writeFileSync(path.join(skillRoot, "SKILL.md"), "# Test skill\n");
  writeJson(path.join(profileRoot, "crlf-worldbook.json"), {
    schema_version: 1,
    id: "crlf-worldbook",
    display_name: "CRLF Worldbook",
    aliases: [],
    reference: "references/games/crlf-worldbook.md",
    stt: { terms: [] }
  });
  const crlfWorldbook = Array.from(
    { length: 600 },
    () => "x".repeat(39)
  ).join("\r\n");
  assert.equal(crlfWorldbook.length, 24598);
  fs.writeFileSync(
    path.join(referenceRoot, "crlf-worldbook.md"),
    crlfWorldbook
  );
  fs.writeFileSync(path.join(root, "bridge_protocol.py"), "");
  fs.writeFileSync(path.join(root, "config.example.json"), "{}\n");
  writeJson(path.join(root, "config.json"), {
    game_profile: "disco-elysium",
    game_profile_root: profileRoot,
    knowledge_enabled: true,
    spoiler_mode: "safe",
    capture_on_message: true,
    direct_codex_enabled: false,
    heartbeat_include_messages: true
  });
  fs.writeFileSync(
    path.join(root, "message_queue.jsonl"),
    '{"id":"one","text":"hello"}\n{"id":"two","text":"world"}\n'
  );
  const script = [
    "import json",
    "import pathlib",
    "import sys",
    "root = pathlib.Path(__file__).resolve().parent",
    "command = sys.argv[1]",
    "if command == 'poll':",
    "    frame_dir = root / '.heartbeat_frames' / 'test-token'",
    "    frame_dir.mkdir(parents=True, exist_ok=True)",
    "    frame = frame_dir / 'frame_01.jpg'",
    "    frame.write_bytes(bytes([255, 216, 255, 217]))",
    "    payload = {",
    "        'status': 'pending',",
    "        'token': 'test-token',",
    "        'created_at': '2026-08-13T00:00:00Z',",
    "        'messages': [{'id': 'private-id', 'created_at': 'now', 'text': '选哪个？'}],",
    "        'description': 'A local target-game frame.',",
    "        'frame_paths': [str(frame)],",
    "        'frame_changed': True,",
    "        'game_context': {",
    "            'profile_id': 'disco-elysium',",
    "            'display_name': 'Disco Elysium',",
    "            'knowledge_enabled': True,",
    "            'spoiler_mode': 'safe',",
    "            'spoiler_label': 'safe',",
    "            'profile_path': str(root / 'private-profile.json'),",
    "            'terms': [{'canonical': '马丁内斯', 'aliases': ['Martinaise'], 'matched': '马丁内斯', 'score': 1.0}]",
    "        }",
    "    }",
    "    print(json.dumps(payload, ensure_ascii=False))",
    "elif command == 'commit':",
    "    (root / 'commit_args.json').write_text(json.dumps(sys.argv[2:], ensure_ascii=False), encoding='utf-8')",
    "    print(json.dumps({'status': 'committed'}, ensure_ascii=False))",
    "else:",
    "    print(json.dumps({'status': 'error', 'error': 'unsupported'}))",
    "    raise SystemExit(1)"
  ].join("\n") + "\n";
  fs.writeFileSync(path.join(root, "heartbeat_bridge.py"), script);
  return root;
}

function assertPrivacyBoundary() {
  const bannedNames = new Set([
    "config.json",
    "chat_history.txt",
    "danmaku.txt",
    "description.txt",
    "message.txt",
    "message_queue.jsonl",
    "current_frame.jpg",
    "direct_codex_status.json",
    "terms.csv",
    "aliases.json"
  ]);
  const personalMacPrefix = "/" + "Users" + "/";
  const personalWindowsPrefix = "C:" + "\\" + "Users" + "\\";
  const files = [];

  function walk(directory) {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const fullPath = path.join(directory, entry.name);
      const relative = path.relative(PLUGIN_ROOT, fullPath);
      const stat = fs.lstatSync(fullPath);
      assert.equal(
        stat.isSymbolicLink(),
        false,
        "plugin must not contain symlinks: " + relative
      );
      if (entry.isDirectory()) {
        walk(fullPath);
      } else if (entry.isFile()) {
        files.push(fullPath);
      }
    }
  }

  walk(PLUGIN_ROOT);
  assert(files.length > 0);
  for (const filePath of files) {
    const relative = path.relative(PLUGIN_ROOT, filePath);
    assert(
      !bannedNames.has(path.basename(filePath)),
      "private runtime file was bundled: " + relative
    );
    const stat = fs.statSync(filePath);
    assert(
      stat.size < 1024 * 1024,
      "unexpected large plugin file: " + relative
    );
    const extension = path.extname(filePath).toLocaleLowerCase();
    if ([".js", ".json", ".md", ".yaml", ".yml", ".py"].includes(extension)) {
      const content = fs.readFileSync(filePath, "utf8");
      assert(
        !content.includes(personalMacPrefix),
        "personal macOS path found in " + relative
      );
      assert(
        !content.includes(personalWindowsPrefix),
        "personal Windows path found in " + relative
      );
      assert(
        !content.includes(".codex" + path.sep + "attachments"),
        "attachment path found in " + relative
      );
    }
  }

  const profileRoot = path.join(
    PLUGIN_ROOT,
    "skills",
    "game-buddy",
    "assets",
    "game-profiles"
  );
  const profileFiles = fs.readdirSync(profileRoot)
    .filter((name) => name.endsWith(".json"))
    .sort();
  assert.deepEqual(profileFiles, [
    "disco-elysium.json",
    "mass-effect-legendary-edition.json"
  ]);
  for (const name of profileFiles) {
    const profile = JSON.parse(
      fs.readFileSync(path.join(profileRoot, name), "utf8")
    );
    assert(
      !Array.isArray(profile.glossaries) || profile.glossaries.length === 0,
      "public profile links a private glossary: " + name
    );
  }
}

async function main() {
  assertPrivacyBoundary();

  const generic = JSON.parse(
    fs.readFileSync(
      path.join(REPO_ROOT, "mcp", "configs", "generic-stdio.json"),
      "utf8"
    )
  );
  const workbuddy = JSON.parse(
    fs.readFileSync(
      path.join(REPO_ROOT, "mcp", "configs", "workbuddy.json"),
      "utf8"
    )
  );
  assert.equal(generic.mcpServers.gamebuddy.command, "npx");
  assert.equal(workbuddy.mcpServers.gamebuddy.disabled, false);

  const pluginManifest = JSON.parse(
    fs.readFileSync(
      path.join(PLUGIN_ROOT, ".codex-plugin", "plugin.json"),
      "utf8"
    )
  );
  const marketplace = JSON.parse(
    fs.readFileSync(
      path.join(REPO_ROOT, ".agents", "plugins", "marketplace.json"),
      "utf8"
    )
  );
  assert.equal(pluginManifest.name, "gamebuddy");
  assert.equal(pluginManifest.mcpServers, "./.mcp.json");
  assert.equal(marketplace.name, "gamebuddy-open-source");
  assert.equal(
    marketplace.plugins[0].source.path,
    "./plugins/gamebuddy"
  );

  const client = new McpClient();
  let fixture = null;
  try {
    const legacy = await client.request("initialize", {
      protocolVersion: "2024-11-05",
      capabilities: {},
      clientInfo: { name: "legacy-test", version: "1.0.0" }
    });
    assert.equal(legacy.result.protocolVersion, "2024-11-05");
    assert.equal(legacy.result.resultType, undefined);

    const modernMeta = {
      _meta: {
        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientInfo": {
          name: "modern-test",
          version: "1.0.0"
        },
        "io.modelcontextprotocol/clientCapabilities": {}
      }
    };
    const discover = await client.request("server/discover", modernMeta);
    assert.equal(discover.result.resultType, "complete");
    assert(discover.result.supportedVersions.includes("2026-07-28"));

    const modernTools = await client.request("tools/list", modernMeta);
    assert.equal(modernTools.result.resultType, "complete");
    assert.equal(modernTools.result.tools.length, 9);

    const legacyTools = await client.request("tools/list", {});
    assert.equal(legacyTools.result.resultType, undefined);
    assert.equal(legacyTools.result.tools.length, 9);

    const games = await client.call("gamebuddy_list_games");
    const ids = games.result.structuredContent.games.map((game) => game.id);
    assert(ids.includes("disco-elysium"));
    assert(ids.includes("mass-effect-legendary-edition"));

    const terms = await client.call("gamebuddy_search_terms", {
      profile_id: "disco-elysium",
      query: "马丁内丝",
      limit: 20
    });
    assert(
      terms.result.structuredContent.terms.some(
        (term) => term.canonical === "马丁内斯"
      )
    );

    const safe = await client.call("gamebuddy_get_context", {
      profile_id: "disco-elysium",
      spoiler_mode: "safe",
      query: "murder solution",
      max_chars: 20000
    });
    const safeText = safe.result.structuredContent.worldbook;
    assert(!safeText.includes("The shooter is the Deserter"));
    assert(!safeText.includes("### Murder solution"));

    const full = await client.call("gamebuddy_get_context", {
      profile_id: "disco-elysium",
      spoiler_mode: "full",
      query: "murder solution",
      max_chars: 20000
    });
    assert(
      full.result.structuredContent.worldbook.includes(
        "The shooter is the Deserter"
      )
    );

    // Without a query the whole worldbook is returned, so the default budget
    // has to hold the largest bundled profile. When it does not, every spoiler
    // mode returns the same truncated head and the filtering looks broken.
    const safeWhole = await client.call("gamebuddy_get_context", {
      profile_id: "disco-elysium",
      spoiler_mode: "safe"
    });
    const fullWhole = await client.call("gamebuddy_get_context", {
      profile_id: "disco-elysium",
      spoiler_mode: "full"
    });
    const safeWholeText = safeWhole.result.structuredContent.worldbook;
    const fullWholeText = fullWhole.result.structuredContent.worldbook;
    assert.equal(
      safeWhole.result.structuredContent.worldbook_truncated,
      false
    );
    assert.equal(
      fullWhole.result.structuredContent.worldbook_truncated,
      false
    );
    assert(!safeWholeText.includes("## Full-spoiler reference"));
    assert(fullWholeText.includes("## Full-spoiler reference"));
    assert(safeWholeText.includes("## Sources and confidence"));
    assert(fullWholeText.includes("## Sources and confidence"));
    assert(fullWholeText.length > safeWholeText.length);

    // A caller-lowered budget must be reported, so a short excerpt is never
    // mistaken for spoiler filtering.
    const clipped = await client.call("gamebuddy_get_context", {
      profile_id: "disco-elysium",
      spoiler_mode: "full",
      max_chars: 5000
    });
    assert.equal(clipped.result.structuredContent.worldbook_truncated, true);
    assert.equal(clipped.result.structuredContent.worldbook_max_chars, 5000);

    const credits = await client.call("gamebuddy_get_credits", {
      profile_id: "disco-elysium"
    });
    assert(credits.result.structuredContent.credits.includes("ZA/UM"));

    const authoring = await client.call(
      "gamebuddy_get_authoring_kit"
    );
    assert.equal(
      authoring.result.structuredContent.profile_template.schema_version,
      1
    );
    assert(
      authoring.result.structuredContent.worldbook_template.includes(
        "spoiler"
      )
    );
    assert(
      authoring.result.structuredContent.source_and_release_rules.includes(
        "Public-release"
      )
    );

    const disconnected = await client.call("gamebuddy_status");
    assert.equal(disconnected.result.structuredContent.connected, false);

    fixture = makeFixture();

    const status = await client.call("gamebuddy_status", {
      gamebuddy_home: fixture
    });
    assert.equal(status.result.structuredContent.connected, true);
    assert.equal(status.result.structuredContent.bridge.queued_messages, 2);
    assert(!JSON.stringify(status.result).includes(fixture));

    const crlfContext = await client.call("gamebuddy_get_context", {
      gamebuddy_home: fixture,
      profile_id: "crlf-worldbook",
      spoiler_mode: "full"
    });
    const crlfText = crlfContext.result.structuredContent.worldbook;
    assert.equal(
      crlfContext.result.structuredContent.worldbook_truncated,
      false
    );
    assert.equal(crlfText.length, 23999);
    assert(!crlfText.includes("\r"));

    const poll = await client.call(
      "gamebuddy_poll",
      { gamebuddy_home: fixture },
      true
    );
    assert.equal(poll.result.resultType, "complete");
    assert.equal(poll.result.structuredContent.token, "test-token");
    assert(
      poll.result.content.some((item) => item.type === "image")
    );
    assert(!JSON.stringify(poll.result).includes(fixture));
    assert(
      !JSON.stringify(poll.result).includes("private-profile.json")
    );

    const reply = await client.call("gamebuddy_reply", {
      gamebuddy_home: fixture,
      token: "test-token",
      reply: "走左边这扇门。"
    });
    assert.equal(reply.result.structuredContent.status, "committed");
    const replyArgs = JSON.parse(
      fs.readFileSync(path.join(fixture, "commit_args.json"), "utf8")
    );
    assert.deepEqual(replyArgs, [
      "--token",
      "test-token",
      "--reply",
      "走左边这扇门。"
    ]);

    const silent = await client.call("gamebuddy_silent", {
      gamebuddy_home: fixture,
      token: "test-token"
    });
    assert.equal(silent.result.structuredContent.silent, true);
    const silentArgs = JSON.parse(
      fs.readFileSync(path.join(fixture, "commit_args.json"), "utf8")
    );
    assert.deepEqual(silentArgs, [
      "--token",
      "test-token",
      "--silent"
    ]);
  } finally {
    await client.close();
    if (fixture) {
      fs.rmSync(fixture, { recursive: true, force: true });
    }
  }

  process.stdout.write(
    "Game Buddy MCP smoke, protocol, bridge, spoiler, and privacy tests passed.\n"
  );
}

main().catch((error) => {
  process.stderr.write((error && error.stack) || String(error));
  process.stderr.write("\n");
  process.exitCode = 1;
});
