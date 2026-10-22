# -*- coding: utf-8 -*-
"""
AGENT 1 — WEBSITE & LEAD MANAGER
=================================
Responsibilities (all free, all local):
  * Every inquiry that arrives from the website chat widget / contact form is
    written to SQLite (and mirrored to a CSV export) instantly.
  * Every visitor booking a visit creates a real appointment row.
  * Scores and tags leads (hot / warm / cold) so the shop knows who to call back.
  * Keeps the dashboard's live lead table up to date.
  * Produces a free daily "call-back list" report.

This agent needs NO browser at all — it is pure local processing, so it always
works instantly, even before any QR scan.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import config
from core import db
from core.ai_engine import detect_intent, detect_language, find_service
from agents.base import BaseAgent

HOT_SERVICES = {"registry", "file", "fard", "bainama", "inteqal", "muawin_zamanat"}
HOT_WORDS = ["aaj", "kal", "foran", "abhi", "urgent", "jaldi", "aana", "aaun", "visit",
             "book", "appointment", "kharcha", "price", "rate", "today", "tomorrow"]


def score_lead(lead: Dict[str, Any]) -> Dict[str, Any]:
    """0-100 lead score + tag. Pure Python, zero cost."""
    score = 25
    reasons: List[str] = []

    if lead.get("name"):
        score += 15
        reasons.append("naam diya")
    if lead.get("phone"):
        score += 25
        reasons.append("phone diya")
    if lead.get("service"):
        score += 10
        reasons.append("service batayi")
    if lead.get("visit_time"):
        score += 15
        reasons.append("visit time diya")

    svc = find_service(lead.get("service", "") + " " + lead.get("message", ""))
    if svc and svc.key in HOT_SERVICES:
        score += 15
        reasons.append("high-value service")

    blob = (lead.get("message", "") or "").lower()
    if any(w in blob for w in HOT_WORDS):
        score += 15
        reasons.append("urgent/visit intent")

    if lead.get("source") in ("whatsapp", "instagram", "facebook", "tiktok"):
        score += 5
        reasons.append(f"{lead['source']} se aaya")

    score = min(100, score)
    tag = "🔥 HOT" if score >= 70 else ("🙂 WARM" if score >= 45 else "❄️ COLD")
    return {"score": score, "tag": tag, "reasons": reasons}


def annotate(lead: Dict[str, Any]) -> Dict[str, Any]:
    s = score_lead(lead)
    lead.update({"score": s["score"], "tag": s["tag"], "reasons": ", ".join(s["reasons"])})
    return lead


class WebsiteLeadManager(BaseAgent):
    id = 1
    name = "Agent 1 — Website & Lead Manager"
    icon = "🗂️"
    platform = "website"
    interval = 25
    description = ("Website inquiries + visit bookings → SQLite/CSV. "
                   "Lead scoring, follow-up list, CSV backup.")

    def run_once(self) -> None:
        # 1) Score + tag every unscored lead
        rows = db.list_leads(limit=500)
        updated = 0
        for lead in rows:
            if lead.get("status") in ("won", "lost", "scored"):
                continue
            ann = annotate(lead)
            if ann["score"] >= 70 and lead.get("status") == "new":
                db.update_lead(lead["id"], notes=f"[{ann['tag']} {ann['score']}/100] {ann['reasons']}")
                updated += 1
            elif ann["score"] >= 45 and not lead.get("notes"):
                db.update_lead(lead["id"], notes=f"[{ann['tag']} {ann['score']}/100]")
                updated += 1

        # 2) Keep a fresh CSV mirror (free backup for the shop owner)
        try:
            db.export_leads_csv()
        except Exception as exc:
            db.log("WARN", self.name, f"CSV export skip: {exc}")

        # 3) Surface hot leads
        hot = [annotate(r) for r in rows if r.get("notes", "").find("HOT") >= 0]
        self.detail = {
            "scored_now": updated,
            "total_leads": len(rows),
            "hot_now": len(hot),
            "next_actions": self._next_actions(hot[:5]),
            "last_csv": "data/exports/leads.csv",
        }

    def _next_actions(self, hot: List[Dict[str, Any]]) -> List[str]:
        out = []
        for h in hot:
            who = h.get("name") or "(naam nahi mila)"
            svc = h.get("service") or "general inquiry"
            out.append(f"☎️ {who} — {svc} — {h.get('created_at','')} — {config.PHONE_DISPLAY} par call karein")
        if not out:
            out.append("Abhi koi hot lead nahi. Website se inquiry aate hi yahan dikhegi.")
        return out

    # ------------------------------------------------------------------ #
    # API helpers used by app.py
    # ------------------------------------------------------------------ #
    def capture(self, name: str = "", phone: str = "", service: str = "", message: str = "",
                source: str = "website", intent: str = "", language: str = "roman",
                visit_time: str = "") -> Dict[str, Any]:
        lead = db.add_lead(name=name, phone=phone, service=service, message=message,
                           source=source, intent=intent, language=language,
                           visit_time=visit_time)
        lead = annotate(lead)
        if visit_time:
            db.add_appointment(lead_id=lead["id"], name=name, phone=phone,
                               service=service, visit_date=db.now()[:10], visit_time=visit_time)
        db.log("INFO", self.name,
               f"Lead capture [{lead['tag']} {lead['score']}] {name or '(no name)'} — {service or 'general'}")
        self.runs += 0
        return lead

    def book_visit(self, name: str, phone: str, service: str, date: str, time: str) -> Dict[str, Any]:
        appt = db.add_appointment(name=name, phone=phone, service=service,
                                  visit_date=date, visit_time=time)
        lead = db.add_lead(name=name, phone=phone, service=service,
                           message=f"Visit book: {date} {time}", source="website",
                           intent="appointment", visit_time=f"{date} {time}", status="booked")
        return {"appointment": appt, "lead": lead}