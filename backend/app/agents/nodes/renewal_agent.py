"""
Renewal agent (Task 32) - writes the ready-to-send renewal message for a
customer whose membership or service is about to expire: "Priya, your monthly
membership at Iron Pulse ends in 5 days".

Unlike follow-ups (enquiries gone quiet) or dues (money owed), this is about
renewing something the customer already bought.

Same 4-part pattern as every agent: form → brief → mock rules → run.
"""

from pydantic import BaseModel, Field

from app.agents.llm import AIResult, get_llm
from app.agents.quick_read import mock_quick_read


# Three situations (decided by plain code in renewal_service, not the AI):
KINDS = {
    "expiring_soon": "the customer's membership/service expires in a few days",
    "expired": "the membership/service has expired (within the last 7 days)",
    "lapsed": "the membership/service expired more than a week ago",
}


# 1. The form ----------------------------------------------------------------------
class RenewalMessage(BaseModel):
    message: str = Field(min_length=10, max_length=600,
                         description="The renewal message to send on WhatsApp/Instagram, 2-3 short lines")


# 2. The brief ---------------------------------------------------------------------
SYSTEM = (
    "You write a short RENEWAL REMINDER from a small local business in India to a customer whose "
    "membership or service is about to expire (or just expired). The owner will read it, may edit it, "
    "and sends it themselves.\n"
    "Rules:\n"
    "- Write in the customer's language: English → English, Hinglish → Hinglish, Hindi → Hindi.\n"
    "- Sound like the business (follow its brand voice). Warm, short, human: 2-3 short lines, at most 1 emoji.\n"
    "- Greet them by first name if you know it.\n"
    "- Mention what is expiring (the service) and when (in X days, or 'just expired').\n"
    "- If it's expiring soon, be upbeat: encourage them to renew so they don't miss out.\n"
    "- If it expired recently, be gentle: check if they'd like to continue.\n"
    "- If it lapsed (over a week ago), be soft: we miss them, would love to have them back.\n"
    "- End with ONE easy question (e.g. 'Shall I renew it for you?').\n"
    "- NEVER mention any price, fee, discount, offer or ₹ amount. NEVER promise slots, results or timings.\n"
    "- No links, no hashtags. Do not invent facts about the business."
)


# 3. The mock: ready-made messages, filled in ---------------------------------------
def mock_renewal(business: dict, customer_name: str | None, service: str,
                 kind: str, days: int) -> dict:
    """days = days until expiry (negative = already expired)."""
    hinglish = False
    first = (customer_name or "").split()[0].title() if customer_name else ""
    name = business["name"]
    hello = f"Hi {first}!" if first else "Hi!"

    # Detect language from business brand_voice
    voice = (business.get("brand_voice") or "").lower()
    if any(w in voice for w in ("hinglish", "hindi", "desi")):
        hinglish = True

    if hinglish:
        if kind == "expiring_soon":
            text = (f"{hello} {name} se 🙂 Aapki {service} {days} din mein expire ho rahi hai. "
                    f"Renew kar lein taaki break na aaye? Ek word mein bata dijiye!")
        elif kind == "expired":
            text = (f"{hello} {name} se. Aapki {service} abhi expire ho gayi hai. "
                    f"Continue karna chahein toh hum ready hain 🙏 Batayein?")
        else:
            text = (f"{hello} {name} se. Aapki {service} kuch din pehle expire ho gayi thi. "
                    f"Hum aapko miss kar rahe hain! Wapas aana chahein toh bata dijiye 🙏")
    else:
        if kind == "expiring_soon":
            text = (f"{hello} This is {name} 🙂 Your {service} expires in {days} day{'s' if days != 1 else ''}. "
                    f"Would you like to renew so there's no break? Just say yes!")
        elif kind == "expired":
            text = (f"{hello} This is {name}. Your {service} has just expired. "
                    f"Would you like to continue? We're happy to help 🙏")
        else:
            text = (f"{hello} This is {name}. Your {service} expired a little while ago. "
                    f"We'd love to have you back! Would you like to renew? 🙏")
    return {"message": text[:600]}


# 4. The run -----------------------------------------------------------------------
def write_renewal(business: dict, customer_name: str | None, service: str,
                  kind: str, days: int) -> AIResult[RenewalMessage]:
    services = ", ".join(map(str, business.get("services") or [])) or "not listed"
    when = (f"expires in {days} day{'s' if days != 1 else ''}"
            if days > 0 else "just expired" if days >= -7 else f"expired {-days} days ago")
    prompt = (
        f"Business: {business['name']} ({business['industry']}). Services: {services}.\n"
        f"Brand voice: {business.get('brand_voice') or 'friendly and polite'}\n"
        f"Customer's name: {customer_name or 'unknown'}.\n"
        f"Their {service} {when}. Situation: {KINDS.get(kind, kind)}.\n"
    )
    return get_llm().ask(system=SYSTEM, prompt=prompt, schema=RenewalMessage, max_tokens=400,
                         mock=lambda: mock_renewal(business, customer_name, service, kind, days))
