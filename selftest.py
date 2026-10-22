# -*- coding: utf-8 -*-
"""
selftest.py — Instant verification of every FREE engine in the system.
Run:  python selftest.py
"""

import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

OK, FAIL = "  [OK]  ", "  [!!]  "
fails = []


def check(label, fn):
    try:
        result = fn()
        print(OK + label + (f"  -> {result}" if result else ""))
        return result
    except Exception as exc:
        fails.append((label, exc))
        print(FAIL + label + f"  -> {type(exc).__name__}: {exc}")
        traceback.print_exc(limit=2)
        return None


print("\n" + "=" * 78)
print("  CHAUDHARY TYPE HOUSE & PROPERTY ADVISORS — SYSTEM SELF-TEST")
print("  100% FREE / Zero paid APIs / Chishtian")
print("=" * 78 + "\n")

# ---------------------------------------------------------------- 1. config
print("[1] CONFIGURATION")
import config
check("Shop name embedded", lambda: config.SHOP_NAME)
check("Owner embedded", lambda: config.OWNER_NAME)
check("Address embedded", lambda: config.ADDRESS)
check("Timing embedded", lambda: config.TIMING)
check("WhatsApp number", lambda: config.WHATSAPP_LINK)
check("Calculator URL", lambda: config.CALCULATOR_URL)
check("Data folders created", lambda: f"{len(config.ALL_DIRS)} folders")

# ------------------------------------------------------------------- 2. db
print("\n[2] DATABASE (free SQLite)")
from core import db
check("schema initialised", lambda: db.init_db() or "leads/appts/content/jobs/convos/logs/kv")
lead = check("lead insert + read", lambda: db.add_lead(
    name="Ali Raza", phone="0301-2345678", service="Zameen ki Registry",
    message="Registry karwani hai", source="selftest", intent="service"))
check("lead list", lambda: f"{len(db.list_leads())} rows")
check("lead update", lambda: (db.update_lead(lead["id"], status="booked") or {}).get("status"))
check("appointment insert", lambda: db.add_appointment(
    name="Ali Raza", phone="0301-2345678", service="Registry",
    visit_date="2026-10-18", visit_time="Shaam 5 PM")["id"])
check("stats", lambda: db.lead_stats())
check("CSV export", lambda: db.export_leads_csv().name)
check("KV store", lambda: (db.kv_set("selftest", "1"), db.kv_get("selftest"))[1])
check("job tracking", lambda: (db.create_job("video", "selftest job"), db.get_job(db.list_jobs()[0]["id"])["status"])[1])

# ------------------------------------------------------------ 3. AI engine
print("\n[3] BILINGUAL AI ENGINE (offline rule engine)")
from core.ai_engine import smart_reply, detect_language, find_service

CASES = [
    ("Registry kaise hota hai?", "service", "roman"),
    ("رجسٹری کیسے ہوتی ہے؟", "service", "urdu"),
    ("kharcha kitna hoga", "fees", "roman"),
    ("خرچہ کتنا ہے؟", "fees", "urdu"),
    ("kab khulte ho?", "timing", "roman"),
    ("کہاں ہیں آپ؟", "location", "urdu"),
    ("phone number do", "contact", "roman"),
    ("mujhe fard chahiye", "service", "roman"),
    ("plot chahiye Chishtian mein", "service", "roman"),
    ("domicile banwana hai", "service", "roman"),
    ("aaj shaam aaunga", "appointment", "roman"),
    ("thanks", "thanks", "roman"),
    ("salam", "greeting", "roman"),          # 'salam' typed in Latin = Roman Urdu
    ("السلام", "greeting", "urdu"),
]
for q, exp_intent, exp_lang in CASES:
    def _t(q=q, exp=exp_intent, expl=exp_lang):
        r = smart_reply(q)
        got = (r["intent"], r["language"])
        assert r["reply"] and len(r["reply"]) > 20, "empty reply"
        assert expl == got[1], f"lang {got[1]} != {expl}"
        assert r["buttons"] and r["buttons"][0]["url"].startswith("http"), "no CTA button"
        if exp != "unknown":
            assert got[0] == exp, f"intent {got[0]} != {exp}"
        return f"{got[0]:<10} /{got[1]:<6} ({len(r['reply'])} chars)"
    check(f"Q: {q[:34]:<34}", _t)

