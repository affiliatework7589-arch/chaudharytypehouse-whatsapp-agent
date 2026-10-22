# Deployment Guide — Chaudhary Type House & Property Advisors

Zero paid APIs · Fully local AI · Inbound-only WhatsApp agent

---

## 0. TL;DR — why messages were not marked read / not answered

| # | Root cause | Where | Fix applied |
|---|---|---|---|
| 1 | **Render free tier has no Background Workers** — only Web Services. A web service that does not bind `$PORT` is marked unhealthy and the container is restarted in a loop, so the WhatsApp socket never survived. | `render.yaml` was `type: worker` | `render.yaml` is now `type: web` + `healthCheckPath: /health`; the bridge now runs a tiny HTTP server on `$PORT` |
| 2 | **`readMessages()` was never called** → WhatsApp never sent the read receipt → messages stayed unread in the sender's chat. | `whatsapp_bridge.js` | `await sock.readMessages([msg.key])` on every inbound message |
| 3 | **`markOnlineOnConnect: false`** → the linked device never announced "available", so presence/typing indicator and read receipts were not delivered. | `whatsapp_bridge.js` | now `true` (Baileys default) |
| 4 | **`syncFullHistory: false`** → anything that arrived while the Render instance was asleep was never delivered. | `whatsapp_bridge.js` | now `true` |
| 5 | **`fetchLatestBaileysVersion()` fetches from raw.githubusercontent.com** — if that call failed the process exited and Render restarted it → re-auth loop. | `whatsapp_bridge.js` | pinned fallback version `[2,3000,1043857760]` + try/catch |
| 6 | **Reconnect leaked sockets** — `startSock()` was called again without closing the old socket. | `whatsapp_bridge.js` | old socket is ended first, backoff reconnect, single module-level socket |
| 7 | **401 / logged-out was not handled** → stale creds kept looping. | `whatsapp_bridge.js` | on `loggedOut` the session folder is wiped so a fresh QR is issued |
| 8 | **No visibility** — the old code logged almost nothing. | `whatsapp_bridge.js` | timestamped `LOG`/`FAIL` traces + `/health` + `/qr` + `/qr` file |
| 9 | **Free tier 15-minute sleep** kills the WebSocket. | Render | `/health` endpoint + external pinger (UptimeRobot) every 5 min + in-process watchdog |

---

## 1. Project structure (what gets deployed)

```
Chaudhary Type House/
├── whatsapp_bridge.js          # Node/Baileys bridge  <- the deployed process
├── whatsapp_ai.py              # Python CLI shim -> core/ai_engine.smart_reply(channel="whatsapp")
├── core/
│   ├── ai_engine.py            # bilingual rule engine + strict persona + relevance filter
│   ├── db.py                   # local SQLite (leads / conversations)
│   └── __init__.py
├── config.py                   # business data, phone, address, timings, calculator URL
├── package.json                # "start": "node whatsapp_bridge.js"
├── package-lock.json
├── requirements-bridge.txt     # ONLY what the bridge needs (requests)
├── Dockerfile                  # node:20-slim + python3 (cloud image)
├── render.yaml                 # Render Blueprint (Web Service + Docker)
├── .dockerignore
├── .gitignore
└── index.html                  # public website (served separately / statically)
```

`auth_info_baileys/` is **created at runtime** and is intentionally **not** committed.
It holds the WhatsApp session — treat it exactly like a password.

> **Do not upload `auth_info_baileys` to GitHub.** A session file committed to a
> public repo is a credential leak, and Render's filesystem is ephemeral anyway.
> Use a Render **persistent disk** (paid plan) or re-scan the QR after a deploy
> (free plan). The session folder must contain `creds.json`
> (`"registered": true`, `"me": {...}`) plus `pre-keys-*.json`,
> `session-*.json`, `app-state-sync-key-*.json`.

---

## 2. Git initialization & GitHub linking

The local repo is already initialised and committed. To push to GitHub:

```bash
cd "C:\Users\Fast Computers\Desktop\Chaudhary Type House"

# 1. Create an EMPTY repo on GitHub first (no README/.gitignore auto-create).
#    https://github.com/new  ->  name: chaudhary-type-house

# 2. Link the remote (replace YOUR_USER with your GitHub username)
git remote add origin https://github.com/YOUR_USER/chaudhary-type-house.git

# 3. Set the branch + push
git branch -M main
git add .
git commit -m "Deploy: WhatsApp AI bridge + Render config"
git push -u origin main
```

