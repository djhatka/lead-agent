"""
Writer agent - turns a planned post idea into a ready-to-post post:

    caption     starts with a scroll-stopping first line ("hook"), ends with a clear call to action
    hashtags    the right number for the platform (Google posts: none)
    script      reels/videos: scene by scene with seconds; carousels: slide by slide
    shot_list   exactly what photo/video to take (the owner still shoots it!)

It writes in the BUSINESS'S OWN VOICE (brand_voice in the business profile):
energetic Hinglish for a gym, premium for a detailing studio, caring for a clinic.

Every caption ends with a WhatsApp link whose pre-filled message carries a
little code, e.g. "(code P12)". When a customer taps it, their message
arrives with that code, and the app links the lead to post #12 automatically.

Same 4-part pattern: form → brief → mock rules → run.
"""

import re
from typing import Optional
from urllib.parse import quote

from pydantic import BaseModel, Field

from app.agents.llm import AIResult, get_llm

# How many hashtags suit each platform (min, max). Google posts don't use hashtags.
HASHTAG_RANGE = {"instagram": (5, 12), "facebook": (1, 3), "linkedin": (3, 5), "youtube": (2, 5), "google": (0, 0)}
CAPTION_TARGET = {"instagram": 900, "facebook": 700, "google": 750, "linkedin": 1200, "youtube": 1000}


# 1. The form ----------------------------------------------------------------------
class WrittenPost(BaseModel):
    caption: str = Field(max_length=2000, description="Full caption. First line = hook. Ends with a call to action.")
    hashtags: list[str] = Field(default_factory=list, max_length=15, description="Without the # sign")
    script: str = Field(default="", max_length=2500,
                        description="Reel/video: scenes with seconds. Carousel: slide-by-slide text. Photo: empty.")
    shot_list: str = Field(max_length=800, description="What exactly to photograph or film, in simple steps.")


# 2. The brief ---------------------------------------------------------------------
SYSTEM = (
    "You write social media posts for small local businesses in India. Rules:\n"
    "- Write in the business's brand voice exactly as described (e.g. Hinglish if it says Hinglish).\n"
    "- First line is a hook that stops the scroll. Short sentences. Plenty of line breaks.\n"
    "- One clear call to action at the end. Use the WhatsApp link you are given, exactly as given.\n"
    "- Never invent prices, discounts, dates or facts that you are not given. If the idea mentions an "
    "offer without numbers, say 'special offer' and ask people to message for details.\n"
    "- Hashtags: follow the count you are given; mix local (area/city) and topic tags; no # sign.\n"
    "- Reels/videos: a script with timed scenes (e.g. '0-3s: ...'), 15-30 seconds total.\n"
    "- Carousels: slide-by-slide text in the script, 5-7 slides.\n"
    "- The shot list must be doable with a phone by a busy owner."
)


def whatsapp_link(phone: Optional[str], post_id: int, title: str) -> Optional[str]:
    """wa.me link with a pre-filled message carrying the post's code."""
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    short = title if len(title) <= 45 else title[:45].rsplit(" ", 1)[0]     # don't cut a word in half
    text = f"Hi! I saw your post about {short}. Please share details (code P{post_id})"
    return f"https://wa.me/{digits}?text={quote(text)}"


def build_prompt(post: dict, business: dict, link: Optional[str]) -> str:
    low, high = HASHTAG_RANGE.get(post["platform"], (3, 8))
    return (
        f"Business: {business['name']} ({business['industry']}), {business.get('area') or ''} {business['city']}\n"
        f"Services: {', '.join(business['services'])}\n"
        f"Brand voice: {business['brand_voice'] or 'friendly and clear'}\n"
        f"Target audience: {business['target_audience'] or 'local customers'}\n\n"
        f"Write this post:\n  Platform: {post['platform']}\n  Format: {post['kind']}\n"
        f"  Type (pillar): {post['pillar']}\n  Title: {post['title']}\n  Idea: {post['media_note']}\n\n"
        f"Caption length: about {CAPTION_TARGET.get(post['platform'], 800)} characters or less.\n"
        f"Hashtags: between {low} and {high}.\n"
        f"WhatsApp link for the call to action: {link or '(none: ask people to DM instead)'}"
    )


