'use strict';
/**
 * whatsapp_bridge.js — Chaudhary Type House & Property Advisors
 * WhatsApp AI Agent bridge (Baileys v7.0.0-rc14) — production build for Render.
 *
 * WHY THIS FILE LOOKS THE WAY IT DOES
 * -----------------------------------
 * 1) Render's FREE tier only offers *Web Services* (Background Workers are
 *    paid-only). A Render web service MUST bind $PORT, otherwise the deploy is
 *    marked unhealthy and the container is restarted in a loop — the WhatsApp
 *    socket then never survives. Hence the small HTTP server below: it binds
 *    $PORT, exposes /health for Render's health check, and keeps the free
 *    instance awake (Render resets its 15-minute sleep timer on inbound HTTP).
 * 2) The session folder is $WA_AUTH_DIR (point it at a Render persistent disk).
 *    NEVER commit it to GitHub and NEVER rely on the ephemeral filesystem.
 * 3) Inbound-only: the bot never initiates a message or a call. It only answers
 *    messages that arrive at the linked number.
 *
 * Diagnostic endpoints:
 *   GET /health  -> JSON: auth state, connection state, counters, last errors
 *   GET /qr      -> raw QR string (so the QR can be fetched from outside the log)
 *   GET /        -> same as /health
 */

const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
  makeCacheableSignalKeyStore,
} = require("@whiskeysockets/baileys");
const pino = require("pino");
const qrcode = require("qrcode-terminal");
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");
const http = require("http");

/* ------------------------------------------------------------------ *
 * CONFIG
 * ------------------------------------------------------------------ */
const AUTH_DIR = path.resolve(
  process.env.WA_AUTH_DIR || path.join(__dirname, "auth_info_baileys")
);
const PYTHON = process.env.PYTHON || "python";
const AI_SCRIPT = path.join(__dirname, "whatsapp_ai.py");
const PORT = Number(process.env.PORT || 3000);
const HOST = process.env.HOST || "0.0.0.0";
const TYPING_MIN_MS = Number(process.env.TYPING_MIN_MS || 5000);
const TYPING_MAX_MS = Number(process.env.TYPING_MAX_MS || 10000);
const FALLBACK_WA_VERSION = [2, 3000, 1043857760]; // bundled with baileys 7.0.0-rc14
const HEARTBEAT_MS = Number(process.env.HEARTBEAT_MS || 30000);
const STALE_MS = Number(process.env.STALE_MS || 20 * 60 * 1000);
// How far back an OFFLINE ("append") message may be and still be answered.
// Guards against replying to ancient history-sync dumps while still covering
// messages that arrived during a Render sleep (Render idles out after 15 min).
const OFFLINE_REPLY_WINDOW_MIN = Number(process.env.OFFLINE_REPLY_WINDOW_MIN || 60);
const LOG_LEVEL = process.env.LOG_LEVEL || "info";
const ALLOW_GROUPS = process.env.WA_ALLOW_GROUPS === "1";
const IGNORE_JIDS = (process.env.WA_IGNORE_JIDS || "status@broadcast")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);

/* ------------------------------------------------------------------ *
 * LOGGING (everything here shows up in the Render log panel)
 * ------------------------------------------------------------------ */
const BOOT = Date.now();
const ts = () => new Date().toISOString().replace("T", " ").slice(0, 19);
const up = () => String(Math.round((Date.now() - BOOT) / 1000)).padStart(5, " ");
function LOG(tag, ...args) {
  console.log(`[${ts()}][+${up()}s] ${String(tag).padEnd(10)}`, ...args);
}
function FAIL(tag, err) {
  const body =
    err && err.stack
      ? err.stack
      : err && err.output
        ? `${err.message} | output=${JSON.stringify(err.output)}`
        : String(err);
  console.error(`[${ts()}][+${up()}s] ${String(tag).padEnd(10)}`, body);
}

/* ------------------------------------------------------------------ *
 * RUNTIME STATE (exposed via /health)
 * ------------------------------------------------------------------ */
const rt = {
  startedAt: new Date().toISOString(),
  uptimeSec: 0,
  connected: false,
  connection: "starting",
  waVersion: null,
  lastQrIssuedAt: 0,
  lastQr: "",
  lastEventAt: 0,
  lastAliveAt: 0,
  lastMessageAt: 0,
  lastError: "",
  reconnects: 0,
  counters: {
    upsert: 0,
    notify: 0,
    skipped: 0,
    replied: 0,
    readReceipts: 0,
    errors: 0,
  },
  auth: {
    dir: AUTH_DIR,
    dirExists: false,
    writable: false,
    credsFile: false,
    registered: false,
    me: null,
    fileCount: 0,
    files: [],
  },
};

