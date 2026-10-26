"""
Tone Agent (sentiment) - reads HOW the customer feels, so the business knows
who to reply to first.

    urgent      wants it now: "need it today", "severe pain", "wedding this weekend"
    frustrated  annoyed, often because nobody replied: "called twice, no answer"
    casual      just asking, no rush: "what are your fees?"

Frustrated beats urgent: an annoyed customer is about to go to a competitor,
so they need a reply the fastest.

Same 4-part pattern: form → brief → mock rules → run.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.agents.llm import AIResult, get_llm


# 1. The form ----------------------------------------------------------------------
class ToneAnswer(BaseModel):
    sentiment: Literal["urgent", "casual", "frustrated"]
    confidence: Literal["low", "medium", "high"] = Field(description="How sure you are.")
    reason: str = Field(max_length=200, description="One short sentence explaining the label, for the business owner.")
    signals: list[str] = Field(default_factory=list, max_length=5,
                               description="Exact words/phrases from the message that show the tone.")


# 2. The brief ---------------------------------------------------------------------
SYSTEM = (
    "You judge the tone of messages that customers send to small local businesses in India "
    "(English, Hindi or Hinglish). Choose exactly one label:\n"
    "- frustrated: annoyed or upset, e.g. complaints about no reply, delays, bad service.\n"
    "- urgent: needs it very soon (today, tomorrow, asap), pain, emergency, a near deadline.\n"
    "- casual: a normal question with no hurry.\n"
    "If a message is both frustrated and urgent, choose frustrated. "
    "The reason must be short and plain, written for a busy shop owner."
)


# 3. The mock: word-spotting rules -------------------------------------------------
FRUSTRATED = (
    "no reply", "no response", "nobody", "no one", "not picked", "didn't pick", "never replied", "called twice",
    "called 3", "sent 3", "still waiting", "waiting since", "worst", "pathetic", "disappointed", "bad service",
    "not happy", "unprofessional", "ignored", "koi jawab nahi", "phone nahi uthaya", "bakwas", "nobody confirmed",
)
URGENT = (
    "today", "tonight", "asap", "urgent", "immediately", "right now", "emergency", "severe", "pain",
    "tomorrow", "this weekend", "wedding", "aaj", "abhi", "jaldi", "kal tak", "itself",
)


def mock_tone(message: str) -> dict:
    lower = message.lower()
    angry = [w for w in FRUSTRATED if w in lower]
    hurry = [w for w in URGENT if w in lower]
    if angry or lower.count("?") >= 3 or lower.count("!") >= 3:
        signals = angry or ["lots of ? or !"]
        return {"sentiment": "frustrated", "confidence": "high" if len(signals) > 1 else "medium",
                "reason": f"Customer sounds annoyed ({', '.join(signals[:3])}). Reply right away.",
                "signals": signals[:5]}
    if hurry:
        return {"sentiment": "urgent", "confidence": "high" if len(hurry) > 1 else "medium",
                "reason": f"Customer wants it soon ({', '.join(hurry[:3])}).", "signals": hurry[:5]}
    return {"sentiment": "casual", "confidence": "medium",
            "reason": "A normal enquiry with no sign of hurry or annoyance.", "signals": []}


# 4. The run -----------------------------------------------------------------------
def run_tone(message: str, earlier_messages: list[str] | None = None) -> AIResult[ToneAnswer]:
    """earlier_messages: what the customer said before, if any (context helps:
    a third 'hello??' after two unanswered messages is clearly frustrated)."""
    history = ""
    if earlier_messages:
        history = "Earlier messages from this customer:\n" + "\n".join(f"- {m}" for m in earlier_messages[-5:]) + "\n\n"
    everything = " ".join([*(earlier_messages or []), message])
    return get_llm().ask(
        system=SYSTEM,
        prompt=f"{history}Latest message:\n\"\"\"\n{message}\n\"\"\"",
        schema=ToneAnswer,
        mock=lambda: mock_tone(everything),
        max_tokens=300,
    )
