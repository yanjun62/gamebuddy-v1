#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { spawn } = require("node:child_process");

const ROOT = __dirname;
const CONFIG_FILE = path.join(ROOT, "config.json");
const QUEUE_FILE = path.join(ROOT, "message_queue.jsonl");
const DANMAKU_FILE = path.join(ROOT, "danmaku.txt");
const FRAME_FILE = path.join(ROOT, "current_frame.jpg");
const STATE_FILE = path.join(ROOT, ".direct_codex_state.json");
const HEARTBEAT_STATE_FILE = path.join(ROOT, ".heartbeat_state.json");
const STATUS_FILE = path.join(ROOT, "direct_codex_status.json");

let config = {};
let state = { processedMessageIds: [], threadId: null, inFlight: null, retries: {} };
let socket = null;
let requestId = 1;
let pendingRequests = new Map();
let active = null;
let connected = false;
let shuttingDown = false;
let serverProcess = null;
let reconnectAttempt = 0;
let pollBusy = false;

function readJson(file, fallback) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return fallback;
  }
}

function atomicWrite(file, contents) {
  const temp = path.join(path.dirname(file), `.${path.basename(file)}.${process.pid}.${Date.now()}.tmp`);
  fs.writeFileSync(temp, contents, "utf8");
  fs.renameSync(temp, file);
}

function saveState() {
  state.processedMessageIds = [...new Set(state.processedMessageIds)].slice(-10000);
  atomicWrite(STATE_FILE, `${JSON.stringify(state, null, 2)}\n`);
}

function bootstrapProcessedMessages() {
  const heartbeat = readJson(HEARTBEAT_STATE_FILE, {});
  const inherited = Array.isArray(heartbeat.processed_message_ids)
    ? heartbeat.processed_message_ids.filter((id) => typeof id === "string")
    : [];
  const pendingMessages = Array.isArray(heartbeat.pending?.messages) ? heartbeat.pending.messages : [];
  for (const message of pendingMessages) {
    if (typeof message?.id === "string") inherited.push(message.id);
  }
  state.processedMessageIds = [...new Set([...state.processedMessageIds, ...inherited])];
  state.bootstrappedFromHeartbeatAt = new Date().toISOString();
  saveState();
}

function writeStatus(status, extra = {}) {
  atomicWrite(
    STATUS_FILE,
    `${JSON.stringify({ status, updatedAt: new Date().toISOString(), threadId: state.threadId, ...extra }, null, 2)}\n`,
  );
}

function validateConfig() {
  if (typeof WebSocket === "undefined") {
    throw new Error("direct_codex_bridge.js 需要 Node.js 22 或更高版本");
  }
  const endpoint = new URL(config.direct_codex_endpoint || "ws://127.0.0.1:8766");
  const host = endpoint.hostname.toLowerCase();
  const loopback = host === "localhost" || host === "::1" || host === "[::1]" || host.startsWith("127.");
  if (endpoint.protocol !== "ws:" || !loopback) {
    throw new Error("direct_codex_endpoint 必须是仅监听本机的 ws:// 地址");
  }
  config.direct_codex_endpoint = endpoint.origin;
  const configuredWorkspace = String(config.direct_codex_workspace || "").trim();
  const workspace = configuredWorkspace && !configuredWorkspace.startsWith("<") ? configuredWorkspace : ROOT;
  config.direct_codex_workspace = path.resolve(workspace);
}

function readQueue() {
  if (!fs.existsSync(QUEUE_FILE)) return [];
  return fs
    .readFileSync(QUEUE_FILE, "utf8")
    .split(/\r?\n/)
    .filter(Boolean)
    .flatMap((line) => {
      try {
        const item = JSON.parse(line);
        return typeof item.id === "string" && typeof item.text === "string" && item.text.trim() ? [item] : [];
      } catch {
        return [];
      }
    });
}

function send(message) {
  if (!socket || socket.readyState !== WebSocket.OPEN) throw new Error("Codex WebSocket 未连接");
  socket.send(JSON.stringify(message));
}

function notify(method, params = {}) {
  send({ method, params });
}

function request(method, params = {}) {
  const id = requestId++;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      pendingRequests.delete(id);
      reject(new Error(`${method} 请求超时`));
    }, Number(config.direct_codex_request_timeout_ms || 30000));
    pendingRequests.set(id, { resolve, reject, timer, method });
    try {
      send({ method, id, params });
    } catch (error) {
      clearTimeout(timer);
      pendingRequests.delete(id);
      reject(error);
    }
  });
}

