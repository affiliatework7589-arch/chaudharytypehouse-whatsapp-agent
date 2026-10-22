# -*- coding: utf-8 -*-
"""
Chaudhary Type House & Property Advisors - Global Configuration
100% FREE / Zero-Investment / Zero-Paid-API system configuration.

Every business constant used anywhere in the system lives here so that the
website, the AI assistant, the WhatsApp bot, the Instagram/Facebook/TikTok
agents and the auto-poster/video-maker all stay perfectly in sync.
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# DIRECTORIES
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "leads.db"
EXPORT_DIR = DATA_DIR / "exports"
MEDIA_DIR = DATA_DIR / "media"
VIDEO_DIR = MEDIA_DIR / "videos"
BANNER_DIR = MEDIA_DIR / "banners"
AUDIO_DIR = MEDIA_DIR / "audio"
PROFILE_DIR = DATA_DIR / "browser_profiles"
LOG_DIR = DATA_DIR / "logs"
UPLOAD_DIR = DATA_DIR / "uploads"

ALL_DIRS = [
    DATA_DIR, EXPORT_DIR, MEDIA_DIR, VIDEO_DIR,
    BANNER_DIR, AUDIO_DIR, PROFILE_DIR, LOG_DIR, UPLOAD_DIR,
]

for _d in ALL_DIRS:
    _d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# BUSINESS DETAILS  (embedded everywhere)
# ---------------------------------------------------------------------------
SHOP_NAME = "Chaudhary Type House & Property Advisors"
SHOP_NAME_UR = "چوہدری ٹائپ ہاؤس اینڈ پراپرٹی ایڈوائزرز"
OWNER_NAME = "Chaudhary Muhammad Sanaullah"
OWNER_NAME_UR = "چوہدری محمد سنا اللہ"

ADDRESS = "Near Baldia Chowk, City Chishtian"
ADDRESS_UR = "نزد بلدیہ چوک، شہر چشتیاں"
TIMING = "Subah 8:00 AM se Shaam 8:00 PM tak"
TIMING_UR = "صبح ۸ بجے سے شام ۸ بجے تک"
HOURS_OPEN = "08:00 AM"
HOURS_CLOSE = "08:00 PM"
WEEKLY_OFF = None  # Chishtian Type House khula hai poore hafte

PHONE_DIGITS = "923277450361"                 # wa.me international format (no +)
PHONE_DISPLAY = "0327-7450361"
PHONE_INTL = "+92 327 7450361"
WHATSAPP_LINK = f"https://wa.me/{PHONE_DIGITS}"
CALCULATOR_URL = "https://chtype.online"
CALCULATOR_NAME = "Online Registry Kharcha Calculator"

BRAND_TAGLINE = "Registry • Inteqal • Fard • Property — Chishtian"
BRAND_TAGLINE_UR = "رجسٹری • انتقال • فرد • پراپرٹی — چشتیاں"

# ---------------------------------------------------------------------------
# THEME  (Emerald Green & Gold)
# ---------------------------------------------------------------------------
THEME = {
    "emerald_dark": "#04352b",
    "emerald": "#046b4d",
    "emerald_light": "#0fa678",
    "gold": "#d4af37",
    "gold_light": "#f2d579",
    "cream": "#fbf7ea",
    "ink": "#06231c",
}

# ---------------------------------------------------------------------------
# AI ENGINE  (100% offline rule engine + OPTIONAL free Gemini tier)
# ---------------------------------------------------------------------------
# Leave GEMINI_API_KEY empty to run fully offline. If set to a *free tier*
# Google AI Studio key the engine blends in smarter answers, but NEVER requires it.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_ENABLED = bool(GEMINI_API_KEY)
AI_PROVIDER = "Gemini (free) + Built-in Engine" if GEMINI_ENABLED else "Built-in Offline Engine"

# ---------------------------------------------------------------------------
# FREE TEXT-TO-SPEECH (Microsoft edge-tts - free, no key, no signup)
# ---------------------------------------------------------------------------
TTS_VOICES = {
    "urdu": "ur-PK-UzmaNeural",     # Urdu narration
    "roman": "hi-IN-SwaraNeural",   # Roman Urdu / Hindi narration (reads Latin script well)
    "male_urdu": "ur-PK-SalmaNeural",
    "english": "en-US-AriaNeural",
}
TTS_LANG = os.environ.get("TTS_LANG", "roman").strip()

# ---------------------------------------------------------------------------
# INSTAGRAM SEO HASHTAGS  (Chishtian + real estate, 15 per post)
# ---------------------------------------------------------------------------
BASE_HASHTAGS = [
    "ChishtianProperty", "ChishtianRealEstate", "ChishtianPropertyDealer",
    "ChaudharyTypeHouse", "ZameenKharidChishtian", "PropertyAdvisorChishtian",
    "JamabandiChishtian", "RegistryKarcha", "ZameenRegistry", "PropertyInChishtian",
    "PlotsForSaleChishtian", "Zaraizameen", "ChishtianCity", "PunjabProperty",
    "RealEstatePakistan",
]

INSTAGRAM_REACH_HASHTAGS = [
    "chtypeonline", "OnlineApplyCenter", "NADRAeSahulat", "DomicileTyping",
    "PropertyPakistan", "RealEstateTrends", "HouseForSale", "InvestmentProperty",
    "ChishtianLiving", "PropertyInvestment",
]

# ---------------------------------------------------------------------------
# SOCIAL PLATFORM CONFIG  (browser automation only - NO APIs, NO webhooks, $0)
# ---------------------------------------------------------------------------
PLATFORMS = {
    "whatsapp": {
        "name": "WhatsApp Web",
        "url": "https://web.whatsapp.com/",
        "profile": "whatsapp",
        "agent": 2,
        "color": "#25D366",
    },
    "instagram": {
        "name": "Instagram",
        "url": "https://www.instagram.com/",
        "profile": "instagram",
        "agent": 3,
        "color": "#E1306C",
    },
    "facebook": {
        "name": "Facebook Page",
        "url": "https://www.facebook.com/",
        "profile": "facebook",
        "agent": 4,
        "color": "#1877F2",
    },
    "tiktok": {
        "name": "TikTok",
        "url": "https://www.tiktok.com/",
        "profile": "tiktok",
        "agent": 5,
        "color": "#FE2C55",
    },
}

# ---------------------------------------------------------------------------
# AGENT SETTINGS  (auto-send ON by default, kill switch in dashboard)
# ---------------------------------------------------------------------------
AUTO_SEND_DEFAULT = True
AGENT_POLL_SECONDS = {
    "whatsapp": 20,
    "instagram": 45,
    "facebook": 45,
    "tiktok": 45,
}

# Global kill switch file - if this file exists, ALL agents refuse to send.
KILL_SWITCH_FILE = DATA_DIR / "AGENTS_PAUSED"

# ---------------------------------------------------------------------------
# SERVER
# ---------------------------------------------------------------------------
HOST = os.environ.get("CTH_HOST", "127.0.0.1")
PORT = int(os.environ.get("CTH_PORT", "8000"))

# ---------------------------------------------------------------------------
# FONT AUTO-DETECTION  (free system fonts only - nothing downloaded)
# ---------------------------------------------------------------------------
URDU_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\JameelNooriNastaleeq.ttf",
    r"C:\Windows\Fonts\NotoNastaliqUrdu-Regular.ttf",
    r"C:\Windows\Fonts\NotoNaskhArabic-Regular.ttf",
    r"C:\Windows\Fonts\UrduTypesetting-Regular.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
    "/usr/share/fonts/truetype/noto/NotoNastaliqUrdu-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
    "/System/Library/Fonts/Supplemental/Noto Nastaliq Urdu.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
]

LATIN_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\segoeuib.ttf",
    r"C:\Windows\Fonts\seguisb.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]

# ---------------------------------------------------------------------------
# VIDEO
# ---------------------------------------------------------------------------
VIDEO_W = 1080
VIDEO_H = 1920
RENDER_W = 540          # render at half size, ffmpeg upscales (fast + free)
RENDER_H = 960
VIDEO_FPS = 30