/* ------------------------------------------------------------------ *
 * SMALL UTILITIES
 * ------------------------------------------------------------------ */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const typingDelay = () =>
  TYPING_MIN_MS + Math.floor(Math.random() * Math.max(1, TYPING_MAX_MS - TYPING_MIN_MS));

// Message cache so Baileys' getMessage() can resolve full payloads
// (view-once / unsupported types) instead of silently returning undefined.
const msgCache = new Map();
const MSG_CACHE_MAX = 500;

// Per-contact serial queue: a 5-10s typing delay on one chat must not block
// another chat, but the SAME chat must stay strictly in order.
const queues = new Map();
function enqueue(jid, fn) {
  const prev = queues.get(jid) || Promise.resolve();
  const next = prev
    .then(fn)
    .catch((e) => FAIL("queue", e))
    .then(() => {
      if (queues.get(jid) === next) queues.delete(jid);
    });
  queues.set(jid, next);
  return next;
}

// Per-contact conversation state (name / service / booking stage).
const states = new Map();

function pythonAI(message, state) {
  return new Promise((resolve, reject) => {
    const child = spawn(PYTHON, [AI_SCRIPT], {
      cwd: __dirname,
      env: { ...process.env, PYTHONIOENCODING: "utf-8" },
    });
    let stdout = "";
    let stderr = "";
    const timer = setTimeout(() => {
      try { child.kill(); } catch (_) {}
      reject(new Error("python AI timeout"));
    }, 30000);
    child.stdout.on("data", (d) => (stdout += d.toString("utf8")));
    child.stderr.on("data", (d) => (stderr += d.toString("utf8")));
    child.on("error", (e) => { clearTimeout(timer); reject(e); });
    child.on("close", (code) => {
      clearTimeout(timer);
      if (code !== 0) {
        reject(new Error(`python exited ${code}: ${stderr.slice(0, 500)}`));
        return;
      }
      try {
        resolve(JSON.parse(stdout));
      } catch (e) {
        reject(new Error(`bad json from AI: ${stdout.slice(0, 300)}`));
      }
    });
    child.stdin.write(JSON.stringify({ message, state: state || {} }));
    child.stdin.end();
  });
}

/* ------------------------------------------------------------------ *
 * AUTH / SESSION DIAGNOSTICS
 * ------------------------------------------------------------------ */
function inspectAuthDir() {
  rt.auth.dir = AUTH_DIR;
  rt.auth.dirExists = false;
  rt.auth.writable = false;
  rt.auth.credsFile = false;
  rt.auth.registered = false;
  rt.auth.me = null;
  rt.auth.files = [];
  try {
    fs.mkdirSync(AUTH_DIR, { recursive: true });
    rt.auth.dirExists = true;
  } catch (e) {
    FAIL("auth", `cannot create auth dir ${AUTH_DIR}: ${e.message}`);
    return;
  }
  try {
    const probe = path.join(AUTH_DIR, ".probe");
    fs.writeFileSync(probe, "ok");
    fs.unlinkSync(probe);
    rt.auth.writable = true;
  } catch (e) {
    FAIL("auth", `auth dir NOT writable (disk not mounted?): ${e.message}`);
  }
  try {
    const files = fs.readdirSync(AUTH_DIR);
    rt.auth.fileCount = files.length;
    rt.auth.files = files.slice(0, 25);
    const credsPath = path.join(AUTH_DIR, "creds.json");
    if (fs.existsSync(credsPath)) {
      rt.auth.credsFile = true;
      const c = JSON.parse(fs.readFileSync(credsPath, "utf8"));
      rt.auth.registered = !!c.registered;
      rt.auth.me = c.me ? c.me.id : null;
      rt.auth.registeredAt = c.registered || null;
    }
  } catch (e) {
    FAIL("auth", `cannot read auth dir: ${e.message}`);
  }
  LOG(
    "auth",
    `dir=${AUTH_DIR} exists=${rt.auth.dirExists} writable=${rt.auth.writable} ` +
      `creds.json=${rt.auth.credsFile} registered=${rt.auth.registered} ` +
      `me=${rt.auth.me || "-"} files=${rt.auth.fileCount}`
  );
}

