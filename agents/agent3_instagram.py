# -*- coding: utf-8 -*-
"""
AGENT 3 — INSTAGRAM FREE CONTENT & DM AGENT
=============================================
NO Meta Graph API. NO business.facebook.com token. NO cost.

Two jobs, both via the user's own logged-in browser session:
  1. POST — build a pixel-perfect 1080x1080 banner with Pillow (free), write a
     bilingual caption + 15 Chishtian real-estate SEO hashtags, then upload it
     to instagram.com through the browser.
  2. DM   — open the Direct inbox, reply to unread DMs with the same bilingual
     AI brain, capture name/phone, and hand the lead to WhatsApp.

Everything it posts comes from core/content.py so the shop can also approve and
post manually from the dashboard if they prefer.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import config
from core import content as content_engine
from core import db, media
from core.ai_engine import smart_reply
from core.browser import SESSIONS
from agents.base import BaseAgent, clean_incoming, mark_seen, seen_before

CREATE_SELECTORS = [
    'svg[aria-label="Create"]',
    '[aria-label="Create"]',
    'a[href="/create/"]',
    'div[role="button"][aria-label="Create"]',
]

POST_OPTION_TEXTS = ["Post", "Reel", "Live photo", "Carousel"]
FILE_INPUT = 'input[type="file"]'
NEXT_SELECTORS = [
    'div[role="button"]:has-text("Next")',
    'button:has-text("Next")',
    '[aria-label="Next"]',
]
CAPTION_SELECTORS = [
    'div[contenteditable="true"][aria-label="Write a caption..."]',
    'div[contenteditable="true"][aria-label*="caption" i]',
    'div[contenteditable="true"][role="textbox"]',
]
SHARE_SELECTORS = [
    'button:has-text("Share")',
    'div[role="button"]:has-text("Share")',
    'button:has-text("Post")',
    '[aria-label="Share"]',
]

DM_URL = "https://www.instagram.com/direct/inbox/"


class InstagramAgent(BaseAgent):
    id = 3
    name = "Agent 3 — Instagram Content & DM"
    icon = "📸"
    platform = "instagram"
    interval = config.AGENT_POLL_SECONDS["instagram"]
    description = ("Pillow se auto-designed banners + bilingual captions + 15 SEO "
                   "hashtags, browser se auto-post, aur DM auto-reply. No Meta API.")

    def __init__(self) -> None:
        super().__init__()
        self.detail = {"posts": 0, "dms": 0, "note": ""}

    def run_once(self) -> None:
        sess = SESSIONS.get("instagram")
        if sess._ctx is None or not sess.page:
            self.detail["note"] = "Browser band hai — dashboard se 'Start Browser' dabayein."
            return
        if not sess.detect_login():
            self.detail["note"] = "Instagram login nahi hua. Browser window mein login kar lein."
            return

        # ---- 1. DMs first (leads are more urgent than posts) ----
        try:
            self.detail["dms"] = self._handle_dms(sess)
        except Exception as exc:
            db.log("WARN", self.name, f"DM pass: {exc}")

        # ---- 2. Then publish one queued post ----
        try:
            self.detail["posts"] = self._publish_one(sess)
        except Exception as exc:
            db.log("WARN", self.name, f"Post pass: {exc}")

    # ------------------------------------------------------------------ #
    # POSTING
    # ------------------------------------------------------------------ #
    def _publish_one(self, sess) -> int:
        pending = db.pending_content("instagram", limit=3)
        if not pending:
            self.detail["note"] = "Instagram ke liye koi draft post nahi hai."
            return 0

        for item in pending:
            # 1) make the banner (free, local)
            banner = item.get("media_path") or media.make_banner(
                title=_short_title(item.get("caption", "")),
                subtitle=config.SHOP_NAME,
                bullets=_bullets_from_caption(item.get("caption", "")),
                preset="instagram_post",
                filename=f"ig_{item['id']}.png",
            )
            if not banner:
                return 0
            db.update_content(item["id"], media_path=banner)

            if not self.may_send():
                db.log("WARN", self.name,
                       f"Auto-post OFF — draft ready with banner: {banner}")
                return 0

            if self._upload(sess, banner, item.get("caption", "")):
                db.update_content(item["id"], status="published", published_at=db.now())
                self.posts_published += 1
                db.log("INFO", self.name, f"Instagram post published: {item['topic']}")
                return 1
            db.log("WARN", self.name, "Upload nahi hua — selectors change ho sakte hain. "
                                       "Dashboard se 'Manual Assist' dekhein.")
            return 0
        return 0

    def _upload(self, sess, image_path: str, caption: str) -> bool:
        page = sess.page
        try:
            page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=45_000)
            sess.wait(2.5)

            if not sess.click(CREATE_SELECTORS, timeout=9000):
                return False
            sess.wait(1.6)

            # choose "Post" in the create menu (not Reel/Live)
            picked = False
            for label in POST_OPTION_TEXTS[:1] + POST_OPTION_TEXTS[2:]:
                try:
                    page.get_by_text(label, exact=True).first.click(timeout=3500)
                    picked = True
                    break
                except Exception:
                    continue
            sess.wait(1.4)

            # upload the file
            try:
                page.locator(FILE_INPUT).first.set_input_files(image_path, timeout=20_000)
            except Exception:
                return False
            sess.wait(3.0)

            # crop → next (may appear twice: filter, then caption)
            for _ in range(2):
                if not sess.click(NEXT_SELECTORS, timeout=7000):
                    break
                sess.wait(2.2)

            # caption
            for sel in CAPTION_SELECTORS:
                try:
                    loc = page.locator(sel).first
                    if loc.count() and loc.is_visible():
                        loc.click(timeout=5000)
                        loc.fill(caption[:2200], timeout=15_000)
                        break
                except Exception:
                    continue
            sess.wait(1.0)

            ok = sess.click(SHARE_SELECTORS, timeout=9000)
            sess.wait(4.0 if ok else 1.0)
            return ok
        except Exception as exc:
            db.log("WARN", self.name, f"Upload flow: {exc}")
            return False

    # ------------------------------------------------------------------ #
    # DMs
    # ------------------------------------------------------------------ #
    def _handle_dms(self, sess) -> int:
        page = sess.page
        try:
            page.goto(DM_URL, wait_until="domcontentloaded", timeout=45_000)
            sess.wait(3.0)

            rows = page.locator('div[role="listitem"]')
            n = min(rows.count(), 25)
            unread = []
            for i in range(n):
                r = rows.nth(i)
                try:
                    aria = r.locator('[aria-label]').first.get_attribute("aria-label") or ""
                    txt = (r.inner_text(timeout=3000) or "")
                except Exception:
                    continue
                blob = f"{aria} {txt}".lower()
                if "unread" in blob or "not read" in blob:
                    name = txt.split("\n")[0].strip() or "instagram-user"
                    unread.append((i, name))
            if not unread:
                self.detail["note"] = "Koi unread Instagram DM nahi."
                return 0

            handled = 0
            for idx, name in unread[:4]:
                try:
                    rows.nth(idx).click(timeout=7000)
                    sess.wait(2.4)
                    text = self._last_inbound_text(sess)
                    if not text or seen_before(f"ig:{name}:{text[:60]}"):
                        continue
                    mark_seen(f"ig:{name}:{text[:60]}")

                    out = smart_reply(text, channel="instagram")
                    db.add_lead(service=out.get("service_title", ""), message=text,
                                source="instagram", intent=out["intent"],
                                language=out["language"])
                    db.upsert_conversation("instagram", name, last_lang=out["language"],
                                           state=out["state"], last_text=text[:400],
                                           last_reply=out["reply"][:800])

                    if self.may_send() and self._dm_send(sess, out["reply"]):
                        self.replies_sent += 1
                        handled += 1
                        db.log("INFO", self.name, f"IG DM → {name}: {out['reply'][:90]}")
                    sess.wait(2.0)
                except Exception as exc:
                    db.log("WARN", self.name, f"IG DM error: {exc}")
            return handled
        except Exception as exc:
            db.log("WARN", self.name, f"DM inbox: {exc}")
            return 0

    def _last_inbound_text(self, sess) -> Optional[str]:
        try:
            bubbles = sess.page.locator('div[dir="ltr"], div[dir="rtl"]')
            texts: List[str] = []
            for i in range(min(bubbles.count(), 20)):
                try:
                    t = (bubbles.nth(i).inner_text(timeout=2500) or "").strip()
                    if t and 2 < len(t) < 1500:
                        texts.append(t)
                except Exception:
                    continue
            return texts[-1] if texts else None
        except Exception:
            return None

    def _dm_send(self, sess, text: str) -> bool:
        for sel in ('div[contenteditable="true"][role="textbox"]',
                    'div[contenteditable="true"][aria-label*="Message" i]',
                    'div[contenteditable="true"]'):
            try:
                loc = sess.page.locator(sel).first
                if loc.count() and loc.is_visible():
                    loc.click(timeout=5000)
                    loc.type(text, delay=16, timeout=25_000)
                    sess.wait(0.7)
                    for s in ('svg[aria-label="Send"]', '[aria-label="Send"]',
                              'div[role="button"]:has-text("Send")'):
                        if sess.click([s], timeout=5000):
                            return True
                    loc.press("Enter")
                    return True
            except Exception:
                continue
        return False


# --------------------------------------------------------------------------
def _short_title(caption: str) -> str:
    for ln in (caption or "").split("\n"):
        ln = ln.strip().lstrip("🔥 ").strip()
        if len(ln) > 12:
            return ln[:70]
    return "Chaudhary Type House"


def _bullets_from_caption(caption: str) -> List[str]:
    out = []
    for ln in (caption or "").split("\n"):
        ln = ln.strip()
        if re_num(ln):
            out.append(ln[:90])
        if len(out) >= 5:
            break
    return out or ["Registry", "Inteqal", "Fard", "Property Dealing"]


def re_num(s: str) -> bool:
    import re
    return bool(re.match(r"^\d+[.)]\s+\S", s))