# -*- coding: utf-8 -*-
"""
agents/base.py — Shared base class for all 5 agents.

Each agent runs in its OWN daemon thread (so Playwright's sync API never fights
with FastAPI's asyncio loop). A global kill-switch file
(data/AGENTS_PAUSED) plus an in-memory `enabled` flag lets the dashboard stop
every agent instantly — that is the panic button for auto-send.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, List, Optional

import config
from core import db


class BaseAgent:
    id: int = 0
    name: str = "Agent"
    platform: str = ""
    interval: int = 30
    icon: str = "🤖"
    description: str = ""

    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.enabled = config.AUTO_SEND_DEFAULT
        self.auto_send = config.AUTO_SEND_DEFAULT
        self.status = "stopped"          # stopped | starting | running | paused | error
        self.last_run = ""
        self.last_error = ""
        self.runs = 0
        self.replies_sent = 0
        self.posts_published = 0
        self.detail: Dict[str, Any] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ #
    # kill switch
    # ------------------------------------------------------------------ #
    @staticmethod
    def paused_globally() -> bool:
        return config.KILL_SWITCH_FILE.exists()

    def may_send(self) -> bool:
        """The single 'is it safe to send right now' gate for every agent."""
        if self.paused_globally():
            db.log("WARN", self.name, "Global KILL SWITCH active — kuch nahi bheja gaya.")
            return False
        if not self.auto_send:
            return False
        return True

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #
    def start(self) -> Dict[str, Any]:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return self.info()
            self._stop.clear()
            self.enabled = True
            self.status = "starting"
            self._thread = threading.Thread(target=self._loop, name=self.name, daemon=True)
            self._thread.start()
            db.log("INFO", self.name, f"{self.name} shuru ho gaya (har {self.interval}s).")
        return self.info()

    def stop(self) -> Dict[str, Any]:
        with self._lock:
            self._stop.set()
            self.enabled = False
            self.status = "stopped"
            db.log("INFO", self.name, f"{self.name} band kar diya gaya.")
        return self.info()

    def restart(self) -> Dict[str, Any]:
        self.stop()
        time.sleep(1.0)
        return self.start()

    def set_auto_send(self, value: bool) -> Dict[str, Any]:
        self.auto_send = bool(value)
        db.log("INFO", self.name,
               f"Auto-send {'ON' if self.auto_send else 'OFF'} set kiya gaya.")
        return self.info()

    def _loop(self) -> None:
        self.status = "running"
        # give the browser session a moment to boot
        self._stop.wait(3)
        while not self._stop.is_set():
            try:
                self.run_once()
                self.runs += 1
                self.last_run = db.now()
                self.status = "paused" if self.paused_globally() else "running"
            except Exception as exc:
                self.last_error = str(exc)
                self.status = "error"
                db.log("ERROR", self.name, f"Run error: {exc}")
            # responsive stop: sleep in small slices
            waited = 0.0
            while waited < self.interval and not self._stop.is_set():
                self._stop.wait(1.0)
                waited += 1.0

    # ------------------------------------------------------------------ #
    def run_once(self) -> None:      # pragma: no cover - overridden
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    def info(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "platform": self.platform,
            "icon": self.icon,
            "description": self.description,
            "status": self.status,
            "enabled": self.enabled,
            "auto_send": self.auto_send,
            "globally_paused": self.paused_globally(),
            "interval": self.interval,
            "runs": self.runs,
            "replies_sent": self.replies_sent,
            "posts_published": self.posts_published,
            "last_run": self.last_run,
            "last_error": self.last_error,
            "detail": self.detail,
        }


# ---------------------------------------------------------------------------
# Global pause switch (used by the dashboard's red KILL button)
# ---------------------------------------------------------------------------
def set_global_pause(paused: bool) -> bool:
    if paused:
        config.KILL_SWITCH_FILE.write_text("paused by owner", encoding="utf-8")
    elif config.KILL_SWITCH_FILE.exists():
        try:
            config.KILL_SWITCH_FILE.unlink()
        except Exception:
            pass
    db.log("WARN", "system",
           "GLOBAL AGENT PAUSE ON — sab auto-replies band" if paused else "Agents dobara chal rahe hain.")
    return BaseAgent.paused_globally()


# ---------------------------------------------------------------------------
# Small helpers shared by the browser agents
# ---------------------------------------------------------------------------
def seen_before(key: str) -> bool:
    return db.kv_get(f"seen:{key}") is not None


def mark_seen(key: str, value: str = "1") -> None:
    db.kv_set(f"seen:{key}", value)


def note(msg: str, level: str = "INFO") -> None:
    db.log(level, "agent", msg)


def clean_incoming(text: str) -> str:
    """Strip WhatsApp/IG system prefixes so the AI brain reads clean text."""
    import re
    out = text or ""
    out = re.sub(r"^\[\d{1,2}/\d{1,2}/\d{2,4},?\s*\d{1,2}:\d{2}(?::\d{2})?\s*(?:[APap]\.?[Mm]\.?)?\]\s*", "", out)
    out = re.sub(r"^[‹‹\s]+\d{1,2}/\d{1,2}/\d{2,4}[››\s]*", "", out)
    out = re.sub(r"^Messages and calls are end-to-end encrypted.*$", "", out,
                 flags=re.MULTILINE | re.IGNORECASE)
    return out.strip()