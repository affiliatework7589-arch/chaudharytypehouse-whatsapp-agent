// whatsapp_bridge.js — Chaudhary Type House & Property Advisors
// WhatsApp AI Agent Bridge (Baileys) — inbound-only, human-like typing, lifetime session.
//
// Start:  node whatsapp_bridge.js
// First run prints a QR code in the terminal — scan with WhatsApp on 03277450361.
// Session is persisted in ./auth_info_baileys (no repeated QR scans).

const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
  makeCacheableSignalKeyStore,
} = require("@whiskeysockets/baileys");
const qrcode = require("qrcode-terminal");
const { spawn } = require("child_process");
const path = require("path");

// Session folder — override with WA_AUTH_DIR for cloud persistent disks.
const AUTH_DIR = process.env.WA_AUTH_DIR || path.join(__dirname, "auth_info_baileys");
const PYTHON = process.env.PYTHON || "python";
const AI_SCRIPT = path.join(__dirname, "whatsapp_ai.py");

// Per-contact conversation state (in-memory; survives for the process lifetime).
const states = new Map();

function pythonAI(message, state) {
  return new Promise((resolve, reject) => {
    const child = spawn(PYTHON, [AI_SCRIPT], {
      cwd: __dirname,
      env: { ...process.env, PYTHONIOENCODING: "utf-8" },
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (d) => (stdout += d.toString("utf8")));
    child.stderr.on("data", (d) => (stderr += d.toString("utf8")));
    child.on("error", (e) => reject(e));
    child.on("close", (code) => {
      if (code !== 0) {
        reject(new Error(`python exited ${code}: ${stderr.slice(0, 400)}`));
        return;
      }
      try {
        resolve(JSON.parse(stdout));
      } catch (e) {
        reject(new Error(`bad json: ${stdout.slice(0, 400)}`));
      }
    });
    const payload = JSON.stringify({ message, state: state || {} });
    child.stdin.write(payload);
    child.stdin.end();
  });
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function randomDelay() {
  // 5 to 10 seconds, human-like
  return 5000 + Math.floor(Math.random() * 5001);
}

async function startSock() {
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
  const { version } = await fetchLatestBaileysVersion();
  const sock = makeWASocket({
    version,
    auth: {
      creds: state.creds,
      keys: makeCacheableSignalKeyStore(state.keys, console),
    },
    printQRInTerminal: false,
    browser: ["Chaudhary Type House", "Chrome", "1.0.0"],
    syncFullHistory: false,
    markOnlineOnConnect: false,
  });

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", (update) => {
    const { connection, lastDisconnect, qr } = update;
    if (qr) {
      console.log("\n=== SCAN THIS QR WITH WHATSAPP (03277450361) ===");
      qrcode.generate(qr, { small: true });
      console.log("=================================================\n");
    }
    if (connection === "close") {
      const code = lastDisconnect?.error?.output?.statusCode;
      const shouldReconnect = code !== DisconnectReason.loggedOut;
      console.log("Connection closed. code=", code, "reconnect=", shouldReconnect);
      if (shouldReconnect) {
        setTimeout(startSock, 3000);
      } else {
        console.log("Logged out. Delete auth_info_baileys and restart to re-link.");
      }
    } else if (connection === "open") {
      console.log("✅ WhatsApp bridge connected. Inbound-only mode active.");
    }
  });

  // INBOUND-ONLY: only react to messages, never initiate.
  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") return;
    for (const msg of messages) {
      try {
        if (!msg.message || msg.key.fromMe) continue; // ignore own/outgoing
        const jid = msg.key.remoteJid;
        if (!jid || jid.endsWith("@g.us")) continue; // skip groups (optional safety)
        // skip status broadcasts
        if (jid === "status@broadcast") continue;

        // Extract text
        const m = msg.message;
        let text = "";
        if (m.conversation) text = m.conversation;
        else if (m.extendedTextMessage?.text) text = m.extendedTextMessage.text;
        else if (m.imageMessage?.caption) text = m.imageMessage.caption;
        else if (m.videoMessage?.caption) text = m.videoMessage.caption;
        else if (m.audioMessage) text = ""; // voice note -> ask to type

        const isVoice = !!m.audioMessage;

        if (isVoice) {
          // simulate human delay then ask to type
          await sock.sendPresenceUpdate("composing", jid);
          await sleep(randomDelay());
          await sock.sendPresenceUpdate("paused", jid);
          await sock.sendMessage(jid, {
            text: "G. Voice message mila. Please text mein likh dein taake main aap ki madad kar sakun. Baldia Chowk office: 0327-7450361.",
          });
          continue;
        }

        if (!text.trim()) continue;

        const prev = states.get(jid) || {};
        // human-like typing delay
        await sock.sendPresenceUpdate("composing", jid);
        await sleep(randomDelay());
        await sock.sendPresenceUpdate("paused", jid);

        let out;
        try {
          out = await pythonAI(text, prev);
        } catch (e) {
          console.error("AI error:", e.message);
          out = {
            reply:
              "G. Thori technical issue hai. Please 0327-7450361 par call kar lein ya thori der baad try karein.",
            state: prev,
          };
        }

        const reply = (out && out.reply) ? String(out.reply) : "";
        const newState = (out && out.state) ? out.state : prev;
        states.set(jid, newState);

        if (reply.trim()) {
          await sock.sendMessage(jid, { text: reply });
        }
      } catch (e) {
        console.error("message handling error:", e);
      }
    }
  });

  return sock;
}

startSock().catch((e) => {
  console.error("Fatal:", e);
  process.exit(1);
});