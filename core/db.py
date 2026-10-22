# -*- coding: utf-8 -*-
"""
core/db.py — Free local SQLite lead/content/job store + CSV export.

* ZERO COST: Python ships with sqlite3 built in. No server, no cloud, no signup.
* Thread-safe: every agent runs in its own thread, so each call opens a short
  lived connection (simplest correct pattern) plus WAL for concurrent readers.
"""

from __future__ import annotations

import csv
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import config

_WRITE_LOCK = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id            TEXT PRIMARY KEY,
    name          TEXT,
    phone         TEXT,
    service       TEXT,
    message       TEXT,
    source        TEXT,
    intent        TEXT,
    language      TEXT,
    status        TEXT DEFAULT 'new',
    visit_time    TEXT,
    notes         TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS appointments (
    id            TEXT PRIMARY KEY,
    lead_id       TEXT,
    name          TEXT,
    phone         TEXT,
    service       TEXT,
    visit_date    TEXT,
    visit_time    TEXT,
    status        TEXT DEFAULT 'booked',
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS content (
    id            TEXT PRIMARY KEY,
    platform      TEXT,
    topic         TEXT,
    language      TEXT,
    caption       TEXT,
    hashtags      TEXT,
    media_path    TEXT,
    status        TEXT DEFAULT 'draft',
    published_at  TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id            TEXT PRIMARY KEY,
    kind          TEXT,
    title         TEXT,
    status        TEXT DEFAULT 'queued',
    progress      INTEGER DEFAULT 0,
    message       TEXT,
    result        TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id            TEXT PRIMARY KEY,
    channel       TEXT,
    contact       TEXT,
    name          TEXT,
    phone         TEXT,
    last_lang     TEXT,
    state         TEXT,          -- json blob of collected fields
    last_text     TEXT,
    last_reply    TEXT,
    status        TEXT DEFAULT 'open',
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL,
    level         TEXT,
    source        TEXT,
    message       TEXT
);

CREATE TABLE IF NOT EXISTS kv (
    key           TEXT PRIMARY KEY,
    value         TEXT,
    updated_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_leads_created  ON leads(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_content_created ON content(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_conv_updated    ON conversations(updated_at DESC);
"""


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


@contextmanager
def conn():
    """Short-lived connection. Safe across agent threads."""
    c = sqlite3.connect(str(config.DB_PATH), timeout=30.0)
    c.row_factory = sqlite3.Row
    try:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA busy_timeout=30000")
        yield c
        c.commit()
    finally:
        c.close()


def init_db() -> None:
    with _WRITE_LOCK, conn() as c:
        c.executescript(SCHEMA)


def _row_to_dict(r: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    return dict(r) if r is not None else None


# ---------------------------------------------------------------------------
# LEADS  (Agent 1 - Website & Lead Manager)
# ---------------------------------------------------------------------------
def add_lead(
    name: str = "",
    phone: str = "",
    service: str = "",
    message: str = "",
    source: str = "website",
    intent: str = "",
    language: str = "roman",
    status: str = "new",
    visit_time: str = "",
    notes: str = "",
) -> Dict[str, Any]:
    lead = {
        "id": new_id("lead_"),
        "name": (name or "").strip(),
        "phone": (phone or "").strip(),
        "service": (service or "").strip(),
        "message": (message or "").strip(),
        "source": source,
        "intent": intent,
        "language": language,
        "status": status,
        "visit_time": visit_time,
        "notes": notes,
        "created_at": now(),
    }
    with _WRITE_LOCK, conn() as c:
        c.execute(
            """INSERT INTO leads (id,name,phone,service,message,source,intent,
                                  language,status,visit_time,notes,created_at)
               VALUES (:id,:name,:phone,:service,:message,:source,:intent,
                       :language,:status,:visit_time,:notes,:created_at)""",
            lead,
        )
    log("INFO", "leads", f"New lead: {lead['name'] or '(no name)'} — {lead['service'] or 'general'} — {lead['message'][:70]}")
    return lead


def list_leads(limit: int = 200, status: str = "") -> List[Dict[str, Any]]:
    q = "SELECT * FROM leads"
    args: List[Any] = []
    if status:
        q += " WHERE status = ?"
        args.append(status)
    q += " ORDER BY created_at DESC LIMIT ?"
    args.append(limit)
    with conn() as c:
        return [dict(r) for r in c.execute(q, args)]


def update_lead(lead_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
    allowed = {"name", "phone", "service", "message", "status", "visit_time", "notes", "intent"}
    sets = {k: v for k, v in fields.items() if k in allowed}
    if not sets:
        return get_lead(lead_id)
    clause = ", ".join(f"{k}=:{k}" for k in sets)
    sets["id"] = lead_id
    with _WRITE_LOCK, conn() as c:
        c.execute(f"UPDATE leads SET {clause} WHERE id=:id", sets)
    return get_lead(lead_id)


def get_lead(lead_id: str) -> Optional[Dict[str, Any]]:
    with conn() as c:
        return _row_to_dict(c.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone())


def delete_lead(lead_id: str) -> bool:
    with _WRITE_LOCK, conn() as c:
        cur = c.execute("DELETE FROM leads WHERE id=?", (lead_id,))
    return cur.rowcount > 0


def lead_stats() -> Dict[str, Any]:
    with conn() as c:
        total = c.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        today = c.execute(
            "SELECT COUNT(*) FROM leads WHERE substr(created_at,1,10)=?", (datetime.now().strftime("%Y-%m-%d"),)
        ).fetchone()[0]
        by_source = {
            r["source"]: r["n"]
            for r in c.execute("SELECT source, COUNT(*) n FROM leads GROUP BY source")
        }
        by_status = {
            r["status"]: r["n"]
            for r in c.execute("SELECT status, COUNT(*) n FROM leads GROUP BY status")
        }
    return {"total": total, "today": today, "by_source": by_source, "by_status": by_status}


def export_leads_csv() -> Path:
    """Free, instant CSV backup of every lead."""
    rows = list_leads(limit=100000)
    path = config.EXPORT_DIR / "leads.csv"
    cols = ["id", "name", "phone", "service", "message", "source",
            "intent", "language", "status", "visit_time", "notes", "created_at"]
    with _WRITE_LOCK, open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cols})
    log("INFO", "leads", f"CSV export written: {path.name} ({len(rows)} rows)")
    return path


# ---------------------------------------------------------------------------
# APPOINTMENTS
# ---------------------------------------------------------------------------
def add_appointment(lead_id: str = "", name: str = "", phone: str = "",
                    service: str = "", visit_date: str = "", visit_time: str = "") -> Dict[str, Any]:
    appt = {
        "id": new_id("appt_"),
        "lead_id": lead_id,
        "name": name,
        "phone": phone,
        "service": service,
        "visit_date": visit_date,
        "visit_time": visit_time,
        "status": "booked",
        "created_at": now(),
    }
    with _WRITE_LOCK, conn() as c:
        c.execute(
            """INSERT INTO appointments (id,lead_id,name,phone,service,visit_date,visit_time,status,created_at)
               VALUES (:id,:lead_id,:name,:phone,:service,:visit_date,:visit_time,:status,:created_at)""",
            appt,
        )
    log("INFO", "appointments", f"Visit booked: {name or '(no name)'} — {service} — {visit_date} {visit_time}")
    return appt


def list_appointments(limit: int = 200) -> List[Dict[str, Any]]:
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM appointments ORDER BY created_at DESC LIMIT ?", (limit,))]


# ---------------------------------------------------------------------------
# CONTENT  (Agent 3 / 4 / 5 post + caption + media records)
# ---------------------------------------------------------------------------
def add_content(platform: str, topic: str, language: str, caption: str,
                hashtags: str, media_path: str = "") -> Dict[str, Any]:
    row = {
        "id": new_id("cnt_"),
        "platform": platform,
        "topic": topic,
        "language": language,
        "caption": caption,
        "hashtags": hashtags,
        "media_path": media_path,
        "status": "draft",
        "published_at": "",
        "created_at": now(),
    }
    with _WRITE_LOCK, conn() as c:
        c.execute(
            """INSERT INTO content (id,platform,topic,language,caption,hashtags,
                                    media_path,status,published_at,created_at)
               VALUES (:id,:platform,:topic,:language,:caption,:hashtags,
                       :media_path,:status,:published_at,:created_at)""",
            row,
        )
    log("INFO", "content", f"Content generated for {platform}: {topic}")
    return row


def list_content(platform: str = "", limit: int = 100) -> List[Dict[str, Any]]:
    q, args = "SELECT * FROM content", []
    if platform:
        q += " WHERE platform=?"
        args.append(platform)
    q += " ORDER BY created_at DESC LIMIT ?"
    args.append(limit)
    with conn() as c:
        return [dict(r) for r in c.execute(q, args)]


def update_content(content_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
    allowed = {"caption", "hashtags", "media_path", "status", "published_at", "topic", "language"}
    sets = {k: v for k, v in fields.items() if k in allowed}
    if not sets:
        return None
    clause = ", ".join(f"{k}=:{k}" for k in sets)
    sets["id"] = content_id
    with _WRITE_LOCK, conn() as c:
        c.execute(f"UPDATE content SET {clause} WHERE id=:id", sets)
    return get_content(content_id)


def get_content(content_id: str) -> Optional[Dict[str, Any]]:
    with conn() as c:
        return _row_to_dict(c.execute("SELECT * FROM content WHERE id=?", (content_id,)).fetchone())


def pending_content(platform: str, limit: int = 5) -> List[Dict[str, Any]]:
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM content WHERE platform=? AND status='draft' ORDER BY created_at LIMIT ?",
            (platform, limit))]


# ---------------------------------------------------------------------------
# JOBS  (video rendering / heavy work progress tracking)
# ---------------------------------------------------------------------------
def create_job(kind: str, title: str) -> Dict[str, Any]:
    row = {
        "id": new_id("job_"), "kind": kind, "title": title, "status": "queued",
        "progress": 0, "message": "Queued…", "result": "", "created_at": now(), "updated_at": now(),
    }
    with _WRITE_LOCK, conn() as c:
        c.execute(
            """INSERT INTO jobs (id,kind,title,status,progress,message,result,created_at,updated_at)
               VALUES (:id,:kind,:title,:status,:progress,:message,:result,:created_at,:updated_at)""",
            row,
        )
    return row


def update_job(job_id: str, **fields: Any) -> None:
    allowed = {"status", "progress", "message", "result"}
    sets = {k: v for k, v in fields.items() if k in allowed}
    sets["id"] = job_id
    sets["updated_at"] = now()
    clause = ", ".join(f"{k}=:{k}" for k in sets)
    with _WRITE_LOCK, conn() as c:
        c.execute(f"UPDATE jobs SET {clause} WHERE id=:id", sets)


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with conn() as c:
        return _row_to_dict(c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())


def list_jobs(limit: int = 30) -> List[Dict[str, Any]]:
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,))]


def recover_stale_jobs() -> int:
    """
    A job left in 'running' belongs to a process that has already exited (the
    server was closed mid-render). Mark it interrupted so the dashboard is
    honest instead of showing a progress bar that will never move.
    """
    with _WRITE_LOCK, conn() as c:
        cur = c.execute(
            "UPDATE jobs SET status='failed', message=?, updated_at=? WHERE status='running'",
            ("Server band ho gaya tha — render adhoora reh gaya. Dobara try karein.", now()),
        )
    return cur.rowcount


# ---------------------------------------------------------------------------
# CONVERSATIONS  (WhatsApp / IG / FB / TikTok + website chat memory)
# ---------------------------------------------------------------------------
import json  # noqa: E402


def upsert_conversation(channel: str, contact: str, **fields: Any) -> Dict[str, Any]:
    with _WRITE_LOCK, conn() as c:
        row = c.execute(
            "SELECT * FROM conversations WHERE channel=? AND contact=?",
            (channel, contact)).fetchone()
        if row is None:
            base = {
                "id": new_id("cnv_"), "channel": channel, "contact": contact,
                "name": "", "phone": "", "last_lang": "", "state": "{}",
                "last_text": "", "last_reply": "", "status": "open",
                "updated_at": now(),
            }
            allowed = {"name", "phone", "last_lang", "last_text", "last_reply", "status", "state"}
            for k, v in fields.items():
                if k in allowed:
                    base[k] = v if k != "state" else json.dumps(v, ensure_ascii=False)
            c.execute(
                """INSERT INTO conversations (id,channel,contact,name,phone,last_lang,state,
                                              last_text,last_reply,status,updated_at)
                   VALUES (:id,:channel,:contact,:name,:phone,:last_lang,:state,
                           :last_text,:last_reply,:status,:updated_at)""",
                base,
            )
            return base
        d = dict(row)
        allowed = {"name", "phone", "last_lang", "last_text", "last_reply", "status", "state"}
        for k, v in fields.items():
            if k in allowed:
                d[k] = v if k != "state" else json.dumps(v, ensure_ascii=False)
        d["updated_at"] = now()
        c.execute(
            """UPDATE conversations SET name=:name, phone=:phone, last_lang=:last_lang,
                       state=:state, last_text=:last_text, last_reply=:last_reply,
                       status=:status, updated_at=:updated_at
               WHERE id=:id""", d)
        return d


def get_conversation(channel: str, contact: str) -> Optional[Dict[str, Any]]:
    with conn() as c:
        row = c.execute("SELECT * FROM conversations WHERE channel=? AND contact=?",
                        (channel, contact)).fetchone()
        if row is None:
            return None
        d = dict(row)
        try:
            d["state"] = json.loads(d.get("state") or "{}")
        except Exception:
            d["state"] = {}
        return d


def list_conversations(limit: int = 100) -> List[Dict[str, Any]]:
    with conn() as c:
        out = []
        for r in c.execute("SELECT * FROM conversations ORDER BY updated_at DESC LIMIT ?", (limit,)):
            d = dict(r)
            try:
                d["state"] = json.loads(d.get("state") or "{}")
            except Exception:
                d["state"] = {}
            out.append(d)
        return out


# ---------------------------------------------------------------------------
# LOGS
# ---------------------------------------------------------------------------
def log(level: str, source: str, message: str) -> None:
    try:
        with _WRITE_LOCK, conn() as c:
            c.execute("INSERT INTO logs (ts,level,source,message) VALUES (?,?,?,?)",
                      (now(), level.upper(), source, message))
    except Exception:
        pass


def recent_logs(limit: int = 120) -> List[Dict[str, Any]]:
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,))]


# ---------------------------------------------------------------------------
# KV  (tiny key/value store — used for "already replied" message markers)
# ---------------------------------------------------------------------------
def kv_get(key: str, default: Any = None) -> Any:
    with conn() as c:
        r = c.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
    return r["value"] if r is not None else default


def kv_set(key: str, value: str) -> None:
    with _WRITE_LOCK, conn() as c:
        c.execute(
            "INSERT INTO kv (key,value,updated_at) VALUES (?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, str(value), now()),
        )


def kv_del(key: str) -> None:
    with _WRITE_LOCK, conn() as c:
        c.execute("DELETE FROM kv WHERE key=?", (key,))


def kv_prefix_count(prefix: str) -> int:
    with conn() as c:
        return c.execute("SELECT COUNT(*) FROM kv WHERE key LIKE ?", (prefix + "%",)).fetchone()[0]