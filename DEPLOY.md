# Deployment Guide — Chaudhary Type House & Property Advisors

Zero paid APIs · Fully local AI · Inbound-only WhatsApp agent

---

## 1. Project structure (what gets deployed)

```
Chaudhary Type House/
├── whatsapp_bridge.js          # Node/Baileys WhatsApp bridge (the deployed process)
├── whatsapp_ai.py              # Python CLI shim -> core/ai_engine.smart_reply(channel="whatsapp")
├── core/
│   ├── ai_engine.py            # bilingual rule engine + strict persona + relevance filter
│   ├── db.py                   # local SQLite (leads / conversations)
│   └── __init__.py
├── agents/                     # optional local lead agents (not needed in the cloud worker)
├── config.py                   # business data, phone, address, timings, calculator URL
├── package.json                # "start": "node whatsapp_bridge.js"
├── package-lock.json
├── requirements-bridge.txt     # ONLY what the bridge needs (requests)
├── Dockerfile                  # node:20-slim + python3 (cloud image)
├── render.yaml                 # Render Blueprint (background worker + persistent disk)
├── .dockerignore
├── .gitignore
└── index.html                  # public website (served separately / statically)
```

`auth_info_baileys/` is **created at runtime** and is intentionally **not** committed
(it holds the WhatsApp session — treat it like a password).

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

## 3. Deploy to Render (Blueprint / automated)

### Option A — Blueprint (recommended, fully automated)

1. Push to GitHub (section 2).
2. In Render: **New → Blueprint** → select `chaudhary-type-house` → Render reads `render.yaml`.
3. Settings created automatically:
   - Type: **Background Worker**
   - Runtime: **Docker** (uses `Dockerfile`)
   - Build: `docker build`
   - Start: `npm start`
   - Disk: `wa-session` → mounted at `/app/auth_info_baileys` (1 GB, persistent)
4. Click **Apply**. Watch the build log until you see the QR code banner.

### Option B — Manual

1. Render → **New → Background Worker** (requires a paid plan for disks).
2. Connect the GitHub repo.
3. Environment: **Docker**; Dockerfile path `./Dockerfile`; Context `.`.
4. Add a **Disk**: name `wa-session`, mount `/app/auth_info_baileys`, size 1 GB.
5. Environment Variables:
   | Key | Value |
   |---|---|
   | `PYTHON` | `python3` |
   | `WA_AUTH_DIR` | `/app/auth_info_baileys` |
   | `PYTHONIOENCODING` | `utf-8` |
6. **Create & Deploy** → open **Logs** → QR code appears.

### Link the number (one-time, from Render logs)

1. Open the worker **Logs** panel in Render.
2. Copy the QR code (or open the raw `qr` string from the log).
3. On the phone with **03277450361**:
   WhatsApp → **Settings → Linked Devices → Link a Device** → scan the QR.
4. The bridge prints `✅ WhatsApp bridge connected. Inbound-only mode active.`
5. The session is written to the disk → **survives restarts & redeploys**.

> If the session is ever invalidated (phone unlinks), delete the disk contents
> (or delete `auth_info_baileys/` locally) and re-scan the QR.

---

## 4. Run locally (Windows)

```powershell
cd "C:\Users\Fast Computers\Desktop\Chaudhary Type House"
npm install                 # first time only
npm start                   # or: node whatsapp_bridge.js
```

- First run prints the QR in the terminal → scan from WhatsApp on 03277450361.
- Session persists in `./auth_info_baileys` → no repeat scans.
- Stop with `Ctrl+C`.

---

## 5. Behaviour guarantees (implemented in code)

| Requirement | Where |
|---|---|
| Inbound-only (never initiates a message/call) | `whatsapp_bridge.js` → `messages.upsert` handler ignores `msg.key.fromMe`, groups (`@g.us`) and `status@broadcast` |
| Human-like typing delay 5–10 s | `randomDelay()` + `sendPresenceUpdate("composing" → "paused")` |
| Strict relevance filter | `core/ai_engine.py` → `respond()` strict mode (`channel != "website"`) |
| Exact rejection line | `"G. Hum sirf property aur registry ki services provide karte hain. Allah Hafiz."` |
| Every business reply starts with `G.` | strict prefix applied in `respond()` |
| No `bhai jaan` / `bhan` / `sir` / `dear` | professional templates only |
| chtype.online rates | `config.CALCULATOR_URL` → `https://chtype.online` |
| Office CTA | Baldia Chowk, Infront of City Police Station (A) Division, Chishtian (8:00 AM – 8:00 PM) |
| Voice notes | polite "please type" reply (no paid STT) |
| Local-only privacy | no third-party logging; AI runs on the same machine; session folder is local |

---

## 6. Verification (run before/after any change)

```powershell
$env:PYTHONIOENCODING="utf-8"
python check_purity.py   # -> RESULT: ALL CHECKS PASSED          (exit 0)
python selftest.py       # -> RESULT: ALL CHECKS PASSED — 100% free, zero paid APIs. (exit 0)
```

Both suites are green at all times and are **not** modified by deployment work.
