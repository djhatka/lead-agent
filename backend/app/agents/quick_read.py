"""
Quick Read - a tiny practice agent that shows the pattern EVERY agent follows.

Each agent is made of four parts:
    1. The form   (schema)  - what the answer must look like
    2. The brief  (system)  - the agent's job description
    3. The mock   (rules)   - free fake answer for mock mode / safety net
    4. The run    (function)- puts it together and calls the AI connector

Quick Read looks at one customer message and tells us: which language,
a one-line summary, do they ask about price, do they want it soon.
(The real Intake and Tone agents in Task 8 work exactly the same way.)
"""

import re
from typing import Literal

from pydantic import BaseModel, Field

from app.agents.llm import AIResult, get_llm


# 1. The form ----------------------------------------------------------------------
class QuickRead(BaseModel):
    language: Literal["english", "hindi", "hinglish", "other"] = Field(
        description="Language of the message. Hinglish = Hindi written in English letters, often mixed with English."
    )
    summary: str = Field(max_length=150, description="One short line saying what the customer wants.")
    asks_price: bool = Field(description="Does the customer ask about price, fees or cost?")
    wants_it_soon: bool = Field(description="Do they want it today, tomorrow, this week, or say urgent/asap?")


# 2. The brief ---------------------------------------------------------------------
SYSTEM = (
    "You read messages that customers send to small local businesses in India "
    "(gyms, salons, clinics, car shops...). Messages may be in English, Hindi or Hinglish. "
    "Read the message carefully and fill in the answer form. Be brief and factual."
)


# 3. The mock: simple word-spotting rules ------------------------------------------
HINGLISH_WORDS = {"kitna", "kitne", "hai", "hain", "ka", "ke", "ki", "batao", "bhai", "chahiye",
                  "kya", "kab", "aaj", "kal", "mujhe", "karna", "se", "hu", "hoon", "acha"}
PRICE_WORDS = ("price", "cost", "fee", "fees", "charges", "rate", "kitna", "kitne", "₹", "rs", "emi", "how much")
SOON_WORDS = ("today", "tomorrow", "asap", "urgent", "now", "this week", "aaj", "kal", "jaldi", "immediately")


def mock_quick_read(message: str) -> dict:
    lower = message.lower()
    words = set(re.findall(r"[a-z]+", lower))
    if re.search(r"[ऀ-ॿ]", message):           # Devanagari letters → Hindi
        language = "hindi"
    elif len(words & HINGLISH_WORDS) >= 2:
        language = "hinglish"
    else:
        language = "english"
    return {
        "language": language,
        "summary": message.strip()[:100] or "(empty message)",
        "asks_price": any(w in lower for w in PRICE_WORDS),
        "wants_it_soon": any(w in lower for w in SOON_WORDS),
    }


# 4. The run -----------------------------------------------------------------------
def quick_read(message: str) -> AIResult[QuickRead]:
    return get_llm().ask(
        system=SYSTEM,
        prompt=f"Customer message:\n\"\"\"\n{message}\n\"\"\"",
        schema=QuickRead,
        mock=lambda: mock_quick_read(message),
        max_tokens=300,
    )
