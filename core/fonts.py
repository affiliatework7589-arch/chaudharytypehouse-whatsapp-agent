# -*- coding: utf-8 -*-
"""
core/fonts.py — FREE Urdu/Arabic font manager + complex-script shaping.

TWO PROBLEMS THIS SOLVES (both are 100% fixable at zero cost):

1. Pillow only performs Arabic letter-joining and bidi re-ordering when it is
   built with **libraqm**. The plain Windows wheel is not. Without it Urdu comes
   out as disconnected, reversed letters.
   -> We fix it in pure Python with the free packages `arabic-reshaper`
      (letter joining) + `python-bidi` (visual re-ordering). No binaries.

2. Windows ships good Arabic fonts (Traditional Arabic, Simplified Arabic,
   Sakkal Majalla, Arabic Typesetting, Segoe UI) but **no Nastaliq**.
   -> `ensure_urdu_font()` can download NOTO Nastaliq Urdu once from the
      Google Fonts repository (SIL Open Font License = free for commercial
      use) into `data/fonts/`. Cached forever, optional, ~300 KB.

If neither is available the graphics engine silently falls back to readable
Roman Urdu instead of emitting broken Urdu.
"""

from __future__ import annotations

import os
import shutil
from functools import lru_cache
from pathlib import Path
from typing import Optional, Tuple

import config
from core import db

FONT_DIR = config.DATA_DIR / "fonts"
FONT_DIR.mkdir(parents=True, exist_ok=True)

# Free, SIL Open Font License — safe for commercial use.
NOTO_NASTALIQ_URL = ("https://github.com/googlefonts/noto-fonts/raw/main/"
                     "hinted/ttf/NotoNastaliqUrdu/NotoNastaliqUrdu-Regular.ttf")
NOTO_NASKH_URL = ("https://github.com/notofonts/notofonts.github.io/raw/main/"
                  "fonts/NotoNaskhArabic/hinted/ttf/NotoNaskhArabic-Regular.ttf")

_LOCAL_URDU: Optional[str] = None
_SHAPING: Optional[Tuple[object, object]] = None
_NOTO_B64: Optional[str] = None


# ---------------------------------------------------------------------------
# Shaping (pure Python, free)
# ---------------------------------------------------------------------------
def shaping_available() -> bool:
    try:
        import arabic_reshaper  # noqa: F401
        from bidi.algorithm import get_display  # noqa: F401
        return True
    except Exception:
        return False


def raqm_available() -> bool:
    """True when Pillow itself can shape Arabic (best case, no pre-shaping)."""
    try:
        from PIL import ImageFont
        return bool(getattr(ImageFont.core, "HAVE_RAQM", False))
    except Exception:
        return False


def shape(text: str) -> str:
    """
    Convert logical-order Urdu/Arabic into visual order with correct joining.
    Returns the text unchanged when shaping libraries are unavailable.

    NOTE: always feed the ORIGINAL logical text. Never pass already-shaped text
    back in — bidi re-ordering is not idempotent.
    """
    global _SHAPING
    if not text or not any("\u0600" <= c <= "\u06FF" for c in text):
        return text
    if raqm_available():
        return text                      # Pillow does it natively
    if _SHAPING is None:
        try:
            import arabic_reshaper
            from bidi.algorithm import get_display
            _SHAPING = (arabic_reshaper, get_display)
        except Exception:
            _SHAPING = (None, None)
    reshaper, get_display = _SHAPING          # type: ignore[misc]
    if reshaper is None:
        return text
    try:
        return get_display(reshaper.reshape(text))
    except Exception:
        return text


_shape_cached = lru_cache(maxsize=8192)(shape)


# ---------------------------------------------------------------------------
# Font resolution
# ---------------------------------------------------------------------------
def _covers_shaped(path: str, probe: int = 32) -> bool:
    """
    A font is only usable for our Pillow path if it actually contains the
    Arabic Presentation Forms that arabic_reshaper emits (many modern fonts,
    including Noto Nastaliq Urdu, contain base codepoints only and rely on
    HarfBuzz — which plain Pillow does not have).
    """
    try:
        from PIL import ImageFont
        f = ImageFont.truetype(path, probe)
    except Exception:
        return False
    try:
        ref = f.getmask("\ufffe").getbbox()
        shaped = shape("\u0679\u06c1\u06cc\u06a9\u06d2 \u0633\u06d2 \u0632\u0645\u06cc\u0646 "
                       "\u06a9\u06cc \u0627\u0635\u0644 \u062d\u0627\u0644\u062a\u06cc \u06a9\u06cc\u0633\u06d2")
        for ch in set(shaped):
            if ord(ch) < 0x0600:
                continue
            if f.getmask(ch).getbbox() == ref:
                return False
        return True
    except Exception:
        return False


