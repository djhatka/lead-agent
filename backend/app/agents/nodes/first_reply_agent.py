"""
First Reply agent (Task 29) - writes the instant "thanks, we got your message"
reply to a NEW WhatsApp / Instagram / Facebook enquiry, in the business's voice.

What it reads:
    the customer's message, the business profile (name, type, services, brand
    voice), whether the business is open right now and when it next opens, and
    the owner's optional note (e.g. "For emergencies call 98100 00000").

What it must never do: give prices, discounts or promises (it can't know them),
invent facts, or give medical advice. Plain code double-checks that afterwards
(auto_reply_service.safe_reply): if the reply mentions money or a link, the safe
ready-made reply below goes out instead.

Same 4-part pattern as every agent: form → brief → mock rules → run.
"""

import re

from pydantic import BaseModel, Field

from app.agents.llm import AIResult, get_llm
from app.agents.quick_read import mock_quick_read


# 1. The form ----------------------------------------------------------------------
class FirstReply(BaseModel):
    reply: str = Field(min_length=10, max_length=600,
                       description="The WhatsApp/Instagram reply to send, 2-3 short lines")


# 2. The brief ---------------------------------------------------------------------
SYSTEM = (
    "You write the FIRST reply to a new customer enquiry for a small local business in India. "
    "It is sent automatically within seconds on WhatsApp or Instagram, so the customer knows they were heard.\n"
    "Rules:\n"
    "- Reply in the customer's language: English → English, Hinglish → Hinglish, Hindi → Hindi.\n"
    "- Sound like the business (follow its brand voice). Warm, short, human: 2-3 short lines, at most 1-2 emojis.\n"
    "- Thank them, greet them by first name if you know it, and show you understood what they want.\n"
    "- If the business is CLOSED now, say so politely and say when the team will get back (use the time given). "
    "If it is OPEN, say the team will reply with details shortly.\n"
    "- Ask ONE simple helpful question (e.g. which day suits them, which car they have).\n"
    "- NEVER mention any price, fee, discount, offer or ₹ amount, even if they ask: say the team will share details.\n"
    "- NEVER promise availability, slots, results or timings beyond what is given. No medical advice.\n"
    "- No links, no hashtags. Do not invent facts about the business.\n"
    "- If an owner's note is given, end with it word for word."
)


# 3. The mock: ready-made replies, filled in ----------------------------------------
QUESTIONS = {
    "gym": ("What time of day suits you for a visit?", "Aapko kis time aana suit karega?"),
    "clinic": ("Which day would suit you for an appointment?", "Appointment ke liye aapko kaunsa din theek rahega?"),
    "car_detailing": ("Which car do you have, and which day suits you to bring it in?",
                      "Aapki kaunsi car hai, aur kis din laana theek rahega?"),
    "auto_service": ("Which car do you have, and which day suits you to bring it in?",
                     "Aapki kaunsi car hai, aur kis din laana theek rahega?"),
    "salon": ("Which day and time would suit you?", "Aapko kaunsa din aur time theek rahega?"),
}
DEFAULT_QUESTION = ("When would suit you?", "Aapko kab theek rahega?")


def find_service(message: str, services: list) -> str | None:
    """The first of the business's own services that the customer mentions."""
    lower = message.lower()
    for service in services or []:
        if service and re.search(rf"\b{re.escape(str(service).lower())}\b", lower):
            return str(service)
    return None


def mock_first_reply(message: str, business: dict, customer_name: str | None, open_now: bool,
                     back_at: str, note: str = "") -> dict:
    hinglish = mock_quick_read(message)["language"] in ("hinglish", "hindi")
    first = (customer_name or "").split()[0].title() if customer_name else ""
    name, service = business["name"], find_service(message, business.get("services", []))
    question = QUESTIONS.get(business.get("industry"), DEFAULT_QUESTION)[1 if hinglish else 0]
    if hinglish:
        hello = f"Hi {first}! " if first else "Hi! "
        about = f"{service} ke baare mein aapka message mil gaya. " if service else "Aapka message mil gaya. "
        when = (f"Abhi hum band hain, hamari team {back_at} aapko details bhejegi. " if not open_now
                else "Hamari team thodi der mein aapko details bhejegi. ")
        text = f"{hello}{name} ko message karne ke liye thank you 🙏 {about}{when}{question}"
    else:
        hello = f"Hi {first}! " if first else "Hi! "
        about = f"Thanks for asking about {service}. " if service else "We've got your message. "
        when = (f"We're closed right now, but our team will get back to you {back_at} with the details. "
                if not open_now else "Our team will reply with the details shortly. ")
        text = f"{hello}Thank you for messaging {name} 🙏 {about}{when}{question}"
    if note:
        text = f"{text}\n{note}"
    return {"reply": text[:600]}


# 4. The run -----------------------------------------------------------------------
def write_first_reply(message: str, business: dict, customer_name: str | None, open_now: bool,
                      back_at: str, note: str = "") -> AIResult[FirstReply]:
    services = ", ".join(map(str, business.get("services") or [])) or "not listed"
    prompt = (
        f"Business: {business['name']} ({business['industry']}). Services: {services}.\n"
        f"Brand voice: {business.get('brand_voice') or 'friendly and polite'}\n"
        f"Right now the business is {'OPEN' if open_now else 'CLOSED'}."
        + ("" if open_now else f" The team will get back {back_at}.") + "\n"
        f"Customer's name: {customer_name or 'unknown'}\n"
        f"Owner's note to end with: {note or '(none)'}\n"
        f"Customer's message:\n\"\"\"\n{message}\n\"\"\""
    )
    return get_llm().ask(system=SYSTEM, prompt=prompt, schema=FirstReply, max_tokens=400,
                         mock=lambda: mock_first_reply(message, business, customer_name, open_now, back_at, note))
