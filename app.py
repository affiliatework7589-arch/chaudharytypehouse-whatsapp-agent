# -*- coding: utf-8 -*-
"""
app.py — Chaudhary Type House & Property Advisors
FREE local automation server (FastAPI + SQLite + Playwright + Pillow + FFmpeg)

Run it:      python app.py      (or just double-click run.bat / ./run.sh)
Then open:   http://127.0.0.1:8000/          <- public website + AI assistant
             http://127.0.0.1:8000/dashboard <- admin control panel

ZERO paid APIs are used anywhere. Ever.
"""

from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import platform
import sys
import threading
import time
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

# --- make sure the project root is importable no matter how it was launched ---
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import Body, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               PlainTextResponse, RedirectResponse, Response)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
from agents import AGENTS, all_agents, get as get_agent, set_global_pause
from core import content as content_engine
from core import db, media
from core.ai_engine import SERVICES, smart_reply
from core.browser import SESSIONS, playwright_browsers_installed, playwright_installed

# ---------------------------------------------------------------------------
APP_TITLE = "Chaudhary Type House & Property Advisors — FREE Automation System"

db.init_db()

app = FastAPI(title=APP_TITLE, version="1.0.0", docs_url="/api/docs", redoc_url=None)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=False,
    allow_methods=["*"], allow_headers=["*"],
)

# Media served straight from the local data folder (banners, videos, audio).
app.mount("/media", StaticFiles(directory=str(config.MEDIA_DIR)), name="media")
app.mount("/files", StaticFiles(directory=str(config.DATA_DIR)), name="files")


# ===========================================================================
# PAGES
# ===========================================================================
@app.get("/", response_class=HTMLResponse)
def homepage() -> FileResponse:
    return FileResponse(str(ROOT / "index.html"))


@app.get("/dashboard", response_class=HTMLResponse)
@app.get("/dashboard.html", response_class=HTMLResponse)
def dashboard() -> FileResponse:
    return FileResponse(str(ROOT / "dashboard.html"))


@app.get("/favicon.ico")
def favicon() -> Response:
    # tiny emerald/gold "CTH" dot — no external file needed
    svg = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>"
           "<rect width='64' height='64' rx='14' fill='#046b4d'/>"
           "<text x='32' y='43' font-size='28' font-family='Segoe UI,Arial' "
           "font-weight='bold' fill='#d4af37' text-anchor='middle'>C</text></svg>")
    return Response(svg, media_type="image/svg+xml")


# ===========================================================================
# SYSTEM STATUS
# ===========================================================================
def system_info() -> Dict[str, Any]:
    fx = media.ffmpeg_path()
    return {
        "shop": {
            "name": config.SHOP_NAME,
            "name_ur": config.SHOP_NAME_UR,
            "owner": config.OWNER_NAME,
            "owner_ur": config.OWNER_NAME_UR,
            "address": config.ADDRESS,
            "address_ur": config.ADDRESS_UR,
            "timing": config.TIMING,
            "timing_ur": config.TIMING_UR,
            "phone": config.PHONE_DISPLAY,
            "whatsapp": config.WHATSAPP_LINK,
            "calculator": config.CALCULATOR_URL,
        },
        "engines": {
            "ai_provider": config.AI_PROVIDER,
            "gemini_enabled": config.GEMINI_ENABLED,
            "pillow": media.PIL_AVAILABLE,
            "ffmpeg": bool(fx),
            "ffmpeg_path": fx or "",
            "edge_tts": media.EDGE_TTS_AVAILABLE,
            "playwright": playwright_installed(),
            "playwright_chromium": playwright_browsers_installed(),
            "fonts": media.font_status(),
            "urdu_font": media.urdu_supported(),
        },
        "globals": {
            "auto_send_default": config.AUTO_SEND_DEFAULT,
            "globally_paused": config.KILL_SWITCH_FILE.exists(),
            "host": config.HOST,
            "port": config.PORT,
            "python": platform.python_version(),
            "os": platform.system(),
        },
        "db": db.lead_stats(),
    }


@app.get("/api/system")
def api_system() -> Dict[str, Any]:
    return system_info()


@app.get("/api/health")
def api_health() -> PlainTextResponse:
    return PlainTextResponse("OK — Chaudhary Type House system is running (100% free).")


# ---------------------------------------------------------------------------
# FONTS  (free Noto Nastaliq Urdu, one click)
# ---------------------------------------------------------------------------
@app.get("/api/fonts")
def api_fonts() -> Dict[str, Any]:
    return {"fonts": media.font_status()}