def _find_system_font() -> Optional[str]:
    win_dir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    # Order matters: we need BOTH an Arabic font AND Presentation-Forms coverage.
    preferred = [
        "JameelNooriNastaleeq.ttf",       # if the user installed a real Nastaliq
        "segoeui.ttf",                    # ships with Windows, full coverage
        "segoeuib.ttf",
        "seguisb.ttf",
        "NotoNaskhArabic-Regular.ttf",
        "UrduTypesetting-Regular.ttf",
        "arabtype.ttf",
        "majalla.ttf",
        "trado.ttf",
        "simpo.ttf",
        "tahoma.ttf",
        "arial.ttf",
    ]
    roots = [FONT_DIR, win_dir, Path("/usr/share/fonts"), Path("/Library/Fonts")]
    fallback: Optional[str] = None
    for root in roots:
        for name in preferred:
            p = root / name
            if not p.exists():
                continue
            if _covers_shaped(str(p)):
                return str(p)
            fallback = fallback or str(p)
    for cand in config.URDU_FONT_CANDIDATES:
        if cand and Path(cand).exists():
            return cand
    return fallback


def urdu_font_path() -> Optional[str]:
    """Cached path of a font that can render Urdu (or None)."""
    global _LOCAL_URDU
    if _LOCAL_URDU is None:
        _LOCAL_URDU = _find_system_font() or ""
    return _LOCAL_URDU or None


def download_noto(silent: bool = False) -> Optional[str]:
    """
    One-time, FREE download of Noto Nastaliq Urdu (OFL licence).
    Returns the saved path, or None if offline / failed.
    """
    global _LOCAL_URDU
    target = FONT_DIR / "NotoNastaliqUrdu-Regular.ttf"
    if target.exists() and target.stat().st_size > 50_000:
        return str(target)
    try:
        import requests
        with requests.get(NOTO_NASTALIQ_URL, timeout=45, stream=True) as r:
            r.raise_for_status()
            tmp = target.with_suffix(".part")
            with open(tmp, "wb") as fh:
                for chunk in r.iter_content(8192):
                    fh.write(chunk)
        if tmp.stat().st_size < 50_000:
            raise RuntimeError("font file too small")
        tmp.replace(target)
        _LOCAL_URDU = str(target)
        db.log("INFO", "fonts", "Noto Nastaliq Urdu (FREE/OFL) download ho gaya — ab images par asli Nastaliq aayegi.")
        return str(target)
    except Exception as exc:
        if not silent:
            db.log("WARN", "fonts", f"Font download nahi hua ({exc}); system font use ho raha hai.")
        return None


def urdu_ready() -> bool:
    """True when Urdu text can be rendered *correctly* (font + shaping)."""
    return bool(urdu_font_path()) and (raqm_available() or shaping_available())


def browser_urdu_ready() -> bool:
    """
    True when Playwright is available so Urdu can be rendered by a real browser
    engine (full HarfBuzz shaping → perfect Nastaliq). Purely optional.
    """
    try:
        import playwright  # noqa: F401
        from playwright.sync_api import sync_playwright
        p = sync_playwright().start()
        ok = Path(p.chromium.executable_path).exists()
        p.stop()
        return ok
    except Exception:
        return False


def nastaliq_font_b64() -> str:
    """Base64 of the free Noto Nastaliq Urdu font, for HTML rendering."""
    global _NOTO_B64
    if _NOTO_B64 is None:
        p = FONT_DIR / "NotoNastaliqUrdu-Regular.ttf"
        if not p.exists():
            download_noto(silent=True)
        if p.exists():
            import base64
            _NOTO_B64 = base64.b64encode(p.read_bytes()).decode("ascii")
        else:
            _NOTO_B64 = ""
    return _NOTO_B64


def font_status() -> dict:
    p = urdu_font_path()
    return {
        "font": Path(p).name if p else "",
        "font_path": p or "",
        "font_ok": bool(p),
        "raqm": raqm_available(),
        "shaping_libs": shaping_available(),
        "noto_installed": (FONT_DIR / "NotoNastaliqUrdu-Regular.ttf").exists(),
        "urdu_renderable": urdu_ready(),
        "browser_urdu": browser_urdu_ready(),
        "note": (
            "Urdu images browser (Nastaliq) se render hoti hain."
            if browser_urdu_ready() else
            "Urdu images Pillow Naskh se render hoti hain (theek, joining sahi)."
            if urdu_ready() else
            "Urdu shaping available nahi — images par Roman Urdu use hoga (website par Urdu phir bhi theek hai)."
        ),
    }