If the remote already exists (or you prefer SSH):

```bash
git remote set-url origin https://github.com/YOUR_USER/chaudhary-type-house.git
# or: git remote set-url origin git@github.com:YOUR_USER/chaudhary-type-house.git
```

Verify:

```bash
git remote -v
git status
```

---

## 3. Deploy to Render

### Option A — Blueprint (recommended, automated)

1. Push to GitHub (section 2).
2. Render: **New → Blueprint** → select `chaudhary-type-house` → Render reads `render.yaml`.
3. Auto-created settings:
   - Type: **Web Service** (NOT worker — workers are paid-only)
   - Runtime: **Docker** (uses `Dockerfile`)
   - Start: `npm start`
   - Health check path: `/health`
   - Plan: `free`
4. Click **Apply** → open **Logs**.

### Option B — Manual

1. Render → **New → Web Service** → connect the GitHub repo.
2. Environment: **Docker**; Dockerfile path `./Dockerfile`; Context `.`.
3. Environment Variables:
   | Key | Value |
   |---|---|
   | `PYTHON` | `python3` |
   | `WA_AUTH_DIR` | `/app/auth_info_baileys` |
   | `PYTHONIOENCODING` | `utf-8` |
   | `LOG_LEVEL` | `info` |
   | `TYPING_MIN_MS` / `TYPING_MAX_MS` | `5000` / `10000` |
4. Health check path: `/health`.
5. *(Paid plan only)* **Disks** tab → mount a 1 GB disk at `/app/auth_info_baileys`.
6. **Create & Deploy** → open **Logs** → QR code appears.

### Link the number (one-time, from Render logs)

1. Open the **Logs** panel in Render.
2. Copy the QR code (or open `https://<your-service>.onrender.com/qr` for the raw string).
3. On the phone with **03277450361**:
   WhatsApp → **Settings → Linked Devices → Link a Device** → scan the QR.
4. The log prints `OPEN - connected to WhatsApp (inbound-only mode active)`.
5. The session is written to `auth_info_baileys/` → survives restarts (with a disk).

> If the session is ever invalidated (phone unlinks the device), the bridge detects
> status **401**, wipes the session folder and prints a fresh QR automatically.

---

## 4. Render free-tier lifecycle (read this, it is the #1 cause of "no replies")

- Render's **free** tier sleeps a web service after **15 minutes of inactivity**.
  "Inactive" = no inbound HTTP request. While asleep the process is frozen and the
  WhatsApp WebSocket is silently dead — WhatsApp will not deliver anything, and
  nothing in the log will explain it.
- **Fix A (must do):** point an external pinger at `https://<service>.onrender.com/health`
  every 5 minutes. Free options: UptimeRobot, cron-job.org, or a GitHub Actions
  `schedule` job that curls the URL. Every ping also resets Render's sleep timer.
- **Fix B (built in):** the bridge exposes `/health` and `/qr`, and an in-process
  watchdog restarts a dead WebSocket (`watchdog` / `watchdog-stale` log lines).
- **Fix C:** `syncFullHistory: true` means messages that arrived while the instance
  was asleep are delivered after wake-up.
- **Free tier has no persistent disk.** After a *new deploy* the session is gone and
  a fresh QR is needed. A paid plan + disk removes this step.

---

## 5. Diagnostics — read the exact error trace

### 5.1 From the Render log

Every line is timestamped and tagged:

```
[2026-10-22 07:49:10][+    0s] auth       dir=/app/auth_info_baileys exists=true writable=true creds.json=true registered=true me=923277450361@s.whatsapp.net files=14
[2026-10-22 07:49:10][+    0s] http       health server listening on 0.0.0.0:10000  ->  /health  /qr
[2026-10-22 07:49:10][+    0s] wa         WhatsApp Web version 2.3000.1043857760 (fetched)
[2026-10-22 07:49:10][+    0s] conn       connecting to WhatsApp Web ...
[2026-10-22 07:49:11][+    1s] conn       QR issued - scan with WhatsApp (Linked Devices) on 03277450361
[2026-10-22 07:49:12][+    2s] conn       OPEN - connected to WhatsApp (inbound-only mode active)
[2026-10-22 08:01:44][+ 754s] msg        messages.upsert type=notify count=1 requestId=...
[2026-10-22 08:01:44][+ 754s] msg        marked READ -> 923277450361@s.whatsapp.net
[2026-10-22 08:01:44][+ 754s] msg        INBOUND 923277450361@s.whatsapp.net voice=false text="Registry ka kharcha kitna hoga?"
[2026-10-22 08:01:49][+ 759s] msg        typing indicator on for 7000ms (jid=...)
[2026-10-22 08:01:56][+ 766s] msg        replied -> ... :: G. 🧮 Registry ki poori kharcha ...
```

