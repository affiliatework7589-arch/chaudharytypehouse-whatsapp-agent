# Chaudhary Type House & Property Advisors — Chishtian
## 100% FREE · Zero-Investment · Instant-Run Web Interface + Local Multi-Agent Automation

> **Owner:** Chaudhary Muhammad Sanaullah
> **Address:** Near Baldia Chowk, City Chishtian
> **Timing:** Subah 8:00 AM se Shaam 8:00 PM tak
> **Phone & WhatsApp:** 0327-7450361 — https://wa.me/923277450361
> **FREE Registry Kharcha Calculator:** https://chtype.online

---

## 🚀 START IN ONE CLICK

**Windows** → double-click **`run.bat`**
**macOS / Linux** → in terminal: `chmod +x run.sh && ./run.sh`

The script creates a virtual environment, installs only **free open-source**
packages, downloads the free Playwright Chromium (one time), and launches:

| URL | What |
|---|---|
| `http://127.0.0.1:8000/` | Public website — 5 views, strict English / اردو switch |
| `http://127.0.0.1:8000/dashboard` | Admin control panel (5 agents) |

---

## 🌐 The public website (`index.html`)

A clean, uncluttered **5-view site** with 3D buttons and smooth animations:

| View | Contents |
|---|---|
| **Welcome** | Hero + office-at-a-glance + three trust reasons. No clutter, no external links. |
| **Our Services** | 7 animated sub-tabs, each with *What it is · Required Documents · Step-by-step process*, ending in one **Contact Us Now** button that routes to Contact. |
| **Our Office** | Founder & CEO profiles, address, timings, plus *Visit Our Location* (Google Maps, new tab) and *Contact Us*. |
| **Contact Us** | Direct number, address, timings and the green **Contact on WhatsApp** button (new tab). |
| **Privacy Policy** | 8 numbered sections: data collected, usage, document security, ethical dealing, access, storage, your rights, contact. |

**Strict language switch.** A 3D `English | اردو` toggle sits at the far end of the
navbar. English mode is `dir="ltr"` with 100% English; Urdu mode is `dir="rtl"`
with 100% Urdu in **Noto Nastaliq Urdu**. This is guaranteed *structurally*, not
by discipline: every string lives in one `{en, ur}` dictionary and the views
render from it, so a string cannot leak across modes. `check_purity.py` proves
it by walking every rendered text node in both languages.

> The services page contains **no WhatsApp link and no external URL at all** —
> the only outbound links on the whole site are the WhatsApp button (Contact
> page) and the Google Maps button (Office page).

### Floating AI Property Advisor

A minimal 3D pill sits in the bottom corner (bottom-**left** in Urdu mode, so it
mirrors correctly). It is **closed by default** — one unobtrusive pill that never
clutters the page. Clicking it opens a small chat that answers in the **currently
selected site language**, no matter which language you type in:

* in English mode → **pure English** answers, even if you type Urdu
* in Urdu mode → **pure Urdu script**, even if you type English

It guides visitors through all seven services (registry, expense calculation,
mutation, fard/muawin, property dealing, NADRA, domicile & photostat). Every
answer is **2–3 crisp sentences**: the direct answer first, then a push to visit
the office near Baldia Chowk or WhatsApp **0327-7450361** (8:00 AM–8:00 PM), then
a **Contact Us / WhatsApp →** button inside the bubble that routes internally to
`#/contact`. The answers always name the shop, the address and the number, so
every reply is a lead.

**The logic is 100% self-contained in the page** — no fetch, no WebSocket and no
API on the answer path. Both the **Send button** and the **Enter key** append the
message bubble and render the reply synchronously (measured 1–4 ms), so the widget
behaves identically whether `index.html` is served by `app.py`, uploaded to public
hosting, or opened straight from disk.

The one optional network call is a **fire-and-forget lead note to `/api/chat`**.
It runs *only* on localhost, *after* the answer is already on screen, is never
awaited, and is wrapped in `try/catch` + `.catch()` + a 2 s abort timer — so it
can never block, hang or break the chat. It records the inquiry in the local
dashboard so you can see which topics visitors are asking about. Greetings and
"thank you" are deliberately not logged.

> **Uploading to public hosting?** Everything works as-is. The Nastaliq font is
> loaded automatically on localhost; elsewhere no font request is made at all, so
> there is nothing that can 404. Urdu then uses the visitor's system Nastaliq font.
> If you also upload the font file, set one line near the top of the script:
> `const SITE_FONT_URL = "fonts/NotoNastaliqUrdu-Regular.ttf";`

### Verifying the site

```bash
python check_purity.py     # needs app.py running; audits both languages in a real browser
python selftest.py         # audits the automation engines
```

> `index.html` also works **completely standalone** — just double-click it.
> The AI assistant then uses its built-in JavaScript brain (same knowledge,
> same behaviour, zero setup, zero cost).

---