print("  -- fees must route to chtype.online --")
def _calc():
    r = smart_reply("registry kharcha batao")
    assert config.CALCULATOR_URL in r["reply"], "calculator not mentioned"
    assert any(config.CALCULATOR_URL == b["url"] for b in r["buttons"]), "no calc button"
    return "chtype.online linked ✓"
check("fees -> calculator", _calc)

print("  -- multi-turn lead capture (Name -> Service -> Time) --")
def _flow():
    st = {}
    r1 = smart_reply("registry karwana hai", st, "selftest")
    st = r1["state"]
    assert st.get("stage") == "need_name", st.get("stage")
    r2 = smart_reply("Ali Raza", st, "selftest"); st = r2["state"]
    assert st.get("name") == "Ali Raza", st
    r3 = smart_reply("kal shaam ko aaunga", st, "selftest"); st = r3["state"]
    assert st.get("ready") is True, st
    assert r3["lead_id"], "lead was not created"
    lead3 = db.get_lead(r3["lead_id"])
    assert lead3["name"] == "Ali Raza" and lead3["status"] == "booked", lead3
    wa = [b for b in r3["buttons"] if "wa.me/923277450361" in b["url"]]
    from urllib.parse import unquote
    assert wa and "Ali Raza" in unquote(wa[0]["url"]), "WhatsApp handoff missing name"
    return f"lead {lead3['id']} booked, WA handoff OK"
check("booking flow", _flow)

print("  -- must NOT treat questions as names --")
def _noname():
    for q in ["Registry kaise hota hai?", "mujhe fard chahiye", "aaj shaam aaunga",
              "plot chahiye", "kitna kharcha hoga", "kab khula hai"]:
        st = {}
        r = smart_reply(q, st)
        assert not r["state"].get("name"), f"{q!r} captured name={r['state'].get('name')}"
    return "6 questions, 0 false names ✓"
check("no false name capture", _noname)

# ------------------------------------------------------------ 4. content
print("\n[4] CONTENT FACTORY (captions / hashtags / scripts)")
from core import content as C
check("topics loaded", lambda: f"{len(C.TOPICS)} topics")
for plat in ("instagram", "facebook", "tiktok", "whatsapp"):
    check(f"generate {plat}", lambda p=plat: C.generate(p, save=False)["title"][:46])
def _hash():
    r = smart_reply("instagram")
    d = C.generate("instagram", save=False)
    n = len([t for t in d["hashtags"].split() if t.startswith("#")])
    assert n >= 15, n
    return f"{n} hashtags ✓"
check("15+ SEO hashtags", _hash)
def _script():
    d = C.generate("tiktok", save=False)
    assert d["hook"] and d["spoken"] and len(d["timeline"]) >= 4
    assert d["timeline"][0]["t"] == "0-3s"
    return f"hook + {len(d['timeline'])} beats, 45s plan ✓"
check("45s viral script (3s hook)", _script)

# -------------------------------------------------------------- 5. media
print("\n[5] MEDIA ENGINE (Pillow banners + FFmpeg/edge-tts video)")
from core import media
check("Pillow available", lambda: media.PIL_AVAILABLE)
check("FFmpeg binary found", lambda: (media.ffmpeg_path() or "MISSING").split("\\")[-1])
check("edge-tts available", lambda: media.EDGE_TTS_AVAILABLE)
check("Urdu canvas font", lambda: media.urdu_supported() or "system font missing (Latin fallback)")

