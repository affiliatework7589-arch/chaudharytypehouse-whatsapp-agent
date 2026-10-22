# -*- coding: utf-8 -*-
"""
core/ai_engine.py — The Bilingual (Roman Urdu + Urdu) Smart Response Engine.

DESIGN GOALS
------------
1. Works 100% OFFLINE and INSTANTLY. Zero API key required. Zero paid service.
2. Understands Roman Urdu ("registry kaise hota hai?") AND Urdu script ("رجسٹری کیسے ہوتی ہے؟")
   and answers in the SAME language the customer used.
3. Optional free Gemini tier (gemini-2.5-flash) is blended in when a key is
   present — but the system never depends on it.
4. Multi-turn lead capture: Name → Service → Preferred visit time → WhatsApp handoff.
5. Always ends with a free zero-cost WhatsApp deep link to +92 327 7450361.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import config
from core import db

# ---------------------------------------------------------------------------
# LANGUAGE DETECTION
# ---------------------------------------------------------------------------
URDU_BLOCK = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")

# Words that must never be mistaken for a customer's name.
NAME_STOPWORDS = {
    "kya", "hai", "hain", "ka", "ki", "ke", "ko", "mein", "par", "aur", "ya", "se",
    "mujhe", "chahiye", "kaise", "kar", "karna", "karo", "karein", "karwana", "karta",
    "karti", "karte", "batao", "batayein", "bata", " bata", "please", "mujhko", "hum",
    "aap", "main", "mera", "meri", "hamara", "hamari", "koi", "sab", "sari", "har",
    "sir", "ji", "hai?", "hona", "hota", "hoti", "lage", "lagta", "chahiye?", "krna",
    "krwa", "krwaya", "dalna", "dena", "lena", "dena", "banwa", "banwana", "aaunga",
    "aaungi", "aana", "aayega", "aaye", "abhi", "foran", "jaldi", "aaj", "kal", "parso",
    "shaam", "subah", "dopahar", "raat", "shukriya", "thanks", "assalam", "salam",
    "salam", "salaam", "hello", "hi", "hey", "the", "and", "for", "you", "your",
    "please", "how", "what", "when", "where", "why", "is", "are", "my", "me", "i",
}


def detect_language(text: str) -> str:
    """'urdu' if the message contains Urdu/Arabic script letters, else 'roman'."""
    return "urdu" if URDU_BLOCK.search(text or "") else "roman"


def normalize(text: str) -> str:
    """Lowercase, strip accents/punctuation-ish noise for keyword matching."""
    t = (text or "").lower()
    t = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = re.sub(r"[^a-z0-9\u0600-\u06FF\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def kw_hit(text_norm: str, keyword: str) -> bool:
    """
    Word-boundary match for Latin keywords so 'chahiye' never matches 'hi',
    while Urdu/Arabic keywords (which are not space-separated) match as substrings.
    """
    k = normalize(keyword).strip()
    if not k:
        return False
    if re.search(r"[\u0600-\u06FF]", k):
        return k in text_norm
    return re.search(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])", text_norm) is not None


def wa_link(message: str) -> str:
    """Zero-cost WhatsApp click-to-chat deep link with the message pre-filled."""
    return f"{config.WHATSAPP_LINK}?text={quote(message, safe='')}"


# ---------------------------------------------------------------------------
# SERVICE CATALOGUE  (single source of truth, 16 services)
# ---------------------------------------------------------------------------
@dataclass
class Service:
    key: str
    title_ru: str
    title_ur: str
    icon: str
    blurb_ru: str
    blurb_ur: str
    keywords: List[str] = field(default_factory=list)
    priority: int = 0        # higher = more specific, wins keyword-length ties


SERVICES: List[Service] = [
    Service("registry", "Zameen ki Registry", "زمین کی رجسٹری", "📄",
            "Jamandari / Arazi Registry – naam, khatoni number aur malik ke naam par nayi registry.",
            "جمندری / اراضی رجسٹری — نام، کھتونی نمبر اور مالک کے نام پر نئی رجسٹری۔",
            ["registry", "reg", "register", "jamandari", "jamandari registry", "zameen registry",
             "land registry", "razi registry", "arazi registry", "new registry", "registry karwana",
             "رجسٹری", "رجسٹر", "جمندری"]),
    Service("file", "Registry ki Complete File", "رجسٹری کی مکمل فائل", "🗂️",
            "Poori file: Registry, Fard, Mutation, verification aurkhayen — ek jagah.",
            "مکمل فائل: رجسٹری، فرد، انتقال، تصدیقی کاغذات — ایک جگہ۔",
            ["complete file", "file", "puri file", "muttamil file", "registry file", "documents file",
             "papers", "takbeer", "file tayyar", "مکمل فائل", "فائل"]),
    Service("fard", "Fard (Fard-e-Malkiat / Jamabandi)", "فرد (فردِ ملکیت)", "📋",
            "Jamabandi ka Fard, Fard ki copy aur Fard ke usool par tamam kaam.",
            "جمبندی کا فرد، فرد کی کاپی اور فرد کے اصول پر تمام کام۔",
            ["fard", "jamabandi", "fard e malkiat", "fard-e-malkiat", "fard malikat", "khatooni",
             "khatuni", "jamabandi ka fard", "land record", "mutation", "تغییر", "فرد", "فرد ملکیت", "جمبندی", "کھتونی"]),
    Service("bainama", "Bai Nama / Bay Nama (بیع نامہ)", "بیع نامہ", "📜",
            "Khareed-o-farokht ka rasmi bay nama — khatoni ke saath tayyar.",
            "خرید و فروخت کا رسمی بیع نامہ — کھتونی کے ساتھ تیار۔",
            ["bay nama", "bai nama", "bainama", "sale deed", "sale contract", "agreement",
             "bil e hoch", "bayanama", "بیع نامہ", "بیع", "سیل ڈیڈ"]),
    Service("inteqal", "Zameen ka Inteqal", "زمین کا انتقال", "🔁",
            "Wirasat aur khareed-o-farokht ka inteqal — dono taraf se poora kaam.",
            "وراثت اور خرید و فروخت کا انتقال — دونوں طرف سے پورا کام۔",
            ["inteqal", "intiqal", "transfer", "mutation", "انتقال", "تغییر"]),
    Service("inteqal_wirasat", "Wirasat ka Inteqal", "وراثت کا انتقال", "🕊️",
            "Death certificate, heir certificate aur family register ke mutabiq naam badal kar registry.",
            "Death certificate، heir certificate اور family register کے مطابق نام بدل کر registry۔",
            ["wirasat", "inheritance", "warasat", "heir", "nasheel", "death certificate",
             "وراثت", "heir certificate", "میراث"], priority=1),
    Service("inteqal_khareed", "Khareed-o-Farokht ka Inteqal", "خرید و فروخت کا انتقال", "🤝",
            "Sale ke baad naam badalna — tayfe ke saath poora inteqal ka kaam.",
            "Sale کے بعد نام بدلنا — تکیے کے ساتھ پورا انتقال۔",
            ["khareed", "farokht", "sale ke baad", "naam badalna", "tabahi",
              "خرید", "فروخت", "تبدیلی نام"], priority=1),
    Service("muawin_ajra", "Arazi Muawin – Fard ka Ajra", "اراضی معاون – فرد کا اجرا", "📄",
            "Muawin franchise ke zariye fard ki mukhtalif awraaj (copies) tayyar.",
            "معاون فرانچائز کے ذریعے فرد کی مختلف اوراج (کاپیاں) تیار۔",
            ["ajra", "awraj", "copy", "photocopy", "muawin", "moavin", "fard ajra",
             "اجرا", "اوراج", "معاون", "فرد کا اجرا"], priority=1),
    Service("muawin_hasool", "Arazi Muawin – Fard ka Hasool", "اراضی معاون – فرد کا تحصیل", "✅",
            "Hasool / parcha tayyar karna aur us ki tasdeeq.",
            "تحصیل / پرچہ تیار کرنا اور اس کی تصدیق۔",
            ["hasool", "hassool", "parcha", "obtain fard", "fard hasil", "hasul",
             "تحصیل", "پرچہ", "حاصل"], priority=1),
    Service("muawin_zamanat", "Arazi Muawin – Fard Zamanat", "اراضی معاون – فرد ضمانت", "🛡️",
            "Fard ki zamanat / attestation – dhoka se bachne ke liye.",
            "فرد کی ضمانت / تصدیق — دھوکے سے بچنے کے لیے۔",
            ["zamanat", "attestation", "tasdeeq", "verify", "guarantee", "anti fraud",
             "ضمانت", "تصدیق", "توثیق"], priority=1),
    Service("property", "Property Advisors & Dealing", "پراپرٹی اڈوایزر اینڈ ڈیلنگ", "🏘️",
            "Chishtian mein plots, zarai zameen aur makaan — khareed, farokht aur dealing.",
            "چشتیاں میں پلاٹ، زرعی زمین اور مکان — خرید، فروخت اور ڈیلنگ۔",
            ["property", "dealing", "dealer", "advisor", "buy", "sale",
             "پراپرٹی", "ڈیلنگ", "اڈوایزر"]),
    Service("property_plots", "Plots (Abadi & Commercial)", "پلاٹ (ابادی و کمرشل)", "🏠",
            "Residential aur commercial plots — deal aur registry dono.",
            "رہائشی اور کمرشل پلاٹ — ڈیل اور رجسٹری دونوں۔",
            ["plot", "plots", "abadi plot", "commercial plot", "پلاٹ", "پلاٹس"], priority=1),
    Service("property_zara", "Zarai Zameen (Agri Land)", "زرعی زمین", "🌾",
            "Kheti ki zameen, khet, kisan zameen — khareed-o-farokht aur verification.",
            "کھیت کی زمین، کسان زمین — خرید و فروخت اور تصدیق۔",
            ["zara zameen", "zarai zameen", "agri", "agricultural", "khet", "kisan",
              "زرعی", "کھیت", "کسان"], priority=1),
    Service("property_makan", "Makaan khareed-o-farokht", "مکان خرید و فروخت", "🏢",
            "Ghar ka lena ya dena — Fard verify kar ke poora kaam.",
            "گھر کا لینا یا دینا — فرد تصدیق کر کے پورا کام۔",
            ["makan", "makaan", "house", "ghar", "residence", "مکان", "گھر", "مسکن"], priority=1),
    Service("nadra", "NADRA e-Sahulat", "نادرا ای سہولت", "🆔",
            "NADRA e-Sahulat center – CNIC, domicile aur doosry kaam.",
            "نادرا ای سہولت سینٹر – سی آئی سی، ڈارمل اور دوسرے کام۔",
            ["nadra", "e sahulat", "esahulat", "cnic", "identity card", "nic", "nadan",
             "نادرا", "سی آئی سی", "شناختی کارڈ"]),
    Service("domicile", "Domicile Typing", "ڈارمل ٹائپنگ", "📝",
            "Domicile certificate ki typing aur online apply.",
            "ڈارمل سرٹیفکیٹ کی ٹائپنگ اور آن لائن اپلائی۔",
            ["domicile", "domical", "domicel", "tehseel", "تیسریل", "ڈارمل", "ڈومیسل"]),
    Service("online", "Online Apply Center", "آن لائن اپلائی سنٹر", "💻",
            "Government forms ki typing, printing aur online submission.",
            "سرکاری فارمز کی ٹائپنگ، پرننگ اور آن لائن جمع کروائی۔",
            ["online", "apply", "form", "filling", "form filling", "print", "printing",
             "آن لائن", "اپلائی", "فارم", "پرنٹ"]),
    Service("photostat", "Photostat / Printing", "فوٹو سٹیٹ / پرننگ", "🖨️",
            "Photostat, photocopy, printing aur lamination.",
            "فوٹو سٹیٹ، فوٹو کاپی، پرننگ اور لیمینیشن۔",
            ["photostat", "photocopy", "xerox", "copy", "printing", "print out", "lamination",
             "فوٹو سٹیٹ", "کاپی", "پرننگ"]),
]


def find_service(text: str) -> Optional[Service]:
    t = normalize(text)
    if not t:
        return None
    best, best_len = None, 0
    for s in SERVICES:
        for kw in s.keywords:
            k = normalize(kw).strip()
            # specificity breaks ties: "wirasat"(7) must beat generic "inteqal"(7)
            score = len(k) + (1000 if s.priority else 0)
            if k and kw_hit(t, kw) and score > best_len:
                best, best_len = s, score
    return best


# ---------------------------------------------------------------------------
# INTENT ENGINE
# ---------------------------------------------------------------------------
INTENT_KEYWORDS: List[Tuple[str, List[str]]] = [
    ("fees", ["kharcha", "kharche", "kharacha", "fees", "fee", "rate", "cost", "price",
              "kitna", "kitne", "paisa", "paisay", "rupees", "kitne paise", "charge",
              "kharcha kya", "kharcha kitna", "registry kharcha",
              "خarcha", "خArchA", "خرچہ", "فیس", "کتنے", "قیمت", "پیسے", "رقم"]),
    ("timing", ["timing", "time", "kab", "kab tak", "khula", "open", "band", "closing",
                "schedule", "hours", "subah", "shaam", "waqt",
                "اوقات", "وقت", "کب", "کب تک", "کھلا", "بند", "صبح", "شام"]),
    ("location", ["address", "location", "kahan", "kidhar", "where", "near", "baldia",
                  "baldiya", "chowk", "map", "pahunchna", "direction",
                  "پتہ", "کہاں", "کدھر", "بالڈیا", "چوک", "نشانی"]),
    ("contact", ["phone", "number", "contact", "whatsapp", "call", "ring", "mobile",
                 "phone number", "sampark", "rabta", "call karo", "phone karo",
                 "فون", "نمبر", "رابطہ", "کال", "واٹس ایپ"]),
    ("appointment", ["appointment", "book", "booking", "visit", "aana", "aaunga", "aaungi",
                     "slot", "time slot", "kab aaun", "kab aaun", "milna", "mulaqat",
                     "ملاقات", "اپائنٹمنٹ", "بکنگ", "آنا", "آؤں گا", "وقت لینا"]),
    ("services", ["services", "kya karte", "kya karti", "kaam", "menu", "list", "kaise madad",
                  "madad", "help", "kuch", "sab", "available", "option",
                  "خدمات", "کیا کرتے", "کام", "مدد", "فہرست", "آپشن"]),
    ("human", ["human", "agent", "officer", "staff", "sir", "malik", "owner", "boss",
               "insaan", "baat karni", "call karo", "insaan se",
               "آدمی", "ملازم", "محترم", "-owner", "مالک", "بھیس"]),
    ("thanks", ["thanks", "thank you", "shukriya", "jazak", "bohot shukriya", "thx",
                "شکریہ", "جزا", "ماشاءاللہ"]),
    ("greeting", ["hello", "hi", "hey", "salam", "assalam", "assalamualaikum", "salaam",
                  "good morning", "good evening", "helo", "hii",
                  "السلام", "سلام", "صبح بخیر", "شب بخیر", "ہیلو"]),
    ("bye", ["bye", "goodbye", "khuda hafiz", "allah hafiz", "bye bye", "ja raha",
             "خدا حافظ", "الوداع", "خدا حافظ"]),
]

PRIORITY = ["fees", "appointment", "human", "human", "timing", "location",
            "contact", "services", "thanks", "greeting", "bye"]


def detect_intent(text: str) -> str:
    t = normalize(text)
    if not t:
        return "unknown"
    service = find_service(text)
    # Fees strongly overrides, but if they ask fees for a service we still know service.
    scores: Dict[str, int] = {}
    for intent, kws in INTENT_KEYWORDS:
        hits = sum(1 for k in kws if kw_hit(t, k))
        if hits:
            scores[intent] = hits
    if service and scores.get("fees", 0) > 0:
        scores["fees"] += 1
    if not scores:
        return "service" if service else "unknown"
    for p in PRIORITY:
        if p in scores:
            return p
    return max(scores, key=lambda k: scores[k])


# ---------------------------------------------------------------------------
# ANSWER BANK
# ---------------------------------------------------------------------------
def _brand(lang: str) -> str:
    return config.SHOP_NAME_UR if lang == "urdu" else config.SHOP_NAME


def _addr(lang: str) -> str:
    return config.ADDRESS_UR if lang == "urdu" else config.ADDRESS


def _time(lang: str) -> str:
    return config.TIMING_UR if lang == "urdu" else config.TIMING


def _phone(lang: str) -> str:
    return config.PHONE_DISPLAY


def a(svc: Service, lang: str) -> str:
    """Accessory line for a service (what we actually do)."""
    return svc.blurb_ur if lang == "urdu" else svc.blurb_ru


def t(svc: Service, lang: str) -> str:
    """Title for a service."""
    return svc.title_ur if lang == "urdu" else svc.title_ru


def answer_for(intent: str, svc: Optional[Service], lang: str) -> str:
    L = lang
    brand = _brand(L)

    if intent == "fees":
        if L == "urdu":
            return (
                f"🧮 رجسٹری کی تفصیلی فیس / خرچہ — ہماری مفت آن لائن کیلکولیٹر پر دیکھیں:\n\n"
                f"👉 {config.CALCULATOR_URL}\n\n"
                f"یہاں آپ اپنی کھتونی نمبر، زمین کی قسم اور کام کے According مکمل خرچہ شامل فریس، "
                f"Govt فیس اور ہماری فیس سب calculate ہو جائے گا۔\n\n"
                f"کسی بھی Confusion کے لیے {config.OWNER_NAME_UR} سے بات کریں: {config.PHONE_DISPLAY}\n\n"
                f"مزید رہنمائی کے لیے ہمارے آفس آئیں: Baldia Chowk, Infront of City Police Station (A) Division, Chishtian "
                f"(Subah 8:00 AM se Shaam 8:00 PM)."
            )
        return (
            f"🧮 Registry ki poori kharcha / fees ke liye hamari FREE online calculator kholen:\n\n"
            f"👉 {config.CALCULATOR_URL}\n\n"
            f"Yahan aap apni khatoni number, zameen ki type aur kaam ke mutabiq poora kharcha — "
            f"govt fees, stamp duty aur humari service fee — sab foran calculate ho jayega.\n\n"
            f"Kisi bhi confusion ke liye {config.OWNER_NAME} se baat karein: {config.PHONE_DISPLAY}\n\n"
            f"Mazeed rahnumai ke liye hamare office aaiye: Baldia Chowk, Infront of City Police Station (A) Division, "
            f"Chishtian (Subah 8:00 AM se Shaam 8:00 PM)."
        )

    if intent == "timing":
        if L == "urdu":
            return (f"🕘 ہمارا وقت: {_time(L)}\n\n"
                    f"آپ کسی بھی وقت آ کر face-to-face mashwara le sakte hain — "
                    f"بغیرAppointment ke bhi. پہلے WhatsApp par confirm kar lein.")
        return (f"🕘 Hamara time: {_time(L)}\n\n"
                f"Aap kisi bhi waqt aa kar seedha aa jaiye — appointment ke baghair bhi. "
                f"Pehle WhatsApp par confirm kar lein taake koi na miss kare.")

    if intent == "location":
        if L == "urdu":
            return (f"📍 ہمارا پتہ: {_addr(L)}\n\n"
                    f"بالڈیا چوک سے بالکل قریب — آپ آ کر ڈائریکشن لے لیں۔ "
                    f"راستہ کے بارے میں مزید بات چاہیے تو {config.PHONE_DISPLAY} پر کال کریں۔")
        return (f"📍 Hamara address: {_addr(L)}\n\n"
                f"Baldia Chowk se bilkul qareeb — aa kar rasta le lein. "
                f"Map ya rasta ke liye {config.PHONE_DISPLAY} par call kar dein.")

    if intent == "contact":
        return (f"📞WhatsApp / Phone: {config.PHONE_DISPLAY}\n"
                f"🌐 Online calculator: {config.CALCULATOR_URL}\n\n"
                f"Aap isi number par WhatsApp karein, hum foran jawab dein ge. {brand} — {_addr('roman')}")

    if intent == "services":
        if L == "urdu":
            lines = [f"✅ {brand} کی تمام خدمات:"]
            for s in SERVICES:
                lines.append(f"{s.icon} {s.title_ur}")
            lines.append(f"\nکسی بھی کام کے لیے یہاں لکھیں یا {config.PHONE_DISPLAY} پر کال کریں۔ "
                         f"آپ کی visit {config.ADDRESS_UR} پر ہے۔")
            return "\n".join(lines)
        lines = [f"✅ {brand} — humari tamam services:"]
        for s in SERVICES:
            lines.append(f"{s.icon} {s.title_ru}")
        lines.append(f"\nKisi bhi kaam ke liye yahan likhein ya {config.PHONE_DISPLAY} par call karein. "
                     f"Visit ka address: {config.ADDRESS}.")
        return "\n".join(lines)

    if intent == "appointment":
        if L == "urdu":
            return (f"📅 ضرور، visit book کر لیتے ہیں۔\n\n"
                    f"براہ کرم اپنا **نام** بتا دیں؟")
        return (f"📅 Theek hai, main aap ki visit book kar deta hoon.\n\n"
                f"Pehle apna **naam** bata dein?")

    if intent == "human":
        return (f"📞 Abhi {config.OWNER_NAME} se direct baat ho jayegi:\n\n"
                f"WhatsApp: {config.PHONE_DISPLAY}\n"
                f"Shop: {_addr(L)}\nTime: {_time(L)}")

    if intent == "thanks":
        if L == "urdu":
            return ("❤️ شکریہ! اگر کبھی بھی زمین، رجسٹری یا کسی بھی کاغذ کے کام ہوں تو بے جھجک بتائیں۔ "
                    f"خدا حافظ! 🌟")
        return ("❤️ Shukriya! Kabhi bhi zameen, registry ya kisi bhi kaam ka ho toh "
                "bina himmat bata dein. Allah Hafiz! 🌟")

    if intent == "greeting":
        if L == "urdu":
            return (f"السلام علیکم! خوش آمدید 🌙\n{brand} میں خوشی ہوگی۔\n\n"
                    f"مجھے بتائیں آپ کو کس کام میں مدد چاہیے؟ (رجسٹری، انتقال، فرد، ڈارمل، پراپرٹی …)\n"
                    f"یا {config.PHONE_DISPLAY} پر کال کریں۔")
        return (f"Assalam-o-Alaikum! Khushi ho gi aap ka 🌙\n{brand} mein aap ka swagat hai.\n\n"
                f"Batayein aap ko kis kaam mein madad chahiye? (Registry, Inteqal, Fard, Domicile, Property …)\n"
                f"Ya {config.PHONE_DISPLAY} par call kar dein.")

    if intent == "bye":
        if L == "urdu":
            return ("خدا حافظ! 🙏\nاگر کوئی بھی کام ہو تو بے جھجک بتائیں — "
                    f"{brand}، {_addr(L)}۔")
        return ("Allah Hafiz! 🙏\nKoi bhi kaam ho toh bata dena — "
                f"{brand}, {_addr(L)}.")

    # ---- Service-specific ----
    if svc:
        if L == "urdu":
            base = (f"{svc.icon} **{t(svc, L)}**\n\n{a(svc, L)}\n\n"
                    f"یہ کام ہمارے یہاں {config.ADDRESS_UR} پر ہوتا ہے — {config.TIMING_UR}۔\n\n"
                    f"اگر آپ آج یا کل آنا چاہتے ہیں تو اپنا نام بتا دیں، میں visit book کر دیتا ہوں۔ "
                    f"یا {config.PHONE_DISPLAY} پر کال کریں۔")
            if svc.key in ("registry", "file", "inteqal", "bainama"):
                base += f"\n\n🧮 خرچہ جاننا ہے؟ {config.CALCULATOR_URL}"
        else:
            base = (f"{svc.icon} **{t(svc, L)}**\n\n{a(svc, L)}\n\n"
                    f"Yeh kaam hamare yahan {config.ADDRESS} par hota hai — {config.TIMING}.\n\n"
                    f"Agar aaj ya kal aana chahte hain to apna naam bata dein, main visit book kar "
                    f"dunga. Ya {config.PHONE_DISPLAY} par call kar lein.")
            if svc.key in ("registry", "file", "inteqal", "bainama"):
                base += f"\n\n🧮 Kharcha jaanna hai? {config.CALCULATOR_URL}"
        return base

    # ---- Unknown ----
    if L == "urdu":
        return (f"🤔 معذرت، میں نہیں سمجھ سکا۔\nمیں آپ کی ان چیزوں میں مدد کر سکتا ہوں:\n"
                + "\n".join(f"{s.icon} {s.title_ur}" for s in SERVICES[:6])
                + f"\n\nمزید کے لیے {config.OWNER_NAME_UR} سے بات کریں: {config.PHONE_DISPLAY}")
    return (f"🤔 Maazrat, main samajh nahi paya.\nMain in cheezo mein aap ki madad kar sakta hoon:\n"
            + "\n".join(f"{s.icon} {s.title_ru}" for s in SERVICES[:6])
            + f"\n\nAur ke liye {config.OWNER_NAME} se baat karein: {config.PHONE_DISPLAY}")


# ---------------------------------------------------------------------------
# MULTI-TURN LEAD CAPTURE  (Name → Time → Handoff)
# ---------------------------------------------------------------------------
def _looks_like_name(text: str) -> bool:
    """
    Very conservative: a real person writes 1-3 plain words, no question mark,
    and never only common Urdu/English words. Anything else is treated as a
    question, not a name.
    """
    raw = (text or "").strip()
    if not raw or "?" in raw or "؟" in raw:
        return False
    words = normalize(raw).split()
    if not (1 <= len(words) <= 3):
        return False
    for w in words:
        if not w.isalpha():
            return False
        if w in NAME_STOPWORDS:
            return False
        if find_service(raw):
            return False
    return True


def _looks_like_phone(text: str) -> bool:
    digits = re.sub(r"\D", "", text)
    return 10 <= len(digits) <= 13


TIME_WORDS = {
    "aaj": ["aaj", "today", "آج"],
    "kal": ["kal", "tomorrow", "کل"],
    "parso": ["parso", "day after", "پرسوں"],
    "subah": ["subah", "morning", "صبح"],
    "dopahar": ["dopahar", "afternoon", "دوپہر"],
    "shaam": ["shaam", "evening", "شام"],
    "raat": ["raat", "night", "رات"],
}


def _time_slot(text: str) -> str:
    """
    Detect the visit slot. Handles combinations like "kal shaam" or
    "aaj 5 pm" so the booked lead shows the real intent, not just "kal".
    """
    t_ = normalize(text)
    m = re.search(r"\b([0-9]{1,2})\s*(am|pm|baje)", t_)
    found = [k for k, kws in TIME_WORDS.items() if any(kw_hit(t_, x) for x in kws)]
    if m:
        day = next((f for f in found if f in ("aaj", "kal", "parso")), "")
        return (day + " " + m.group(0)).strip() if day else m.group(0)
    if found:
        # a day part plus a time-of-day part reads best: "kal shaam"
        day = next((f for f in found if f in ("aaj", "kal", "parso")), "")
        part = next((f for f in found if f in ("subah", "dopahar", "shaam", "raat")), "")
        if day and part:
            return f"{day} {part}"
        return (day or part or found[0])
    return ""


def _cta(intent: str, svc: Optional[Service], state: Dict[str, Any], lang: str) -> Dict[str, str]:
    """Primary call-to-action for the current turn."""
    name = state.get("name", "")
    # fall back to the service the customer mentioned earlier in the chat
    svc_title = (svc.title_ru if svc else "") or state.get("service_title", "")

    if state.get("ready") or (name and state.get("slot")):
        if lang == "urdu":
            msg = (f"السلام علیکم! میں {name} ہوں۔ مجھے {svc_title or 'معلومات'} "
                   f"کے بارے میں بات کرنی ہے۔ کیا {state.get('slot','foran')} آنا ممکن ہے؟")
        else:
            msg = (f"Assalam-o-Alaikum! My name is {name}. I need to talk about "
                   f"{svc_title or 'property services'}. Can I visit you "
                   f"{state.get('slot', 'today')}?")
        return {"label": f"WhatsApp par {name or 'batayen'} ✅", "url": wa_link(msg)}

    if intent == "fees":
        return {"label": "🧮 Kharcha Calculator kholen", "url": config.CALCULATOR_URL}
    if intent in ("appointment", "human", "contact"):
        return {"label": f"WhatsApp {config.PHONE_DISPLAY}", "url": wa_link(
            f"Assalam-o-Alaikum, mujhe {config.SHOP_NAME} se baat karni hai.")}
    if svc_title:
        if lang == "urdu":
            q = f"السلام علیکم! مجھے {svc_title} کے بارے میں معلومات اور visit کا وقت چاہیے۔"
        else:
            q = (f"Assalam-o-Alaikum! Mujhe {svc_title} ke baare mein maloom aur "
                 f"visit ka waqt chahiye.")
        return {"label": f"WhatsApp: {svc_title[:24]}", "url": wa_link(q)}
    return {"label": f"WhatsApp {config.PHONE_DISPLAY}",
            "url": wa_link(f"Assalam-o-Alaikum! Mujhe {config.SHOP_NAME} se madad chahiye.")}


# ---------------------------------------------------------------------------
# MAIN ENTRY POINT
# ---------------------------------------------------------------------------
def respond(message: str, state: Optional[Dict[str, Any]] = None,
            channel: str = "website") -> Dict[str, Any]:
    """
    The single brain used by:
      * website chat widget  (index.html)
      * WhatsApp auto-responder (Agent 2)
      * Instagram / Facebook / TikTok DMs (Agents 3-5)

    Returns a dict with: reply, language, intent, service, buttons, state, collect, lead
    """
    state = dict(state or {})
    message = (message or "").strip()
    lang = detect_language(message) or state.get("lang", "roman")
    state["lang"] = lang

    intent = detect_intent(message)
    svc = find_service(message)
    if svc:
        state.setdefault("service", svc.key)
        state["service_title"] = svc.title_ur if lang == "urdu" else svc.title_ru

    reply = ""
    lead = None
    stage = state.get("stage", "")

    # =====================================================================
    # BOOKING FLOW  —  Name  →  Service  →  Visit time  →  Handoff
    # Robust to any order the customer types things in.
    # =====================================================================
    in_flow = stage in ("need_name", "need_slot", "done") or intent == "appointment"

    # Strict persona (WhatsApp / DM channels): relevance filter + "G." prefix.
    strict = (channel != "website")
    spam_tokens = {"viagra", "cheap", "casino", "lottery", "crypto", "bitcoin",
                   "porn", "sex", "spam", "hack", "loan", "crypto"}
    is_spam = any(tok in normalize(message) for tok in spam_tokens)
    if strict and not in_flow and (intent in ("greeting", "unknown") or is_spam):
        return {
            "reply": "G. Hum sirf property aur registry ki services provide karte hain. Allah Hafiz.",
            "language": lang,
            "intent": "rejected",
            "service": "",
            "service_title": "",
            "buttons": [],
            "state": state,
            "lead_id": "",
        }

    if in_flow:
        slot = _time_slot(message)
        is_name = _looks_like_name(message) and not _looks_like_phone(message)
        is_phone = _looks_like_phone(message)
        has_digits = bool(re.search(r"\d", message))

        # capture whatever we can from this message
        if is_phone and not state.get("phone"):
            state["phone"] = re.sub(r"\D", "", message)
        if is_name and not state.get("name"):
            state["name"] = message.strip()

        # 1) we have everything -> confirm + create the lead
        if state.get("name") and slot and not state.get("ready"):
            state["slot"] = slot
            state["ready"] = True
            state["stage"] = "done"
            nm = state["name"]
            if lang == "urdu":
                reply = (f"ماشاءاللہ {nm}! بہت خوب ✅\n\n"
                         f"میں نے آپ کی visit note کر لی ہے — {slot}۔\n"
                         f"آپ {config.ADDRESS_UR} پر آئیں، {config.TIMING_UR}۔\n\n"
                         f"👇 نیچے والے بٹن سے WhatsApp پر اپنی تفصیل بھیج دیں — "
                         f"{config.OWNER_NAME_UR} آپ کو فوراً جواب دیں گے۔")
            else:
                reply = (f"Mashallah {nm}! Bohat khub ✅\n\n"
                         f"Main ne aap ki visit note kar li hai — {slot}.\n"
                         f"Aap {config.ADDRESS} par aaiye, {config.TIMING}.\n\n"
                         f"👇 Neeche button se apni details WhatsApp par bhej dein — "
                         f"{config.OWNER_NAME} aap ko foran jawab dein ge.")
            lead = db.add_lead(
                name=nm,
                phone=state.get("phone", ""),
                service=svc.title_ru if svc else state.get("service_title", "") or "General",
                message=message, source=channel, intent=intent,
                language=lang, visit_time=slot, status="booked",
            )

        # 2) we have a name but no time yet
        elif state.get("name") and not state.get("ready"):
            state["stage"] = "need_slot"
            if lang == "urdu":
                reply = (f"خوش آمدید {state['name']} بھائی! 🤝\n\n"
                         f"آپ کو کون سا کام کرانا ہے؟ (رجسٹری، انتقال، فرد، ڈارمل …)\n\n"
                         f"اور کب آنا چاہتے ہیں — آج / کل / کون سا وقت؟ ({config.TIMING_UR})")
            else:
                reply = (f"Welcome {state['name']} bhai! 🤝\n\n"
                         f"Kaunsa kaam karwana hai? (Registry, Inteqal, Fard, Domicile …)\n\n"
                         f"Aur kab aana chahte hain — aaj / kal / kaunsa waqt? ({config.TIMING})")

        # 3) we have a time but no name yet
        elif slot and not state.get("name"):
            state["slot"] = slot
            state["stage"] = "need_name"
            if lang == "urdu":
                reply = (f"ٹھیک ہے، {slot} کے لیے note کر لیا۔ 📅\n\n"
                         f"براہ کرم اپنا **نام** بتا دیں؟")
            else:
                reply = (f"Theek hai, {slot} ke liye note kar liya. 📅\n\n"
                         f"Pehle apna **naam** bata dein?")

        # 4) nothing usable -> re-ask gently (never dead-end)
        else:
            state["stage"] = "need_name"
            if lang == "urdu":
                reply = ("براہ کرم اپنا **نام** لکھیں (مثلاً: علی رضا) — پھر میں آپ کی visit "
                         "book کر دوں گا۔\nیا براہ کرم WhatsApp پر لکھیں: ۰۳۰۸۳۰۲۷۵۸۹")
            else:
                reply = ("Please apna **naam** likhein (jaise: Ali Raza) — phir main aap ki "
                         "visit book kar doonga.\nYa WhatsApp kar dein: 0327-7450361")

    # =====================================================================
    # NORMAL CONVERSATION
    # =====================================================================
    elif not reply:
        if intent == "appointment":
            state["stage"] = "need_name"
            reply = answer_for("appointment", svc, lang)
        elif not state.get("name") and _looks_like_name(message) and intent in ("greeting", "unknown"):
            state["name"] = message.strip()
            state["stage"] = "need_slot"
            if lang == "urdu":
                reply = (f"خوش آمدید {state['name']}! 🌙 میں {config.SHOP_NAME_UR} کا assistant ہوں۔ "
                         f"بتائیں کس کام میں مدد چاہیے؟ اور کب آنا چاہتے ہیں؟")
            else:
                reply = (f"Welcome {state['name']}! 🌙 Main {config.SHOP_NAME} ka assistant hoon. "
                         f"Batayein kis kaam mein madad chahiye? Aur kab aana chahte hain?")
        else:
            reply = answer_for(intent, svc, lang)
            # after a normal service answer, gently open the booking flow
            if intent in ("service", "human") or (svc and state.get("stage") != "done"):
                if not state.get("name") and intent == "service":
                    state["stage"] = "need_name"

    cta = _cta(intent, svc, state, lang)
    buttons = [{"label": cta["label"], "url": cta["url"]}]

    # Always append the calculator as a secondary button when relevant.
    if intent == "fees" or (svc and svc.key in ("registry", "file", "inteqal", "bainama")):
        buttons.append({"label": "🧮 Registry Kharcha Calculator",
                        "url": config.CALCULATOR_URL})

    # Persist conversation memory (for WhatsApp / DMs)
    if channel != "website":
        db.upsert_conversation(channel, contact_key(message),
                               name=state.get("name", ""),
                               last_lang=lang, state=state,
                               last_text=message[:400], last_reply=reply[:600])

    if strict and reply and not reply.startswith("G.") and not reply.startswith("G,"):
        reply = "G. " + reply

    return {
        "reply": reply,
        "language": lang,
        "intent": intent,
        "service": svc.key if svc else "",
        "service_title": (svc.title_ur if lang == "urdu" else svc.title_ru) if svc else "",
        "buttons": buttons,
        "state": state,
        "lead_id": lead["id"] if lead else "",
    }


def contact_key(message: str) -> str:
    """Stable per-conversation key for non-website channels."""
    return f"msg:{abs(hash(normalize(message))) % 10**10}"


def brand_ur() -> str:
    return config.SHOP_NAME


# ---------------------------------------------------------------------------
# OPTIONAL: FREE Gemini tier (used only if the user pasted a free API key)
# ---------------------------------------------------------------------------
def gemini_free_reply(message: str, lang: str) -> str:
    """Blend in a free Gemini answer. Returns '' if unavailable/offline."""
    if not config.GEMINI_ENABLED:
        return ""
    try:
        import requests  # free, part of our requirements
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent"
        sys_prompt = (
            f"You are the WhatsApp/web assistant for {config.SHOP_NAME} in Chishtian, Pakistan. "
            f"Owner: {config.OWNER_NAME}. Address: {config.ADDRESS}. Hours: {config.TIMING}. "
            f"Phone/WhatsApp: {config.PHONE_DISPLAY}. Free registry-fee calculator: {config.CALCULATOR_URL}. "
            "Reply in the SAME language as the user (Roman Urdu or Urdu). Be warm, short (max 4 lines), "
            "always invite them to WhatsApp " + config.PHONE_DISPLAY + " or visit the shop."
        )
        r = requests.post(
            url,
            params={"key": config.GEMINI_API_KEY},
            json={"contents": [{"parts": [{"text": message}]}],
                  "system_instruction": {"parts": [{"text": sys_prompt}]}},
            timeout=12,
        )
        if r.status_code == 200:
            return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        pass
    return ""


def smart_reply(message: str, state: Optional[Dict[str, Any]] = None,
                channel: str = "website") -> Dict[str, Any]:
    """Public entry — rule engine always runs; Gemini (optional) enriches."""
    out = respond(message, state, channel)
    if config.GEMINI_ENABLED and out["intent"] in ("unknown", "service"):
        extra = gemini_free_reply(message, out["language"])
        if extra:
            out["reply"] = extra + "\n\n" + out["reply"]
            out["provider"] = "Gemini (free) + Engine"
    else:
        out["provider"] = "Built-in Engine"
    return out


if __name__ == "__main__":
    # Quick self-test
    for q in ["Registry kaise hota hai?", "رجسٹری کی فیس کتنی ہے؟", "kharcha batao",
              "kab khulte ho?", "kahan ho?", "mujhe fard chahiye", "plot chahiye Chishtian mein",
              "domicile banwana hai", "thanks"]:
        r = smart_reply(q)
        print("=" * 70)
        print("Q:", q, "->", r["intent"], "/", r["language"])
        print(r["reply"])