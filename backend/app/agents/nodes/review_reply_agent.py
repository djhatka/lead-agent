"""
Review Reply agent - reads a customer review and drafts the business's reply.

It also tags the review:
    sentiment        positive / neutral / negative
    topics           what it's about: staff, price, wait time, result, cleanliness...
    needs_attention  True for unhappy customers: the owner should read it themselves

Replies are DRAFTS. The owner approves before anything is posted, and
replies to negative reviews are never posted automatically.

Same 4-part pattern: form → brief → mock rules → run.
"""

import re
from typing import Literal

from pydantic import BaseModel, Field

from app.agents.llm import AIResult, get_llm

TOPICS = ("staff", "price", "wait time", "result", "cleanliness", "booking", "location", "communication")


# 1. The form ----------------------------------------------------------------------
class ReplyAnswer(BaseModel):
    sentiment: Literal["positive", "neutral", "negative"]
    topics: list[Literal[TOPICS]] = Field(default_factory=list, max_length=4)
    needs_attention: bool = Field(description="True if the customer is unhappy and the owner should step in")
    reply: str = Field(min_length=10, max_length=700, description="The public reply, 2-4 sentences")


# 2. The brief ---------------------------------------------------------------------
SYSTEM = (
    "You write public replies to customer reviews for a small local business in India. Rules:\n"
    "- Thank the reviewer by first name. Mention one specific thing they said.\n"
    "- Positive: warm and short. Neutral: thank them, acknowledge the issue, say you're working on it.\n"
    "- Negative: apologise sincerely, never argue or blame the customer, and invite them to call the business "
    "so you can make it right (use the phone number given). Mark needs_attention true.\n"
    "- NEVER offer discounts, refunds or freebies, and never promise anything specific.\n"
    "- NEVER reveal private details: no treatments, prices paid, car numbers or personal information, "
    "even if the review mentions them (this matters a lot for clinics).\n"
    "- 2-4 sentences. No hashtags. Sign off with the business name."
)


# 3. The mock: keywords + templates -------------------------------------------------
TOPIC_WORDS = {
    "staff": ("staff", "team", "doctor", "trainer", "behaviour", "behavior", "friendly", "rude", "polite", "helpful"),
    "price": ("price", "cost", "expensive", "cheap", "value", "charges", "overcharged", "money", "costly"),
    "wait time": ("wait", "waited", "late", "delay", "slow", "hours", "time taking", "on time"),
    "result": ("result", "finish", "shine", "painless", "pain", "results", "quality", "work", "transformation"),
    "cleanliness": ("clean", "hygiene", "hygienic", "dirty", "neat", "smell"),
    "booking": ("appointment", "booking", "slot", "schedule"),
    "communication": ("call", "reply", "response", "respond", "phone", "whatsapp", "informed"),
    "location": ("parking", "location", "find", "far", "near"),
}
PRAISE = {"staff": "Your kind words about our team mean a lot",
          "result": "We're so happy you loved the result",
          "cleanliness": "Glad you noticed the care we put into keeping things clean",
          "price": "Happy you found it good value",
          "booking": "Glad booking with us was easy"}


def find_topics(text: str) -> list[str]:
    lower = text.lower()
    return [t for t, words in TOPIC_WORDS.items() if any(re.search(rf"\b{re.escape(w)}", lower) for w in words)][:4]


def mock_reply(rating: int, text: str, author: str, business: dict) -> dict:
    first = (author or "there").split()[0].title()
    topics = find_topics(text)
    name, phone = business["name"], business.get("phone") or "us"
    if rating >= 4:
        liked = next((PRAISE[t] for t in topics if t in PRAISE), "We're so glad you had a great experience")
        reply = f"Thank you so much, {first}! 🙏 {liked}. See you again soon! - Team {name}"
        return {"sentiment": "positive", "topics": topics, "needs_attention": False, "reply": reply}
    issue = next((t for t in topics if t in ("wait time", "price", "staff", "communication", "cleanliness")), None)
    if rating == 3:
        noted = f"we've noted your point about {issue}" if issue else "we've noted your feedback"
        return {"sentiment": "neutral", "topics": topics, "needs_attention": False,
                "reply": f"Thank you for your honest feedback, {first}. {noted.capitalize()} and are working on it. "
                         f"We hope to give you a 5-star experience next time! - Team {name}"}
    about = f" with the {issue}" if issue else ""
    return {"sentiment": "negative", "topics": topics, "needs_attention": True,
            "reply": f"Hi {first}, we're truly sorry about your experience{about}. This isn't the standard we aim for. "
                     f"Please call us at {phone} so we can understand what happened and make it right. - Team {name}"}


# 4. The run -----------------------------------------------------------------------
def run_reply(rating: int, text: str, author: str, business: dict) -> AIResult[ReplyAnswer]:
    prompt = (f"Business: {business['name']} ({business['industry']}). Phone for unhappy customers: "
              f"{business.get('phone') or 'not given (ask them to message us)'}\n"
              f"Review by {author or 'a customer'}, {rating} stars:\n\"\"\"\n{text or '(no text, only stars)'}\n\"\"\"")
    result = get_llm().ask(system=SYSTEM, prompt=prompt, schema=ReplyAnswer,
                           mock=lambda: mock_reply(rating, text, author, business), max_tokens=500)
    # Safety net: stars decide at least this much, whatever the AI says
    if rating <= 2:
        result.data.needs_attention = True
        if result.data.sentiment == "positive":
            result.data.sentiment = "negative"
    return result