/* ------------------------------------------------------------------ *
 * VERSION (never let a GitHub hiccup crash-loop the container)
 * ------------------------------------------------------------------ */
async function resolveVersion() {
  try {
    const { version } = await fetchLatestBaileysVersion();
    if (Array.isArray(version) && version.length === 3) {
      rt.waVersion = version.join(".");
      LOG("wa", `WhatsApp Web version ${rt.waVersion} (fetched)`);
      return version;
    }
  } catch (e) {
    FAIL("wa", `version fetch failed -> using pinned fallback: ${e.message}`);
  }
  rt.waVersion = FALLBACK_WA_VERSION.join(".");
  return FALLBACK_WA_VERSION;
}

/* ------------------------------------------------------------------ *
 * MESSAGE TEXT EXTRACTION (v7 payload shapes)
 * ------------------------------------------------------------------ */
function extractText(m) {
  if (!m) return "";
  if (m.conversation) return m.conversation;
  if (m.extendedTextMessage && m.extendedTextMessage.text) return m.extendedTextMessage.text;
  if (m.imageMessage && m.imageMessage.caption) return m.imageMessage.caption;
  if (m.videoMessage && m.videoMessage.caption) return m.videoMessage.caption;
  if (m.documentMessage && m.documentMessage.caption) return m.documentMessage.caption;
  if (m.documentWithCaptionMessage && m.documentWithCaptionMessage.message) {
    return extractText(m.documentWithCaptionMessage.message);
  }
  if (m.viewOnceMessageV2 && m.viewOnceMessageV2.message) return extractText(m.viewOnceMessageV2.message);
  if (m.viewOnceMessage && m.viewOnceMessage.message) return extractText(m.viewOnceMessage.message);
  if (m.buttonsResponseMessage && m.buttonsResponseMessage.selectedButtonId) {
    return m.buttonsResponseMessage.selectedButtonId;
  }
  if (m.listResponseMessage && m.listResponseMessage.singleSelectReply) {
    return m.listResponseMessage.singleSelectReply.selectedRowId || "";
  }
  if (m.templateMessage && m.templateMessage.hydratedTemplate) {
    return m.templateMessage.hydratedTemplate.hydratedContentText || "";
  }
  return "";
}

function isVoice(m) {
  return !!(m && m.audioMessage);
}

/* ------------------------------------------------------------------ *
 * REPLY HANDLER
 * ------------------------------------------------------------------ */
async function handleMessage(s, jid, text, voice) {
  const prev = states.get(jid) || {};
  try {
    // Human-like presence: available -> composing -> (delay) -> paused
    try { await s.sendPresenceUpdate("available", jid); } catch (_) {}
    try { await s.sendPresenceUpdate("composing", jid); } catch (_) {}

    const wait = typingDelay();
    LOG("msg", `typing indicator on for ${wait}ms (jid=${jid})`);
    await sleep(wait);
    try { await s.sendPresenceUpdate("paused", jid); } catch (_) {}

    if (voice) {
      await s.sendMessage(jid, {
        text:
          "G. Voice message mila. Please text mein likh dein taake main aap ki madad kar sakun. " +
          "Office: Baldia Chowk, Infront of City Police Station (A) Division, Chishtian (8:00 AM - 8:00 PM).",
      });
      rt.counters.replied++;
      LOG("msg", `voice reply sent -> ${jid}`);
      return;
    }

    if (!text.trim()) {
      rt.counters.skipped++;
      LOG("msg", `empty text -> skipped (jid=${jid})`);
      return;
    }

    let out;
    try {
      out = await pythonAI(text, prev);
    } catch (e) {
      FAIL("ai", e);
      rt.counters.errors++;
      out = {
        reply:
          "G. Thori technical issue hai. Please 0327-7450361 par call kar lein ya thori der baad try karein.",
        state: prev,
      };
    }

    const reply = out && out.reply ? String(out.reply) : "";
    states.set(jid, (out && out.state) || prev);

    if (reply.trim()) {
      await s.sendMessage(jid, { text: reply });
      rt.counters.replied++;
      LOG("msg", `replied -> ${jid} :: ${reply.slice(0, 70).replace(/\n/g, " ")}`);
    } else {
      rt.counters.skipped++;
      LOG("msg", `AI returned empty reply (jid=${jid})`);
    }
  } catch (e) {
    FAIL("handler", e);
    rt.counters.errors++;
  }
}