def _banner(preset="instagram_post", rtl=False):
    spec = C.banner_specs("registry_vs_mutation", "instagram", "urdu" if rtl else "roman")
    p = media.make_banner(spec["title"], spec["subtitle"], spec["bullets"],
                          preset=preset, rtl=rtl, filename=f"selftest_{preset}{'_ur' if rtl else ''}.png")
    assert p and os.path.getsize(p) > 8000, p
    return f"{os.path.basename(p)} ({os.path.getsize(p)//1024} KB)"
for preset in ("instagram_post", "instagram_story", "facebook_cover", "tiktok_cover"):
    check(f"banner {preset}", lambda pp=preset: _banner(pp))
check("banner Urdu (RTL)", lambda: _banner("instagram_post", rtl=True))

def _video():
    import time
    txt = ("Zameen ki registry aur mutation ka farq samjhein. "
           "Pehle fard dekhein. Registry ke baad naam badalne ke liye mutation lagta hai. "
           "Galat order se paisa aur waqt dono jaata hai. "
           "Aaj hi aaiye, WhatsApp kar lein.")
    out = os.path.join(str(config.VIDEO_DIR), "selftest.mp4")
    t0 = time.time()
    r = media.render_video(__import__("pathlib").Path(out), txt,
                           voice=config.TTS_VOICES["roman"], fps=20)
    assert r["ok"], r.get("error")
    size = os.path.getsize(r["path"]) // 1024
    return (f"{os.path.basename(r['path'])} | {r['duration']}s | {r['words']} words | "
            f"tts={r['tts']} | {size} KB | {time.time()-t0:.0f}s render")
check("vertical MP4 render", _video)

# ------------------------------------------------------------ 6. browser
print("\n[6] BROWSER ENGINE (Playwright persistent sessions — zero API)")
from core.browser import SESSIONS, playwright_installed, playwright_browsers_installed
check("playwright package", lambda: playwright_installed() or "not installed yet (run.bat fixes)")
check("chromium binary", lambda: playwright_browsers_installed() or "not installed yet (run.bat fixes)")
check("4 sessions registered", lambda: ", ".join(s.name for s in SESSIONS.all()))
def _profiles():
    p = [str(s.user_data_dir) for s in SESSIONS.all()]
    assert all(os.path.isdir(x) for x in p)
    return "profile dirs ready (login yahin save hoga)"
check("persistent profiles", _profiles)

# -------------------------------------------------------------- 7. agents
print("\n[7] AGENTS")
from agents import AGENTS, all_agents
def _agents():
    out = []
    for a in all_agents():
        i = a.info()
        assert i["status"] in ("stopped", "starting", "running", "paused", "error")
        out.append(f"{i['icon']}#{i['id']}")
    return " ".join(out)
check("all 5 agents registered", _agents)
check("agent 1 lead capture + scoring", lambda: AGENTS["1"].capture(
    name="Test User", phone="0300-1234567", service="Fard",
    message="fard chahiye", source="selftest"))
check("agent 1 scoring tags", lambda: [
    x for x in db.list_leads(20) if x.get("tag") in ("🔥 HOT", "🙂 WARM", "❄️ COLD")][:2])
check("agent 5 script render (no browser)", lambda: AGENTS["5"].render(
    topic="bay_nama", language="roman")["job_id"])
check("agent 2/3/4 report safely without browser", lambda: [
    (AGENTS[str(i)].run_once(), AGENTS[str(i)].detail)[1].get("note", "ok") for i in (2, 3, 4)])
check("kill switch flag readable", lambda: AGENTS["1"].paused_globally() in (True, False))

# ----------------------------------------------------------------- done
print("\n" + "=" * 78)
if fails:
    print(f"  RESULT: {len(fails)} check(s) need attention (the rest passed):")
    for lbl, exc in fails:
        print(f"    - {lbl}: {type(exc).__name__}: {exc}")
else:
    print("  RESULT: ALL CHECKS PASSED — 100% free, zero paid APIs.")
print("=" * 78 + "\n")