function rejectPending(reason) {
  for (const pending of pendingRequests.values()) {
    clearTimeout(pending.timer);
    pending.reject(reason);
  }
  pendingRequests.clear();
}

async function eventText(data) {
  if (typeof data === "string") return data;
  if (data instanceof ArrayBuffer) return Buffer.from(data).toString("utf8");
  if (typeof data?.text === "function") return data.text();
  return String(data);
}

async function handleMessage(event) {
  let message;
  try {
    message = JSON.parse(await eventText(event.data));
  } catch (error) {
    writeStatus("error", { error: `无法解析 app-server 消息: ${error.message}` });
    return;
  }

  if (Object.prototype.hasOwnProperty.call(message, "id")) {
    const pending = pendingRequests.get(message.id);
    if (!pending) return;
    pendingRequests.delete(message.id);
    clearTimeout(pending.timer);
    if (message.error) pending.reject(new Error(`${pending.method}: ${message.error.message || "未知错误"}`));
    else pending.resolve(message.result);
    return;
  }

  const params = message.params || {};
  if (message.method === "item/completed" && active && params.turnId === active.turnId) {
    const item = params.item || {};
    if (item.type === "agentMessage" && typeof item.text === "string" && item.text.trim()) {
      if (item.phase === "final_answer") active.finalText = item.text.trim();
      else active.fallbackText = item.text.trim();
    }
  } else if (message.method === "item/agentMessage/delta" && active && params.turnId === active.turnId) {
    active.deltaText += params.delta || "";
  } else if (message.method === "turn/completed" && active && params.turn?.id === active.turnId) {
    completeTurn(params.turn);
  } else if (message.method === "error") {
    writeStatus("error", { error: params.error?.message || params.message || "Codex app-server error" });
  }
}

function markRetry(message, reason) {
  const previous = state.retries[message.id] || { attempts: 0 };
  const attempts = previous.attempts + 1;
  const delay = Math.min(60000, 1000 * 2 ** Math.min(attempts, 6));
  state.retries[message.id] = { attempts, nextAt: Date.now() + delay, reason };
  state.inFlight = null;
  active = null;
  saveState();
  writeStatus("retrying", { error: reason, retryInMs: delay, messageId: message.id });
}

function completeTurn(turn) {
  const current = active;
  const text = current.finalText || current.fallbackText || current.deltaText.trim();
  if (turn.status === "completed" && text) {
    atomicWrite(DANMAKU_FILE, text);
    state.processedMessageIds.push(current.message.id);
    delete state.retries[current.message.id];
    state.inFlight = null;
    active = null;
    saveState();
    writeStatus("ready", { lastMessageId: current.message.id });
    return;
  }
  markRetry(current.message, turn.error?.message || `Codex turn ${turn.status || "failed"}`);
}

function freshFrameInput() {
  try {
    const stat = fs.statSync(FRAME_FILE);
    const maxAgeMs = Number(config.direct_codex_screenshot_max_age_seconds || 15) * 1000;
    if (Date.now() - stat.mtimeMs <= maxAgeMs) {
      return { type: "localImage", path: path.resolve(FRAME_FILE), detail: "auto" };
    }
  } catch {
    // Screenshot is optional.
  }
  return null;
}

function captureFrameOnMessage() {
  if (config.capture_on_message === false) return Promise.resolve(false);
  const configuredPython = String(config.capture_python_executable || "").trim();
  const venvPython = process.platform === "win32"
    ? path.join(ROOT, ".venv", "Scripts", "python.exe")
    : path.join(ROOT, ".venv", "bin", "python");
  const executable = configuredPython
    || (fs.existsSync(venvPython) ? venvPython : (process.platform === "win32" ? "python" : "python3"));
  const script = path.join(ROOT, "capture_once.py");
  return new Promise((resolve) => {
    let settled = false;
    const child = spawn(executable, [script], {
      cwd: ROOT,
      windowsHide: true,
      stdio: "ignore",
    });
    const finish = (success) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(success);
    };
    const timer = setTimeout(() => {
      child.kill();
      finish(false);
    }, Number(config.capture_on_message_timeout_ms || 5000));
    child.once("error", () => finish(false));
    child.once("exit", (code) => finish(code === 0));
  });
}