/* ------------------------------------------------------------------ *
 * SOCKET WIRING
 * ------------------------------------------------------------------ */
let sock = null;
let starting = false;
let reconnectTimer = null;

/** Single reconnect scheduler - prevents double startSock() from the close
 *  handler AND the watchdog firing at the same time. */
function scheduleReconnect(reason, delayMs) {
  if (reconnectTimer) {
    LOG("conn", `reconnect already scheduled (${reason}) - keeping existing timer`);
    return;
  }
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    startSock(reason);
  }, delayMs);
  if (reconnectTimer.unref) reconnectTimer.unref();
  LOG("conn", `reconnect scheduled in ${delayMs}ms (${reason})`);
}

function wire(s, saveCreds) {
  s.ev.on("creds.update", async () => {
    try {
      await saveCreds();
      LOG("auth", "creds saved to disk");
    } catch (e) {
      FAIL("creds", e);
    }
  });

  s.ev.on("connection.update", (update) => {
    rt.lastEventAt = Date.now();
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      rt.lastQr = qr;
      rt.lastQrIssuedAt = Date.now();
      rt.connection = "qr";
      LOG("conn", "QR issued - scan with WhatsApp (Linked Devices) on 03277450361");
      try {
        fs.writeFileSync(path.join(AUTH_DIR, "last_qr.txt"), qr, "utf8");
      } catch (e) {
        FAIL("qr", e);
      }
      qrcode.generate(qr, { small: true });
      LOG("conn", `raw QR also available at http://localhost:${PORT}/qr`);
    }

    if (connection) rt.connection = connection;

    if (connection === "connecting") LOG("conn", "connecting to WhatsApp Web ...");
    if (connection === "open") {
      rt.connected = true;
      rt.lastAliveAt = Date.now();
      rt.lastError = "";
      LOG("conn", "OPEN - connected to WhatsApp (inbound-only mode active)");
    }

    if (connection === "close") {
      // A socket that has already been replaced must not trigger a reconnect.
      if (s !== sock) {
        LOG("conn", "close from a stale socket - ignored");
        return;
      }
      rt.connected = false;
      const code = lastDisconnect && lastDisconnect.error && lastDisconnect.error.output
        ? lastDisconnect.error.output.statusCode
        : undefined;
      const detail =
        (lastDisconnect && lastDisconnect.error && lastDisconnect.error.message) ||
        (lastDisconnect && lastDisconnect.error && lastDisconnect.error.output
          ? JSON.stringify(lastDisconnect.error.output)
          : "");
      rt.lastError = `closed code=${code} ${detail}`;
      LOG("conn", `CLOSED code=${code} ${detail}`);

      if (code === DisconnectReason.loggedOut) {
        LOG("auth", "logged out (401) - wiping session folder, a fresh QR scan is required");
        try {
          fs.rmSync(AUTH_DIR, { recursive: true, force: true });
        } catch (e) {
          FAIL("auth", e);
        }
        scheduleReconnect("after-logout", 3000);
      } else {
        const wait = Math.min(30000, 3000 * (rt.reconnects + 1));
        rt.reconnects++;
        LOG("conn", `reconnecting in ${wait}ms (attempt ${rt.reconnects})`);
        scheduleReconnect("after-close", wait);
      }
    }
  });

  s.ev.on("messages.upsert", async (ev) => {
    const { messages, type, requestId } = ev || {};
    rt.counters.upsert++;
    rt.lastEventAt = Date.now();
    LOG("msg", `messages.upsert type=${type} count=${(messages || []).length} requestId=${requestId}`);

    if (type !== "notify" && type !== "append") {
      rt.counters.skipped++;
      LOG("msg", `ignored batch (type=${type})`);
      return;
    }

    for (const msg of messages || []) {
      try {
        if (!msg.key) { rt.counters.skipped++; continue; }
        if (msg.message) {
          msgCache.set(msg.key.id, msg.message);
          if (msgCache.size > MSG_CACHE_MAX) msgCache.delete(msgCache.keys().next().value);
        }

        if (msg.key.fromMe) {
          rt.counters.skipped++;
          LOG("msg", `skip fromMe id=${msg.key.id}`);
          continue;
        }
        if (!msg.message) {
          rt.counters.skipped++;
          LOG("msg", `skip: empty payload id=${msg.key.id}`);
          continue;
        }

        const jid = msg.key.remoteJid;
        if (!jid) { rt.counters.skipped++; continue; }
        if (IGNORE_JIDS.indexOf(jid) !== -1) {
          rt.counters.skipped++;
          LOG("msg", `skip ignored jid=${jid}`);
          continue;
        }
        if (jid.endsWith("@g.us") && !ALLOW_GROUPS) {
          rt.counters.skipped++;
          LOG("msg", `skip group=${jid}`);
          continue;
        }

        // ----------------------------------------------------------------
        // Baileys delivers messages that arrived while the device was
        // OFFLINE (Render sleep / dropped socket) with type = "append",
        // not "notify"  ->  process-message.js:1432
        //   upsertMessage(msg, node.attrs.offline ? 'append' : 'notify')
        // Ignoring "append" therefore silently loses every message that
        // arrived while the instance was asleep.
        // To avoid answering ancient history-sync dumps we only reply to
        // offline messages newer than OFFLINE_REPLY_WINDOW_MIN minutes.
        // ----------------------------------------------------------------
        let offline = false;
        if (type === "append") {
          const ts = (msg.messageTimestamp || (msg.key && msg.key.timestamp) || 0);
          const ageMin = ts ? Math.round((Date.now() / 1000 - ts) / 60) : 99999;
          if (ageMin > OFFLINE_REPLY_WINDOW_MIN) {
            rt.counters.skipped++;
            LOG("msg", `skip stale offline message (${ageMin} min old) id=${msg.key.id}`);
            continue;
          }
          offline = true;
          LOG("msg", `offline message picked up (${ageMin} min old) id=${msg.key.id}`);
        }

        // ---- MARK AS READ / SEEN (blue ticks) -------------------------
        try {
          await s.readMessages([msg.key]);
          rt.counters.readReceipts++;
          LOG("msg", `marked READ -> ${jid}`);
        } catch (e) {
          FAIL("read", e);
        }

        const text = extractText(msg.message);
        const voice = isVoice(msg.message);
        rt.counters.notify++;
        rt.lastMessageAt = Date.now();
        LOG(
          "msg",
          `INBOUND ${jid} type=${type} voice=${voice} text="${(text || "").slice(0, 90).replace(/\n/g, " ")}"`
        );

        enqueue(jid, () => handleMessage(s, jid, text, voice));
      } catch (e) {
        FAIL("msg", e);
        rt.counters.errors++;
      }
    }
  });

  s.ev.on("messages.update", (updates) => {
    rt.lastEventAt = Date.now();
    LOG("receipt", `messages.update x${(updates || []).length}`);
  });

  s.ev.on("message-receipt.update", (updates) => {
    rt.lastEventAt = Date.now();
    LOG("receipt", `message-receipt.update x${(updates || []).length}`);
  });

  s.ev.on("groups.update", () => { rt.lastEventAt = Date.now(); });
}