## 💸 THE ZERO-COST PROMISE (strictly enforced)

| Not used | Used instead |
|---|---|
| ❌ WhatsApp Cloud API | ✅ Real `web.whatsapp.com` in a persistent local browser |
| ❌ Meta Graph API | ✅ Real `instagram.com` / `facebook.com` in the browser |
| ❌ TikTok Developer API | ✅ Real `tiktok.com` in the browser |
| ❌ Paid webhooks / SaaS | ✅ FastAPI + SQLite, running on your own PC |
| ❌ Paid AI / API key | ✅ Built-in offline bilingual rule engine (optional free Gemini) |
| ❌ Paid TTS | ✅ Microsoft **edge-tts** (free neural voice, no key, no signup) |
| ❌ Paid video/cloud render | ✅ **Pillow** + **FFmpeg** (free binary via `imageio-ffmpeg`) |
| ❌ Docker / cloud / approval | ✅ One script, runs instantly |
| ❌ Paid Urdu typesetting | ✅ **Noto Nastaliq Urdu** (SIL OFL, free) + browser shaping |

Login happens **once** (QR scan in a normal browser window) and is stored in
`data/browser_profiles/<platform>/` — forever.

---

## ✅ Built-in self-test

Run `python selftest.py` any time. It exercises all 7 subsystems end-to-end
(config → database → AI → content → media → browser → agents) and prints a
pass/fail line for each. It even renders a real MP4 with a real voice-over.

---

## 🖼️ Urdu graphics that actually look right

Generating Urdu inside images is genuinely hard: Pillow only shapes Arabic when
built with **libraqm**, which the default Windows wheel is not. This system
handles all three cases automatically:

1. **Playwright available (normal case)** → the Urdu banner is rendered by a
   real browser engine (HarfBuzz) using **Noto Nastaliq Urdu**, giving real,
   beautiful Nastaliq. The browser renderer automatically falls back from the
   modern *headless-shell* build → full Chromium → a visible window, so it works
   on every Playwright installation.
2. **No browser** → `arabic-reshaper` + `python-bidi` (both pure Python, free)
   shape the text and a font with full *Presentation Forms* coverage is chosen
   automatically (Segoe UI on Windows) — correct joining, Naskh style.
3. **Neither** → the banner quietly switches to Roman Urdu instead of shipping
   broken text, and the dashboard says so.

Roman-Urdu banners never need any of this — they render directly with Pillow.

---

## 📁 What gets built

```
Chaudhary Type House/
├── index.html            Public website — 5 views, strict English / اردو switch
├── dashboard.html        Admin control panel
├── app.py                FastAPI server + every REST endpoint
├── selftest.py           One command that verifies all 7 subsystems
├── check_purity.py       Audits the website's language purity + link safety
├── config.py             All business details, theme, platforms, fonts
├── core/
│   ├── db.py             SQLite leads / appointments / content / jobs / logs / KV
│   ├── ai_engine.py      Bilingual (Roman Urdu + Urdu) brain + optional Gemini
│   ├── content.py        Instagram / Facebook / TikTok / WhatsApp content factory
│   ├── media.py          Pillow auto-poster + browser Nastaliq + FFmpeg video
│   ├── fonts.py          Free Noto Nastaliq + Arabic shaping / font detection
│   └── browser.py        Playwright persistent-session manager (the zero-API core)
├── agents/
│   ├── base.py           Threading, kill switch, de-duplication
│   ├── agent1_leads.py   Website & Lead Manager
│   ├── agent2_whatsapp.py WhatsApp Web free auto-responder
│   ├── agent3_instagram.py Instagram content + DM agent
│   ├── agent4_facebook.py Facebook post + comment/inbox agent
│   └── agent5_tiktok.py  TikTok viral script + video maker + inbox agent
├── requirements.txt
├── run.bat / run.sh
└── data/                 (auto-created) leads.db, media/, fonts/, browser_profiles/
```

---

## 🤖 The 5 Agents

### Agent 1 — Website & Lead Manager
* Every website inquiry + visit booking → **SQLite** (and a live **CSV** mirror at `data/exports/leads.csv`)
* Scores each lead 0–100 and tags it **🔥 HOT / 🙂 WARM / ❄️ COLD** using name, phone, visit-time, service value and urgency words
* Produces the next "call back now" list shown on the dashboard
* Needs **no browser** — works instantly, even before you scan any QR

### Agent 2 — WhatsApp Web Free Auto-Responder
* Persistent `web.whatsapp.com` profile (scan QR once)
* Finds unread chats, reads the newest incoming message, replies in **Roman Urdu or Urdu** — whichever the customer used
* Multi-turn capture: **Name → Service → Preferred visit time → booking**, then a summary + WhatsApp handoff
* Records every inquiry as a lead
* Fees questions are answered with the **chtype.online** calculator link

