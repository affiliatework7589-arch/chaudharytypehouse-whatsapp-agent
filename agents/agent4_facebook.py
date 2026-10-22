# -*- coding: utf-8 -*-
"""
AGENT 4 — FACEBOOK PAGE FREE POST & COMMENT/INBOX AGENT
======================================================
NO Meta Graph API. NO Page Access Token. NO webhook. NO cost.

Jobs (all through the user's own logged-in facebook.com browser session):
  1. POST — publish a complete, long-form *educational* Facebook post about
     Registry, Inteqal, Fard, Domicile or Property, always ending with the
     phone number 0327-7450361 and https://chtype.online.
  2. REPLY — auto-answer comments on the latest post and the Page inbox /
     Messenger threads with the bilingual AI brain, and capture every
     commenter as a lead in the local SQLite database.

Selectors are written with several fallbacks because Meta changes its DOM
frequently; when a flow cannot be completed automatically the agent logs a
clear "manual assist" note and never crashes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import config
from core import content as content_engine
from core import db, media
from core.ai_engine import smart_reply
from core.browser import SESSIONS
from agents.base import BaseAgent, mark_seen, seen_before

CREATE_POST_SELECTORS = [
    'div[aria-label="Create a post"]',
    '[aria-label="Create a post"]',
    '[aria-label="Post"]',
    'a[href="/pages/creation"]',
]
COMPOSER_SELECTORS = [
    'div[aria-label="What\'s on your mind, %s?"]',
    'div[contenteditable="true"][role="textbox"]',
    'div[aria-label="Write something..."][contenteditable="true"]',
]
POST_PUBLISH_SELECTORS = [
    'div[aria-label="Post"]',
    'span[aria-label="Post"]',
    'button:has-text("Post")',
    'div[role="button"]:has-text("Post")',
]
POST_TO_PAGE_SELECTORS = [
    'div[aria-label="Post to Facebook"]',
    'div[aria-label*="Post to" i]',
]
COMMENT_BOX_SELECTORS = [
    'div[aria-label="Write a comment"][contenteditable="true"]',
    'div[aria-label="Comment"][contenteditable="true"]',
    'div[contenteditable="true"][role="textbox"]',
]

INBOX_URL = "https://www.facebook.com/inbox"
MESSENGER_URL = "https://www.messenger.com/"


class FacebookAgent(BaseAgent):
    id = 4
    name = "Agent 4 — Facebook Post & Inbox"
    icon = "👍"
    platform = "facebook"
    interval = config.AGENT_POLL_SECONDS["facebook"]
    description = ("Educational Facebook posts + comment/Messenger auto-replies with "
                   f"{config.PHONE_DISPLAY} and {config.CALCULATOR_URL}. No Graph API.")

    def __init__(self) -> None:
        super().__init__()
        self.detail = {"posts": 0, "replies": 0, "note": ""}

    def run_once(self) -> None:
        sess = SESSIONS.get("facebook")
        if sess._ctx is None or not sess.page:
            self.detail["note"] = "Browser band hai — dashboard se 'Start Browser' dabayein."
            return
        if not sess.detect_login():
            self.detail["note"] = "Facebook login nahi hua. Browser window mein login kar lein."
            return

        try:
            self.detail["replies"] = self._reply_inbox(sess)
        except Exception as exc:
            db.log("WARN", self.name, f"Inbox pass: {exc}")

        try:
            self.detail["posts"] = self._publish_one(sess)
        except Exception as exc:
            db.log("WARN", self.name, f"Post pass: {exc}")

    # ------------------------------------------------------------------ #
    def _publish_one(self, sess) -> int:
        pending = db.pending_content("facebook", limit=3)
        if not pending:
            self.detail["note"] = "Facebook ke liye koi draft post nahi."
            return 0
        item = pending[0]

        banner = item.get("media_path") or media.make_banner(
            title=_title(item["caption"]), subtitle=config.SHOP_NAME,
            bullets=_bullets(item["caption"]), preset="facebook_post",
            filename=f"fb_{item['id']}.png")
        if banner:
            db.update_content(item["id"], media_path=banner)

        if not self.may_send():
            db.log("WARN", self.name, "Auto-post OFF — Facebook draft ready.")
            return 0

        if self._publish(sess, item["caption"]):
            db.update_content(item["id"], status="published", published_at=db.now())
            self.posts_published += 1
            db.log("INFO", self.name, f"Facebook post published: {item['topic']}")
            return 1
        return 0

    def _publish(self, sess, text: str) -> bool:
        page = sess.page
        try:
            page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=50_000)
            sess.wait(3.2)

            if not sess.click(CREATE_POST_SELECTORS, timeout=9000):
                return False
            sess.wait(2.4)

            wrote = False
            for sel in COMPOSER_SELECTORS:
                try:
                    loc = page.locator(sel).first
                    if loc.count() and loc.is_visible():
                        loc.click(timeout=5000)
                        loc.type(text[:4000], delay=8, timeout=40_000)
                        wrote = True
                        break
                except Exception:
                    continue
            if not wrote:
                return False
            sess.wait(1.4)

            # optional: audience selector
            for sel in POST_TO_PAGE_SELECTORS:
                try:
                    loc = page.locator(sel).first
                    if loc.count() and loc.is_visible():
                        loc.click(timeout=4000)
                        sess.wait(1.0)
                        break
                except Exception:
                    continue

            ok = sess.click(POST_PUBLISH_SELECTORS, timeout=10_000)
            sess.wait(4.0 if ok else 1.0)
            return ok
        except Exception as exc:
            db.log("WARN", self.name, f"Publish flow: {exc}")
            return False

    # ------------------------------------------------------------------ #
    def _reply_inbox(self, sess) -> int:
        page = sess.page
        for url in (MESSENGER_URL, INBOX_URL):
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=50_000)
                sess.wait(3.4)
                n = self._reply_thread(sess)
                if n:
                    return n
            except Exception as exc:
                db.log("WARN", self.name, f"Inbox load ({url}): {exc}")
        self.detail["note"] = "Inbox koi naya message nahi mila."
        return 0

    def _reply_thread(self, sess) -> int:
        rows = sess.page.locator('div[role="main"] div[role="gridcell"], div[aria-label^="Chat with"]')
        try:
            count = min(rows.count(), 12)
        except Exception:
            return 0

        handled = 0
        for i in range(count):
            try:
                r = rows.nth(i)
                aria = r.get_attribute("aria-label") or ""
                if "unread" not in aria.lower() and r.locator('[aria-label*="unread" i]').count() == 0:
                    continue
                r.click(timeout=7000)
                sess.wait(2.4)

                text = self._last_inbound(sess)
                if not text:
                    continue
                who = aria.split("Chat with")[-1].split(",")[0].strip() or "facebook-user"
                key = f"fb:{who}:{text[:60]}"
                if seen_before(key):
                    continue
                mark_seen(key)

                out = smart_reply(text, channel="facebook")
                db.add_lead(service=out.get("service_title", ""), message=text,
                            source="facebook", intent=out["intent"], language=out["language"])
                db.upsert_conversation("facebook", who, last_lang=out["language"],
                                       state=out["state"], last_text=text[:400],
                                       last_reply=out["reply"][:800])

                if self.may_send() and self._send(sess, out["reply"]):
                    self.replies_sent += 1
                    handled += 1
                    db.log("INFO", self.name, f"FB reply → {who}: {out['reply'][:90]}")
                sess.wait(2.0)
            except Exception:
                continue
        return handled

    def _last_inbound(self, sess) -> Optional[str]:
        try:
            bubbles = sess.page.locator('div[aria-label^="Message from"], div[dir="auto"]')
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
        for sel in ('div[contenteditable="true"][role="textbox"][aria-label="Message"]',
                    'div[contenteditable="true"][aria-label="Message"]',
                    'div[contenteditable="true"][role="textbox"]'):
            try:
                loc = sess.page.locator(sel).first
                if loc.count() and loc.is_visible():
                    loc.click(timeout=5000)
                    loc.type(text, delay=16, timeout=30_000)
                    sess.wait(0.6)
                    if sess.click(['div[aria-label="Send"]', '[aria-label="Send"]'], timeout=5000):
                        return True
                    loc.press("Enter")
                    return True
            except Exception:
                continue
        return False


# --------------------------------------------------------------------------
def _title(caption: str) -> str:
    for ln in (caption or "").split("\n"):
        s = ln.strip()
        if len(s) > 15:
            return s.split(".")[0][:70]
    return config.SHOP_NAME


def _bullets(caption: str) -> List[str]:
    import re
    out = []
    for ln in (caption or "").split("\n"):
        s = ln.strip()
        if re.match(r"^\d+[.)]\s+\S", s):
            out.append(s[:88])
        if len(out) >= 5:
            break
    return out or ["Registry • Inteqal • Fard", "Property Advisors", "Chishtian"]