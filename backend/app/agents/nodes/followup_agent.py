"""
Follow-up agent (Task 30) - writes the ready-to-send follow-up message for an
enquiry that's gone quiet: "Rahul asked about Zumba 2 days ago and got no follow-up".

Unlike the instant first reply, nothing here is sent automatically: the owner
sees the message, can change it, and sends it with one tap.

What it reads:
    the business profile, the customer's name, what they asked about, why the
    reminder is showing (see KINDS), how many days it's been, and how many
    follow-ups have already gone out since the customer last wrote.

What it must never do: invent prices, offers or promises, or nag. Plain code
double-checks (followup_service.draft): money or links → the ready-made message
below is used instead (the owner can still add a price by hand before sending).

Same 4-part pattern as every agent: form → brief → mock rules → run.
"""

from pydantic import BaseModel, Field

from app.agents.llm import AIResult, get_llm
from app.agents.nodes.first_reply_agent import QUESTIONS, DEFAULT_QUESTION, find_service
from app.agents.quick_read import mock_quick_read

# Why a reminder shows (decided by plain code in followup_service, not the AI):
KINDS = {
    "no_reply": "the customer wrote and nobody from the business has replied yet",
    "waiting": "the customer wrote again and is waiting for the business to answer",
    "gone_quiet": "the business replied, but the customer hasn't written back",
}


# 1. The form ----------------------------------------------------------------------
class FollowUp(BaseModel):
    message: str = Field(min_length=10, max_length=600,
                         description="The follow-up message to send on WhatsApp/Instagram, 2-3 short lines")


# 2. The brief ---------------------------------------------------------------------
SYSTEM = (
    "You write a short FOLLOW-UP message from a small local business in India to a customer whose enquiry "
    "has gone quiet. The owner will read it, may edit it, and sends it themselves.\n"
    "Rules:\n"
    "- Write in the customer's language: English → English, Hinglish → Hinglish, Hindi → Hindi.\n"
    "- Sound like the business (follow its brand voice). Warm, short, human: 2-3 short lines, at most 1 emoji.\n"
    "- Greet them by first name if you know it and mention what they asked about.\n"
    "- If nobody replied to them yet, start with a short, sincere sorry for the late reply.\n"
    "- If the business already replied and the customer went quiet, check in gently. Never guilt-trip or pressure.\n"
    "- If this is the 2nd or later follow-up, make it the last gentle check: it's fine if they're not interested.\n"
    "- End with ONE easy question they can answer in a word or two (e.g. which day suits them).\n"
    "- NEVER mention any price, fee, discount, offer or ₹ amount. NEVER promise slots, results or timings.\n"
    "- No links, no hashtags. Do not invent facts about the business."
)


# 3. The mock: ready-made messages, filled in ---------------------------------------
def mock_follow_up(business: dict, customer_name: str | None, asked: str, service: str | None,
                   kind: str, nth: int) -> dict:
    """nth = which follow-up this is since the customer last wrote (1 = the first)."""
    hinglish = mock_quick_read(asked or "")["language"] in ("hinglish", "hindi")
    first = (customer_name or "").split()[0].title() if customer_name else ""
    name = business["name"]
    service = service or find_service(asked or "", business.get("services", []))
    question = QUESTIONS.get(business.get("industry"), DEFAULT_QUESTION)[1 if hinglish else 0]
    hello = f"Hi {first}!" if first else "Hi!"

    if hinglish:
        about = f"{service} ke baare mein" if service else "aapke message ke baare mein"
        if kind in ("no_reply", "waiting"):
            text = f"{hello} {name} se. Late reply ke liye sorry 🙏 Aapne {about} poocha tha. {question}"
        elif nth >= 2:
            text = (f"{hello} {name} se ek last check: kya aap abhi bhi {about.replace(' ke baare mein', '')} "
                    f"mein interested hain? Agar abhi nahi, toh bilkul theek hai 🙏 Bas ek word mein bata dijiye.")
        else:
            text = f"{hello} {name} se bas check kar rahe the 🙂 Aapne {about} poocha tha. {question}"
    else:
        about = f"about {service}" if service else "with us"
        if kind in ("no_reply", "waiting"):
            text = f"{hello} This is {name}. Sorry for the late reply 🙏 You'd asked {about}. {question}"
        elif nth >= 2:
            text = (f"{hello} Just one last check from {name}: are you still interested"
                    f"{' in ' + service if service else ''}? If not right now, that's completely fine 🙏 "
                    f"A one-word reply is enough.")
        else:
            text = f"{hello} Just checking in from {name} 🙂 You'd asked {about}. {question}"
    return {"message": text[:600]}


# 4. The run -----------------------------------------------------------------------
def write_follow_up(business: dict, customer_name: str | None, asked: str, service: str | None,
                    kind: str, nth: int, days: int) -> AIResult[FollowUp]:
    services = ", ".join(map(str, business.get("services") or [])) or "not listed"
    prompt = (
        f"Business: {business['name']} ({business['industry']}). Services: {services}.\n"
        f"Brand voice: {business.get('brand_voice') or 'friendly and polite'}\n"
        f"Customer's name: {customer_name or 'unknown'}. They asked about: {service or 'see their message'}.\n"
        f"Situation: {KINDS.get(kind, kind)}, for {days} day{'s' if days != 1 else ''}. "
        f"This is follow-up number {nth}.\n"
        f"The customer's last message:\n\"\"\"\n{asked}\n\"\"\""
    )
    return get_llm().ask(system=SYSTEM, prompt=prompt, schema=FollowUp, max_tokens=400,
                         mock=lambda: mock_follow_up(business, customer_name, asked, service, kind, nth))