/* ------------------------------------------------------------------ *
 * BOOT / RECONNECT
 * ------------------------------------------------------------------ */
async function startSock(reason) {
  if (starting) return;
  starting = true;
  try {
    if (sock) {
      LOG("conn", `closing previous socket before restart (${reason})`);
      try { sock.end(new Error("restart")); } catch (_) {}
      sock = null;
    }

    inspectAuthDir();
    const version = await resolveVersion();
    const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
    LOG("auth", `session loaded: registered=${!!state.creds.registered} me=${state.creds.me ? state.creds.me.id : "-"}`);

    // Baileys v7 only flips creds.registered to true when the device is paired
    // through a QR/link-code. A session restored from disk therefore keeps
    // registered=false even though it logs in perfectly (the real gate is
    // creds.me). Normalise it so the state we persist back to disk is
    // self-consistent and future Baileys releases agree.
    if (state.creds.me && !state.creds.registered) {
      state.creds.registered = true;
      rt.auth.registered = true;
      try {
        await saveCreds();
        LOG("auth", "creds.registered normalised false -> true (creds.me present)");
      } catch (e) {
        FAIL("auth", e);
      }
    }

    const logger = pino({ level: LOG_LEVEL });
    const newSock = makeWASocket({
      version,
      logger,
      auth: {
        creds: state.creds,
        keys: makeCacheableSignalKeyStore(state.keys, logger),
      },
      printQRInTerminal: false,
      browser: ["Chaudhary Type House", "Chrome", "1.0.0"],
      // --- the two settings that decide whether messages arrive at all ---
      syncFullHistory: true,      // deliver messages that arrived while we were asleep
      markOnlineOnConnect: true, // required for typing indicator + read receipts
      emitOwnEvents: true,
      getMessage: async (key) => (key && msgCache.get(key.id)) || null,
      keepAliveIntervalMs: 30000,
      connectTimeoutMs: 20000,
      retryRequestDelayMs: 250,
      maxMsgRetryCount: 5,
    });

    sock = newSock;
    wire(newSock, saveCreds);
    LOG("boot", `socket created (reason=${reason})`);
  } catch (e) {
    FAIL("boot", e);
    rt.lastError = String((e && e.message) || e);
    rt.counters.errors++;
    setTimeout(() => startSock("retry-after-error"), 5000);
  } finally {
    starting = false;
  }
}