### 5.2 From the health endpoint

```bash
curl https://<your-service>.onrender.com/health
```

```json
{
  "ok": true,
  "connected": true,
  "connection": "open",
  "waVersion": "2.3000.1043857760",
  "lastError": "",
  "reconnects": 0,
  "counters": { "upsert": 12, "notify": 12, "skipped": 0, "replied": 12, "readReceipts": 12, "errors": 0 },
  "auth": { "dir": "/app/auth_info_baileys", "writable": true, "credsFile": true, "registered": true, "me": "923277450361@s.whatsapp.net", "fileCount": 14 }
}
```

**How to read it:**

| Symptom in `/health` | Meaning | Fix |
|---|---|---|
| `auth.writable = false` | the disk is not mounted / wrong `WA_AUTH_DIR` | attach the disk at exactly `$WA_AUTH_DIR` |
| `auth.registered = false` | no valid session → QR needed | scan the QR from the log or `/qr` |
| `connection = "qr"` | still waiting for the scan | scan it |
| `counters.upsert = 0` but you messaged the bot | the socket is asleep (Render free tier) | add the pinger; check `lastEventAt` |
| `counters.skipped` rising, `replied = 0` | messages are being filtered out | read the `skip ...` log lines |
| `counters.readReceipts = 0` | `readMessages()` failing | check the `read` error lines |
| `lastError` non-empty | last socket failure | the error is printed in full in `conn` lines |

### 5.3 Fetch the QR without scrolling the log

```bash
curl https://<your-service>.onrender.com/qr
```

It is also written to `auth_info_baileys/last_qr.txt` on disk.

---

## 6. Run locally (Windows)

```powershell
cd "C:\Users\Fast Computers\Desktop\Chaudhary Type House"
npm install                 # first time only
npm start                   # or: node whatsapp_bridge.js
```

- First run prints the QR in the terminal → scan from WhatsApp on 03277450361.
- Session persists in `./auth_info_baileys` → no repeat scans.
- Local health check: `http://localhost:3000/health` (set `$env:PORT` to change).
- Stop with `Ctrl+C`.

---

## 7. Behaviour guarantees (implemented in code)

| Requirement | Where |
|---|---|
| Inbound-only (never initiates a message/call) | `messages.upsert` handler ignores `msg.key.fromMe`, groups (`@g.us`) and `status@broadcast`; nothing else calls `sendMessage` |
| Marked as read / seen (blue ticks) | `await sock.readMessages([msg.key])` |
| Human-like typing delay 5–10 s | `typingDelay()` + `sendPresenceUpdate("composing" → "paused")` |
| Strict relevance filter | `core/ai_engine.py` → `respond()` strict mode (`channel != "website"`) |
| Exact rejection line | `"G. Hum sirf property aur registry ki services provide karte hain. Allah Hafiz."` |
| Every business reply starts with `G.` | strict prefix applied in `respond()` |
| No `bhai jaan` / `bhan` / `sir` / `dear` | professional templates only |
| chtype.online rates | `config.CALCULATOR_URL` → `https://chtype.online` |
| Office CTA | Baldia Chowk, Infront of City Police Station (A) Division, Chishtian (8:00 AM – 8:00 PM) |
| Voice notes | polite "please type" reply (no paid STT) |
| Local-only privacy | no third-party logging; AI runs on the same machine; session folder is local |

---

## 8. Verification (run before/after any change)

```powershell
$env:PYTHONIOENCODING="utf-8"
python check_purity.py   # -> RESULT: ALL CHECKS PASSED          (exit 0)
python selftest.py       # -> RESULT: ALL CHECKS PASSED — 100% free, zero paid APIs. (exit 0)
node --check whatsapp_bridge.js   # -> exit 0
```

Both suites are green at all times and are **not** modified by deployment work.