# 3. The mock: templates that follow the brand voice --------------------------------
HOOKS = {
    "offer": "{service} at a special price this week 👀",
    "transformation": "Before vs after. Same {thing}, 1 visit. 😮",
    "testimonial": "\"Wish I had come here sooner.\"",
    "tips": "3 mistakes people make with {service} (no. 2 is very common)",
    "behind_the_scenes": "Who's actually behind your {service}? Meet the team 👋",
    "trend": "POV: you finally booked {service} 😂",
    "festival": "Happy {festival} from all of us at {name}! 🪔",
}
HINGLISH_HOOKS = {
    "offer": "{service} pe is hafte special offer 🔥 Miss mat karna!",
    "transformation": "Pehle vs baad mein, farak khud dekh lo 😮🔥",
    "testimonial": "\"Pehle aana chahiye tha yaar!\", hamare customer ke words 🙌",
    "tips": "{service} mein ye 3 galtiyan mat karna ❌",
    "behind_the_scenes": "Aapke {service} ke peeche ki team se milo 💪",
    "trend": "POV: finally {service} book kar hi liya 😂",
    "festival": "{name} ki taraf se Happy {festival}! 🪔✨",
}
BODIES = {
    "offer": "Limited slots only.\nGood work, honest price, no hidden charges.\n\nMessage us for the offer details before it ends.",
    "transformation": "Swipe or watch till the end to see the difference.\nThis is what proper {service} looks like.",
    "testimonial": "Real customer. Real result.\nThank you for trusting {name} with your {service}. 🙏\n\nYour story could be next.",
    "tips": "1️⃣ Not asking the right questions before booking\n2️⃣ Choosing only on price\n3️⃣ Skipping the follow-up care\n\nSave this for later 📌",
    "behind_the_scenes": "Every {service} is done by people who care about the details.\nCome say hi anytime.",
    "trend": "Tag a friend who needs this 👇",
    "festival": "May this festival bring you joy, health and success.\nFrom our family to yours. ✨",
}
INDUSTRY_TAGS = {
    "gym": ["fitness", "gym", "workout", "fitnessmotivation", "healthylifestyle"],
    "car_detailing": ["cardetailing", "carcare", "ceramiccoating", "detailing", "carsofinstagram"],
    "auto_service": ["carservice", "carrepair", "carcare", "mechanic"],
    "clinic": ["dentist", "dentalcare", "smile", "oralhealth", "healthysmile"],
    "salon": ["salon", "haircut", "beauty", "makeover", "skincare"],
    "restaurant": ["foodie", "restaurant", "delhifood", "foodlover"],
    "cafe": ["cafe", "coffee", "delhicafe", "cafehopping"],
    "coaching": ["coaching", "students", "education", "exams"],
    "real_estate": ["realestate", "property", "homes", "delhiproperty"],
}
THING = {"car_detailing": "car", "auto_service": "car", "gym": "body", "clinic": "smile", "salon": "look"}