/* ------------------------------------------------------------------ *
 * HTTP SERVER (REQUIRED BY RENDER WEB SERVICES)
 * ------------------------------------------------------------------ */
const server = http.createServer((req, res) => {
  const url = (req.url || "/").split("?")[0];

  if (url === "/qr") {
    if (!rt.lastQr) {
      res.writeHead(404, { "content-type": "text/plain" });
      res.end("no QR issued yet - check /health");
      return;
    }
    res.writeHead(200, { "content-type": "text/plain" });
    res.end(rt.lastQr);
    return;
  }

  if (url === "/" || url === "/health") {
    rt.uptimeSec = Math.round((Date.now() - BOOT) / 1000);
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ ok: true, ...rt }, null, 2));
    return;
  }

  res.writeHead(404, { "content-type": "text/plain" });
  res.end("not found");
});

server.on("error", (e) => FAIL("http", e));
server.listen(PORT, HOST, () => {
  LOG("http", `health server listening on ${HOST}:${PORT}  ->  /health  /qr`);
});

/* ------------------------------------------------------------------ *
 * WATCHDOG + HEARTBEAT (survives Render sleep / dead WebSocket)
 * ------------------------------------------------------------------ */
setInterval(() => {
  rt.uptimeSec = Math.round((Date.now() - BOOT) / 1000);
  if (!sock) return;
  // sock.ws is Baileys' own WebSocketClient wrapper - it exposes isOpen /
  // isClosed getters, NOT a raw ws.readyState number.
  const wsOpen = sock.ws && typeof sock.ws.isOpen === "boolean" ? sock.ws.isOpen : null;
  const wsClosed = sock.ws && typeof sock.ws.isClosed === "boolean" ? sock.ws.isClosed : null;
  if (wsOpen === false || wsClosed === true) {
    LOG("watch", `websocket not OPEN (isOpen=${wsOpen} isClosed=${wsClosed}) - forcing reconnect`);
    try { sock.end(new Error("stale socket")); } catch (_) {}
    scheduleReconnect("watchdog", 2000);
    return;
  }
  // Liveness is proven by the 60s heartbeat (see below), not by message
  // traffic, so a quiet chat never causes a needless reconnect.
  if (rt.lastAliveAt && Date.now() - rt.lastAliveAt > STALE_MS) {
    LOG("watch", `no successful heartbeat for ${Math.round((Date.now() - rt.lastAliveAt) / 1000)}s - forcing reconnect`);
    try { sock.end(new Error("stale connection")); } catch (_) {}
    scheduleReconnect("watchdog-stale", 2000);
  }
}, HEARTBEAT_MS);

// Heartbeat: proves the socket is alive even when no messages arrive.
setInterval(() => {
  if (!sock || !rt.connected) return;
  try {
    sock.sendPresenceUpdate("available").then(() => {
      rt.lastAliveAt = Date.now();
    }).catch((e) => {
      rt.lastAliveAt = 0;
      FAIL("heartbeat", e);
    });
  } catch (e) {
    rt.lastAliveAt = 0;
    FAIL("heartbeat", e);
  }
}, 60000);

process.on("uncaughtException", (e) => {
  FAIL("uncaught", e);
  rt.counters.errors++;
});
process.on("unhandledRejection", (e) => {
  FAIL("unhandled", e);
  rt.counters.errors++;
});

/* ------------------------------------------------------------------ *
 * GO
 * ------------------------------------------------------------------ */
LOG("boot", `node=${process.version} pid=${process.pid} cwd=${process.cwd()}`);
LOG("boot", `AUTH_DIR=${AUTH_DIR} PORT=${PORT} PYTHON=${PYTHON}`);
startSock("initial-start");
