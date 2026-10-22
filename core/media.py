# -*- coding: utf-8 -*-
"""
core/media.py — 100% FREE Auto-Poster + Viral Video Maker.

IMAGES : Pillow (free, pure-python imaging)  -> Instagram banners, FB covers,
         TikTok thumbnails, WhatsApp status cards.
VIDEOS : edge-tts (free Microsoft neural TTS, NO key) + FFmpeg (free, binary
         from imageio-ffmpeg) + Pillow frame rendering.
         Every video is generated with Urdu/Roman-Urdu text overlays that are
         SYNCED to the voice-over using edge-tts word-boundary timings.

No paid API. No watermark. No watermark service. No cloud render.
"""

from __future__ import annotations

import math
import os
import random
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import config
from core import db
from core import fonts as fontlib

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    PIL_AVAILABLE = True
except Exception:  # pragma: no cover
    PIL_AVAILABLE = False

try:
    import imageio_ffmpeg
    FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG_BIN = None

try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except Exception:
    EDGE_TTS_AVAILABLE = False


def ffmpeg_path() -> Optional[str]:
    """Locate a free FFmpeg binary: PATH first, then the pip-provided one."""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    return FFMPEG_BIN


# ---------------------------------------------------------------------------
# FONT RESOLUTION  (uses only fonts already on the machine - downloads nothing)
# ---------------------------------------------------------------------------
_FONT_CACHE: Dict[str, Any] = {}


def _first_existing(candidates: Sequence[str]) -> Optional[str]:
    for p in candidates:
        if p and Path(p).exists():
            return p
    return None


def urdu_font(size: int) -> Any:
    if not PIL_AVAILABLE:
        return None
    key = f"ur_{size}"
    if key not in _FONT_CACHE:
        p = fontlib.urdu_font_path() or _first_existing(config.URDU_FONT_CANDIDATES)
        if p is None:
            _FONT_CACHE[key] = None
        else:
            try:
                _FONT_CACHE[key] = ImageFont.truetype(p, size)
            except Exception:
                _FONT_CACHE[key] = None
    return _FONT_CACHE[key]


def latin_font(size: int, bold: bool = True) -> Any:
    if not PIL_AVAILABLE:
        return None
    key = f"lat_{size}_{bold}"
    if key not in _FONT_CACHE:
        cands = config.LATIN_FONT_CANDIDATES if bold else config.LATIN_FONT_CANDIDATES[2:]
        path = _first_existing(cands)
        if path is None:
            _FONT_CACHE[key] = ImageFont.load_default()
        else:
            try:
                _FONT_CACHE[key] = ImageFont.truetype(path, size)
            except Exception:
                _FONT_CACHE[key] = ImageFont.load_default()
    return _FONT_CACHE[key]


def urdu_supported() -> bool:
    """True when Urdu can be rendered CORRECTLY (Arabic font + shaping)."""
    return fontlib.urdu_ready()


def font_status() -> dict:
    return fontlib.font_status()


# ---------------------------------------------------------------------------
# COLOUR HELPERS
# ---------------------------------------------------------------------------
def hx(h: str) -> Tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore


def gradient(size: Tuple[int, int], c1: str, c2: str, angle: int = 135) -> "Image.Image":
    """Smooth linear gradient (no banding artefacts)."""
    w, h = size
    a, b = hx(c1), hx(c2)
    base = Image.new("RGB", (w, h), a)
    draw = ImageDraw.Draw(base)
    rad = math.radians(angle)
    dx, dy = math.cos(rad), math.sin(rad)
    span = abs(dx) * w + abs(dy) * h
    steps = 220
    for i in range(steps + 1):
        t = i / steps
        col = tuple(int(a[k] + (b[k] - a[k]) * t) for k in range(3))
        if dx >= 0:
            x0, x1 = int(t * w), int(t * w) + int(w / steps) + 3
            draw.rectangle([x0, 0, x1, h], fill=col)
        else:
            x0 = int(w - t * w)
            draw.rectangle([x0 - int(w / steps) - 3, 0, x0, h], fill=col)
    return base


def _rounded(draw: "ImageDraw.ImageDraw", box, radius, fill=None, outline=None, width=2) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _blend_on(img: "Image.Image", xy, color: Sequence[int], alpha: float) -> Tuple[int, int, int]:
    """
    Pillow only alpha-BLENDS when the image mode differs from the draw mode, so a
    translucent `fill` on an RGBA canvas would *replace* pixels instead of
    blending them. We therefore sample the actual background pixel and return an
    opaque pre-blended colour — exact result, no compositing cost.
    """
    x = max(0, min(img.width - 1, int(xy[0])))
    y = max(0, min(img.height - 1, int(xy[1])))
    px = img.getpixel((x, y))
    a = max(0.0, min(1.0, alpha))
    return tuple(int(px[i] * (1 - a) + color[i] * a) for i in range(3))  # type: ignore


