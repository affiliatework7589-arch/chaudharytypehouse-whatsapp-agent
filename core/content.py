# -*- coding: utf-8 -*-
"""
core/content.py — FREE content factory.

Generates, with zero cost and zero APIs:
  * Instagram captions + 15 Chishtian real-estate SEO hashtags
  * Facebook educational posts (Registry / Inteqal / Fard)
  * TikTok 45-second viral scripts with 3-second hooks, titles, hashtags
  * WhatsApp broadcast / status text

Everything is written in Roman Urdu *and* Urdu Nastaliq-ready script.
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

import config
from core.ai_engine import SERVICES, Service, find_service
from core import db

# ---------------------------------------------------------------------------
# KNOWLEDGE BASE  — the actual educational value posted every single day
# ---------------------------------------------------------------------------
TOPICS: List[Dict[str, Any]] = [
    {
        "key": "registry_vs_mutation",
        "topic_ru": "Registry aur Mutation mein farq",
        "topic_ur": "رجسٹری اور انتقال میں فرق",
        "service": "registry",
        "hook_ru": "Zameen ki registry ho gayi lekin naam nahi badla? Tumhara kaam adhoora hai!",
        "hook_ur": "زمین کی رجسٹری ہو گئی لیکن نام نہیں بدلا؟ تمہارا کام ادھورا ہے!",
        "body_ru": ["Pehle Fard nikaal kar dekho ke usme kiska naam hai.",
                    "Registry ke baad naam badalne ke liye MUTATION (Tabahi) lagta hai.",
                    "Registry = nayi entry. Mutation = purani entry ka tez update.",
                    "Dono kaam ek saath nahi ho sakte — pehle registry, phir mutation.",
                    "Galat order = dobara paisa aur waqt dono jaata hai."],
        "body_ur": ["پہلے فرد نکال کر دیکھو کہ اس میں کس کا نام ہے۔",
                     "رجسٹری کے بعد نام بدلنے کے لیے انتقال لگتا ہے۔",
                     "رجسٹری = نئی اندراج، انتقال = پرانی اندراج کا تیز اپ ڈیٹ۔",
                     "دونوں کام ایک ساتھ نہیں ہو سکتے — پہلے رجسٹری، پھر انتقال۔",
                     "غلط ترتیب = دو بار پیسہ اور وقت دونوں جاتا ہے۔"],
        "fb_ru": ("Log aksar poochte hain: 'Registry aur mutation mein kya farq hai?'\n\n"
                  "Simple baat:\n"
                  "• REGISTRY = zameen ka naya record banta hai (pehli dafa).\n"
                  "• MUTATION / TABAHI = purane record mein naam badalna.\n\n"
                  "Agar aap ne zameen khareedi hai aur abhi tak naam nahi badla, to aap ka kaam "
                  "ADHOORA hai. Isi liye har khareed ke baad foran mutation karwana zaroori hai, "
                  "warna baad mein musibat hoti hai — pighaune wale aur ghair-qanooni transfer ka case.\n\n"
                  "Chishtian mein arazi muawin ke zariye ye kaam hum karte hain — sath hi Fard ki "
                  "tasdeeq bhi karwa dete hain taake pata chale ke zameen sach mein aap ki hai ya nahi."),
        "cta_ru": "Apni zameen ka Fard check karwana ho? Aaj hi aa jaiye.",
    },
    {
        "key": "bay_nama",
        "topic_ru": "Bay Nama (Bai Nama) kya hota hai",
        "topic_ur": "بیع نامہ کیا ہوتا ہے",
        "service": "bainama",
        "hook_ru": "Zameen kharidi bina bay nama ke? Sabse badi galti!",
        "hook_ur": "زمین خریدے بغیر بیع نامے کے؟ سب سے بڑی غلطی!",
        "body_ru": ["Bay nama = kharid ka rasmi qarz (agreement).",
                    "Ismein dono party ka naam, khatoni, qeemat aur date likhi hoti hai.",
                    "Bay nama ke baghair registry mumkin nahi.",
                    "Galat bay nama = court case + paisa dono ka nuqsaan.",
                    "Zaroori baat: dono shahed (witness) hon aur stamp lagayen."],
        "body_ur": ["بیع نامہ = خرید کا رسمی معاہدہ۔",
                     "اس میں دونوں فریق کا نام، کھتونی، قیمت اور تاریخ لکھی ہوتی ہے۔",
                     "بیع نامے کے بغیر رجسٹری ممکن نہیں۔",
                     "غلط بیع نامہ = کورٹ کیس اور پیسے دونوں کا نقصان۔",
                     "ضروری بات: دونوں گواہ ہوں اور اسٹیمپ لگے۔"],
        "fb_ru": ("Har saal hazaron zameen transactions puri tarah baghair REGISTRY ke ho jati hain — "
                  "aur phir saalon baad disputes shuru ho jate hain.\n\n"
                  "Sab se pehli baat samjhein: Zameen ki khareed aur zameen ki registry aik cheez nahi. \n\n"
                  "1) BAY NAMA — dono party ka likha hua agreement (qarz).\n"
                  "2) REGISTRY — government record mein naam badalna.\n\n"
                  "Agar aap ne sirf 'hafiz hogi' ya 'baqi paisa baad mein' par deal kar li, to aap ka "
                  "qarz qanooni taur par adhoora hai. Qanooni hisaab se ba-nama ke baghair "
                  "registry nahi ho sakti.\n\n"
                  "Humein har hafte yeh masla milta hai — log 2-3 saal pehle deal kar chuke hain lekin "
                  "aaj tak registry nahi hui. Isi liye hum har deal ke sath: bay nama check, Fard "
                  "verification aur complete registry file ka pakka package dete hain."),
        "cta_ru": "Apni deal ka bay nama check karwana ho? Aaj aa jaiye.",
    },
    {
        "key": "fard_verify",
        "topic_ru": "Fard se zameen ki asli haalat kaise check karein",
        "topic_ur": "فرد سے زمین کی اصل حالت کیسے چیک کریں",
        "service": "fard",
        "hook_ru": "Sawal pooch raha hai? 'Zameen sale pe hai ya nahi?'",
        "hook_ur": "سوال پوچھ رہے ہیں؟ زمین سیل پر ہے یا نہیں؟",
        "body_ru": ["Fard = jamabandi ki official copy.",
                    "Isme khatoni number, naam, area aur malik ka hissa likha hota hai.",
                    "Agar 'Bait-ul-mal' ya 'government' likha hai to deal ruk jaiye.",
                    "Fard ki mukhtalif awraaj (ajra) muawin se mil jati hain.",
                    "Khareed se pehle Fard zaroor milaiye aur check karaiye."],
        "body_ur": ["فرد = جمبندی کی سرکاری کاپی۔",
                     "اس میں کھتونی نمبر، نام، رقبہ اور مالک کا حصہ لکھا ہوتا ہے۔",
                     "اگر بیت المال یا سرکار لکھا ہے تو Deal رک جائے۔",
                     "فرد کی مختلف اوراج معاون سے مل جاتی ہیں۔",
                     "خرید سے پہلے فرد ضرور ملوائیں اور چیک کروائیں۔"],
        "fb_ru": ("Zameen kharidne se pehle sab se badi galti: sirf dealer ke bharose par faisla karna.\n\n"
                  "Hamesha ye 3 cheezein check karein:\n"
                  "1. FARD-E-MALKIAT — Jamabandi ki official copy. Isme khatoni number, area aur "
                  "malke ka naam hota hai.\n"
                  "2. ARAZI MUAWIN SE ZAMANAT — confirm karein ke zameen pe pehle se koi "
                  "qarz (sale, bank, hukm) to nahi hai.\n"
                  "3. BAY NAMA — likha hua, stamp lagaya hua, dono shahed ke saath.\n\n"
                  "Agar Fard mein 'Bait-ul-Mal' ya 'State/Settlement Department' ka naam aata hai, "
                  "to fauran ruk jaiye — aisi zameen lene ka koi faida nahi.\n\n"
                  "Hum Chishtian mein Fard ki awraaj (copy) aur zamanat (attestation) dono karwa "
                  "dete hain — taake aap har deal se pehle poori tarah sure ho sakein."),
        "cta_ru": "Fard ki copy aur zamanat — aaj hi aa kar lijiye.",
    },
    {
        "key": "wirasat_inteqal",
        "topic_ru": "Wirasat mein zameen ka inteqal",
        "topic_ur": "وراثت میں زمین کا انتقال",
        "service": "inteqal",
        "hook_ru": "Waris ke naam zameen thi? Ab register karwana zaroori hai!",
        "hook_ur": "وارث کے نام زمین تھی؟ اب رجسٹر کروانا ضروری ہے!",
        "body_ru": ["Wirasat mein inteqal = waris ke naam se zameen ka naam badla jana.",
                    "Iske liye death certificate, heir certificate aur family register chahiye.",
                    "Inteqal ke baad bhi mutation zaroori hai.",
                    "Sirf 'wirasat ka haq' se zameen nahi aa sakti — record update hona chahiye.",
                    "Sahi waqt par inteqal = bachchon ke liye bhi protection."],
        "body_ur": ["وراثت میں انتقال = وارث کے نام سے زمین کا نام بدلا جانا۔",
                     "اس کے لیے death certificate، heir certificate اور family register چاہیے۔",
                     "انتقال کے بعد بھی mutation ضروری ہے۔",
                     "صرف وراثت کا حق سے زمین نہیں آ سکتی — ریکارڈ اپ ڈیٹ ہونا چاہیے۔",
                     "صحیح وقت پر انتقال = بچوں کے لیے بھی تحفیظ۔"],
        "fb_ru": ("Wirasat mein sab se badi galti ye log karte hain ke zameen qani (unregistered) "
                  "chhorr di jati hai. Phir jab doosri generation aati hai to ladai shuru ho jati hai.\n\n"
                  "Agar kisi bhi waris ne jeene ke dauraan registry nahi karwai to: \n"
                  "• Zameen un-registered reh jati hai\n"
                  "• Koi bhi haq dawat kar sakta hai\n"
                  "• Court case aur legal fees dono lagti hain\n\n"
                  "Sahi tareeqa: WIRASAT KA INTEQAL — jismein death certificate, heir certificate "
                  "aur family register ke mutabiq naam badal kar registry karwai jati hai.\n\n"
                  "Hum ye poora kaam karte hain aur sath mein Fard bhi verify karwa dete hain ke "
                  "zameen waqai waris ke naam aa jayi. Chishtian, Baldia Chowk."),
        "cta_ru": "Wirasat ka inteqal karwana ho? Baat karein.",
    },
    {
        "key": "domicile_process",
        "topic_ru": "Domicile certificate ka apply",
        "topic_ur": "ڈارمل سرٹیفکیٹ کا اپلائی",
        "service": "domicile",
        "hook_ru": "Domicile ke liye kya kya chahiye? Poori list yahan!",
        "hook_ur": "ڈارمل کے لیے کیا کیا چاہیے؟ پوری لسٹ یہاں!",
        "body_ru": ["CNIC (ya CNIC ki copy) zaroori hai.",
                    "Form 17 bharna hota hai — National Identity & Domicile.",
                    "Utility bill (bijli ka bill) address proof ke liye.",
                    "NADRA office ya e-Sahulat center se submit.",
                    "Verification ke baad domicile print ho jata hai."],
        "body_ur": ["سی آئی سی (یا اس کی کاپی) ضروری ہے۔",
                     "فارم 17 بھرنا ہوتا ہے — نیشنل آئیڈنٹیٹی اینڈ ڈارمل۔",
                     "یوٹیلٹی بل (بجلی کا بل) ایڈریس پروف کے لیے۔",
                     "نادرا آفس یا ای سہولت سینٹر سے جمع کرائیں۔",
                     "تصدیق کے بعد ڈارمل پرنٹ ہو جاتا ہے۔"],
        "fb_ru": ("Domicile certificate har naye school admission, scholarship aur govt job form "
                  "mein maangi jati hai. Lekin aksar log galat documents le kar NADRA chhoot jate "
                  "hain aur baar baar laatay rehte hain.\n\n"
                  "COMPLETE LIST:\n"
                  "1. Original CNIC (ya NADRA se copy)\n"
                  "2. Form 17 — National Identity & Domicile Certificate\n"
                  "3. Bijli ka bill (address proof ke liye)\n"
                  "4. Form 17 ke mukammal bhare hue photos\n"
                  "5. NADRA center par submit\n\n"
                  "Chishtian mein hum ye kaam typing ke saath karwate hain aur online apply bhi "
                  "kar dete hain — sirf 0327-7450361 par call kar dein, baqi hum dekh lenge."),
        "cta_ru": "Domicile typing + online apply — aaj hi aa jaiye.",
    },
    {
        "key": "registry_kharcha",
        "topic_ru": "Registry kharcha kaise nikalte hain",
        "topic_ur": "رجسٹری کا خرچہ کیسے نکالتے ہیں",
        "service": "registry",
        "hook_ru": "Registry ka kharcha kitna hoga? Tension mat lo — FREE calculator!",
        "hook_ur": "رجسٹری کا خرچہ کتنا ہوگا؟ فکر نہ کرو — مفت کیلکولیٹر!",
        "body_ru": ["Kharcha khatoni number, area aur type par depend karta hai.",
                    "Govt fees + stamp duty + dealer/service fee — teen hisson mein hota hai.",
                    "Har tehsil ka rate alag hota hai.",
                    "Har dafa rates change hote hain — purana number galat hota hai.",
                    "Isliye hamesha latest calculator use karein."],
        "body_ur": ["خرچہ کھتونی نمبر، رقبہ اور قسم پر منحصر ہے۔",
                     "سرکاری فیس + اسٹیمپ ڈیوٹی + ڈیلر فیس — تین حصوں میں ہوتا ہے۔",
                     "ہر تحصیل کا ریٹ مختلف ہوتا ہے۔",
                     "ہر بار ریٹ بدلتے ہیں — پرانا نمبر غلط ہو جاتا ہے۔",
                     "اس لیے ہمیشہ تازہ ترین کیلکولیٹر استعمال کریں۔"],
        "fb_ru": ("Sab se zyada poochha jane wala sawaal: 'Registry ki fees kitni hai?'\n\n"
                  "Seedhi baat — iska ek hi jawab hai: koi doosra nahi. Registry kharcha in cheezon "
                  "par depend karta hai:\n"
                  "• Khatoni / Khewat number\n"
                  "• Zameen ka area (kanal, marf)\n"
                  "• Zameen ki type (abadi, zeraee)\n"
                  "• Tehsil aur district\n\n"
                  "Isi liye koi fixed number batana GALAT hota hai. Isi liye humari website par "
                  "FREE online calculator lagaya gaya hai: " + config.CALCULATOR_URL + " — wahan apni "
                  "details daal kar poora kharcha foran pata chal jayega, bina kisi call ke.\n\n"
                  "Lekin har dafa govt rates badalte hain. Isi liye registry se pehle ek baar zaroor "
                  "check kar lein. Near Baldia Chowk, Chishtian — subah 8 se shaam 8."),
        "cta_ru": "Apni kharcha foran nikalni hai? " + config.CALCULATOR_URL,
    },
    {
        "key": "property_buying",
        "topic_ru": "Chishtian mein plot kharidne se pehle kya check karein",
        "topic_ur": "چشتیاں میں پلاٹ خریدنے سے پہلے کیا چیک کریں",
        "service": "property",
        "hook_ru": "Plot lene se pehle 7 cheezein check karo — warna baad mein pachtaoge!",
        "hook_ur": "پلاٹ لینے سے پہلے ۷ چیزیں چیک کرو — ورنہ بعد میں پچھتاؤ گے!",
        "body_ru": ["Posession kab tak milega — yeh SABB se pehle poochhein.",
                    "Khatoni number valid hai ya nahi.",
                    "Rozgaar / khasra ke naam hai ya faqir waqf ka.",
                    "Balkhi nazdeek hai ya road ki taraf wala plot.",
                    "Bijli, paani aur sewerage ki facility hai.",
                    "Corner, main road ya back side ka plot hai.",
                    "Kabhi kabhi 'market' ke naam pe sirf kiraye ka plot hota hai."],
        "body_ur": ["قبضہ کب ملے گا — یہ سب سے پہلے پوچھیں۔",
                     "کھتونی نمبر درست ہے یا نہیں۔",
                     "روزگار / خسرہ کے نام ہے یا فقیر واقف کا۔",
                     "بلکھی نزدیک ہے یا سڑک کی طرف والا پلاٹ۔",
                     "بجلی، پانی اور سیوریج کی سہولت ہے۔",
                     "کونہ، مین روڈ یا پیچھے والا پلاٹ ہے۔",
                     "کبھی کبھی 'مارکیٹ' کے نام پر صرف کرایہ کا پلاٹ ہوتا ہے۔"],
        "fb_ru": ("Chishtian mein plot ki bohat demand hai — lekin bohat se log galtiyon ke saath "
                  "deal kar lete hain. Yahan 7 cheezein check karein:\n\n"
                  "1. POSESSION — kab tak plot milega? (yeh sab se zyada important hai)\n"
                  "2. KHATONI NUMBER — khud dalil ke paas dekh kar match karein\n"
                  "3. ROZGAR/KHASRA — naam sahi hai ya faqir waqf?\n"
                  "4. BALKHI NAZDEEK — balkhi wali value hai, road wali value nahi\n"
                  "5. UTILITIES — bijli, paani, sewerage ki facility\n"
                  "6. LOCATION — corner, main road ya back side?\n"
                  "7. NATIJA — kuch plots sirf kiraye ke hote hain, khareed ke nahi\n\n"
                  "Hum Chishtian mein zarai zameen, abadi plots aur makaan — teeno ki khareed-"
                  "farokht aur dealing karte hain. Har deal par Fard verification zaroori hai."),
        "cta_ru": "Plot dekhna hai? 0327-7450361 par raasta bana lijiye.",
    },
    {
        "key": "muawin_franchise",
        "topic_ru": "Arazi Muawin kya kaam karta hai",
        "topic_ur": "اراضی معاون کیا کام کرتا ہے",
        "service": "muawin_ajra",
        "hook_ru": "Fard ki ajri ya zamanat ke liye baar baar tehsil nahi jaana chahiye!",
        "hook_ur": "فرد کی اجرا یا ضمانت کے لیے بار بار تحصیل نہیں جانا چاہیے!",
        "body_ru": ["Arazi Muawin = government se authorized kaam karwane ka tareeqa.",
                    "Fard ki ajra (copy), hasool aur zamanat (attestation) — teeno yahin.",
                    "Bait-ul-mal se related files bhi yahin tayyar hoti hain.",
                    "Kaam mukammal hota hai aur zameen ka mamla mufe hota hai.",
                    "Baldia Chowk, Chishtian — subah 8 se shaam 8."],
        "body_ur": ["اراضی معاون = سرکار سے منظور شدہ کام کروانے کا طریقہ۔",
                     "فرد کی اجرا (کاپی)، تحصیل اور ضمانت — تینوں یہاں۔",
                     "بیت المال سے متعلق فائلز بھی یہاں تیار ہوتی ہیں۔",
                     "کام مکمل ہوتا ہے اور زمین کا معاملہ مفت ہوتا ہے۔",
                     "بالڈیا چوک، چشتیاں — صبح ۸ سے شام ۸۔"],
        "fb_ru": ("Agar aap ko har baar Fard ke liye tehsil jaana parta hai, to aap ka kaam zyada "
                  "aur safar zyada — aur zameen ka mamla zyada.\n\n"
                  "ARAZI MUAWIN kya karta hai?\n"
                  "• FARD KI AJRA (copy) — kisi bhi tehsil ki jamabandi ki copy tayyar\n"
                  "• FARD KA HASOOL — zameen ka parcha tayyar karwa kar lena\n"
                  "• FARD KI ZAMANAT (attestation) — confirm karna ke zameen waqai aap ki hai\n"
                  "• Bait-ul-Mal / Settlement files\n\n"
                  "Yeh sab kaam BILKUL FREE tareeqe se hota hai (sirf govt fees lagti hain) — "
                  "lekin aap ka 3-4 dafa tehsil ka safar bach jata hai aur kaam samay par hota hai.\n\n"
                  "Near Baldia Chowk, Chishtian. Subah 8:00 se Shaam 8:00."),
        "cta_ru": "Muawin se kaam karwana hai? Aaj hi aa jaiye.",
    },
]


def topics_for(platform: str = "") -> List[Dict[str, Any]]:
    if not platform:
        return TOPICS
    return [t for t in TOPICS if not platform or t["service"] == platform] or TOPICS


def get_topic(key_or_index: Any) -> Dict[str, Any]:
    if isinstance(key_or_index, int):
        return TOPICS[key_or_index % len(TOPICS)]
    for t in TOPICS:
        if t["key"] == key_or_index:
            return t
    return TOPICS[0]


# ---------------------------------------------------------------------------
# HASHTAGS
# ---------------------------------------------------------------------------
def hashtags(seed: int = 0, extra: Optional[List[str]] = None, count: int = 15) -> str:
    """Return a ready-to-paste Instagram hashtag block (every tag gets a '#')."""
    rng = random.Random(seed)
    pool = list(config.BASE_HASHTAGS) + list(config.INSTAGRAM_REACH_HASHTAGS)
    rng.shuffle(pool)
    picked = ["#" + p.lstrip("#") for p in pool[:count]]
    for e in extra or []:
        tag = "#" + str(e).lstrip("#").replace(" ", "")
        if tag not in picked:
            picked.append(tag)
    return " ".join(dict.fromkeys(picked))


# ---------------------------------------------------------------------------
# INSTAGRAM
# ---------------------------------------------------------------------------
def instagram_caption(topic: Dict[str, Any], language: str = "roman") -> Dict[str, Any]:
    key = topic["key"]
    ru = language != "urdu"
    hook = topic["hook_ru"] if ru else topic["hook_ur"]
    body = topic["body_ru"] if ru else topic["body_ur"]
    svc = find_service(topic["service"])
    svc_title = svc.title_ru if ru else svc.title_ru

    if ru:
        lines = [f"🔥 {hook}", ""]
        lines += [f"{i+1}. {b}" for i, b in enumerate(body)]
        lines += [
            "",
            f"📍 {config.ADDRESS}",
            f"🕘 {config.TIMING}",
            f"📞 WhatsApp: {config.PHONE_DISPLAY}",
        ]
        if key in ("registry_kharcha", "bay_nama", "registry_vs_mutation", "wirasat_inteqal"):
            lines += ["", f"🧮 FREE kharcha calculator: {config.CALCULATOR_URL}"]
        lines += ["", f"DM karein ya seedha aa jaiye — {config.OWNER_NAME}",
                  f"#ChishtianProperty  (10 second mein batao comments mein 🙂)"]
        title = topic["topic_ru"]
    else:
        lines = [f"🔥 {hook}", ""]
        lines += [f"{i+1}. {b}" for i, b in enumerate(body)]
        lines += [
            "",
            f"📍 {config.ADDRESS_UR}",
            f"🕘 {config.TIMING_UR}",
            f"📞 واٹس ایپ: {config.PHONE_DISPLAY}",
        ]
        if key in ("registry_kharcha", "bay_nama", "registry_vs_mutation", "wirasat_inteqal"):
            lines += ["", f"🧮 مفت خرچہ کیلکولیٹر: {config.CALCULATOR_URL}"]
        lines += ["", f"ڈی ایم کریں یا آ کر ملیں — {config.OWNER_NAME_UR}",
                  f"#چشتیاںProperty  (10 سیکنڈ میں بتائیں کمنٹس میں 🙂)"]
        title = topic["topic_ur"]

    return {
        "title": title,
        "caption": "\n".join(lines),
        "hashtags": hashtags(seed=hash(key) % 9999, extra=[svc_key_tag(topic["service"])]),
        "topic": topic["key"],
        "language": language,
        "service": topic["service"],
    }


def svc_key_tag(service: str) -> str:
    return {
        "registry": "Registry", "file": "RegistryFile", "fard": "Fard",
        "bainama": "BayNama", "inteqal": "Inteqal", "muawin_ajra": "AraziMuawin",
        "muawin_hasool": "FardHasool", "muawin_zamanat": "FardZamanat",
        "property": "PropertyDeals", "nadra": "NADRAeSahulat",
        "domicile": "Domicile", "online": "OnlineApply", "photostat": "Photostat",
    }.get(service, "Chishtian")


# ---------------------------------------------------------------------------
# FACEBOOK  (long-form educational post)
# ---------------------------------------------------------------------------
def facebook_post(topic: Dict[str, Any], language: str = "roman") -> Dict[str, Any]:
    ru = language != "urdu"
    key = topic["key"]

    if ru:
        body = topic["fb_ru"]
        cta = topic["cta_ru"]
    else:
        body = topic.get("fb_ur") or topic["fb_ru"]
        cta = f"آج ہی آ کر ملیں — {config.ADDRESS_UR}۔ {config.TIMING_UR}۔ واٹس ایپ {config.PHONE_DISPLAY}۔"

    footer = (
        f"\n\n———————————————\n"
        f"📍 {config.ADDRESS}\n"
        f"🕘 {config.TIMING}\n"
        f"📞 Phone & WhatsApp: {config.PHONE_DISPLAY}\n"
        f"🌐 FREE Registry Kharcha Calculator: {config.CALCULATOR_URL}\n"
        f"👤 {config.OWNER_NAME} — {config.SHOP_NAME}\n"
        f"———————————————\n"
        f"{cta}"
    )
    return {
        "title": topic["topic_ru"] if ru else topic["topic_ur"],
        "caption": body + footer,
        "hashtags": hashtags(seed=hash("fb" + key) % 9999, extra=[svc_key_tag(topic["service"])], count=8),
        "topic": key,
        "language": language,
        "service": topic["service"],
    }


# ---------------------------------------------------------------------------
# TIKTOK  (45-second viral script, 3-second hook)
# ---------------------------------------------------------------------------
def tiktok_script(topic: Dict[str, Any], language: str = "roman") -> Dict[str, Any]:
    ru = language != "urdu"
    hook = topic["hook_ru"] if ru else topic["hook_ur"]
    body = topic["body_ru"] if ru else topic["body_ur"]
    # Keep it ~45s: hook ~3s, 4 beats, CTA
    beats = body[:4]

    title_ru = f"{topic['topic_ru']} — Chishtian mein sahi tareeqa"
    title_ur = f"{topic['topic_ur']} — چشتیاں میں صحیح طریقہ"

    if ru:
        spoken = (
            f"{hook} "
            + " ".join(f"{i+1}) {b}. " for i, b in enumerate(beats))
            + f"Isi liye aa jaiye {config.ADDRESS}, {config.TIMING}. "
            + f"WhatsApp karo {config.PHONE_DISPLAY}. "
            + f"Kharcha check karna hai? Link bio mein hai."
        )
        caption = (
            f"{topic['topic_ru']} 😳\n\n"
            f"{hook}\n\n"
            + "\n".join(f"{i+1}. {b}" for i, b in enumerate(beats))
            + f"\n\n📍 {config.ADDRESS}\n📞 {config.PHONE_DISPLAY}\n"
            f"🧮 {config.CALCULATOR_URL}\n\n"
            f"Agar ye video helpful lagi to LIKE ❤️ aur FOLLOW karo — roz nayi maloomat."
        )
    else:
        spoken = (
            f"{hook} "
            + " ".join(f"{i+1}) {b}. " for i, b in enumerate(beats))
            + f"اسی لیے آ جائیں {config.ADDRESS_UR}، {config.TIMING_UR}۔ "
            + f"واٹس ایپ کریں {config.PHONE_DISPLAY}۔ "
            f"خرچہ چیک کرنا ہے؟ لنک بائو میں ہے۔"
        )
        caption = (
            f"{topic['topic_ur']} 😳\n\n{hook}\n\n"
            + "\n".join(f"{i+1}. {b}" for i, b in enumerate(beats))
            + f"\n\n📍 {config.ADDRESS_UR}\n📞 {config.PHONE_DISPLAY}\n"
            f"🧮 {config.CALCULATOR_URL}\n\n"
            f"اگر یہ ویڈیو مفید لگی تو LIKE ❤️ اور FOLLOW ضرور کریں۔"
        )

    timeline = [
        {"t": "0-3s", "beat": "HOOK", "line": hook},
    ]
    per = max(3, int((45 - 12) / max(1, len(beats))))
    at = 3
    for i, b in enumerate(beats):
        timeline.append({"t": f"{at}-{at+per}s", "beat": f"BEAT {i+1}", "line": b})
        at += per
    timeline.append({"t": f"{at}-45s", "beat": "CTA", "line":
                     (f"WhatsApp {config.PHONE_DISPLAY} — {config.ADDRESS}" if ru
                      else f"واٹس ایپ {config.PHONE_DISPLAY} — {config.ADDRESS_UR}")})

    return {
        "title": title_ru if ru else title_ur,
        "hook": hook,
        "spoken": spoken,
        "caption": caption,
        "hashtags": hashtags(seed=hash("tt" + topic["key"]) % 9999,
                             extra=[svc_key_tag(topic["service"])], count=15),
        "timeline": timeline,
        "duration_seconds": 45,
        "topic": topic["key"],
        "language": language,
        "service": topic["service"],
    }


# ---------------------------------------------------------------------------
# WHATSAPP BROADCAST / STATUS
# ---------------------------------------------------------------------------
def whatsapp_status(topic: Dict[str, Any]) -> str:
    ru = True
    return (f"📢 *{topic['topic_ru']}*\n\n"
            f"{topic['hook_ru']}\n\n"
            + "\n".join(f"• {b}" for b in topic["body_ru"][:3])
            + f"\n\n📍 {config.ADDRESS}\n🕘 {config.TIMING}\n"
              f"📞 {config.PHONE_DISPLAY}\n🧮 {config.CALCULATOR_URL}")


# ---------------------------------------------------------------------------
# UNIFIED GENERATOR
# ---------------------------------------------------------------------------
def generate(platform: str, topic_key: Optional[str] = None,
             language: str = "roman", save: bool = True) -> Dict[str, Any]:
    """
    platform: instagram | facebook | tiktok | whatsapp | website
    """
    platform = (platform or "instagram").lower()
    topic = get_topic(topic_key) if topic_key else random.choice(TOPICS)

    if platform == "instagram":
        data = instagram_caption(topic, language)
    elif platform == "facebook":
        data = facebook_post(topic, language)
    elif platform == "tiktok":
        data = tiktok_script(topic, language)
    elif platform == "whatsapp":
        data = {"title": topic["topic_ru"], "caption": whatsapp_status(topic),
                "hashtags": "", "topic": topic["key"], "language": "roman",
                "service": topic["service"]}
    else:
        data = instagram_caption(topic, language)

    data["platform"] = platform

    if save:
        row = db.add_content(platform, topic["topic_ru"] if language != "urdu" else topic["topic_ur"],
                             language, data.get("caption", ""), data.get("hashtags", ""))
        data["id"] = row["id"]
        data["created_at"] = row["created_at"]
    return data


def banner_specs(topic_key: Optional[str] = None, platform: str = "instagram",
                 language: str = "roman") -> Dict[str, Any]:
    """Everything core.media.make_banner() needs for this post."""
    topic = get_topic(topic_key) if topic_key else random.choice(TOPICS)
    want_urdu = language == "urdu"
    ru = not want_urdu
    fallback = False

    # Images need an Arabic font + shaping engine. If the machine cannot render
    # Urdu correctly, fall back to Roman Urdu instead of shipping broken text.
    if want_urdu:
        try:
            from core import fonts as fontlib
            if not fontlib.urdu_ready():
                ru, fallback = True, True
        except Exception:
            ru, fallback = True, True

    title = topic["topic_ru"] if ru else topic["topic_ur"]
    sub = config.SHOP_NAME if ru else config.SHOP_NAME_UR
    hook = topic["hook_ru"] if ru else topic["hook_ur"]
    bullets = (topic["body_ru"] if ru else topic["body_ur"])[:5]
    preset = {
        "instagram": "instagram_post", "facebook": "facebook_post",
        "tiktok": "tiktok_cover", "whatsapp": "whatsapp_status",
    }.get(platform, "instagram_post")
    return {"title": title, "subtitle": sub, "hook": hook, "bullets": bullets,
            "preset": preset, "rtl": not ru, "tag": "CHISHTIAN - FREE HELP",
            "fallback_to_roman": fallback}


if __name__ == "__main__":
    for p in ("instagram", "facebook", "tiktok", "whatsapp"):
        d = generate(p, save=False)
        print("=" * 78)
        print(f"[{p.upper()}] {d['title']}")
        print(d["caption"])
        if d.get("hashtags"):
            print("\n" + d["hashtags"])