function formatGameContext(context) {
  if (!context || typeof context !== "object") return "";
  const game = String(context.display_name || context.profile_id || "未指定游戏");
  const mode = String(context.spoiler_mode || "safe");
  const modeRules = {
    safe: "安全模式：只谈画面可见或玩家已提供的信息，不透露后续角色、凶手、死亡、结局或隐藏后果。",
    "current-game": "当前进度攻略：可讲玩家已经到达的内容；隐藏后续章节、跨作继承结果和未触发的永久后果。",
    full: "完整剧透攻略：玩家已在菜单中明确授权，可回答隐藏结局、凶手、死亡与长期后果。",
  };
  const lines = ["[Game Buddy 本地设置]", `游戏：${game}`, modeRules[mode] || modeRules.safe];
  if (context.knowledge_enabled) {
    lines.push("词库：开启。只按当前问题检索少量相关条目，禁止一次加载完整术语库。");
    if (context.profile_path) lines.push(`游戏档案：${context.profile_path}`);
    if (context.reference_path) lines.push(`攻略与世界书：${context.reference_path}`);
    const terms = Array.isArray(context.terms) ? context.terms.slice(0, 30) : [];
    if (terms.length) {
      lines.push(
        "当前相关术语：" +
          terms
            .map((term) => {
              const aliases = Array.isArray(term.aliases) ? term.aliases.slice(0, 3).join(" / ") : "";
              return aliases ? `${term.canonical} (${aliases})` : String(term.canonical || "");
            })
            .filter(Boolean)
            .join("；"),
      );
    }
    lines.push("需要精确信息时，只可按需读取上述本地档案/攻略或使用 Game Buddy lookup；不得修改文件。");
  } else {
    lines.push("词库：关闭。不要读取或引用游戏专属世界书、攻略和术语库。");
  }
  return lines.join("\n");
}

async function sendNextMessage(message) {
  const prefix = String(
    config.direct_codex_prompt_prefix ||
      "这是由 Game Buddy 转发的玩家消息。请保持当前任务中已有的人格、称呼、语气、关系设定与表达习惯；Game Buddy 只提供游戏上下文和剧透边界，不创建或替换人格。如果当前代理已经加载人格或项目指令文件（例如 Claude Code 的 CLAUDE.md、Codex 的 AGENTS.md），请继续遵守；无需仅因本提示而查找这些文件。回复应适合悬浮气泡阅读，但用户已有的交流风格优先。只可按需读取所选本地词库，不得修改文件或执行其他操作。",
  ).trim();
  const gameContext = formatGameContext(message.game_context);
  const text = [prefix, gameContext, `玩家：${message.text.trim()}`].filter(Boolean).join("\n\n");
  const input = [{ type: "text", text }];
  await captureFrameOnMessage();
  const frame = freshFrameInput();
  if (frame) input.push(frame);

  active = {
    message,
    turnId: null,
    finalText: "",
    fallbackText: "",
    deltaText: "",
    recoveryDeadline: 0,
  };
  state.inFlight = { message, turnId: null, startedAt: Date.now() };
  saveState();
  writeStatus("thinking", { messageId: message.id, screenshotAttached: Boolean(frame) });
  try {
    const result = await request("turn/start", {
      threadId: state.threadId,
      input,
      clientUserMessageId: message.id,
    });
    active.turnId = result?.turn?.id;
    if (!active.turnId) throw new Error("turn/start 未返回 turn id");
    state.inFlight.turnId = active.turnId;
    saveState();
  } catch (error) {
    markRetry(message, error.message);
  }
}

async function pollQueue() {
  if (pollBusy || !connected || shuttingDown) return;
  pollBusy = true;
  try {
    if (active) {
      if (active.recoveryDeadline && Date.now() >= active.recoveryDeadline) {
        markRetry(active.message, "重连后未收到原回合完成事件，准备安全重试");
      }
      return;
    }
    const processed = new Set(state.processedMessageIds);
    const now = Date.now();
    const next = readQueue().find((message) => {
      const retry = state.retries[message.id];
      return !processed.has(message.id) && (!retry || Number(retry.nextAt || 0) <= now);
    });
    if (next) await sendNextMessage(next);
  } finally {
    pollBusy = false;
  }
}

function safeConfiguredThreadId() {
  const value = String(config.direct_codex_thread_id || "").trim();
  return value && !value.startsWith("<") ? value : null;
}

