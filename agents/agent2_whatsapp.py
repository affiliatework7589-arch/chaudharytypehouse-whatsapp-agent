# -*- coding: utf-8 -*-
"""
AGENT 2 — WHATSAPP WEB FREE AUTO-RESPONDER
===========================================
NO WhatsApp Cloud API. NO Meta webhook. NO payment. EVER.

How it works (100% free):
  * Playwright opens a real, persistent Chromium profile on this PC.
  * web.whatsapp.com loads. The user scans the QR with the phone ONCE.
  * From then on the profile stays logged in forever (data/browser_profiles/whatsapp).
  * Every poll it finds UNREAD chats, reads the last incoming message, and
    replies using the same bilingual AI brain the website uses.

It replies about: Registry, Complete File, Fard, Bai Nama, Inteqal, Arazi Muawin,
Domicile, NADRA e-Sahulat, Property Dealing — in Roman Urdu or Urdu, and always
pushes the customer towards `chtype.online` for fees and towards the shop visit.

Safety: the global KILL SWITCH + per-agent auto_send flag are checked before
every single send. Nothing is ever sent if they are off.
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Tuple

import config
from core import db
from core.ai_engine import smart_reply
from core.browser import SESSIONS
from agents.base import BaseAgent, clean_incoming, mark_seen, seen_before

CHAT_ROW_SELECTORS = [
    'div[role="listitem"]',
    'div[data-tab]',
    'div[data-id][role="listitem"]',
]

MESSAGE_INPUT_SELECTORS = [
    'div[contenteditable="true"][data-tab="10"]',
    'div[contenteditable="true"][role="textbox"]',
    'footer div[contenteditable="true"]',
    'div[aria-label="Message"][contenteditable="true"]',
    'div[role="textbox"][contenteditable="true"]',
]

SEND_BUTTON_SELECTORS = [
    'button[data-tab="Send"]',
    'span[data-icon="send"]',
    'button[aria-label="Send"]',
    'span[aria-label="Send"]',
]

SYSTEM_NOISE = re.compile(
    r"(messages and calls are end-to-end encrypted|"
    r"missed voice call|this message was deleted|you deleted this message|"
    r"security code changed|tap to see more|today|yesterday)", re.IGNORECASE)


class WhatsAppAgent(BaseAgent):
    id = 2
    name = "Agent 2 — WhatsApp Auto-Responder"
    icon = "💬"
    platform = "whatsapp"
    interval = config.AGENT_POLL_SECONDS["whatsapp"]
    description = ("web.whatsapp.com browser session → auto Roman-Urdu/Urdu replies, "
                   "name & time capture, visit booking. No WhatsApp API, no cost.")

    # ------------------------------------------------------------------ #
    def run_once(self) -> None:
        sess = SESSIONS.get("whatsapp")
        if sess._ctx is None:
            self.detail = {"note": "Browser band hai. Dashboard se 'Start Browser' dabayein."}
            return
        if not sess.page:
            return

        if not sess.detect_login():
            self.detail = {"note": "WhatsApp login nahi hua. QR scan karein (dashboard screenshot dekhein)."}
            return

        unread = self._find_unread_chats(sess)
        self.detail = {"unread_found": len(unread), "processed": 0}

        for chat in unread[:5]:
            try:
                sent = self._handle_chat(sess, chat)
                if sent:
                    self.replies_sent += 1
                    self.detail["processed"] = self.detail.get("processed", 0) + 1
            except Exception as exc:
                db.log("ERROR", self.name, f"Chat handle error: {exc}")
            sess.wait(1.6)          # be polite / human-like pacing

    # ------------------------------------------------------------------ #
    def _find_unread_chats(self, sess) -> List[Dict[str, str]]:
        rows: List[Dict[str, str]] = []
        try:
            loc = sess.page.locator(CHAT_ROW_SELECTORS[0])
            n = min(loc.count(), 40)
            for i in range(n):
                row = loc.nth(i)
                try:
                    if not row.is_visible():
                        continue
                    text = (row.inner_text(timeout=4000) or "").strip()
                except Exception:
                    continue
                if not text:
                    continue
                title = ""
                try:
                    title = row.locator('span[title]').first.get_attribute("title") or ""
                except Exception:
                    pass
                aria = ""
                try:
                    aria = row.locator('span[aria-label]').first.get_attribute("aria-label") or ""
                except Exception:
                    pass
                hay = f"{title} {aria} {text}".lower()
                is_unread = ("unread" in hay or "unread message" in hay
                             or "پڑھا نہیں" in hay or "غير مقروء" in hay)
                if is_unread:
                    rows.append({"title": title or text.split("\n")[0],
                                 "preview": text, "aria": aria, "index": str(i)})
        except Exception as exc:
            db.log("WARN", self.name, f"Unread scan: {exc}")
        return rows

    # ------------------------------------------------------------------ #
    def _handle_chat(self, sess, chat: Dict[str, str]) -> bool:
        page = sess.page
        contact = chat["title"] or "unknown"
        page.locator(CHAT_ROW_SELECTORS[0]).nth(int(chat["index"])).click(timeout=8000)
        sess.wait(2.2)

        incoming = self._read_last_incoming(sess)
        if not incoming:
            return False

        msg_id, text = incoming
        text = clean_incoming(text)
        if not text or SYSTEM_NOISE.match(text) or len(text) < 2:
            return False

        # never answer the same message twice
        if seen_before(f"wa:{msg_id}"):
            return False
        mark_seen(f"wa:{msg_id}")

        # ---- bilingual brain ----
        prior = db.get_conversation("whatsapp", contact) or {}
        state = prior.get("state") or {}
        out = smart_reply(text, state=state, channel="whatsapp")
        reply = out["reply"].strip()

        # save the conversation memory (keyed by contact this time)
        db.upsert_conversation("whatsapp", contact,
                               name=state.get("name") or prior.get("name", ""),
                               last_lang=out["language"], state=out["state"],
                               last_text=text[:500], last_reply=reply[:900])

        # ---- record the inquiry as a lead ----
        db.add_lead(name=state.get("name", ""), phone="",
                    service=out.get("service_title") or out.get("service", ""),
                    message=text, source="whatsapp", intent=out["intent"],
                    language=out["language"], status="new")

        if not self.may_send():
            db.log("WARN", self.name,
                   f"Draft ready (auto-send OFF) for {contact}: {reply[:90]}")
            return False

        ok = self._send(sess, reply)
        db.log("INFO" if ok else "ERROR", self.name,
               f"{contact}: {'→' if ok else '✗'} {reply[:120]}")
        return ok

    # ------------------------------------------------------------------ #
    def _read_last_incoming(self, sess) -> Optional[Tuple[str, str]]:
        """Return (message_id, text) of the newest INCOMING message."""
        try:
            blocks = sess.page.locator('div[data-id]')
            n = blocks.count()
            for i in range(n - 1, -1, -1):
                blk = blocks.nth(i)
                try:
                    mid = blk.get_attribute("data-id") or ""
                except Exception:
                    continue
                if not mid:
                    continue
                # incoming = inside a .message-in container
                incoming = False
                try:
                    cls = blk.evaluate(
                        "e => { let p=e; for(let i=0;i<6 && p;i++){ if(p.className "
                        "&& String(p.className).indexOf('message-in')>=0) return 1; "
                        "p=p.parentElement; } return 0; }")
                    incoming = bool(cls)
                except Exception:
                    incoming = "message-in" in (mid or "")
                if not incoming:
                    continue
                try:
                    txt = blk.inner_text(timeout=4000) or ""
                except Exception:
                    continue
                txt = re.sub(r"\n\d{1,2}:\d{2}(:\d{2})?\s*(AM|PM)?$", "", txt).strip()
                if txt:
                    return mid, txt
        except Exception as exc:
            db.log("WARN", self.name, f"Read messages: {exc}")
        return None

    # ------------------------------------------------------------------ #
    def _send(self, sess, text: str) -> bool:
        page = sess.page
        try:
            if not sess.fill(MESSAGE_INPUT_SELECTORS, ""):
                # click the box first, then retry
                for sel in MESSAGE_INPUT_SELECTORS[:2]:
                    try:
                        loc = page.locator(sel).first
                        if loc.count():
                            loc.click(timeout=4000)
                            break
                    except Exception:
                        continue
                sess.wait(0.6)

            for sel in MESSAGE_INPUT_SELECTORS:
                try:
                    loc = page.locator(sel).first
                    if loc.count() and loc.is_visible():
                        loc.click(timeout=5000)
                        loc.type(text, delay=18, timeout=25_000)
                        sess.wait(0.9)
                        if sess.click(SEND_BUTTON_SELECTORS, timeout=6000):
                            return True
                        # fall back to Enter
                        loc.press("Enter")
                        return True
                except Exception:
                    continue
            return False
        except Exception as exc:
            db.log("ERROR", self.name, f"Send failed: {exc}")
            return False