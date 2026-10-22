# -*- coding: utf-8 -*-
"""
AGENT 5 — TIKTOK VIRAL SCRIPT, VIDEO MAKER & INBOX AGENT
=========================================================
NO TikTok API. NO developer app. NO paid anything.

It makes REAL, uploadable vertical videos for free:
  * 45-second viral script written by core/content.py (3-second hook + beats + CTA)
  * Voice-over with Microsoft **edge-tts** (free neural Urdu/Hindi voice, no key)
  * Word-level timing from edge-tts drives a karaoke-style caption overlay
  * Frames rendered with Pillow, encoded by the free FFmpeg binary
    (shipped by the `imageio-ffmpeg` wheel) → 1080x1920 H.264 MP4
  * If the internet is down it still produces a captions-only MP4

Plus it replies to TikTok web messages through the browser session.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import config
from core import content as content_engine
from core import db, media
from core.ai_engine import smart_reply
from core.browser import SESSIONS
from agents.base import BaseAgent, mark_seen, seen_before

MESSAGES_URL = "https://www.tiktok.com/messages"
UPLOAD_URL = "https://www.tiktok.com/upload"

UPLOAD_FILE = 'input[type="file"]'
UPLOAD_NEXT = [
    'div[role="button"]:has-text("Next")',
    'button:has-text("Next")',
    'button:has-text("Post")',
    '[data-e2e="upload-next"]',
]
CAPTION = [
    'div[contenteditable="true"][data-e2e="video-desc"]',
    'div[contenteditable="true"][aria-label*="caption" i]',
    'div[contenteditable="true"]',
]


class TikTokAgent(BaseAgent):
    id = 5
    name = "Agent 5 — TikTok Script, Video & Inbox"
    icon = "🎬"
    platform = "tiktok"
    interval = config.AGENT_POLL_SECONDS["tiktok"]
    description = ("45-second viral scripts + free edge-tts Urdu voice-over + "
                   "FFmpeg/Pillow vertical MP4 with synced captions, + DM auto-reply.")

    def __init__(self) -> None:
        super().__init__()
        self.detail = {"scripts": 0, "videos": 0, "replies": 0, "note": ""}

    def run_once(self) -> None:
        # 1) Always keep a healthy queue of ready-made viral scripts.
        self._make_scripts()

        sess = SESSIONS.get("tiktok")
        if sess._ctx is None or not sess.page:
            self.detail["note"] = "Browser band hai — video banani ho to sirf 'Generate Video' dabayein."
            return
        if not sess.detect_login():
            self.detail["note"] = "TikTok login nahi hua. Video tab bhi ban jati hai."
            return
        try:
            self.detail["replies"] = self._reply_dms(sess)
        except Exception as exc:
            db.log("WARN", self.name, f"Inbox pass: {exc}")

    # ------------------------------------------------------------------ #
    # SCRIPT GENERATION
    # ------------------------------------------------------------------ #
    def _make_scripts(self) -> int:
        """Keep at least 3 unpublished TikTok scripts waiting in the queue."""
        pending = [c for c in db.list_content("tiktok", limit=50) if c["status"] == "draft"]
        if len(pending) >= 3:
            self.detail["scripts"] = len(pending)
            return len(pending)
        made = 0
        for _ in range(3 - len(pending)):
            d = content_engine.generate("tiktok", language="roman", save=True)
            db.log("INFO", self.name, f"Viral script ready: {d['title']}")
            made += 1
        self.detail["scripts"] = len(pending) + made
        return self.detail["scripts"]

    # ------------------------------------------------------------------ #
    # VIDEO RENDER  (exposed to the dashboard)
    # ------------------------------------------------------------------ #
    def render(self, topic: Optional[str] = None, language: str = "roman",
               voice: Optional[str] = None) -> Dict[str, Any]:
        script_data = content_engine.generate("tiktok", topic, language=language, save=False)
        spoken = script_data["spoken"]
        rtl = (language == "urdu")

        job = db.create_job("video", script_data["title"])

        import threading
        threading.Thread(
            target=media.render_video_job,
            args=(job["id"], spoken, script_data["title"], voice, rtl),
            daemon=True,
            name="video-render",
        ).start()

        # save the script as content too so the queue keeps growing
        row = db.add_content("tiktok", script_data["title"], language,
                             script_data["caption"], script_data["hashtags"])
        db.update_content(row["id"], notes=json_dumps_job(job["id"]))

        return {"job_id": job["id"], "script": script_data, "content_id": row["id"]}

    # ------------------------------------------------------------------ #
    # DM REPLIES
    # ------------------------------------------------------------------ #
    def _reply_dms(self, sess) -> int:
        page = sess.page
        try:
            page.goto(MESSAGES_URL, wait_until="domcontentloaded", timeout=50_000)
            sess.wait(3.4)
            rows = page.locator('div[data-e2e="conversation-item"], div[role="listitem"]')
            try:
                count = min(rows.count(), 15)
            except Exception:
                return 0
            handled = 0
            for i in range(count):
                try:
                    r = rows.nth(i)
                    aria = (r.get_attribute("aria-label") or "") + " " + (r.inner_text(timeout=2500) or "")
                    if "unread" not in aria.lower():
                        continue
                    name = aria.split(".")[0].strip()[:40] or "tiktok-user"
                    r.click(timeout=7000)
                    sess.wait(2.4)
                    text = self._last_inbound(sess)
                    if not text:
                        continue
                    key = f"tt:{name}:{text[:60]}"
                    if seen_before(key):
                        continue
                    mark_seen(key)
                    out = smart_reply(text, channel="tiktok")
                    db.add_lead(service=out.get("service_title", ""), message=text,
                                source="tiktok", intent=out["intent"], language=out["language"])
                    db.upsert_conversation("tiktok", name, last_lang=out["language"],
                                           state=out["state"], last_text=text[:400],
                                           last_reply=out["reply"][:800])
                    if self.may_send() and self._send(sess, out["reply"]):
                        self.replies_sent += 1
                        handled += 1
                        db.log("INFO", self.name, f"TikTok DM → {name}: {out['reply'][:80]}")
                    sess.wait(1.8)
                except Exception:
                    continue
            self.detail["note"] = "TikTok DM check ho gaya."
            return handled
        except Exception as exc:
            db.log("WARN", self.name, f"TikTok inbox: {exc}")
            return 0

    def _last_inbound(self, sess) -> Optional[str]:
        try:
            bubbles = sess.page.locator('[data-e2e="message-text"], div[data-e2e="message"]')
            out: List[str] = []
            for i in range(min(bubbles.count(), 20)):
                try:
                    t = (bubbles.nth(i).inner_text(timeout=2500) or "").strip()
                    if t and 2 < len(t) < 1500:
                        out.append(t)
                except Exception:
                    continue
            return out[-1] if out else None
        except Exception:
            return None

    def _send(self, sess, text: str) -> bool:
        for sel in ('div[data-e2e="message-input"] [contenteditable="true"]',
                    'div[contenteditable="true"][role="textbox"]',
                    'div[contenteditable="true"]'):
            try:
                loc = sess.page.locator(sel).first
                if loc.count() and loc.is_visible():
                    loc.click(timeout=5000)
                    loc.type(text, delay=16, timeout=25_000)
                    sess.wait(0.6)
                    if sess.click(['[data-e2e="message-send"]', '[aria-label="Send"]'], timeout=5000):
                        return True
                    loc.press("Enter")
                    return True
            except Exception:
                continue
        return False


def json_dumps_job(job_id: str) -> str:
    import json
    return json.dumps({"job_id": job_id})