def _text_size(draw: "ImageDraw.ImageDraw", text: str, font) -> Tuple[int, int]:
    """Measure text AFTER Arabic shaping, so wrapping matches what gets drawn."""
    try:
        bbox = draw.textbbox((0, 0), fontlib._shape_cached(text), font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        return draw.textsize(text, font=font)


def _draw_text(draw, xy, text, font, fill, anchor=None, rtl=False, lang=None) -> None:
    """
    Draw Urdu/Arabic with correct letter-joining and bidi re-ordering.

    Pillow shapes Arabic natively only when built with libraqm (not the default
    Windows wheel), so when it is unavailable we pre-shape with the free
    arabic-reshaper + python-bidi pair and then draw in visual order.
    """
    if font is None or not text:
        return
    payload = fontlib._shape_cached(text)
    try:
        if rtl and fontlib.raqm_available():
            draw.text(xy, text, font=font, fill=fill, anchor=anchor,
                      direction="rtl", language=lang or "ur")
        else:
            draw.text(xy, payload, font=font, fill=fill, anchor=anchor)
    except Exception:
        try:
            draw.text(xy, payload, font=font, fill=fill, anchor=anchor)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# TEXT FITTING  (everything measured, nothing ever overflows the canvas)
# ---------------------------------------------------------------------------
def _fit_font(draw, text: str, rtl: bool, max_w: int, start: int,
              minimum: int = 11, bold: bool = True):
    """Return the largest font size whose rendering of `text` fits `max_w`."""
    size = start
    best = None
    while size >= minimum:
        f = urdu_font(size) if rtl else latin_font(size, bold=bold)
        if f is None:
            f = latin_font(size, bold=bold)
        best = best or f
        try:
            wpx = _text_size(draw, text, f)[0]
        except Exception:
            break
        if wpx <= max_w:
            return f
        size -= 2
    return best


def _wrap_to_width(draw, text: str, font, max_w: int,
                   max_lines: int = 3) -> List[str]:
    """Wrap to `max_lines`, truncating the final line with an ellipsis."""
    words = (text or "").split()
    if not words:
        return []
    lines: List[str] = []
    cur = ""
    for w in words:
        trial = (cur + " " + w).strip()
        try:
            tw = _text_size(draw, trial, font)[0]
        except Exception:
            tw = len(trial) * 8
        if tw <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
            if len(lines) == max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    # ellipsis if we cut something off
    if len(lines) == max_lines:
        joined = " ".join(words)
        if " ".join(lines) != joined:
            last = lines[-1]
            while last and _text_size(draw, last + "...", font)[0] > max_w:
                last = last.rsplit(" ", 1)[0] if " " in last else ""
            lines[-1] = (last + "...") if last else ""
    return [ln for ln in lines if ln.strip()]


# ---------------------------------------------------------------------------
# DECORATIVE BACKDROP  (emerald & gold house style)
# ---------------------------------------------------------------------------
def backdrop(size: Tuple[int, int], dark: bool = True) -> "Image.Image":
    w, h = size
    if dark:
        img = gradient(size, config.THEME["emerald"], "#021c16", 100).convert("RGBA")
    else:
        img = gradient(size, config.THEME["cream"], "#e6dcc0", 100).convert("RGBA")
    gold = hx(config.THEME["gold"])

    # soft gold glow, top-right
    r = int(min(w, h) * 0.62)
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse(
        [int(w * 0.78) - r, int(h * 0.04) - r, int(w * 0.78) + r, int(h * 0.04) + r],
        fill=(gold[0], gold[1], gold[2], 34))
    img = Image.alpha_composite(img, layer.filter(ImageFilter.GaussianBlur(r // 3)))

    # soft emerald glow, bottom-left
    r2 = int(min(w, h) * 0.55)
    layer2 = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(layer2).ellipse(
        [int(w * 0.08) - r2, int(h * 0.96) - r2, int(w * 0.08) + r2, int(h * 0.96) + r2],
        fill=(46, 214, 160, 30))
    img = Image.alpha_composite(img, layer2.filter(ImageFilter.GaussianBlur(r2 // 3)))

    d = ImageDraw.Draw(img, "RGBA")
    gold = hx(config.THEME["gold"])

    # elegant double frame + gold corner brackets (never collides with content)
    m = max(10, int(min(w, h) * 0.032))
    lw = max(2, int(min(w, h) * 0.0028))
    d.rectangle([m, m, w - m, h - m],
                outline=_blend_on(img, (m, m), gold, 0.55), width=lw)
    d.rectangle([m + lw * 4, m + lw * 4, w - m - lw * 4, h - m - lw * 4],
                outline=_blend_on(img, (m + 10, m + 10), gold, 0.22), width=max(1, lw - 1))
    bl = int(min(w, h) * 0.085)
    br_col = _blend_on(img, (m + 10, m + 10), gold, 0.85)
    for (cx, cy, sx, sy) in ((m, m, 1, 1), (w - m, m, -1, 1),
                             (m, h - m, 1, -1), (w - m, h - m, -1, -1)):
        d.line([(cx, cy), (cx + sx * bl, cy)], fill=br_col, width=lw * 2)
        d.line([(cx, cy), (cx, cy + sy * bl)], fill=br_col, width=lw * 2)
    return img.convert("RGBA")


def _brand_bar(img: "Image.Image", dark: bool = True) -> None:
    """Shop identity strip pinned to the bottom of every generated graphic."""
    w, h = img.size
    d = ImageDraw.Draw(img, "RGBA")
    bar_h = int(h * 0.082)
    top = h - bar_h
    gold = hx(config.THEME["gold"])
    d.rectangle([0, top, w, h], fill=(3, 26, 21) if dark else (255, 255, 255))
    d.line([(0, top), (w, top)], fill=gold, width=max(3, int(h * 0.005)))

    ink = (255, 255, 255) if dark else hx(config.THEME["ink"])
    mid = top + bar_h // 2

    # phone — always visible, fitted to its column
    f_phone = _fit_font(d, config.PHONE_DISPLAY, False, int(w * 0.30),
                        start=max(18, int(bar_h * 0.40)), minimum=12)
    _draw_text(d, (int(w * 0.055), mid), config.PHONE_DISPLAY, f_phone, ink, anchor="lm")

    # address + timing on the right, fitted so they never collide
    right = w - int(w * 0.055)
    for txt, col in ((config.ADDRESS, gold), (config.TIMING, ink)):
        if not txt:
            continue
        f = _fit_font(d, txt, False, int(w * 0.62), start=max(13, int(bar_h * 0.28)), minimum=9)
        _draw_text(d, (right, mid), txt, f, col, anchor="rm")
        mid += int(bar_h * 0.30)


def _title_block(d: "ImageDraw.ImageDraw", size: Tuple[int, int], title: str,
                 subtitle: str, rtl: bool = False, y: int = 0,
                 max_w_ratio: float = 0.84) -> int:
    """Draw headline + gold rule + subtitle. Returns the next free Y (measured)."""
    w, h = size
    gold = hx(config.THEME["gold"])
    max_w = int(w * max_w_ratio)
    y = y or int(h * 0.115)

    f_main = _fit_font(d, title, rtl, max_w, start=int(h * 0.070), minimum=16)
    lines = _wrap_to_width(d, title, f_main, max_w, max_lines=3)
    lh = int(_text_size(d, "Ag", f_main)[1] * 1.34) or int(h * 0.05)
    for ln in lines:
        _draw_text(d, (w // 2, y), ln, f_main, (255, 255, 255), anchor="ma", rtl=rtl)
        y += lh

    # gold rule, clearly below the last title line (extra room for tall Urdu glyphs)
    y += max(int(h * 0.018), int(lh * 0.38))
    rw = int(w * 0.16)
    ry = y
    d.line([(w // 2 - rw // 2, ry), (w // 2 + rw // 2, ry)],
           fill=gold, width=max(5, int(h * 0.007)))
    y += int(h * 0.032)

    if subtitle:
        f_sub = _fit_font(d, subtitle, rtl, max_w, start=int(h * 0.032), minimum=12, bold=False)
        for ln in _wrap_to_width(d, subtitle, f_sub, max_w, max_lines=2):
            _draw_text(d, (w // 2, y), ln, f_sub, (226, 238, 233), anchor="ma", rtl=rtl)
            y += int(_text_size(d, "Ag", f_sub)[1] * 1.5) + 4
    return y


def _badge(d, size, xy, text, rtl=False, img=None) -> int:
    """Small gold pill label. Returns the Y below it."""
    w, h = size
    gold = hx(config.THEME["gold"])
    f = _fit_font(d, text, rtl, int(w * 0.70), start=max(15, int(h * 0.026)), minimum=10)
    tw, th = _text_size(d, text, f)
    padx, pady = int(h * 0.030), max(8, int(h * 0.013))
    x, y = xy
    bw, bh = tw + padx * 2, th + pady * 2
    fill = _blend_on(img, (x + 4, y + 4), gold, 0.20) if img is not None \
        else (gold[0] // 4, gold[1] // 4, gold[2] // 4)
    _rounded(d, [x, y, x + bw, y + bh], radius=bh // 2,
             fill=fill, outline=gold, width=max(2, int(h * 0.0028)))
    _draw_text(d, (x + bw // 2, y + bh // 2), text, f, gold, anchor="mm", rtl=rtl)
    return y + bh


# ---------------------------------------------------------------------------
# BROWSER-BASED (HarfBuzz) RENDERER — real Urdu Nastaliq on images
# ---------------------------------------------------------------------------
_BANNER_CSS = """
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:%(W)spx;height:%(H)spx;overflow:hidden}
body{
  font-family:'NotoNastaliq','Jameel Noori Nastaleeq','Segoe UI',Tahoma,sans-serif;
  direction:rtl; color:#fff; position:relative;
  background:linear-gradient(120deg,#046b4d 0%%,#03352a 55%%,#021c16 100%%);
  padding:%(PAD)spx %(PAD)spx calc(%(PAD)spx + %(BAR)spx);
  display:flex; flex-direction:column; justify-content:center;
}
.glow1{position:absolute;width:%(G)spx;height:%(G)spx;border-radius:50%%;
  background:rgba(212,175,55,.16);filter:blur(70px);top:-%(G4)spx;left:-%(G6)spx;right:auto}
.glow2{position:absolute;width:%(G)spx;height:%(G)spx;border-radius:50%%;
  background:rgba(46,214,160,.16);filter:blur(70px);bottom:-%(G4)spx;right:-%(G6)spx;left:auto}
.frame{position:absolute;inset:%(M)spx;border:%(LW)spx solid rgba(212,175,55,.55);border-radius:3px}
.frame2{position:absolute;inset:%(M2)spx;border:1px solid rgba(212,175,55,.20);border-radius:3px}
.badge{align-self:flex-start;margin-bottom:%(GAP)spx;border:2px solid #d4af37;color:#d4af37;
  border-radius:999px;padding:%(BPY)spx %(BPX)spx;font-size:%(BFS)spx;font-weight:700;
  font-family:'Segoe UI',sans-serif;background:rgba(212,175,55,.12);line-height:1.4}
h1{font-size:%(TFS)spx;line-height:1.95;font-weight:700;margin-bottom:%(TGAP)spx}
.rule{width:%(RL)spx;height:%(RWT)spx;background:#d4af37;border-radius:2px;margin-bottom:%(GAP)spx}
.sub{font-size:%(SFS)spx;color:#e2eeea;margin-bottom:%(GAP2)spx;line-height:2}
ul{list-style:none;display:flex;flex-direction:column;gap:%(LGAP)spx}
li{background:rgba(1,22,17,.74);border:1.5px solid rgba(212,175,55,.42);
  border-radius:%(LR)spx;padding:%(LY)spx %(LX)spx;display:flex;gap:%(LDOT)spx;
  align-items:center;font-size:%(LFS)spx;line-height:2.1}
.dot{width:%(LS)spx;height:%(LS)spx;border-radius:50%%;background:#d4af37;flex:none}
.bar{position:absolute;left:0;right:0;bottom:0;height:%(BAR)spx;background:#031a15;
  border-top:2px solid #d4af37;display:flex;align-items:center;justify-content:space-between;
  padding:0 %(PAD)spx;direction:ltr;font-family:'Segoe UI',sans-serif}
.bar .ph{font-size:%(BPFS)spx;font-weight:800;color:#fff;white-space:nowrap}
.bar .ri{text-align:right;font-size:%(BRFS)spx;line-height:1.45}
.bar .ri b{color:#d4af37;display:block}
"""


def _html_banner(w: int, h: int, title: str, subtitle: str, bullets: List[str],
                 tag: str) -> str:
    k = dict(
        W=w, H=h, PAD=int(w * 0.075), M=int(min(w, h) * 0.032),
        M2=int(min(w, h) * 0.032) + int(min(w, h) * 0.011),
        LW=max(2, int(min(w, h) * 0.0028)),
        GAP=int(h * 0.030), GAP2=int(h * 0.030), TGAP=int(h * 0.022),
        G=int(min(w, h) * 0.70), G4=int(min(w, h) * 0.18), G6=int(min(w, h) * 0.12),
        BPY=int(h * 0.008), BPX=int(w * 0.028), BFS=int(h * 0.024),
        TFS=int(h * 0.050), SFS=int(h * 0.026),
        RL=int(w * 0.16), RWT=max(4, int(h * 0.006)),
        LGAP=int(h * 0.012), LR=int(h * 0.016), LY=int(h * 0.010), LX=int(h * 0.022),
        LDOT=int(h * 0.018), LS=max(7, int(h * 0.011)), LFS=int(h * 0.027),
        BAR=int(h * 0.082), BPFS=int(h * 0.026), BRFS=int(h * 0.020),
    )
    css = _BANNER_CSS % k
    lis = "".join(f"<li><span class='dot'></span><span>{b}</span></li>"
                  for b in bullets[:6] if str(b).strip())
    phone = config.PHONE_DISPLAY
    return f"""<!doctype html><html lang="ur" dir="rtl"><head><meta charset="utf-8">
<style>
@font-face{{font-family:'NotoNastaliq';src:url(data:font/ttf;base64,{fontlib.nastaliq_font_b64()}) format('truetype');font-display:block}}
{css}
</style></head><body>
<div class="glow1"></div><div class="glow2"></div>
<div class="frame"></div><div class="frame2"></div>
<div class="badge">{tag}</div>
<h1>{title}</h1>
<div class="rule"></div>
<div class="sub">{subtitle}</div>
<ul>{lis}</ul>
<div class="bar"><span class="ph">{phone}</span>
  <span class="ri"><b>{config.ADDRESS}</b>{config.TIMING}</span></div>
</body></html>"""


def render_banner_browser(title: str, subtitle: str = "", bullets: Optional[List[str]] = None,
                          preset: str = "instagram_post",
                          tag: str = "CHISHTIAN - FREE HELP",
                          filename: Optional[str] = None) -> Optional[str]:
    """
    Render an URDU banner through a real browser engine (Playwright).
    Browsers use HarfBuzz, so Urdu comes out as proper Nastaliq — something
    Pillow cannot do without libraqm. Returns None if unavailable.
    """
    size = BANNER_PRESETS.get(preset, BANNER_PRESETS["instagram_post"])
    w, h = size
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return None
    html = _html_banner(w, h, title, subtitle, list(bullets or []), tag)
    out = config.BANNER_DIR / (filename or f"ur_browser_{db.new_id()}.png")
    out = out.with_suffix(".png")
    pw = None
    try:
        pw = sync_playwright().start()
        args = ["--no-sandbox", "--font-render-hinting=none", "--disable-gpu"]
        browser = None
        # Playwright >=1.49 wants a separate 'headless shell' build. Fall back to
        # the full Chromium (channel="chromium", new headless mode) and finally
        # to a visible window, so banner rendering works on any install.
        for opts in ({"headless": True},
                     {"headless": True, "channel": "chromium"},
                     {"headless": False}):
            try:
                browser = pw.chromium.launch(args=args, timeout=45_000, **opts)
                break
            except Exception:
                browser = None
        if browser is None:
            raise RuntimeError("Chromium launch failed in every mode")
        pg = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
        pg.set_content(html, wait_until="load", timeout=30_000)
        pg.wait_for_timeout(500)
        pg.screenshot(path=str(out), type="png")
        browser.close()
        db.log("INFO", "media", f"Urdu banner (browser/Nastaliq): {out.name} ({w}x{h})")
        return str(out)
    except Exception as exc:
        db.log("WARN", "media", f"Browser banner render nahi hua ({exc}); Pillow par fallback.")
        return None
    finally:
        try:
            if pw:
                pw.stop()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# BANNER GENERATOR  (Instagram / Facebook / WhatsApp status / TikTok cover)
# ---------------------------------------------------------------------------
BANNER_PRESETS: Dict[str, Dict[str, Any]] = {
    "instagram_post": (1080, 1080),
    "instagram_story": (1080, 1920),
    "facebook_cover": (1200, 630),
    "facebook_post": (1200, 1200),
    "tiktok_cover": (1080, 1920),
    "whatsapp_status": (1080, 1920),
}


def make_banner(title: str, subtitle: str = "", bullets: Optional[List[str]] = None,
                preset: str = "instagram_post", rtl: bool = False,
                tag: str = "CHISHTIAN - FREE HELP",
                filename: Optional[str] = None) -> Optional[str]:
    """Render one ready-to-post banner. Returns the saved file path (or None)."""
    if not PIL_AVAILABLE:
        db.log("ERROR", "media", "Pillow (PIL) missing — run: pip install Pillow")
        return None

    # Urdu → prefer the browser renderer (real HarfBuzz Nastaliq).
    if rtl and os.environ.get("CTH_NO_BROWSER_RENDER") != "1":
        p = render_banner_browser(title, subtitle, bullets, preset, tag, filename)
        if p:
            return p

    size = BANNER_PRESETS.get(preset, BANNER_PRESETS["instagram_post"])
    w, h = size
    img = backdrop(size, dark=True)
    d = ImageDraw.Draw(img, "RGBA")
    gold = hx(config.THEME["gold"])

    margin = int(w * 0.075)
    bar_h = int(h * 0.082)
    bottom_limit = h - bar_h - int(h * 0.022)

    # --- badge ---
    y = _badge(d, size, (margin, int(h * 0.062)), tag, rtl=rtl, img=img) + int(h * 0.045)

    # --- headline + subtitle (measured) ---
    y = _title_block(d, size, title, subtitle, rtl=rtl, y=y, max_w_ratio=0.85)
    y += int(h * 0.035)

    # --- bullets, laid out inside the space that is actually left ---
    bullets = [b for b in (bullets or []) if str(b).strip()][:6]
    if bullets and y < bottom_limit - int(h * 0.06):
        gap = int(h * 0.014)
        avail = bottom_limit - y
        row_h = int((avail - gap * (len(bullets) - 1)) / len(bullets))
        row_h = max(int(h * 0.045), min(row_h, int(h * 0.092)))
        left, right = margin, w - margin
        inset = int(w * 0.030)
        txt_max = (right - left) - inset * 2 - int(w * 0.02)
        # RTL: marker on the right, text hugs the right edge.
        dot_x = right - inset if rtl else left + inset
        txt_x = right - inset * 2 if rtl else left + inset * 2

        for b in bullets:
            if y + row_h > bottom_limit:
                break
            _rounded(d, [left, y, right, y + row_h], radius=int(row_h * 0.28),
                     fill=_blend_on(img, (left + 6, y + row_h // 2), (1, 22, 17), 0.72),
                     outline=_blend_on(img, (left + 6, y + row_h // 2), gold, 0.42),
                     width=max(2, int(h * 0.002)))
            # gold marker drawn as a shape (emoji / unicode bullets are unreliable)
            r = max(4, int(row_h * 0.13))
            cy = y + row_h // 2
            d.ellipse([dot_x - r, cy - r, dot_x + r, cy + r], fill=gold)

            text = str(b)
            f_bul = _fit_font(d, text, rtl, txt_max, start=int(row_h * 0.46), minimum=13)
            lines = _wrap_to_width(d, text, f_bul, txt_max, max_lines=2)
            anchor_h = "rm" if rtl else "lm"
            if len(lines) == 1:
                _draw_text(d, (txt_x, cy), lines[0], f_bul, (246, 251, 249),
                           anchor=anchor_h, rtl=rtl)
            else:
                lh = int(_text_size(d, "Ag", f_bul)[1] * 1.30) or int(row_h * 0.42)
                ty = cy - (len(lines) * lh) // 2
                for ln in lines:
                    _draw_text(d, (txt_x, ty), ln, f_bul, (246, 251, 249),
                               anchor=anchor_h, rtl=rtl)
                    ty += lh
            y += row_h + gap

    _brand_bar(img, dark=True)

    out = config.BANNER_DIR / (filename or f"{tag.lower().replace(' ', '_')}_{db.new_id()}.png")
    out = out.with_suffix(".png")
    img.convert("RGB").save(out, "PNG", optimize=True)
    db.log("INFO", "media", f"Banner rendered: {out.name} ({w}x{h})")
    return str(out)


# ---------------------------------------------------------------------------
# FREE TEXT-TO-SPEECH  (Microsoft edge-tts — free, no key, no signup)
# ---------------------------------------------------------------------------
def _run_edge_tts(text: str, voice: str, out_mp3: Path) -> List[Dict[str, Any]]:
    """
    Speak `text` and return word-boundary timings so the on-screen captions can
    be highlighted exactly in sync. 100% free (Microsoft's public edge endpoint).
    """
    import asyncio

    async def _go() -> List[Dict[str, Any]]:
        comm = edge_tts.Communicate(text, voice, rate="+8%")
        marks: List[Dict[str, Any]] = []
        with out_mp3.open("wb") as fh:
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    fh.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    marks.append({"word": chunk.get("text", ""),
                                  "start": chunk.get("offset", 0) / 10_000_000,
                                  "end": (chunk.get("offset", 0) / 10_000_000)
                                          + chunk.get("duration", 0) / 10_000_000})
        return marks

    return asyncio.run(_go())


def probe_duration(media: Path) -> float:
    exe = ffmpeg_path()
    if not exe:
        return 0.0
    try:
        out = subprocess.run([exe, "-i", str(media)], capture_output=True, text=True, timeout=60)
        blob = (out.stderr or "") + (out.stdout or "")
        for part in blob.split("Duration:")[-1].split(",")[0:1]:
            hms = part.strip()
            h, m, s = hms.split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
    except Exception:
        pass
    return 0.0


# ---------------------------------------------------------------------------
# VIRAL VIDEO MAKER (vertical 1080x1920, Urdu overlays, synced to TTS)
# ---------------------------------------------------------------------------
def _build_frame_cache(rw: int, rh: int) -> "Image.Image":
    return backdrop((rw, rh), dark=True).convert("RGBA").resize((rw, rh)).convert("RGBA")


def _wrap_words(draw, words: List[str], font, max_w: int, max_lines: int = 4) -> List[List[str]]:
    """Greedily pack WORDS into lines (needed for per-word highlighting)."""
    lines: List[List[str]] = []
    cur: List[str] = []
    cur_w = 0
    sp = _text_size(draw, " ", font)[0]
    for w in words:
        ww = _text_size(draw, w, font)[0]
        add = ww + (sp if cur else 0)
        if cur and cur_w + add > max_w:
            lines.append(cur)
            cur, cur_w = [w], ww
            if len(lines) >= max_lines:
                return lines
        else:
            cur.append(w)
            cur_w += add
    if cur and len(lines) < max_lines:
        lines.append(cur)
    return lines


def _draw_caption(img: "Image.Image", words: List[str], active_idx: int,
                  rtl: bool, t: float, progress: float = 0.0) -> None:
    """Word-level karaoke caption + badge + progress bar + brand bar."""
    rw, rh = img.size
    d = ImageDraw.Draw(img, "RGBA")
    gold = hx(config.THEME["gold"])
    white = (255, 255, 255)
    pad = int(rw * 0.085)

    # bigger type for short chunks, smaller for longer ones — always fills nicely
    n = max(1, len(words))
    frac = 0.082 if n <= 4 else 0.070 if n <= 7 else 0.058 if n <= 12 else 0.050
    f_cap = _fit_font(d, " ".join(words), rtl, rw - pad * 2,
                      start=int(rh * frac), minimum=16)
    if f_cap is None:
        f_cap = latin_font(int(rh * frac))

    lines = _wrap_words(d, words, f_cap, rw - pad * 2, max_lines=4)
    sp = _text_size(d, " ", f_cap)[0]
    line_h = int(_text_size(d, "Ag", f_cap)[1] * 1.50) or int(rh * 0.075)
    total_h = line_h * len(lines)
    y_top = int(rh * 0.50) - total_h // 2

    # scrim padded so ascenders/descenders are never clipped
    ptop = y_top - int(line_h * 0.62)
    pbot = y_top + total_h + int(line_h * 0.34)
    scrim = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(scrim).rounded_rectangle(
        [pad // 2, ptop, rw - pad // 2, pbot],
        radius=int(rh * 0.030), fill=(0, 12, 9, 170))
    img.alpha_composite(scrim)
    d = ImageDraw.Draw(img, "RGBA")

    pulse = (math.sin(t * 6) + 1) / 2
    y = y_top
    base = 0                      # index of the first word of the current line
    for line in lines:
        widths = [_text_size(d, w, f_cap)[0] for w in line]
        line_w = sum(widths) + sp * max(0, len(line) - 1)
        y_final = y + int(line_h * 0.62)
        if rtl:
            xr = rw / 2 + line_w / 2
            for wi, (word, ww) in enumerate(zip(line, widths)):
                _draw_text(d, (xr, y_final), word, f_cap,
                           gold if (base + wi) == active_idx else white,
                           anchor="rm", rtl=rtl)
                xr -= ww + sp
        else:
            x = (rw - line_w) / 2
            for wi, (word, ww) in enumerate(zip(line, widths)):
                _draw_text(d, (x, y_final), word, f_cap,
                           gold if (base + wi) == active_idx else white, anchor="lm")
                x += ww + sp
        base += len(line)
        y += line_h

    # pulse underline under the whole caption block
    if 0 <= active_idx < len(words):
        _rounded(d, [pad // 2 + int(rw * 0.10), pbot - int(line_h * 0.20),
                     rw - pad // 2 - int(rw * 0.10), pbot - int(line_h * 0.20) + max(3, int(rh * 0.004))],
                 radius=2, fill=(gold[0], gold[1], gold[2], int(70 + pulse * 170)))

    # top badge
    badge_txt = "CHISHTIAN - 100% FREE HELP"
    f_badge = _fit_font(d, badge_txt, False, rw - pad, start=int(rh * 0.028), minimum=12)
    bw, bh = _text_size(d, badge_txt, f_badge)
    padx, pady = int(rw * 0.045), int(rh * 0.010)
    bx, by = (rw - bw) // 2 - padx, int(rh * 0.062)
    _rounded(d, [bx, by, bx + bw + padx * 2, by + bh + pady * 2],
             radius=(bh + pady * 2) // 2,
             fill=_blend_on(img, (bx + 4, by + 4), gold, 0.22),
             outline=gold, width=max(2, int(rh * 0.003)))
    _draw_text(d, (rw // 2, by + (bh + pady * 2) // 2), badge_txt, f_badge, gold, anchor="mm")

    # playback progress bar under the badge
    track_y = by + bh + pady * 2 + int(rh * 0.022)
    track_w = int(rw * 0.72)
    tx = (rw - track_w) // 2
    th = max(4, int(rh * 0.006))
    _rounded(d, [tx, track_y, tx + track_w, track_y + th], radius=th // 2,
             fill=_blend_on(img, (tx + 4, track_y + 2), (255, 255, 255), 0.16))
    p = max(0.0, min(1.0, progress))
    if p > 0:
        _rounded(d, [tx, track_y, tx + max(th * 2, int(track_w * p)), track_y + th],
                 radius=th // 2, fill=gold)

    _brand_bar(img, dark=True)


def render_video(out_path: Path, script: str, voice: Optional[str] = None,
                 rtl: bool = False, job_id: str = "", fps: int = config.VIDEO_FPS,
                 progress_cb=None) -> Dict[str, Any]:
    """
    Render a complete vertical video: free TTS voice-over + synced captions.
    Falls back to a silent (captions-only) video when TTS is unavailable, so the
    system still produces an uploadable MP4 with ZERO internet.
    """
    exe = ffmpeg_path()
    if not PIL_AVAILABLE or not exe:
        return {"ok": False,
                "error": "Pillow missing or FFmpeg not found (pip install Pillow imageio-ffmpeg)"}

    voice = voice or config.TTS_VOICES.get(config.TTS_LANG, config.TTS_VOICES["roman"])
    rw, rh = config.RENDER_W, config.RENDER_H

    # ---- 1. Voice-over + word timings ----
    audio_path = config.AUDIO_DIR / f"{out_path.stem}.mp3"
    marks: List[Dict[str, Any]] = []
    tts_ok = False
    if EDGE_TTS_AVAILABLE:
        try:
            if progress_cb:
                progress_cb(8, "edge-tts se free voice-over bana rahe hain…")
            marks = _run_edge_tts(script, voice, audio_path)
            tts_ok = audio_path.exists() and audio_path.stat().st_size > 1024
        except Exception as exc:
            db.log("WARN", "video", f"TTS failed ({exc}); silent video bana rahe hain")

    words = [w for w in re_split_words(script)]
    if not words:
        words = ["Chishtian"]

    duration = 0.0
    if tts_ok:
        duration = probe_duration(audio_path)
    if duration <= 0:
        duration = max(9.0, 0.62 * len(words))       # ~1.6 words/sec
        if duration > 75:
            duration = 75.0

    # Normalise word timings to the video duration.
    timings: List[Tuple[float, float]] = []
    if marks and marks[-1]["end"] > 0:
        scale = duration / marks[-1]["end"]
        for m in marks:
            timings.append((m["start"] * scale, m["end"] * scale))
    else:
        per = duration / len(words)
        timings = [(i * per, i * per + per * 0.85) for i in range(len(words))]

    # Build a per-frame display window (chunked karaoke).
    per_line = max(4, min(9, int(len(words) / 6) + 2))
    chunks = [words[i:i + per_line] for i in range(0, len(words), per_line)]
    chunk_times: List[Tuple[float, float]] = []
    wi = 0
    for ch in chunks:
        start = timings[wi][0]
        wi += len(ch)
        end = timings[min(wi, len(timings)) - 1][1]
        chunk_times.append((start, max(end, start + 0.8)))

    if progress_cb:
        progress_cb(20, f"{len(words)} words · {duration:.1f}s · captions sync ho rahe hain")

    total_frames = max(1, int(duration * fps))

    # ---- 2. Render frames + pipe straight into FFmpeg (never stores PNG spam) ----
    bg = _build_frame_cache(rw, rh)
    cmd = [
        exe, "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{rw}x{rh}", "-r", str(fps), "-i", "-",
    ]
    if tts_ok:
        cmd += ["-i", str(audio_path)]
    cmd += [
        "-vf", f"scale={config.VIDEO_W}:{config.VIDEO_H}:flags=lanczos,format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
    ]
    if tts_ok:
        cmd += ["-c:a", "aac", "-b:a", "128k", "-shortest"]
    cmd += [str(out_path)]

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE)

    try:
        for f in range(total_frames):
            t = f / fps
            # which chunk / word is active now
            ci = 0
            for i, (s, e) in enumerate(chunk_times):
                if t >= s:
                    ci = i
            ch_words = chunks[ci]
            ch_start = chunk_times[ci][0]
            local = max(0, t - ch_start)
            rel = local / max(0.001, chunk_times[ci][1] - ch_start)
            active = int(rel * len(ch_words))
            active = max(0, min(len(ch_words) - 1, active))

            frame = bg.copy()
            _draw_caption(frame, ch_words, active, rtl, t, progress=f / total_frames)
            proc.stdin.write(frame.convert("RGB").tobytes())  # type: ignore[union-attr]

            if progress_cb and f % max(1, fps) == 0:
                progress_cb(20 + int(70 * f / total_frames),
                            f"Frame {f}/{total_frames} render ho rahe hain…")
    finally:
        if proc.stdin:
            proc.stdin.close()
        proc.wait(timeout=300)

    if proc.returncode != 0:
        err = (proc.stderr.read().decode("utf-8", "ignore") if proc.stderr else "")[:400]
        return {"ok": False, "error": f"FFmpeg failed: {err}"}

    # ---- 3. Cover thumbnail (free, reuses frame 1) ----
    try:
        cover = backdrop((1080, 1920), dark=True)
        cd = ImageDraw.Draw(cover, "RGBA")
        _title_block(cd, (1080, 1920), script.split(".")[0][:70],
                     config.SHOP_NAME, rtl=rtl)
        _brand_bar(cover, dark=True)
        cover.convert("RGB").save(config.VIDEO_DIR / f"{out_path.stem}_cover.jpg", quality=92)
    except Exception:
        pass

    return {"ok": True, "path": str(out_path), "duration": round(duration, 2),
            "words": len(words), "tts": tts_ok, "voice": voice if tts_ok else "silent (captions only)",
            "size": out_path.stat().st_size}


def re_split_words(text: str) -> List[str]:
    import re
    return [w for w in re.split(r"\s+", text.strip()) if w]


def render_video_job(job_id: str, script: str, title: str, voice: Optional[str] = None,
                     rtl: bool = False) -> Dict[str, Any]:
    """Worker wrapper used by the FastAPI background tasks."""
    def cb(pct: int, msg: str) -> None:
        db.update_job(job_id, progress=pct, message=msg)

    out = config.VIDEO_DIR / f"{db.new_id('vid_')}.mp4"
    db.update_job(job_id, status="running", progress=3, message="Shuru ho gaya…")
    res = render_video(out, script, voice=voice, rtl=rtl, job_id=job_id, progress_cb=cb)
    if res.get("ok"):
        db.update_job(job_id, status="done", progress=100,
                      message="Video tayyar hai — upload kar dein!",
                      result=res.get("path", ""))
        db.log("INFO", "video", f"Video ready: {out.name} ({res.get('duration')}s, tts={res.get('tts')})")
    else:
        db.update_job(job_id, status="failed", message=res.get("error", "unknown error"))
    return res


# ---------------------------------------------------------------------------
# THUMBNAIL FROM VIDEO (no FFmpeg re-encode hacks — simple still grab)
# ---------------------------------------------------------------------------
def video_thumbnail(video: Path, at_second: float = 1.0) -> Optional[str]:
    exe = ffmpeg_path()
    if not exe:
        return None
    out = config.VIDEO_DIR / f"{video.stem}_thumb.jpg"
    try:
        subprocess.run([exe, "-y", "-loglevel", "error", "-ss", str(at_second),
                        "-i", str(video), "-frames:v", "1", "-q:v", "2", str(out)],
                       check=True, timeout=90)
        return str(out)
    except Exception:
        return None


if __name__ == "__main__":
    print("Pillow :", PIL_AVAILABLE)
    print("FFmpeg :", ffmpeg_path())
    print("edgeTTS:", EDGE_TTS_AVAILABLE)
    print("Urdu font:", urdu_supported())
    p = make_banner("Zameen ki Registry", "Complete file & Fard — Chishtian",
                    ["Fard-e-Malkiat", "Bay Nama", "Inteqal"], "instagram_post")
    print("Banner :", p)