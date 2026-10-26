"""
Intake Agent - the receptionist who reads a new message and fills in the lead card.

From a message like
    "Hi I'm Rahul from Dwarka, need ceramic coating for my Creta this Saturday"
it works out:
    customer_name = "Rahul"           area    = "Dwarka"
    service       = "Ceramic coating" (picked from THIS business's own service list)
    details       = {"car_model": "Hyundai Creta", "preferred_day": "Saturday"}
    language      = "english"         summary = "Wants ceramic coating on Creta, Saturday"

It knows what to look for in each industry: a gym needs batch timing and
fitness goal, a car shop needs the car model, a clinic needs a preferred day...

Same 4-part pattern as quick_read.py: form → brief → mock rules → run.
"""

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.agents.llm import AIResult, get_llm
from app.agents.quick_read import mock_quick_read

# What extra details matter for each industry (key: what it means)
DETAILS_TO_LOOK_FOR: dict[str, dict[str, str]] = {
    "gym": {"batch": "morning/evening timing", "goal": "fitness goal, e.g. weight loss"},
    "salon": {"preferred_day": "day they want to come", "preferred_time": "morning/afternoon/evening"},
    "clinic": {"preferred_day": "day they want to come", "preferred_time": "morning/afternoon/evening",
               "problem": "symptom or problem, e.g. tooth pain"},
    "restaurant": {"party_size": "number of people", "date": "date of visit", "occasion": "birthday, party..."},
    "cafe": {"party_size": "number of people", "date": "date of visit", "occasion": "birthday, party..."},
    "coaching": {"subject": "subject or course", "class_level": "class, exam or level"},
    "real_estate": {"budget": "budget", "property_type": "flat, plot, shop...", "locality": "preferred area"},
    "auto_service": {"car_model": "car make and model", "preferred_day": "day they want to come"},
    "car_detailing": {"car_model": "car make and model", "preferred_day": "day they want to come"},
    "retail": {"product": "product they ask about", "quantity": "how many"},
    "other": {},
}


# 1. The form ----------------------------------------------------------------------
class IntakeAnswer(BaseModel):
    customer_name: Optional[str] = Field(default=None, description="Customer's name ONLY if they say it, else null.")
    area: Optional[str] = Field(default=None, description="Locality/area they mention, e.g. Dwarka, else null.")
    service: Optional[str] = Field(
        default=None, description="The service they want, copied EXACTLY from the business's service list, or null if unclear."
    )
    details: dict[str, str] = Field(
        default_factory=dict, description="Extra details from the list given. Only include details actually mentioned."
    )
    language: Literal["english", "hindi", "hinglish", "other"]
    summary: str = Field(max_length=150, description="One short line: what the customer wants.")


# 2. The brief ---------------------------------------------------------------------
SYSTEM = (
    "You are the intake assistant for a small local business in India. A customer has sent a message "
    "(English, Hindi or Hinglish). Fill in the lead card. Rules:\n"
    "- Only use facts the customer actually wrote. Never guess or invent.\n"
    "- For 'service', choose the closest match from the business's service list, copied exactly. "
    "If none fits clearly, use null.\n"
    "- For 'details', only use the detail keys you are given."
)


def build_prompt(message: str, business_name: str, industry: str, services: list[str]) -> str:
    wanted = DETAILS_TO_LOOK_FOR.get(industry, {})
    detail_lines = "\n".join(f"  - {key}: {meaning}" for key, meaning in wanted.items()) or "  (none)"
    return (
        f"Business: {business_name} (industry: {industry})\n"
        f"Service list: {', '.join(services) or '(not given)'}\n"
        f"Detail keys to look for:\n{detail_lines}\n\n"
        f"Customer message:\n\"\"\"\n{message}\n\"\"\""
    )


