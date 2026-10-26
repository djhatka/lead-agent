"""
Scoring Agent - gives each lead a score from 1 to 100: "how likely is this
person to actually buy?"

It's a HYBRID, on purpose:

  Part 1. FIXED POINTS (plain code, no AI)
     Clear facts anyone can check: where they came from, did they share a
     phone number, how many messages, do they sound urgent...
     → the same lead always gets the same points, and the owner can see why.

  Part 2. AI ADJUSTMENT (-20 to +20)
     The AI reads the actual words and judges buying intent:
     "Book me for Saturday 10am" (+15) vs "just checking prices, maybe later" (-15).
     Code can't understand meaning like this; the AI can.

  Final score = fixed points + AI adjustment, kept between 1 and 100.

Every point is listed in a "breakdown", e.g.
    {"Starting points": 10, "Source: Google": 20, "Shared phone number": 10,
     "Tone: urgent": 10, "AI: buying intent high": 15}
so the dashboard can show exactly WHY a lead got its score.
"""

from dataclasses import dataclass, field
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.agents.llm import AIResult, get_llm
from app.platforms import PLATFORMS

# ---------------------------------------------------------------------------
# Part 1: the fixed points
# ---------------------------------------------------------------------------
STARTING_POINTS = 10

# How good leads from each place usually are. Someone recommended by a friend
# or who walks in is far more likely to buy than someone scrolling Instagram.
# (Later, Task 16 can tune these per business using its real sales data.)
SOURCE_POINTS = {
    "referral": 25, "walk_in": 25, "phone_call": 20, "google": 20,
    "whatsapp": 15, "website": 15, "email": 12,
    "instagram": 8, "facebook": 6, "youtube": 6, "linkedin": 8,
    "justdial": 8, "sulekha": 8, "indiamart": 12, "tradeindia": 10,
}
CATEGORY_POINTS = {"marketplace": 15, "directory": 8, "social": 6, "search_maps": 15,
                   "messaging": 12, "own": 12, "offline": 15}

TONE_POINTS = {"urgent": 10, "frustrated": 5, "casual": 0}   # frustrated = wants it, but at risk


@dataclass
class LeadFacts:
    """Everything the scorer needs to know about a lead."""

    source: str
    message: str                          # latest customer message
    has_phone: bool = False
    has_name: bool = False
    service: Optional[str] = None         # from the Intake agent
    details: dict = field(default_factory=dict)
    inbound_messages: int = 1             # how many times the customer has written
    sentiment: str = "casual"             # from the Tone agent
    industry: str = "other"


def fixed_points(facts: LeadFacts) -> dict[str, int]:
    """Plain rules → a breakdown of points. No AI involved."""
    platform = PLATFORMS.get(facts.source)
    source_pts = SOURCE_POINTS.get(facts.source) or CATEGORY_POINTS.get(platform.category if platform else "", 8)
    name = platform.name if platform else facts.source

    points = {"Starting points": STARTING_POINTS, f"Source: {name}": source_pts}
    if facts.has_phone:
        points["Shared phone number"] = 10
    if facts.has_name:
        points["Gave their name"] = 3
    if facts.service:
        points[f"Clear service: {facts.service}"] = 7
    if facts.details:
        points[f"Gave details ({len(facts.details)})"] = min(3 * len(facts.details), 9)
    if facts.inbound_messages >= 3:
        points["Very engaged (3+ messages)"] = 10
    elif facts.inbound_messages == 2:
        points["Engaged (2 messages)"] = 5
    if TONE_POINTS.get(facts.sentiment):
        points[f"Tone: {facts.sentiment}"] = TONE_POINTS[facts.sentiment]
    return points


# ---------------------------------------------------------------------------
# Part 2: the AI adjustment (same 4-part pattern as the other agents)
# ---------------------------------------------------------------------------
class IntentAnswer(BaseModel):
    intent: Literal["high", "medium", "low"] = Field(description="How ready is this customer to buy?")
    adjustment: int = Field(ge=-20, le=20, description="Points to add or remove: +20 ready to book now ... -20 clearly just browsing.")
    reason: str = Field(max_length=200, description="One short sentence for the business owner.")


SYSTEM = (
    "You judge BUYING INTENT in messages customers send to small local businesses in India "
    "(English, Hindi or Hinglish). Other facts (source, phone number, tone) are already scored "
    "separately, so judge ONLY how ready this person is to buy from their words.\n"
    "- high (+10 to +20): wants to book, asks for a slot/address/availability, says they will come.\n"
    "- medium (-5 to +9): interested, asking normal questions such as price or timings.\n"
    "- low (-20 to -6): just browsing, 'maybe later', comparing, asking for someone else, far future."
)

BUYING_WORDS = ("book", "booking", "appointment", "slot", "join", "joining", "confirm", "address", "location",
                "when can i come", "available", "visit", "pick up", "start from", "kab aa", "aa jaunga", "aa sakta")
BROWSING_WORDS = ("just asking", "just checking", "maybe later", "not now", "next month", "next year",
                  "for my friend", "just want to know", "only price", "comparing", "thinking about", "dekhte hai")


def mock_intent(message: str) -> dict:
    lower = message.lower()
    buying = [w for w in BUYING_WORDS if w in lower]
    browsing = [w for w in BROWSING_WORDS if w in lower]
    if browsing and not buying:
        return {"intent": "low", "adjustment": -10, "reason": f"Seems to be just browsing ({', '.join(browsing[:2])})."}
    if buying:
        return {"intent": "high", "adjustment": 10 + 5 * min(len(buying) - 1, 2),
                "reason": f"Ready to take the next step ({', '.join(buying[:2])})."}
    return {"intent": "medium", "adjustment": 0, "reason": "Interested, asking normal questions."}


def build_prompt(facts: LeadFacts) -> str:
    return (
        f"Industry: {facts.industry}\nService: {facts.service or 'unclear'}\n"
        f"Customer message:\n\"\"\"\n{facts.message}\n\"\"\""
    )


# ---------------------------------------------------------------------------
# Putting it together
# ---------------------------------------------------------------------------
@dataclass
class ScoreResult:
    score: int                       # 1–100
    breakdown: dict[str, int]        # every ingredient of the score
    reason: str                      # one plain sentence for the owner
    ai: AIResult[IntentAnswer]       # the AI step (mode, timing, errors) for the run log


def score_lead(facts: LeadFacts) -> ScoreResult:
    points = fixed_points(facts)

    ai = get_llm().ask(
        system=SYSTEM, prompt=build_prompt(facts), schema=IntentAnswer,
        mock=lambda: mock_intent(facts.message), max_tokens=300,
    )
    if ai.data.adjustment:
        points[f"AI: buying intent {ai.data.intent}"] = ai.data.adjustment

    score = max(1, min(100, sum(points.values())))

    # A short reason: the AI's view + the biggest plus points
    top = sorted((k for k, v in points.items() if v > 0 and k != "Starting points"),
                 key=lambda k: -points[k])[:3]
    reason = f"{ai.data.reason} Main factors: {', '.join(top)}." if top else ai.data.reason
    return ScoreResult(score=score, breakdown=points, reason=reason, ai=ai)