def _tag(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _service_in(post: dict, services: list[str]) -> str:
    text = f"{post['title']} {post['media_note']}".lower()
    return next((s for s in services if s.lower() in text), services[0] if services else "our services")


def mock_write(post: dict, business: dict, link: Optional[str], festival: Optional[str]) -> dict:
    voice = (business.get("brand_voice") or "").lower()
    hinglish = "hinglish" in voice
    service = _service_in(post, business["services"])
    fill = {"service": service, "name": business["name"], "festival": festival or "the festival",
            "thing": THING.get(business["industry"], "result")}

    pillar = post["pillar"]
    hook = (HINGLISH_HOOKS if hinglish else HOOKS)[pillar].format(**fill)
    if festival and pillar == "offer":
        hook = f"{festival} special! " + hook
    body = BODIES[pillar].format(**fill)
    cta = (f"📲 Book on WhatsApp: {link}" if link else "📩 DM us to book.")
    if hinglish:
        cta = cta.replace("Book on WhatsApp", "Abhi WhatsApp karo").replace("DM us to book", "DM karo, abhi book karo")
    if pillar == "festival":
        cta = ""                                         # a greeting is a greeting, not a sales pitch
    caption = f"{hook}\n\n{body}" + (f"\n\n{cta}" if cta else "")
    if "emoji" not in voice and not hinglish:
        caption = caption.replace(" 🔥", "").replace(" 😂", "")

    low, high = HASHTAG_RANGE.get(post["platform"], (3, 8))
    pool = ([_tag(service), _tag(business.get("area") or ""), _tag(business["city"]) + business["industry"].split("_")[0]]
            + INDUSTRY_TAGS.get(business["industry"], ["local", "smallbusiness"]))
    if festival:
        pool.insert(1, _tag(festival))
    hashtags = [t for i, t in enumerate(pool) if t and t not in pool[:i]][:high]

    if post["kind"] in ("reel", "video", "story"):
        script = (f"0-3s: Hook on screen: \"{hook}\" (face to camera or the best shot first)\n"
                  f"3-12s: Show {service} being done: 3-4 quick clips, 2 seconds each\n"
                  f"12-20s: The result / the happy customer / the offer details\n"
                  f"20-25s: \"WhatsApp us now, link in caption\" + business name on screen")
        shots = (f"Film vertically (9:16) in good daylight. 1) A close-up of {service} in progress. "
                 f"2) The final result from 2 angles. 3) You or the team saying one line to camera. Keep each clip 2-3 s.")
    elif post["kind"] == "carousel":
        script = (f"Slide 1: {hook}\nSlide 2-4: one point per slide, big text, few words\n"
                  f"Slide 5: a real photo from {business['name']}\nSlide 6: \"Save this & WhatsApp us to book\"")
        shots = f"One clean photo for slide 5: {service} result or the team at work, square (1:1), no clutter."
    else:
        script = ""
        shots = f"One sharp photo: {service} result or your shop front, good light, square or 4:5. Add your logo small in a corner."
    if pillar == "festival":
        shots = ("A festive photo: your team together, or the shop with diyas/lights/rangoli. "
                 "Smiling faces, good light. Add your logo small in a corner.")

    if post["platform"] == "google":
        hashtags = []                                                     # Google posts don't use hashtags
        caption = caption.replace("📲 ", "").replace("📩 ", "")
    return {"caption": caption[:2000], "hashtags": hashtags, "script": script, "shot_list": shots}


# 4. The run -----------------------------------------------------------------------
def run_writer(post: dict, business: dict, festival: Optional[str] = None) -> AIResult[WrittenPost]:
    link = whatsapp_link(business.get("phone"), post["id"], post["title"])
    result = get_llm().ask(
        system=SYSTEM, prompt=build_prompt(post, business, link), schema=WrittenPost,
        mock=lambda: mock_write(post, business, link, festival), max_tokens=1500,
    )
    # Tidy-up: platform hashtag limits, no '#', no duplicates; make sure the WhatsApp link survived
    low, high = HASHTAG_RANGE.get(post["platform"], (3, 8))
    seen, tags = set(), []
    for tag in result.data.hashtags:
        tag = tag.strip().lstrip("#").replace(" ", "")
        if tag and tag.lower() not in seen:
            seen.add(tag.lower())
            tags.append(tag)
    result.data.hashtags = tags[:high]
    if (link and post["pillar"] != "festival" and link not in result.data.caption
            and len(result.data.caption) + len(link) < 1990):
        result.data.caption = f"{result.data.caption}\n\n📲 WhatsApp: {link}"
    return result