### Agent 3 — Instagram Free Content & DM Agent
* Designs a **1080×1080 banner with Pillow** (emerald & gold house style) — no Canva, no paid template
* Writes a Roman-Urdu/Urdu caption + **15 Chishtian real-estate SEO hashtags**
* Uploads it through the logged-in `instagram.com` browser session
* Replies to unread DMs with the same bilingual brain

### Agent 4 — Facebook Page Free Post & Comment/Inbox Agent
* Generates long-form **educational posts** (Registry vs Mutation, Bay Nama, Fard verification, Wirasat, Domicile, property buying checklist)
* Publishes via the browser composer
* Auto-replies to comments and Messenger/inbox threads, always surfacing
  `0327-7450361` and `https://chtype.online`

### Agent 5 — TikTok Viral Script, Video Maker & Inbox Agent
* Writes **45-second viral scripts** with a 3-second hook, timed beats and a CTA
* Speaks them with **free edge-tts** (Urdu / Hindi neural voices)
* Uses edge-tts **word-boundary timings** to render a karaoke-style caption
  overlay that is perfectly in sync with the voice
* Encodes a real **1080×1920 H.264 MP4** with Pillow → FFmpeg (plus cover image)
* If the internet is down it still produces a captions-only MP4 — always uploadable
* Replies to TikTok web messages through the browser

---

## 🧠 The AI Assistant (works with or without the server)

* Understands **Roman Urdu** (`"registry kaise hota hai?"`) and **Urdu** (`"رجسٹری کیسے ہوتی ہے؟"`) and always replies in the **same language**
* Topics: Registry, Complete File, Fard, Bai Nama, Inteqal (wirasat + khareed-o-farokht), Arazi Muawin (ajra / hasool / zamanat), Property Dealing, NADRA e-Sahulat, Domicile, Online Apply, Photostat, timings, address, fees
* Fee/kharcha questions are routed to **https://chtype.online**
* Every turn shows a **live WhatsApp button** that pre-fills the customer's
  own question into `https://wa.me/923277450361?text=…` — so leads reach you
  at zero cost
* Runs on the built-in rule engine **offline**; if you optionally paste a free
  Google AI Studio key into `config.py` (`GEMINI_API_KEY`), `gemini-2.5-flash`
  blends in for richer answers — but it is **never required**

---

## 🛑 Safety controls

| Control | Where |
|---|---|
| **Emergency Kill Switch** (red button, dashboard header) | Stops every send instantly by creating `data/AGENTS_PAUSED` |
| **Master Auto-Send** toggle | Turns sending on/off for all 5 agents at once |
| **Per-agent Auto-Send toggle** | Each agent card has its own switch |
| **Run Once** button | Run a single tick on demand, without a loop |
| **Message de-duplication** | `kv` store — the same message is never answered twice |
| **Politeness delay** | ~1.5–2 s between chats, visible headed browser |

---

## 🧪 First-time checklist

1. `run.bat` → wait for the server banner.
2. Open **Dashboard** → **5 Agents** → confirm all five are *running*.
3. Go to **Browser & QR Login** → press **Start Browser** for WhatsApp →
   scan the QR in the visible window → status flips to **LOGGED IN**.
   Repeat for Instagram, Facebook, TikTok.
4. **Content Factory** → choose platform → **Generate Content** → a banner and
   caption appear instantly (download or let Agent 3/4 auto-post).
5. **Video Maker** → pick a topic → **Render** → a free MP4 appears with a
   download button.
6. **Leads** → send yourself a WhatsApp message, or fill the website form →
   the lead appears live with a score.

---

## ❓ Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError` | Run `run.bat` again — it installs everything |
| Browser window says "Chromium install nahi hua" | `.\.venv\Scripts\python.exe -m playwright install chromium` |
| Urdu image text looks disconnected | Run `python selftest.py`; install the free Nastaliq font with the dashboard button |
| WhatsApp keeps asking for QR | Scan with the phone's **WhatsApp → Linked Devices** |
| Instagram/Facebook post flow failed | Their DOM changes often — the agent logs a clear note; generate the banner manually and post it yourself |
| Video job stuck at 0% | `edge-tts` needs internet for the voice; a silent MP4 is still produced |
| Port 8000 busy | `set CTH_PORT=8010` then run again |
| Everything off / silent | Check the **Emergency Kill Switch** state and per-agent Auto-Send |
| Browser-based Urdu not using Nastaliq | `python -m playwright install chromium` again, then re-generate the banner |

---

## 📜 Licence & fair use

All third-party components are free/open-source (FastAPI, Uvicorn, Playwright,
Pillow, imageio-ffmpeg, edge-tts). The browser agents automate **your own**
accounts on **your own** computer at your own discretion — use them in line with
each platform's terms of service and post only genuine, useful content.

**Chaudhary Type House & Property Advisors — Near Baldia Chowk, City Chishtian.**
*Subah 8:00 AM se Shaam 8:00 PM tak · 0327-7450361 · https://chtype.online*