# 3. The mock: word-spotting rules -------------------------------------------------
CAR_MODELS = {
    "creta": "Hyundai Creta", "venue": "Hyundai Venue", "i20": "Hyundai i20", "verna": "Hyundai Verna",
    "swift": "Maruti Swift", "baleno": "Maruti Baleno", "brezza": "Maruti Brezza", "dzire": "Maruti Dzire",
    "ertiga": "Maruti Ertiga", "nexon": "Tata Nexon", "harrier": "Tata Harrier", "seltos": "Kia Seltos",
    "sonet": "Kia Sonet", "xuv700": "Mahindra XUV700", "thar": "Mahindra Thar", "scorpio": "Mahindra Scorpio",
    "fortuner": "Toyota Fortuner", "innova": "Toyota Innova", "city": "Honda City",
}
DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "today", "tomorrow")
TIMES = {"morning": "morning", "subah": "morning", "afternoon": "afternoon", "evening": "evening", "shaam": "evening", "night": "evening"}
GOALS = {"weight loss": "weight loss", "fat loss": "weight loss", "muscle": "muscle gain", "bulk": "muscle gain",
         "flexib": "flexibility", "fitness": "general fitness"}
AREAS = ("Rajouri Garden", "Kirti Nagar", "Janakpuri", "Dwarka", "Karol Bagh", "Punjabi Bagh", "Moti Nagar",
         "Tilak Nagar", "Patel Nagar", "Paschim Vihar", "Vikaspuri", "Uttam Nagar", "Laxmi Nagar", "Saket",
         "Lajpat Nagar", "Rohini", "Pitampura", "Noida", "Gurgaon", "Gurugram")
NAME_PATTERN = re.compile(r"\b(?:i am|i'm|im|my name is|this is|main)\s+([a-z]{3,15})\b", re.IGNORECASE)
NOT_NAMES = {"looking", "interested", "from", "here", "planning", "trying", "asking", "new", "not", "very", "also"}


def _match_service(message: str, services: list[str]) -> Optional[str]:
    """Find which of the business's services the message mentions."""
    lower = message.lower()
    for service in services:                                  # whole name first: "ceramic coating"
        if service.lower() in lower:
            return service
    for service in services:                                  # then any key word: "coating"
        words = [w for w in re.findall(r"[a-z]+", service.lower()) if len(w) > 3]
        if any(w in lower for w in words):
            return service
    return None


def mock_intake(message: str, industry: str, services: list[str]) -> dict:
    lower = message.lower()
    wanted = DETAILS_TO_LOOK_FOR.get(industry, {})
    details: dict[str, str] = {}

    if "car_model" in wanted:
        for word, model in CAR_MODELS.items():
            if re.search(rf"\b{word}\b", lower):
                details["car_model"] = model
                break
    if "preferred_day" in wanted:
        day = next((d for d in DAYS if d in lower), None)
        if day:
            details["preferred_day"] = day.capitalize()
    for key in ("preferred_time", "batch"):
        if key in wanted:
            time_of_day = next((v for k, v in TIMES.items() if k in lower), None)
            if time_of_day:
                details[key] = time_of_day
    if "goal" in wanted:
        goal = next((v for k, v in GOALS.items() if k in lower), None)
        if goal:
            details["goal"] = goal
    if "problem" in wanted and "pain" in lower:
        details["problem"] = "pain"

    name_match = NAME_PATTERN.search(message)
    name = name_match.group(1).capitalize() if name_match and name_match.group(1).lower() not in NOT_NAMES else None
    area = next((a for a in AREAS if a.lower() in lower), None)
    quick = mock_quick_read(message)

    return {
        "customer_name": name, "area": area, "service": _match_service(message, services),
        "details": details, "language": quick["language"], "summary": quick["summary"],
    }


# 4. The run -----------------------------------------------------------------------
def run_intake(message: str, business_name: str, industry: str, services: list[str]) -> AIResult[IntakeAnswer]:
    result = get_llm().ask(
        system=SYSTEM,
        prompt=build_prompt(message, business_name, industry, services),
        schema=IntakeAnswer,
        mock=lambda: mock_intake(message, industry, services),
        max_tokens=500,
    )
    # Tidy-up: make the service match the business's list exactly (e.g. "zumba" → "Zumba"),
    # and drop any detail keys we didn't ask for.
    answer = result.data
    if answer.service:
        exact = next((s for s in services if s.lower() == answer.service.lower()), None)
        answer.service = exact or _match_service(answer.service, services) or answer.service
    allowed = DETAILS_TO_LOOK_FOR.get(industry, {})
    answer.details = {k: v for k, v in answer.details.items() if k in allowed and v}
    return result
