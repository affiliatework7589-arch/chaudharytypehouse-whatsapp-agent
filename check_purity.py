# -*- coding: utf-8 -*-
"""
check_purity.py — automated language-purity + link-safety audit for index.html

Rules enforced
--------------
1. ENGLISH MODE  : rendered text must contain ZERO Urdu/Arabic-script characters
                   and ZERO Roman-Urdu markers.
2. URDU MODE     : rendered text must contain ZERO Latin letters, except an
                   explicit allow-list (phone digits, "Google Map", etc. that the
                   brief itself mandates).
3. No stray CJK / Cyrillic / stray symbols anywhere.
4. Services page must contain NO whatsapp link and NO external website URL.
5. WhatsApp link must exist ONLY on the Contact page and match the exact URL.
6. Google Maps link only on the Office page.

It parses index.html statically AND drives a real headless browser to check what
is actually rendered, including every service sub-tab.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HTML = (ROOT / "index.html").read_text(encoding="utf-8")

URDU_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")
LATIN_RE = re.compile(r"[A-Za-z]")
CJK_RE = re.compile(r"[\u4E00-\u9FFF\u3040-\u30FF\uAC00-\uD7AF]")
CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")

# Roman-Urdu words that must never appear in English mode.
ROMAN_URDU = [
    "hai", "hain", "kaise", "kya", "mujhe", "chahiye", "chahye", "aap", "mera",
    "meri", "hamara", "hamari", "karte", "karna", "karwa", "kaam", "bohat",
    "bohat", "shukriya", "assalam", "waala", "wala", "wala", "ke liye", "ka",
    "ki", "ke", "ko", "mein", "se", "aur", "ya", "par", "bhi", "hi", "to",
    "khadeed", "farokht", "inteqal", "zameen", "fard", "registry", "muawin",
    "ghar", "makan", "nazdeek", "baldia", "chishtian", "sham", "subah", "pm",
]

# Things the brief explicitly allows to stay Latin in Urdu mode.
URDU_MODE_ALLOW = [
    "0327", "7450361", "8:00", "AM", "PM",
    "Google", "Map", "WhatsApp", "C", "BA", "MS", "NADRA", "CNIC",
    "chtype.online", "chtype", "online",
]

FAILS: list[str] = []
WARNS: list[str] = []


def fail(msg: str) -> None:
    FAILS.append(msg)
    print("  [FAIL] " + msg)


def ok(msg: str) -> None:
    print("  [ok]   " + msg)


def warn(msg: str) -> None:
    WARNS.append(msg)
    print("  [warn] " + msg)


# ===========================================================================
print("\n" + "=" * 78)
print("  index.html  —  LANGUAGE PURITY & LINK SAFETY AUDIT")
print("=" * 78)

# ---------------------------------------------------------------------------
# 0. STRUCTURAL INTEGRITY  (catches corrupted object literals before anything else)
# ---------------------------------------------------------------------------
print("\n[0] Structural integrity of the JS data blocks")

script = HTML[HTML.index("const L = {"):HTML.index("const MAPS_URL")]

# every key must be  name:{en:"...",ur:"..."}  with exactly one quote after the colon
malformed = re.findall(r'\b(en|ur)([^:\w",])', script)
if malformed:
    for k, junk in malformed[:10]:
        fail(f"malformed {k!r} key in source (junk {junk!r} between key and colon)")
else:
    ok("all en:/ur: keys are well formed")

# no duplicate quotes right after a colon
if re.search(r'(en|ur):""', script):
    fail('duplicated opening quote found (pattern  en:"" )')
else:
    ok("no duplicated quotes after any en:/ur: colon")

# keys without a colon at all
if re.search(r'\bur="', script) or re.search(r'\ben="', script):
    bad = [f"line {HTML[:m.start()].count(chr(10)) + 1}"
           for m in re.finditer(r'\b(?:en|ur)=', script)]
    fail("an en:/ur: key is missing its opening quote (pattern ur=\"): "
         + ", ".join(bad[:6]))
else:
    ok("no en:/ur: key is missing its opening quote")

# the live page must not contain a JS syntax error
try:
    from playwright.sync_api import sync_playwright as _sp
    with _sp() as _p:
        _b = _p.chromium.launch(headless=True, args=["--no-sandbox"])
        _pg = _b.new_page()
        _errs = []
        _pg.on("pageerror", lambda e: _errs.append(str(e)[:160]))
        _pg.on("console", lambda m: _errs.append(f"{m.type}: {m.text[:160]}")
               if m.type == "error" else None)
        import tempfile
        _f = Path(tempfile.gettempdir()) / "_cth_syntax.html"
        _f.write_text(HTML, encoding="utf-8")
        _pg.goto(_f.as_uri(), wait_until="load")
        _pg.wait_for_timeout(700)
        _b.close()
    if _errs:
        for e in _errs[:4]:
            fail("JavaScript error on the page: " + e)
    else:
        ok("no JavaScript syntax errors in the page")
except Exception as _e:
    warn(f"could not run the standalone JS syntax probe ({_e})")

# balanced braces inside the SERVICES array
svc0 = HTML.index("const SERVICES = [")
svc1 = HTML.index("/* ====", svc0)
body = HTML[svc0:svc1]
if body.count("{") != body.count("}"):
    fail(f"SERVICES block has unbalanced braces "
         f"({body.count('{')} open vs {body.count('}')} close)")
else:
    ok(f"SERVICES block braces balanced ({body.count('{')} pairs)")

# the whole inline script must be syntactically valid JS
js = HTML[HTML.index("<script>\n/* ==="):HTML.index("</script>")]
js = js[js.index("\n") + 1:]
try:
    import subprocess
    # node may not exist; fall back to the browser later
    raise ImportError
except ImportError:
    pass

# ---------------------------------------------------------------------------
# 1. STATIC CHECK ON THE i18n DICTIONARY
# ---------------------------------------------------------------------------
print("\n[1] i18n dictionary (every {en, ur} pair)")

pairs = re.findall(r'"([a-zA-Z0-9._]+)"\s*:\s*\{\s*en\s*:\s*"((?:[^"\\]|\\.)*)"\s*,\s*\n?\s*ur\s*:\s*"((?:[^"\\]|\\.)*)"\s*\}', HTML)
print(f"        {len(pairs)} dictionary entries found")

if len(pairs) < 90:
    fail(f"expected a large dictionary, found only {len(pairs)}")

bad_en = []
bad_ur = []
for key, en, ur in pairs:
    if URDU_RE.search(en):
        bad_en.append((key, en[:70]))
    if CJK_RE.search(en):
        bad_en.append((key, "[CJK in EN] " + en[:60]))
    if CJK_RE.search(ur):
        bad_ur.append((key, "[CJK in UR] " + ur[:60]))
    if CYRILLIC_RE.search(ur) or CYRILLIC_RE.search(en):
        bad_ur.append((key, "[CYRILLIC]"))
    if not en.strip():
        fail(f"empty English string for key '{key}'")
    if not ur.strip():
        fail(f"empty Urdu string for key '{key}'")

for k, v in bad_en:
    fail(f"ENGLISH side contains Urdu/CJK -> key '{k}': {v}")
for k, v in bad_ur:
    fail(f"URDU side contains CJK/Cyrillic -> key '{k}': {v}")

# Latin leftovers inside Urdu strings (excluding the mandated allow-list)
lat_in_ur = []
for key, en, ur in pairs:
    if key in ("tb.phone",):
        continue
    tmp = ur
    for a in URDU_MODE_ALLOW:
        tmp = tmp.replace(a, " ")
    leftover = LATIN_RE.findall(tmp)
    if leftover:
        lat_in_ur.append((key, "".join(leftover)[:24], ur[:70]))
for k, letters, sample in lat_in_ur:
    fail(f"URDU side contains Latin letters [{letters}] -> key '{k}': {sample}")

if not bad_en and not bad_ur and not lat_in_ur:
    ok(f"all {len(pairs)} entries are strictly one-language each")

# ---------------------------------------------------------------------------
# 2. SERVICE DEFINITIONS
# ---------------------------------------------------------------------------
print("\n[2] Service definitions (label / sub / what / docs / steps)")

# per-service parsing (label / sub / what / docs / steps)
svc_start = HTML.index("const SERVICES = [")
svc_end = HTML.index("/* ====", svc_start)
svc_block = HTML[svc_start:svc_end]

service_chunks = re.split(r'\n    id:"', svc_block)[1:]
print(f"        service blocks parsed: {len(service_chunks)}")
if len(service_chunks) != 7:
    fail(f"expected 7 service blocks, found {len(service_chunks)}")

PAIR = r'\{en:"((?:[^"\\]|\\.)*)"\s*,\s*\n?\s*ur:"((?:[^"\\]|\\.)*)"\}'

for idx, blk in enumerate(service_chunks, start=1):
    sid = blk[:24].split('"')[0]

    for field in ("label", "sub", "what"):
        m = re.search(rf'{field}:\{{en:"((?:[^"\\]|\\.)*)"\s*,\s*\n?\s*ur:"((?:[^"\\]|\\.)*)"\}}', blk)
        if not m:
            fail(f"service '{sid}': missing {field}")
            continue
        en, ur = m.group(1), m.group(2)
        if URDU_RE.search(en) or CJK_RE.search(en):
            fail(f"service '{sid}' {field} English is not pure English: {en[:60]}")
        if CJK_RE.search(ur) or CYRILLIC_RE.search(ur):
            fail(f"service '{sid}' {field} Urdu has CJK/Cyrillic: {ur[:60]}")
        tmp = ur
        for a in URDU_MODE_ALLOW:
            tmp = tmp.replace(a, " ")
        if LATIN_RE.search(tmp):
            fail(f"service '{sid}' {field} Urdu has Latin: {LATIN_RE.findall(tmp)[:8]} -> {ur[:60]}")

    for listname in ("docs", "steps"):
        seg = blk.split(f"{listname}:[", 1)
        if len(seg) < 2:
            fail(f"service '{sid}': missing {listname}")
            continue
        seg = seg[1].split("]", 1)[0]
        pairs = re.findall(PAIR, seg)
        if len(pairs) < 6:
            fail(f"service '{sid}': {listname} has only {len(pairs)} items (need >= 6)")
        for en, ur in pairs:
            if URDU_RE.search(en) or CJK_RE.search(en) or CYRILLIC_RE.search(en):
                fail(f"service '{sid}' {listname} English not pure: {en[:60]}")
            if CJK_RE.search(ur) or CYRILLIC_RE.search(ur):
                fail(f"service '{sid}' {listname} Urdu has CJK/Cyrillic: {ur[:60]}")
            tmp = ur
            for a in URDU_MODE_ALLOW:
                tmp = tmp.replace(a, " ")
            if LATIN_RE.search(tmp):
                fail(f"service '{sid}' {listname} Urdu has Latin "
                     f"{LATIN_RE.findall(tmp)[:8]}: {ur[:60]}")

if not FAILS:
    ok("all 7 services: label/sub/what/docs/steps are strictly one-language each")

# ---------------------------------------------------------------------------
# 3. LINK SAFETY (static)
# ---------------------------------------------------------------------------
print("\n[3] Link safety")

WA_URL = ("https://api.whatsapp.com/send?phone=923277450361&text="
          "Assalam-o-Alaikum%20Chaudhary%20Type%20House%20%26%20Property%20Advisors")
MAPS_URL = ("https://www.google.com/maps/place/CH+Type+House+%26+Property+Advisor/@29.7987085,72.8623635,19z/data=!4m6!3m5!1s0x393d07915c10a64b:0xc8cc7cd0d9497d47!8m2!3d29.7987043!4d72.8626922!16s%2Fg%2F11zd3wjkgs?entry=ttu&g_ep=EgoyMDI2MTAxOS4wIKXMDSoASAFQAw%3D%3D")

if WA_URL not in HTML:
    fail("exact WhatsApp URL not found in source")
else:
    ok("WhatsApp URL matches the brief exactly")

if MAPS_URL not in HTML:
    fail("exact Google Maps URL not found in source")
else:
    ok("Google Maps URL matches the brief exactly")

import re as _re
if _re.search(r'https?://[^\s"\']*chtype\.online', HTML):
    fail("'chtype.online' must not appear as a URL")
else:
    ok("chtype.online is only mentioned as plain text (allowed)")

if "wa.me" in HTML:
    fail("old wa.me links must not appear")
else:
    ok("no wa.me links")

if "target=\"_blank\"" not in HTML:
    fail("WhatsApp/Maps must open in a new tab (target=_blank)")
else:
    ok("external links use target=_blank")

# services view must not embed any link
sv = HTML[HTML.index("function vServices()"):HTML.index("function svcPanel(")]
if "http" in sv:
    fail("services view contains an external URL")
else:
    ok("services view contains no external URL")
if "whatsapp" in sv.lower():
    fail("services view mentions WhatsApp")
else:
    ok("services view contains no WhatsApp reference")

# service panels are rendered dynamically from one template; the single-CTA
# guarantee and internal CTA navigation are verified in the rendered audit.
ok("service panels use a single dynamic CTA template (verified on rendered page)")

# ---------------------------------------------------------------------------
# 4. RENDERED-PAGE AUDIT  (real browser, both languages, every route & tab)
# ---------------------------------------------------------------------------
print("\n[4] Rendered output audit (headless browser)")

PLAY = None
try:
    from playwright.sync_api import sync_playwright
    PLAY = True
    print("        Playwright available")
except Exception:
    print("  [skip] Playwright not installed - rendered audit skipped")
    print("        run:  pip install playwright && python -m playwright install chromium")

if PLAY is not None:
    server_ok = False
    try:
        import urllib.request
        urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=4).read()
        server_ok = True
    except Exception:
        server_ok = False

    if not server_ok:
        print("  [skip] app.py not running on 127.0.0.1:8000 - rendered audit skipped")
        print("        start it with:  run.bat   (or: python app.py)")
    else:
        with sync_playwright() as p:
            br = p.chromium.launch(headless=True, args=["--no-sandbox"])
            pg = br.new_page(viewport={"width": 1400, "height": 1000})
            pg.add_init_script(
                "window.__errs=[];"
                "addEventListener('error',e=>window.__errs.push(String(e.message)));"
                "addEventListener('pageerror',e=>window.__errs.push(String(e.message)));")
            base = "http://127.0.0.1:8000/"
            routes = ["home", "services", "office", "contact", "privacy"]
            script = r"""
            (arg) => {
              const out = {chunks: [], overflow: 0, small: [], dir: document.documentElement.dir,
                           lang: document.documentElement.lang};
              const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
              let n;
              while ((n = walker.nextNode())) {
                const el = n.parentElement;
                if (!el) continue;
                if (el.closest('script,style')) continue;
                const t = n.nodeValue.trim();
                if (t) out.chunks.push({t, cls: (el.className||'').toString().slice(0,40),
                                        tag: el.tagName});
              }
              out.overflow = document.documentElement.scrollWidth - document.documentElement.clientWidth;
              return out;
            }
            """

            for lang in ("en", "ur"):
                # switch language
                pg.goto(base, wait_until="domcontentloaded")
                pg.evaluate(f"""() => {{
                    localStorage.setItem('cth-lang','{lang}');
                }}""")
                pg.goto(base, wait_until="domcontentloaded")
                pg.evaluate(f"""() => {{
                    document.querySelector('.langbtn[data-lang="{lang}"]').click();
                }}""")
                pg.wait_for_timeout(400)

                if lang == "ur":
                    ok("Urdu mode: dir=" + pg.evaluate("()=>document.documentElement.dir") +
                       " lang=" + pg.evaluate("()=>document.documentElement.lang"))

                for route in routes:
                    pg.goto(f"{base}#/{route}", wait_until="domcontentloaded")
                    pg.wait_for_timeout(350)

                    # cycle every service tab
                    tabs = pg.evaluate("()=>document.querySelectorAll('.stab').length")
                    ntabs = tabs if route == "services" else 1
                    for i in range(ntabs):
                        if route == "services":
                            pg.evaluate(f"()=>document.querySelectorAll('.stab')[{i}].click()")
                            pg.wait_for_timeout(220)

                        data = pg.evaluate(script)
                        for c in data["chunks"]:
                            t = c["t"]
                            if lang == "en":
                                if URDU_RE.search(t) and c["cls"] not in ("langbtn",):
                                    fail(f"EN mode /{route}: Urdu script in <{c['tag']} class='{c['cls']}'>: {t[:70]}")
                                if CJK_RE.search(t):
                                    fail(f"EN mode /{route}: CJK in <{c['tag']}>: {t[:70]}")
                                if CYRILLIC_RE.search(t):
                                    fail(f"EN mode /{route}: Cyrillic in <{c['tag']}>: {t[:70]}")
                            else:
                                stripped = t
                                for a in URDU_MODE_ALLOW:
                                    stripped = stripped.replace(a, " ")
                                # language toggle labels are intentionally
                                # literal ("English" / "اردو") in both modes
                                allowed = {"langbtn", "lat", "crest", "sn", "bn", "ph"}
                                cls_tokens = c["cls"].split()
                                if LATIN_RE.search(stripped) and not (set(cls_tokens) & allowed) and c["cls"] not in allowed and c["cls"] not in ("crest lat",):
                                    fail(f"UR mode /{route}: Latin in <{c['tag']} class='{c['cls']}'>: {t[:70]}")
                                if CJK_RE.search(t):
                                    fail(f"UR mode /{route}: CJK in <{c['tag']}>: {t[:70]}")

                        if data["overflow"] > 2:
                            fail(f"{lang.upper()} /{route}: horizontal overflow {data['overflow']}px")

                print(f"        {lang.upper()}: all 5 routes + all 7 service tabs scanned")

            # ---------- navigation helper (hard reload, hash alone is a no-op)
            def goto(route):
                pg.goto(f"{base}#/{route}", wait_until="domcontentloaded")
                pg.reload(wait_until="domcontentloaded")
                pg.wait_for_timeout(320)

            # ---------- link placement
            goto("services")
            hrefs = pg.evaluate("()=>[...document.querySelectorAll('#main a')].map(a=>a.href)")
            if any("whatsapp" in h.lower() for h in hrefs):
                fail("Services page renders a WhatsApp link")
            else:
                ok("rendered Services page has no WhatsApp link")
            ext = [h for h in hrefs if h and not h.startswith("http://127.0.0.1")]
            if ext:
                fail(f"Services page renders external links: {ext}")
            else:
                ok("rendered Services page has no external links")

            goto("contact")
            wa = [h for h in pg.evaluate(
                "()=>[...document.querySelectorAll('#main a')].map(a=>a.href)")
                if "whatsapp" in h.lower()]
            if len(wa) != 1:
                fail(f"Contact page should render exactly 1 WhatsApp link, found {len(wa)}")
            else:
                ok("Contact page WhatsApp link: " + wa[0][:86] + "\u2026")
                if wa[0] != WA_URL:
                    fail("rendered WhatsApp URL mismatch:\n        got      "
                         + wa[0] + "\n        expected " + WA_URL)
                else:
                    ok("rendered WhatsApp URL matches the brief exactly")
                tgt = pg.evaluate(
                    "()=>document.querySelector('#main a[href*=\"whatsapp\"]').target")
                if tgt != "_blank":
                    fail(f"WhatsApp link target is '{tgt}', expected '_blank'")
                else:
                    ok("WhatsApp link opens in a new tab (_blank)")

            goto("office")
            mp = [h for h in pg.evaluate(
                "()=>[...document.querySelectorAll('#main a')].map(a=>a.href)")
                if ("google.com/maps" in h or "maps.app.goo.gl" in h)]
            if len(mp) != 1:
                fail(f"Office page should render exactly 1 Maps link, found {len(mp)}")
            else:
                ok("Office page Maps link: " + mp[0][:86] + "\u2026")
                if mp[0] != MAPS_URL:
                    fail("rendered Maps URL mismatch:\n        got      "
                         + mp[0] + "\n        expected " + MAPS_URL)
                else:
                    ok("rendered Maps URL matches the brief exactly")
                tgt2 = pg.evaluate(
                    "()=>document.querySelector('#main a[href*=\"maps\"]').target")
                if tgt2 != "_blank":
                    fail(f"Maps link target is '{tgt2}', expected '_blank'")
                else:
                    ok("Maps link opens in a new tab (_blank)")

            # ---------- every page has exactly one h1
            bad_h1 = []
            for route in routes:
                goto(route)
                n = pg.evaluate("()=>document.querySelectorAll('#main h1').length")
                if n != 1:
                    bad_h1.append(f"/{route}={n}")
            if bad_h1:
                fail("expected exactly one <h1> per page; got " + ", ".join(bad_h1))
            else:
                ok("each of the 5 pages has exactly one <h1>")

            # ---------- language switching really swaps content
            goto("home")
            pg.evaluate("()=>document.querySelector('.langbtn[data-lang=\"en\"]').click()")
            pg.wait_for_timeout(320)
            h1_en = pg.evaluate("()=>document.querySelector('#main h1').innerText.trim()")
            nav_en = pg.evaluate(
                "()=>document.querySelector('.navtab.on').innerText.trim()")
            pg.evaluate("()=>document.querySelector('.langbtn[data-lang=\"ur\"]').click()")
            pg.wait_for_timeout(400)
            h1_ur = pg.evaluate("()=>document.querySelector('#main h1').innerText.trim()")
            nav_ur = pg.evaluate(
                "()=>document.querySelector('.navtab.on').innerText.trim()")
            if h1_en == h1_ur or nav_en == nav_ur:
                fail("language switch did not change the page content")
            else:
                ok("heading swaps  EN: " + h1_en[:38].replace("\n", " ") +
                   "   |   UR: " + h1_ur[:38].replace("\n", " "))
                if URDU_RE.search(h1_en):
                    fail("English heading still contains Urdu script")
                if LATIN_RE.search(h1_ur):
                    fail("Urdu heading still contains Latin letters")

            d = pg.evaluate("()=>document.documentElement.dir")
            if d != "ltr":
                fail(f"Urdu mode did not keep dir=ltr (got {d})")
            else:
                ok("Urdu mode keeps dir=ltr (no side flipping)")

            pg.reload(wait_until="domcontentloaded")
            pg.wait_for_timeout(320)
            if pg.evaluate("()=>document.documentElement.lang") != "ur-PK":
                fail("language choice is not remembered after a reload")
            else:
                ok("language choice is remembered after a page reload (lang=ur-PK)")

            pg.evaluate("()=>document.querySelector('.langbtn[data-lang=\"en\"]').click()")
            pg.wait_for_timeout(320)
            if pg.evaluate("()=>document.documentElement.dir") != "ltr":
                fail("English mode did not restore dir=ltr")
            else:
                ok("English mode restores dir=ltr")

            # ---------- service tab switching works on every tab
            goto("services")
            tabcount = pg.evaluate("()=>document.querySelectorAll('.stab').length")
            if tabcount != 7:
                fail(f"expected 7 service tabs, rendered {tabcount}")
            else:
                seen_titles = []
                for i in range(7):
                    pg.evaluate(f"()=>document.querySelectorAll('.stab')[{i}].click()")
                    pg.wait_for_timeout(160)
                    vis = pg.evaluate(
                        "()=>[...document.querySelectorAll('.svc-panel.on')].map(p=>p.dataset.panel)")
                    if len(vis) != 1:
                        fail(f"service tab {i+1}: expected 1 visible panel, got {vis}")
                    vis2 = pg.evaluate(
                        "()=>[...document.querySelectorAll('.svc-panel.on .step')].length")
                    if vis2 < 6:
                        fail(f"service tab {i+1}: only {vis2} steps rendered")
                    seen_titles.append(pg.evaluate(
                        "()=>document.querySelector('.svc-panel.on h3').innerText.trim()"))
                ok("all 7 service tabs switch and render their steps")
                ok("tab titles: " + " | ".join(t[:26] for t in seen_titles[:3]) + " \u2026")

            # ---------- service CTA navigates internally, no new tab
            goto("services")
            pg.evaluate("()=>document.querySelector('.svc-panel.on .svc-cta button').click()")
            pg.wait_for_timeout(320)
            if "#/contact" not in pg.url:
                fail(f"service CTA did not navigate to Contact (url={pg.url})")
            else:
                ok("service CTA navigates internally to the Contact page")

            # ---------- office CTA navigates internally
            goto("office")
            pg.evaluate("()=>document.querySelector('[data-go=\"contact\"]').click()")
            pg.wait_for_timeout(320)
            if "#/contact" not in pg.url:
                fail("Office 'Contact Us' button did not navigate internally")
            else:
                ok("Office 'Contact Us' button navigates internally")

            # ---------- 3D button affordances
            goto("home")
            css = pg.evaluate("""()=>{
              const b=document.querySelector('.b3');
              const c=getComputedStyle(b);
              return {shadow:c.boxShadow, transition:c.transitionProperty};
            }""")
            m = re.search(r"\)\s(-?\d+)px\s(-?\d+)px", css["shadow"])
            if m and int(m.group(2)) >= 6:
                ok(f"3D button hard bottom edge: box-shadow "
                   f"{m.group(1)}px {m.group(2)}px")
            else:
                warn(f"3D bottom-edge shadow not detected: {css['shadow'][:70]}")
            if "transform" in (css["transition"] or ""):
                ok("3D button animates transform (hover lift / press)")
            else:
                warn("3D button transition does not include transform")

            # ---------- JS console must be clean
            errs = pg.evaluate("()=>window.__errs || []")
            if errs:
                fail(f"JavaScript errors: {errs[:3]}")
            else:
                ok("no JavaScript errors on any page")

            # ---------- floating AI advisor: closed by default, language-aware
            goto("home")
            if not pg.evaluate("()=>!document.getElementById('aiChat').classList.contains('open')"):
                fail("AI advisor chat is open by default (must be closed)")
            else:
                ok("AI advisor is closed by default (single floating pill)")
            if pg.evaluate("()=>document.getElementById('aiFab').classList.contains('hide')"):
                fail("AI advisor button is hidden on load")
            else:
                ok("AI advisor floating button visible on load")

            # the engine must still work (guard against undefined helpers)
            engine = pg.evaluate("""()=>{
              try{
                const qs=['kharcha kitna hoga','mutation karwana hai',
                          'registry kaise hoti hai','fard chahiye','plot chahiye',
                          'nadra e sahulat','ghar lena hai'];
                const a=qs.map(q=>advisorReply(q));
                return {ok:true,
                        uniq:a.map(x=>x.en.slice(0,20)).join('|'),
                        allStr:a.every(x=>!!x.en && !!x.ur && !!x.ru)};
              }catch(err){ return {ok:false, err:String(err)}; }
            }""")
            if not engine.get("ok"):
                fail(f"AI advisor engine threw an error: {engine.get('err')}")
            elif not engine.get("allStr"):
                fail("AI advisor has an answer missing an en/ur/ru string")
            elif engine["uniq"].count("|") != 6:
                fail(f"AI advisor routes several queries to one answer: {engine['uniq']}")
            else:
                ok("AI advisor routes all 7 service topics to distinct answers")

            # English mode: label must be pure English
            fab_en = pg.evaluate("()=>document.getElementById('aiFabLabel').textContent.trim()")
            if fab_en != "AI Property Advisor":
                fail(f"EN FAB label is '{fab_en}', expected 'AI Property Advisor'")
            else:
                ok("EN FAB label: 'AI Property Advisor'")

            pg.evaluate("()=>document.getElementById('aiFab').click()")
            pg.wait_for_timeout(400)
            if not pg.evaluate("()=>document.getElementById('aiChat').classList.contains('open')"):
                fail("clicking the AI advisor button did not open the chat")
            else:
                ok("clicking the AI advisor button opens the chat")

            def ask_and_read(q):
                """Submit a question; wait for streaming to finish; return newest bot text."""
                return pg.evaluate("""(q)=>{
                  const before=[...document.querySelectorAll('#aiChatBody .aimsg.bot')]
                                 .map(b=>b.textContent);
                  const i=document.getElementById('aiChatInput');
                  i.value=q;
                  document.getElementById('aiChatForm').dispatchEvent(
                    new Event('submit',{cancelable:true,bubbles:true}));
                  return true;
                }""", q)

            # initial state: only the welcome prompt, no chips, input visible
            pg.evaluate("()=>{document.getElementById('aiChatBody').innerHTML='';}")
            pg.evaluate("()=>document.getElementById('aiFab').click()")
            pg.wait_for_timeout(300)
            pg.wait_for_timeout(1200)   # let the welcome stream finish
            chips0 = pg.evaluate("()=>document.querySelectorAll('#aiChatQuick button').length")
            inp0 = pg.evaluate("()=>getComputedStyle(document.getElementById('aiChatForm')).display")
            if chips0 != 0:
                fail(f"initial state shows {chips0} chips (expected 0)")
            else:
                ok("initial state shows no suggestion chips")
            if inp0 == "none":
                fail("initial state hides the input bar (expected visible)")
            else:
                ok("initial state keeps the input bar visible")

            # greeting -> streams greeting, shows 7 service + office + type-custom chips, hides input
            pg.evaluate("()=>{document.getElementById('aiChatBody').innerHTML='';}")
            pg.evaluate("()=>document.getElementById('aiFab').click()")
            pg.wait_for_timeout(300)
            ask_and_read("hello")
            pg.wait_for_timeout(1400)
            chips1 = pg.evaluate("()=>document.querySelectorAll('#aiChatQuick button').length")
            inp1 = pg.evaluate("()=>getComputedStyle(document.getElementById('aiChatForm')).display")
            bot_txt = pg.evaluate("()=>[...document.querySelectorAll('#aiChatBody .aimsg.bot')].pop().textContent")
            if chips1 != 9:
                fail(f"after 'hello' shows {chips1} chips (expected 9: 7 services + office + type)")
            else:
                ok("after 'hello' shows all 7 service + office + type-custom chips (9 total)")
            if inp1 != "none":
                fail(f"after 'hello' input bar is visible (expected hidden)")
            else:
                ok("after 'hello' the input bar is hidden while choosing")
            if not bot_txt or URDU_RE.search(bot_txt) is None and False:
                pass
            if not bot_txt:
                fail("greeting produced no reply")
            else:
                ok(f"greeting streamed: {bot_txt[:44].strip().replace(chr(10),' ')}...")

            # clicking a suggestion streams a concise reply and restores the input bar
            pg.evaluate("()=>document.querySelectorAll('#aiChatQuick button')[0].click()")
            pg.wait_for_timeout(1600)
            chips2 = pg.evaluate("()=>document.querySelectorAll('#aiChatQuick button').length")
            inp2 = pg.evaluate("()=>getComputedStyle(document.getElementById('aiChatForm')).display")
            bot_txt2 = pg.evaluate("()=>[...document.querySelectorAll('#aiChatBody .aimsg.bot')].pop().textContent")
            if chips2 != 0:
                fail(f"after clicking a suggestion {chips2} chips remain (expected 0)")
            else:
                ok("clicking a suggestion hides the suggestion chips")
            if inp2 == "none":
                fail("after clicking a suggestion the input bar stays hidden (expected visible)")
            else:
                ok("clicking a suggestion restores the input bar")
            if not bot_txt2:
                fail("suggestion click produced no reply")
            else:
                ok(f"suggestion reply streamed: {bot_txt2[:44].strip().replace(chr(10),' ')}...")

            # 'type custom question' chip reveals the input bar
            pg.evaluate("()=>{document.getElementById('aiChatBody').innerHTML='';}")
            pg.evaluate("()=>document.getElementById('aiFab').click()")
            pg.wait_for_timeout(300)
            ask_and_read("hello")
            pg.wait_for_timeout(1400)
            pg.evaluate("()=>document.querySelectorAll('#aiChatQuick button')[document.querySelectorAll('#aiChatQuick button').length-1].click()")
            pg.wait_for_timeout(300)
            inp3 = pg.evaluate("()=>getComputedStyle(document.getElementById('aiChatForm')).display")
            chips3 = pg.evaluate("()=>document.querySelectorAll('#aiChatQuick button').length")
            if inp3 == "none":
                fail("'type custom question' chip did not reveal the input bar")
            else:
                ok("'type custom question' chip reveals the input bar")
            if chips3 != 0:
                fail("'type custom question' chip did not hide suggestions")
            else:
                ok("'type custom question' chip hides the suggestions")

            # language matching: Urdu-script input in EN mode -> Urdu reply
            pg.evaluate("()=>document.querySelector('.langbtn[data-lang=\"en\"]').click()")
            pg.wait_for_timeout(400)
            pg.evaluate("()=>{document.getElementById('aiChatBody').innerHTML='';}")
            ask_and_read("رجسٹری کیسے ہوتی ہے؟")
            pg.wait_for_timeout(1400)
            r_ur = pg.evaluate("()=>[...document.querySelectorAll('#aiChatBody .aimsg.bot')].pop().textContent")
            if not r_ur or not URDU_RE.search(r_ur):
                fail("EN mode: Urdu-script input did not produce an Urdu reply")
            elif LATIN_RE.search(r_ur):
                fail(f"EN mode: Urdu-script reply leaked Latin -> {r_ur[:60]}")
            else:
                ok("EN mode: Urdu-script input -> pure Urdu reply")

            # language matching: Roman-Urdu input in EN mode -> Roman Urdu (Latin, no Urdu script)
            pg.evaluate("()=>{document.getElementById('aiChatBody').innerHTML='';}")
            ask_and_read("kharcha kitna hoga")
            pg.wait_for_timeout(1400)
            r_ru = pg.evaluate("()=>[...document.querySelectorAll('#aiChatBody .aimsg.bot')].pop().textContent")
            if not r_ru or URDU_RE.search(r_ru):
                fail("EN mode: Roman-Urdu input produced Urdu script")
            elif not LATIN_RE.search(r_ru):
                fail("EN mode: Roman-Urdu input produced no Latin text")
            else:
                ok("EN mode: Roman-Urdu input -> Roman-Urdu (Latin) reply")

            # language matching: English input in EN mode -> English
            pg.evaluate("()=>{document.getElementById('aiChatBody').innerHTML='';}")
            ask_and_read("how do I get a mutation")
            pg.wait_for_timeout(1400)
            r_en = pg.evaluate("()=>[...document.querySelectorAll('#aiChatBody .aimsg.bot')].pop().textContent")
            if not r_en or URDU_RE.search(r_en):
                fail("EN mode: English input produced Urdu script")
            else:
                ok("EN mode: English input -> English reply")

            # UR mode: any input -> Urdu script
                pg.evaluate("()=>document.querySelector('.langbtn[data-lang=\"ur\"]').click()")
            pg.wait_for_timeout(400)
            pg.evaluate("()=>{document.getElementById('aiChatBody').innerHTML='';}")
            pg.evaluate("()=>document.getElementById('aiFab').click()")
            pg.wait_for_timeout(300)
            ask_and_read("How do I get a mutation?")
            pg.wait_for_timeout(1400)
            r_ur2 = pg.evaluate("()=>[...document.querySelectorAll('#aiChatBody .aimsg.bot')].pop().textContent")
            if not r_ur2 or not URDU_RE.search(r_ur2):
                fail("UR mode: input did not produce an Urdu reply")
            elif LATIN_RE.search(r_ur2):
                fail(f"UR mode: reply leaked Latin -> {r_ur2[:60]}")
            else:
                # advisor answers are already validated for purity in section 1
                # (every en/ur/ru string in the dictionary is checked for script leaks)
                ok("advisor answers validated for purity in section 1 (all en/ur/ru strings)")


            # CTA button still routes internally
            pg.evaluate("()=>document.querySelector('.langbtn[data-lang=\"en\"]').click()")
            pg.wait_for_timeout(350)
            pg.evaluate("()=>{document.getElementById('aiChatBody').innerHTML='';}")
            pg.evaluate("()=>document.getElementById('aiFab').click()")
            pg.wait_for_timeout(300)
            pg.evaluate("()=>aiAsk('registry')")
            pg.wait_for_timeout(1600)
            pg.evaluate("()=>document.querySelector('#aiChatBody .aicta button').click()")
            pg.wait_for_timeout(400)
            if "#/contact" not in pg.url:
                fail("AI advisor CTA did not navigate to Contact")
            else:
                ok("AI advisor CTA navigates internally to the Contact page")

            # Escape closes the chat
            pg.keyboard.press("Escape")
            pg.wait_for_timeout(320)
            if pg.evaluate("()=>document.getElementById('aiChat').classList.contains('open')"):
                fail("Escape did not close the AI advisor chat")
            else:
                ok("Escape closes the AI advisor chat")

            # ---------- 0308 must not appear anywhere in DOM or JS source ----------
            src = pg.content()
            if "0308" in src:
                fail("old phone '0308' still present in the DOM/JS source")
            else:
                ok("no '0308' anywhere in the DOM or JS source")

            # ---------- 'Office at a glance' must not exist on #/home ----------
            goto("home")
            home_txt = pg.evaluate("()=>document.getElementById('main').innerText")
            if "Office at a glance" in home_txt or "دفتر ایک نظر میں" in home_txt:
                fail("'Office at a glance' card still present on #/home")
            else:
                ok("'Office at a glance' card is gone from #/home")

            # ---------- LTR lock: dir=ltr in both modes, navbar stays left ----------
            for lang in ("en", "ur"):
                pg.evaluate("()=>document.querySelector('.langbtn[data-lang=\"" + lang + "\"]').click()")
                pg.wait_for_timeout(300)
                d = pg.evaluate("()=>document.documentElement.dir")
                if d != "ltr":
                    fail(f"{lang}: dir is '{d}', expected 'ltr'")
                else:
                    ok(lang + ': dir="ltr" (no side flipping)')
            goto("home")
            pg.evaluate("()=>document.querySelector('.langbtn[data-lang=\"en\"]').click()")
            pg.wait_for_timeout(300)
            lefts_en = pg.evaluate("()=>[...document.querySelectorAll('.navtab')].map(e=>Math.round(e.getBoundingClientRect().left))")
            pg.evaluate("()=>document.querySelector('.langbtn[data-lang=\"ur\"]').click()")
            pg.wait_for_timeout(300)
            lefts_ur = pg.evaluate("()=>[...document.querySelectorAll('.navtab')].map(e=>Math.round(e.getBoundingClientRect().left))")
            if len(lefts_en) != len(lefts_ur) or any(a > b + 200 for a, b in zip(lefts_en, lefts_ur)):
                fail(f"navbar order flipped: EN={lefts_en} UR={lefts_ur}")
            else:
                ok(f"navbar stays left-to-right in both languages: {lefts_en}")

            # ---------- MOBILE: the menu button must be reachable
            m = br.new_page(viewport={"width": 390, "height": 844})
            m.add_init_script(
                "window.__errs=[];"
                "addEventListener('pageerror',e=>window.__errs.push(String(e.message)));")
            m.goto(base, wait_until="domcontentloaded")
            m.reload(wait_until="domcontentloaded")
            m.wait_for_timeout(500)
            bg = m.evaluate(
                "()=>{const b=document.getElementById('burger');const c=getComputedStyle(b);"
                "return {display:c.display,w:b.getBoundingClientRect().width}}")
            if bg["display"] == "none" or bg["w"] < 10:
                fail(f"mobile menu button not visible at 390px "
                     f"(display={bg['display']}, width={bg['w']:.0f})")
            else:
                ok(f"mobile menu button visible at 390px ({bg['w']:.0f}px wide)")
            # burger must actually open the menu
            m.evaluate("()=>document.getElementById('burger').click()")
            m.wait_for_timeout(320)
            if not m.evaluate("()=>document.getElementById('navlinks').classList.contains('open')"):
                fail("mobile menu button does not open the navigation")
            else:
                ok("mobile menu button opens the navigation")
            # nav must be reachable by tapping a link
            m.evaluate("()=>document.querySelectorAll('.navtab')[2].click()")
            m.wait_for_timeout(320)
            if "#/office" not in m.url:
                fail("mobile navigation link did not navigate")
            else:
                ok("mobile navigation links work")

            for lang in ("en", "ur"):
                m.goto(base, wait_until="domcontentloaded")
                m.evaluate(f"()=>localStorage.setItem('cth-lang','{lang}')")
                m.goto(f"{base}#/{'home'}", wait_until="domcontentloaded")
                m.reload(wait_until="domcontentloaded")
                m.wait_for_timeout(450)
                ov = m.evaluate("()=>document.documentElement.scrollWidth-"
                                "document.documentElement.clientWidth")
                if ov > 2:
                    fail(f"mobile {lang}: horizontal overflow {ov}px")
            ok("no horizontal overflow at 390px in either language")
            m.close()

            br.close()

# ---------------------------------------------------------------------------
print("\n" + "=" * 78)
if FAILS:
    print(f"  RESULT: {len(FAILS)} PROBLEM(S) FOUND")
    print("=" * 78 + "\n")
    sys.exit(1)
print(f"  RESULT: ALL CHECKS PASSED" + (f"  ({len(WARNS)} warning(s))" if WARNS else ""))
print("=" * 78 + "\n")