@app.post("/api/fonts/install")
def api_fonts_install() -> Dict[str, Any]:
    from core import fonts as fontlib
    p = fontlib.download_noto()
    return {"ok": bool(p), "path": p or "", "fonts": media.font_status()}


# ===========================================================================
# AI ASSISTANT  (used by index.html — also works with the local rule engine only)
# ===========================================================================
class ChatIn(BaseModel):
    message: str = ""
    state: Dict[str, Any] = {}
    session: str = "web"
    # Sent only by the public site's AI Advisor, as a fire-and-forget lead
    # note. It never carries the answer - the widget answers in-page.
    source: str = ""
    topic: str = ""
    language: str = ""


@app.post("/api/chat")
def api_chat(payload: ChatIn) -> Dict[str, Any]:
    # --- website AI Advisor: local-only lead logging ------------------------
    # The widget already rendered its own answer, so there is nothing to
    # compute here. We just record the inquiry so it shows up in the local
    # dashboard. Everything is wrapped so logging can never raise.
    if payload.source == "website_ai":
        logged = False
        try:
            msg = (payload.message or "").strip()[:400]
            if msg:
                recent = db.list_leads(limit=10, status="new")
                if not any(l.get("message") == msg for l in recent):
                    AGENTS["1"].capture(
                        name="", phone="",
                        service=payload.topic or "AI Advisor",
                        message=msg,
                        source="website_ai",
                        intent="ai_advisor",
                        language=payload.language or "",
                    )
                    logged = True
        except Exception:
            pass  # a logging failure must never break the endpoint
        return {"ok": True, "logged": logged}

    out = smart_reply(payload.message, state=payload.state, channel="website")
    # Persist website chat inquiries as leads too (Agent 1 watches the DB).
    st = out.get("state") or {}
    if st.get("stage") == "done" or st.get("name"):
        agent1 = AGENTS["1"]
        existing = db.list_leads(limit=5, status="new")
        if not any(l.get("phone") == "" and l.get("name") == st.get("name")
                   and l.get("message") == payload.message for l in existing):
            agent1.capture(name=st.get("name", ""), service=out.get("service_title", ""),
                           message=payload.message, source="website_chat",
                           intent=out["intent"], language=out["language"],
                           visit_time=st.get("slot", ""))
    return out


