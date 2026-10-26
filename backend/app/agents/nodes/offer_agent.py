"""
Offer agent (Task 33) - writes a short, friendly message inviting a past
customer back during one of the business's own quiet time slots, e.g.
"Hi Priya, we have space this Tuesday morning - fancy a CrossFit session?"

The business's quiet time slot and the list of customers to invite are both
decided by plain code (slow_hours_service.py) - this agent only writes the
words. Same rule as every other agent: it never mentions a price, discount
or amount - the owner adds that themselves when they edit the message.

Same 4-part pattern as every agent: form -> brief -> mock rules -> run.
"""

from pydantic import BaseModel, Field

from app.agents.llm import AIResult, get_llm


# 1. The form ----------------------------------------------------------------------
class OfferMessage(BaseModel):
    message: str = Field(min_length=10, max_length=600,
                         description="The invite message to send on WhatsApp/Instagram, 2-3 short lines")


# 2. The brief ---------------------------------------------------------------------
SYSTEM = (
    "You write a short INVITE message from a small local business in India to a customer who has "
    "bought from them before, to fill a time slot that is usually quiet. The owner will read it, may "
    "edit it, and sends it themselves.\n"
    "Rules:\n"
    "- Write in the customer's language: English -> English, Hinglish -> Hinglish, Hindi -> Hindi.\n"
    "- Sound like the business (follow its brand voice). Warm, short, human: 2-3 short lines, at most 1 emoji.\n"
    "- Greet them by first name if you know it.\n"
    "- Mention the quiet time slot naturally (e.g. 'this Tuesday morning') and invite them back for the "
    "service they bought before, if you know it.\n"
    "- Sound like a genuine invite, not a sales blast: friendly, a little personal, not pushy.\n"
    "- End with ONE easy question (e.g. 'Want me to hold a spot for you?').\n"
    "- NEVER mention any price, fee, discount, offer amount or ₹ amount. NEVER promise exact "
    "results or timings.\n"
    "- No links, no hashtags. Do not invent facts about the business."
)


# 3. The mock: ready-made messages, filled in ---------------------------------------
def mock_offer(business: dict, customer_name: str | None, service: str | None,
               day: str, hours: str) -> dict:
    hinglish = False
    first = (customer_name or "").split()[0].title() if customer_name else ""
    name = business["name"]
    hello = f"Hi {first}!" if first else "Hi!"
    when = f"{day} {hours}"
    what = f" for {service}" if service else ""

    voice = (business.get("brand_voice") or "").lower()
    if any(w in voice for w in ("hinglish", "hindi", "desi")):
        hinglish = True

    if hinglish:
        text = (f"{hello} {name} se 🙂 {when} thoda khaali rehta hai, "
                f"aap aana chahein{what} toh bata dijiye, jagah rakh denge!")
    else:
        text = (f"{hello} This is {name} 🙂 We have some space {when}{what}. "
                f"Would you like to come in - shall I hold a spot for you?")
    return {"message": text[:600]}


# 4. The run -----------------------------------------------------------------------
def write_offer(business: dict, customer_name: str | None, service: str | None,
                day: str, hours: str) -> AIResult[OfferMessage]:
    services = ", ".join(map(str, business.get("services") or [])) or "not listed"
    prompt = (
        f"Business: {business['name']} ({business['industry']}). Services: {services}.\n"
        f"Brand voice: {business.get('brand_voice') or 'friendly and polite'}\n"
        f"Customer's name: {customer_name or 'unknown'}. What they bought before: {service or 'not known'}.\n"
        f"Quiet time slot to invite them to: {day} {hours}.\n"
    )
    return get_llm().ask(system=SYSTEM, prompt=prompt, schema=OfferMessage, max_tokens=400,
                         mock=lambda: mock_offer(business, customer_name, service, day, hours))
