# -*- coding: utf-8 -*-
"""
core/browser.py — FREE browser-automation session manager (Playwright).

WHY THIS IS ZERO COST
---------------------
There is no WhatsApp Cloud API, no Meta Graph API, no TikTok developer app and
no paid webhook anywhere in this system. Instead we open a REAL, persistent
Chromium profile (headed) on the user's own machine:

    1. First run  -> QR code / login page appears in a normal browser window.
    2. User scans the QR with their phone (WhatsApp) or types their password
       (Instagram / Facebook / TikTok).  Done — once.
    3. The profile folder (data/browser_profiles/<name>) keeps the login, so
       every later run is already signed in.  Zero API keys, zero cost.

Every session is fully controllable from the dashboard: start, stop, navigate,
screenshot (so the QR code can be shown INSIDE the dashboard), and run one tick.
"""

from __future__ import annotations

import base64
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import config
from core import db


class BrowserNotInstalled(RuntimeError):
    pass


class BrowserSession:
    """One persistent, logged-in browser per platform."""

    def __init__(self, name: str, url: str, label: str = ""):
        self.name = name
        self.url = url
        self.label = label or name
        self.user_data_dir = config.PROFILE_DIR / name
        self.user_data_dir.mkdir(parents=True, exist_ok=True)

        self._pw = None
        self._ctx = None
        self._page = None
        self._lock = threading.RLock()
        self.state = "stopped"          # stopped | starting | ready | logged_out | error
        self.last_error = ""
        self.last_seen_url = ""
        self.logged_in = False
        self.started_at = 0.0

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #
    def start(self) -> Dict[str, Any]:
        with self._lock:
            if self._ctx is not None:
                return self.info()
            self.state = "starting"
            self.last_error = ""
            try:
                from playwright.sync_api import sync_playwright
            except Exception as exc:  # pragma: no cover
                self.state = "error"
                self.last_error = (f"Playwright install nahi hai: {exc}. "
                                   "run.bat / run.sh dobara chala dein.")
                db.log("ERROR", self.name, self.last_error)
                return self.info()

            try:
                self._pw = sync_playwright().start()
                self._ctx = self._pw.chromium.launch_persistent_context(
                    user_data_dir=str(self.user_data_dir),
                    headless=False,                      # headed: user scans the QR
                    viewport={"width": 1280, "height": 860},
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-blink-features=AutomationControlled",
                        "--no-first-run",
                        "--no-default-browser-check",
                        "--disable-notifications",
                        "--start-maximized",
                        "--lang=en-US",
                    ],
                    ignore_default_args=["--enable-automation"],
                    timeout=90_000,
                )
                self._ctx.set_default_timeout(20_000)
                pages = self._ctx.pages
                self._page = pages[0] if pages else self._ctx.new_page()
                self._goto(self.url)
                self.state = "ready"
                self.started_at = time.time()
                db.log("INFO", self.name,
                       f"{self.label} browser khuli. Agar QR aaye to scan kar lein "
                       f"(login ke baad ye status 'logged in' ho jayega).")
            except Exception as exc:
                self.state = "error"
                self.last_error = str(exc)
                db.log("ERROR", self.name, f"Browser start fail: {exc}")
                self._hard_close()
            return self.info()

    def _hard_close(self) -> None:
        for obj, meth in ((self._ctx, "close"), (self._pw, "stop")):
            try:
                if obj is not None:
                    getattr(obj, meth)()
            except Exception:
                pass
        self._ctx = None
        self._pw = None
        self._page = None

    def stop(self) -> Dict[str, Any]:
        with self._lock:
            self._hard_close()
            self.state = "stopped"
            self.logged_in = False
            db.log("INFO", self.name, f"{self.label} browser band kar di gayi.")
        return self.info()

    def restart(self) -> Dict[str, Any]:
        self.stop()
        time.sleep(1.5)
        return self.start()

    # ------------------------------------------------------------------ #
    # page helpers
    # ------------------------------------------------------------------ #
    @property
    def page(self):
        return self._page

    def ensure(self):
        if self._ctx is None:
            self.start()
        if self._ctx is None:
            raise BrowserNotInstalled(self.last_error or "Browser available nahi hai")
        return self._ctx

    def _goto(self, url: str) -> None:
        try:
            self._page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            self.last_seen_url = self._page.url
        except Exception as exc:
            self.last_error = f"goto failed: {exc}"

    def navigate(self, url: str) -> Dict[str, Any]:
        with self._lock:
            self.ensure()
            if self._page is None:
                return {"ok": False, "error": self.last_error}
            try:
                self._page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                self.last_seen_url = self._page.url
                return {"ok": True, "url": self._page.url}
            except Exception as exc:
                return {"ok": False, "error": str(exc)}

    def reload(self) -> Dict[str, Any]:
        with self._lock:
            self.ensure()
            try:
                self._page.reload(wait_until="domcontentloaded", timeout=45_000)
                return {"ok": True, "url": self._page.url}
            except Exception as exc:
                return {"ok": False, "error": str(exc)}

    def click(self, selectors: List[str], timeout: int = 8000) -> bool:
        """Try a list of CSS/text selectors in order. First hit wins."""
        for sel in selectors:
            try:
                loc = self._page.locator(sel).first
                if loc.count() and loc.is_visible():
                    loc.click(timeout=timeout)
                    return True
            except Exception:
                continue
        return False

    def fill(self, selectors: List[str], text: str, timeout: int = 8000) -> bool:
        for sel in selectors:
            try:
                loc = self._page.locator(sel).first
                if loc.count() and loc.is_visible():
                    loc.fill(text, timeout=timeout)
                    return True
            except Exception:
                continue
        return False

    def wait(self, seconds: float) -> None:
        try:
            self.ensure()
            self._page.wait_for_timeout(int(seconds * 1000))
        except Exception:
            pass

    def screenshot_b64(self, full: bool = False, quality: int = 70,
                       max_w: int = 1100) -> Optional[str]:
        """PNG/JPEG as base64 so the dashboard can show the live QR code."""
        try:
            self.ensure()
            if self._page is None:
                return None
            import io
            data = self._page.screenshot(full_page=full, type="jpeg", quality=quality)
            img = None
            try:
                from PIL import Image
                img = Image.open(io.BytesIO(data))
                if img.width > max_w:
                    img = img.resize((max_w, int(img.height * max_w / img.width)))
                buf = io.BytesIO()
                img.save(buf, "JPEG", quality=80)
                data = buf.getvalue()
            except Exception:
                pass
            return base64.b64encode(data).decode("ascii")
        except Exception as exc:
            self.last_error = str(exc)
            return None

    # ------------------------------------------------------------------ #
    # login detection (per platform, best-effort / heuristic)
    # ------------------------------------------------------------------ #
    def detect_login(self) -> bool:
        try:
            self.ensure()
            if self._page is None:
                return False
            url = (self._page.url or "").lower()
            body = ""
            try:
                body = (self._page.inner_text("body", timeout=6000) or "").lower()
            except Exception:
                pass
            self.last_seen_url = self._page.url

            if self.name == "whatsapp":
                if "qr" in url or "appverification" in url:
                    self.logged_in = False
                if "unread" in body or "chats" in body or "web.whatsapp.com" == url:
                    self.logged_in = "unread" in body or ("web.whatsapp.com" in url and "qr" not in url)
            elif self.name == "instagram":
                self.logged_in = any(k in url for k in ("/accounts", "/direct", "/explore", "/reels"))
            elif self.name == "facebook":
                self.logged_in = "login" not in url and "checkpoint" not in url
            elif self.name == "tiktok":
                self.logged_in = "login" not in url and any(
                    k in url for k in ("/upload", "/messages", "/following", "/foryou", "/@"))
            self.state = "ready" if self.logged_in else ("ready" if self._ctx else "stopped")
        except Exception:
            self.logged_in = False
        return self.logged_in

    def info(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "state": self.state,
            "logged_in": self.logged_in,
            "url": self.last_seen_url,
            "error": self.last_error,
            "profile_dir": str(self.user_data_dir),
            "uptime": round(time.time() - self.started_at, 1) if self.started_at else 0,
        }


# ---------------------------------------------------------------------------
# REGISTRY — one session per platform
# ---------------------------------------------------------------------------
class SessionRegistry:
    def __init__(self) -> None:
        self._sessions: Dict[str, BrowserSession] = {}
        for name, meta in config.PLATFORMS.items():
            self._sessions[name] = BrowserSession(name, meta["url"], meta["name"])

    def get(self, name: str) -> BrowserSession:
        if name not in self._sessions:
            raise KeyError(f"Unknown session: {name}")
        return self._sessions[name]

    def all(self) -> List[BrowserSession]:
        return list(self._sessions.values())

    def info(self) -> List[Dict[str, Any]]:
        return [s.info() for s in self._sessions.values()]

    def stop_all(self) -> None:
        for s in self._sessions.values():
            try:
                s.stop()
            except Exception:
                pass


SESSIONS = SessionRegistry()


def playwright_installed() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except Exception:
        return False


def playwright_browsers_installed() -> bool:
    """True when a chromium build is actually downloaded (~/.cache/ms-playwright)."""
    try:
        from playwright.sync_api import sync_playwright
        p = sync_playwright().start()
        exe = p.chromium.executable_path
        p.stop()
        return bool(exe) and Path(exe).exists()
    except Exception:
        return False