async function initializeConnection() {
  await request("initialize", {
    clientInfo: { name: "game_buddy", title: "Game Buddy", version: "2.0.0" },
    capabilities: { optOutNotificationMethods: [] },
  });
  notify("initialized", {});

  const configuredThreadId = safeConfiguredThreadId();
  const threadId = configuredThreadId || state.threadId;
  const safeOverrides = config.direct_codex_read_only === false ? {} : { approvalPolicy: "never", sandbox: "read-only" };
  if (threadId) {
    try {
      const result = await request("thread/resume", {
        threadId,
        cwd: config.direct_codex_workspace,
        ...safeOverrides,
      });
      state.threadId = result?.thread?.id || threadId;
    } catch (error) {
      if (configuredThreadId) throw error;
      state.threadId = null;
    }
  }
  if (!state.threadId) {
    const result = await request("thread/start", {
      cwd: config.direct_codex_workspace,
      ...safeOverrides,
    });
    state.threadId = result?.thread?.id;
    if (!state.threadId) throw new Error("thread/start 未返回 thread id");
  }
  saveState();

  if (!active && state.inFlight?.message) {
    active = {
      message: state.inFlight.message,
      turnId: state.inFlight.turnId,
      finalText: "",
      fallbackText: "",
      deltaText: "",
      recoveryDeadline: Date.now() + Number(config.direct_codex_reconnect_grace_ms || 90000),
    };
  }
  connected = true;
  reconnectAttempt = 0;
  writeStatus(active ? "thinking" : "ready", { recoveredInFlight: Boolean(active) });
}

function connect() {
  if (shuttingDown) return;
  writeStatus("starting", { endpoint: config.direct_codex_endpoint });
  socket = new WebSocket(config.direct_codex_endpoint);
  socket.onmessage = (event) => void handleMessage(event);
  socket.onopen = () => {
    void initializeConnection().catch((error) => {
      writeStatus("error", { error: error.message });
      socket.close();
    });
  };
  socket.onerror = () => {
    connected = false;
  };
  socket.onclose = () => {
    connected = false;
    if (active) {
      active.recoveryDeadline = Date.now() + Number(config.direct_codex_reconnect_grace_ms || 90000);
    }
    rejectPending(new Error("Codex WebSocket 已断开"));
    if (shuttingDown) return;
    reconnectAttempt += 1;
    const delay = Math.min(30000, 500 * 2 ** Math.min(reconnectAttempt, 6)) + Math.floor(Math.random() * 500);
    writeStatus("starting", { reconnectInMs: delay });
    setTimeout(connect, delay);
  };
}

function maybeSpawnServer() {
  if (!config.direct_codex_spawn_server) return;
  const executable = String(config.direct_codex_executable || "codex");
  const env = { ...process.env };
  if (config.direct_codex_home && !String(config.direct_codex_home).startsWith("<")) {
    env.CODEX_HOME = String(config.direct_codex_home);
  }
  serverProcess = spawn(executable, ["app-server", "--listen", config.direct_codex_endpoint], {
    cwd: config.direct_codex_workspace,
    env,
    windowsHide: true,
    stdio: ["ignore", "ignore", "pipe"],
  });
  serverProcess.stderr?.on("data", (chunk) => {
    const text = String(chunk).trim();
    if (text) writeStatus("starting", { serverLog: text.slice(-1000) });
  });
  serverProcess.on("error", (error) => writeStatus("error", { error: `无法启动 Codex app-server: ${error.message}` }));
}

function shutdown() {
  if (shuttingDown) return;
  shuttingDown = true;
  writeStatus("stopped");
  try {
    socket?.close();
  } catch {}
  if (serverProcess && !serverProcess.killed) serverProcess.kill();
  setTimeout(() => process.exit(0), 100).unref();
}

function main() {
  config = readJson(CONFIG_FILE, {});
  const stateFileExisted = fs.existsSync(STATE_FILE);
  state = { ...state, ...readJson(STATE_FILE, {}) };
  state.processedMessageIds = Array.isArray(state.processedMessageIds) ? state.processedMessageIds : [];
  state.retries = state.retries && typeof state.retries === "object" ? state.retries : {};
  if (!stateFileExisted || (!state.threadId && !state.inFlight && state.processedMessageIds.length === 0)) {
    bootstrapProcessedMessages();
  }
  validateConfig();
  maybeSpawnServer();
  connect();
  setInterval(() => void pollQueue(), Number(config.direct_codex_poll_interval_ms || 500));
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}

try {
  main();
} catch (error) {
  writeStatus("error", { error: error.message });
  console.error(`[GameBuddy] ${error.stack || error.message}`);
  process.exitCode = 1;
}
