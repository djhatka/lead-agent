"""
Call note agent (Task 38) - turns a phone call's transcript into one short line for
the dashboard: "Asked about Zumba pricing and this week's availability."

Same 4-part pattern as every agent: form -> brief -> mock rules -> run.
Plain code (calltracking_service.py) decides WHEN there's a transcript worth
summarising; this agent only ever writes the one-line note, never invents facts
about the call that aren't in the transcript.
"""

from pydantic import BaseModel, Field

from app.agents.llm import AIResult, get_llm

PRICE_WORDS = ("price", "cost", "charge", "fee", "₹")
AVAILABILITY_WORDS = ("available", "availability", "today", "tomorrow", "slot", "book", "appointment", "timing")


# 1. The form ----------------------------------------------------------------------
class CallNote(BaseModel):
    note: str = Field(min_length=3, max_length=300,
                      description="One short line: what the caller asked about or wanted, in plain English")


# 2. The brief ---------------------------------------------------------------------
SYSTEM = (
    "You read the TRANSCRIPT of a phone call to a small local business in India, and write ONE short "
    "line (under 25 words) for the owner's dashboard, summarising what the caller asked about or wanted.\n"
    "Rules:\n"
    "- Plain, factual, third person ('Asked about...', 'Wanted to know...').\n"
    "- Only use what's actually said in the transcript. Never invent a name, price, or outcome not in it.\n"
    "- No greeting, no filler, no quotes from the call - just the gist."
)


# 3. The mock: simple keyword rules ---------------------------------------------
def mock_call_note(business: dict, transcript: str) -> dict:
    text = (transcript or "").lower()
    if not text.strip():
        return {"note": "No transcript available - play the recording to hear what was asked"}
    for service in business.get("services") or []:
        if str(service).strip() and str(service).lower() in text:
            return {"note": f"Asked about {service}"[:300]}
    if any(w in text for w in PRICE_WORDS):
        return {"note": "Asked about pricing"}
    if any(w in text for w in AVAILABILITY_WORDS):
        return {"note": "Asked about availability or booking a slot"}
    return {"note": "Called in with a general enquiry"}


# 4. The run -----------------------------------------------------------------------
def write_call_note(business: dict, transcript: str) -> AIResult[CallNote]:
    prompt = (f"Business: {business['name']} ({business['industry']}). "
             f"Services: {', '.join(map(str, business.get('services') or [])) or 'not listed'}.\n"
             f"Call transcript:\n{(transcript or '').strip()[:3000]}\n")
    return get_llm().ask(system=SYSTEM, prompt=prompt, schema=CallNote, max_tokens=120,
                         mock=lambda: mock_call_note(business, transcript))