@app.post("/api/lead")
def api_lead(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Contact-form / quick-inquiry endpoint (website + dashboard)."""
    lead = AGENTS["1"].capture(
        name=str(payload.get("name", "")),
        phone=str(payload.get("phone", "")),
        service=str(payload.get("service", "")),
        message=str(payload.get("message", "")),
        source=str(payload.get("source", "website_form")),
    )
    return {"ok": True, "lead": lead}


@app.post("/api/appointment")
def api_appointment(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    data = AGENTS["1"].book_visit(
        name=str(payload.get("name", "")),
        phone=str(payload.get("phone", "")),
        service=str(payload.get("service", "")),
        date=str(payload.get("date", "")) or db.now()[:10],
        time=str(payload.get("time", "")) or "Aaj",
    )
    return {"ok": True, **data}


@app.get("/api/services")
def api_services() -> Dict[str, Any]:
    return {
        "services": [
            {"key": s.key, "title_ru": s.title_ru, "title_ur": s.title_ur,
             "icon": s.icon, "blurb_ru": s.blurb_ru, "blurb_ur": s.blurb_ur}
            for s in SERVICES
        ]
    }


# ===========================================================================
# LEADS  (Agent 1)
# ===========================================================================
@app.get("/api/leads")
def api_leads(limit: int = 200, status: str = "") -> Dict[str, Any]:
    from agents.agent1_leads import annotate
    return {"leads": [annotate(r) for r in db.list_leads(limit=limit, status=status)],
            "stats": db.lead_stats()}


@app.patch("/api/leads/{lead_id}")
def api_lead_update(lead_id: str, payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    lead = db.update_lead(lead_id, **payload)
    if not lead:
        raise HTTPException(404, "Lead nahi mila")
    from agents.agent1_leads import annotate
    return {"ok": True, "lead": annotate(lead)}


@app.delete("/api/leads/{lead_id}")
def api_lead_delete(lead_id: str) -> Dict[str, Any]:
    return {"ok": db.delete_lead(lead_id)}


@app.get("/api/leads.csv")
def api_leads_csv() -> FileResponse:
    path = db.export_leads_csv()
    return FileResponse(str(path), media_type="text/csv", filename="leads.csv")


@app.get("/api/appointments")
def api_appointments() -> Dict[str, Any]:
    return {"appointments": db.list_appointments()}


@app.get("/api/conversations")
def api_conversations() -> Dict[str, Any]:
    return {"conversations": db.list_conversations(limit=100)}


@app.get("/api/logs")
def api_logs(limit: int = 120) -> Dict[str, Any]:
    return {"logs": db.recent_logs(limit)}


# ===========================================================================
# CONTENT FACTORY  (Agents 3, 4, 5)
# ===========================================================================
@app.get("/api/topics")
def api_topics() -> Dict[str, Any]:
    return {"topics": [{"key": t["key"], "title": t["topic_ru"], "title_ur": t["topic_ur"],
                        "service": t["service"]} for t in content_engine.TOPICS]}


@app.post("/api/content/generate")
def api_content_generate(payload: Dict[str, Any] = Body(default={})) -> Dict[str, Any]:
    platform = str(payload.get("platform", "instagram")).lower()
    topic = payload.get("topic") or None
    language = str(payload.get("language", "roman")).lower()
    data = content_engine.generate(platform, topic, language=language, save=True)

    # optionally render the free banner straight away
    banner = None
    if payload.get("with_banner", True):
        spec = content_engine.banner_specs(data.get("topic"), platform, language)
        banner = media.make_banner(
            title=spec["title"], subtitle=spec["subtitle"],
            bullets=spec["bullets"], preset=spec["preset"], rtl=spec["rtl"],
            tag="CHISHTIAN", filename=f"{platform}_{data['id']}.png")
        if banner:
            db.update_content(data["id"], media_path=banner)
    data["media_path"] = banner or ""
    return {"ok": True, "content": data}


@app.get("/api/content")
def api_content(platform: str = "", limit: int = 60) -> Dict[str, Any]:
    return {"content": db.list_content(platform, limit)}


@app.patch("/api/content/{content_id}")
def api_content_update(content_id: str, payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    row = db.update_content(content_id, **payload)
    return {"ok": bool(row), "content": row}


@app.post("/api/content/{content_id}/banner")
def api_content_banner(content_id: str, payload: Dict[str, Any] = Body(default={})) -> Dict[str, Any]:
    row = db.get_content(content_id)
    if not row:
        raise HTTPException(404, "Content nahi mila")
    spec = content_engine.banner_specs(payload.get("topic") or row.get("topic"),
                                       row["platform"], row.get("language", "roman"))
    p = media.make_banner(title=spec["title"], subtitle=spec["subtitle"],
                          bullets=spec["bullets"], preset=spec["preset"],
                          rtl=spec["rtl"], tag="CHISHTIAN",
                          filename=f"{row['platform']}_{content_id}.png")
    if p:
        db.update_content(content_id, media_path=p)
    return {"ok": bool(p), "media_path": p}


@app.get("/api/script")
def api_script(topic: str = "", language: str = "roman") -> Dict[str, Any]:
    d = content_engine.generate("tiktok", topic or None, language=language, save=False)
    return {"ok": True, "script": d}


# ===========================================================================
# VIDEO FACTORY  (Agent 5) — free edge-tts + FFmpeg
# ===========================================================================
@app.post("/api/video/render")
def api_video_render(payload: Dict[str, Any] = Body(default={})) -> Dict[str, Any]:
    return AGENTS["5"].render(
        topic=payload.get("topic") or None,
        language=str(payload.get("language", "roman")),
        voice=payload.get("voice") or None,
    )


@app.post("/api/video/render-text")
def api_video_render_text(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    text = str(payload.get("text", "")).strip()
    if not text:
        raise HTTPException(400, "text zaroori hai")
    rtl = str(payload.get("language", "roman")) == "urdu"
    job = db.create_job("video", text[:60])
    threading.Thread(target=media.render_video_job,
                     args=(job["id"], text, text[:60], payload.get("voice"), rtl),
                     daemon=True).start()
    return {"ok": True, "job_id": job["id"]}


@app.get("/api/jobs")
def api_jobs(limit: int = 30) -> Dict[str, Any]:
    return {"jobs": db.list_jobs(limit)}


@app.get("/api/jobs/{job_id}")
def api_job(job_id: str) -> Dict[str, Any]:
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job nahi mila")
    return {"job": job}


# ===========================================================================
# BROWSER SESSIONS  (Playwright persistent profiles — the zero-API core)
# ===========================================================================
@app.get("/api/browsers")
def api_browsers() -> Dict[str, Any]:
    return {"sessions": SESSIONS.info(),
            "installed": playwright_installed(),
            "chromium": playwright_browsers_installed()}


@app.post("/api/browsers/{name}/start")
def api_browser_start(name: str) -> Dict[str, Any]:
    try:
        s = SESSIONS.get(name)
    except KeyError:
        raise HTTPException(404, f"Unknown browser: {name}")
    return {"ok": True, "session": s.start()}


@app.post("/api/browsers/{name}/stop")
def api_browser_stop(name: str) -> Dict[str, Any]:
    try:
        s = SESSIONS.get(name)
    except KeyError:
        raise HTTPException(404, f"Unknown browser: {name}")
    return {"ok": True, "session": s.stop()}


@app.post("/api/browsers/{name}/restart")
def api_browser_restart(name: str) -> Dict[str, Any]:
    s = SESSIONS.get(name)
    return {"ok": True, "session": s.restart()}


@app.post("/api/browsers/{name}/navigate")
def api_browser_navigate(name: str, payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    s = SESSIONS.get(name)
    return s.navigate(str(payload.get("url", s.url)))


@app.post("/api/browsers/{name}/login-check")
def api_browser_login_check(name: str) -> Dict[str, Any]:
    s = SESSIONS.get(name)
    return {"logged_in": s.detect_login(), "session": s.info()}


@app.get("/api/browsers/{name}/screenshot")
def api_browser_screenshot(name: str) -> Response:
    s = SESSIONS.get(name)
    b64 = s.screenshot_b64()
    if not b64:
        raise HTTPException(503, s.last_error or "Screenshot nahi mil saka")
    import base64
    return Response(base64.b64decode(b64), media_type="image/jpeg",
                    headers={"Cache-Control": "no-store"})


# ===========================================================================
# AGENT CONTROL
# ===========================================================================
@app.get("/api/agents")
def api_agents() -> Dict[str, Any]:
    return {"agents": [a.info() for a in all_agents()],
            "globally_paused": config.KILL_SWITCH_FILE.exists()}


@app.post("/api/agents/{agent_id}/start")
def api_agent_start(agent_id: str) -> Dict[str, Any]:
    try:
        return {"ok": True, "agent": get_agent(agent_id).start()}
    except KeyError:
        raise HTTPException(404, "Agent nahi mila")


@app.post("/api/agents/{agent_id}/stop")
def api_agent_stop(agent_id: str) -> Dict[str, Any]:
    try:
        return {"ok": True, "agent": get_agent(agent_id).stop()}
    except KeyError:
        raise HTTPException(404, "Agent nahi mila")


@app.post("/api/agents/{agent_id}/toggle")
def api_agent_toggle(agent_id: str) -> Dict[str, Any]:
    a = get_agent(agent_id)
    return {"ok": True, "agent": a.stop() if a.enabled else a.start()}


@app.post("/api/agents/{agent_id}/run-once")
def api_agent_run_once(agent_id: str) -> Dict[str, Any]:
    a = get_agent(agent_id)
    try:
        a.run_once()
        return {"ok": True, "agent": a.info()}
    except Exception as exc:
        raise HTTPException(500, f"{type(exc).__name__}: {exc}")


@app.post("/api/agents/{agent_id}/auto-send")
def api_agent_autosend(agent_id: str, payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    return {"ok": True, "agent": get_agent(agent_id).set_auto_send(bool(payload.get("value", True)))}


@app.post("/api/agents/all/start")
def api_agents_start_all() -> Dict[str, Any]:
    for a in all_agents():
        a.start()
    return {"ok": True, "agents": [a.info() for a in all_agents()]}


@app.post("/api/agents/all/stop")
def api_agents_stop_all() -> Dict[str, Any]:
    for a in all_agents():
        a.stop()
    return {"ok": True, "agents": [a.info() for a in all_agents()]}


@app.post("/api/agents/all/auto-send")
def api_agents_autosend_all(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    val = bool(payload.get("value", True))
    for a in all_agents():
        a.auto_send = val
    return {"ok": True, "auto_send": val}


@app.post("/api/kill-switch")
def api_kill_switch(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    paused = bool(payload.get("paused", True))
    now_paused = set_global_pause(paused)
    if not paused:
        db.log("INFO", "system", "Kill switch released — agents dobara message bhej sakte hain.")
    return {"ok": True, "globally_paused": now_paused}


# ===========================================================================
# LIVE EVENT STREAM (Server-Sent Events → dashboard live table + logs)
# ===========================================================================
@app.get("/api/events")
async def events():
    from fastapi.responses import StreamingResponse

    async def gen():
        last_leads = 0
        while True:
            stats = db.lead_stats()
            payload = json.dumps({
                "ts": db.now(),
                "lead_stats": stats,
                "agents": [a.info() for a in all_agents()],
                "browsers": SESSIONS.info(),
                "new_leads": stats["total"] != last_leads,
            }, ensure_ascii=False)
            last_leads = stats["total"]
            yield f"data: {payload}\n\n"
            await asyncio.sleep(3)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


# ===========================================================================
# MEDIA PREVIEW
# ===========================================================================
def _safe_media(rel: str) -> Path:
    p = (config.MEDIA_DIR / rel).resolve()
    if not str(p).startswith(str(config.MEDIA_DIR.resolve())):
        raise HTTPException(403, "Not allowed")
    return p


@app.get("/api/media")
def api_media_list(kind: str = "") -> Dict[str, Any]:
    out: List[Dict[str, Any]] = []
    for folder, k in ((config.BANNER_DIR, "banners"), (config.VIDEO_DIR, "videos")):
        if kind and kind != k:
            continue
        for f in sorted(folder.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)[:60]:
            out.append({"kind": k, "name": f.name,
                        "url": f"/media/{k}/{f.name}",
                        "size": f.stat().st_size,
                        "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(f.stat().st_mtime))})
    return {"media": out}


# ===========================================================================
# STARTUP / SHUTDOWN
# ===========================================================================
@asynccontextmanager
async def lifespan(_app: FastAPI):
    stale = db.recover_stale_jobs()
    if stale:
        db.log("WARN", "system", f"{stale} adhoora render job band kar diya gaya (server restart).")
    db.log("INFO", "system", f"{APP_TITLE} shuru ho gaya (port {config.PORT}).")
    # Auto-start every agent; browser-based ones simply wait for a login.
    for a in all_agents():
        a.start()
    try:
        yield
    finally:
        db.log("INFO", "system", "System band ho raha hai…")
        for a in all_agents():
            a.stop()
        SESSIONS.stop_all()


app.router.lifespan_context = lifespan


def _open_browser() -> None:
    time.sleep(2.0)
    for url in (f"http://{config.HOST}:{config.PORT}/dashboard",
                f"http://{config.HOST}:{config.PORT}/"):
        try:
            webbrowser.open(url)
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn

    banner = r"""
  ____                 _   _   _ _____ _   _           _
 / ___|__ _ _ __ ___  | | | | |_   _| \ | | ___  ___| | ___ _   _
| |   / _` | '_ ` _ \ | |_| | | | | |  \| |/ _ \/ __| |/ _ \ | | |
| |__| (_| | | | | | ||  _  | | |_| | |\  |  __/\__ \ |  __/ |_| |
 \____\__,_|_| |_| |_||_| |_|_|\__,_|_| \_|\___||___/_\___|\__,_| |
                                                                   |_/   100% FREE · ZERO PAID API
    Registry • Inteqal • Fard • Property Advisors — Chishtian
"""
    print(banner)
    print(f"  Website  : http://{config.HOST}:{config.PORT}/")
    print(f"  Dashboard: http://{config.HOST}:{config.PORT}/dashboard")
    print(f"  Owner    : {config.OWNER_NAME} — {config.PHONE_DISPLAY}")
    print(f"  AI engine: {config.AI_PROVIDER}")
    print(f"  Pillow   : {'OK' if media.PIL_AVAILABLE else 'MISSING (pip install Pillow)'}")
    print(f"  FFmpeg   : {'OK' if media.ffmpeg_path() else 'MISSING (pip install imageio-ffmpeg)'}")
    print(f"  edge-tts : {'OK' if media.EDGE_TTS_AVAILABLE else 'MISSING (pip install edge-tts)'}")
    print(f"  Playwright: {'OK' if playwright_installed() else 'MISSING (pip install playwright)'}")
    print("-" * 72)

    threading.Thread(target=_open_browser, daemon=True).start()

    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="info",
                access_log=False)