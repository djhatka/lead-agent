"""
Checks for the Intake and Tone agents (Task 8).

Mostly in free mock mode. A fake Claude checks the real-mode path:
that the agents send the right information and tidy up the AI's answer.
"""

from types import SimpleNamespace

import pytest

import app.agents.llm as llm_module
from app.agents.llm import LLM
from app.agents.nodes.intake_agent import build_prompt, mock_intake, run_intake
from app.agents.nodes.sentiment_agent import mock_tone, run_tone

GYM = ["Gym membership", "Zumba", "Personal training", "Yoga", "CrossFit"]
DETAILING = ["Ceramic coating", "PPF", "Interior deep cleaning", "Car wash & wax", "Paint correction"]
CLINIC = ["Dental cleaning", "Root canal", "Teeth whitening", "Braces", "Dental implant"]


# ----- Tone: the 5+ sample messages from the plan -------------------------------------------
@pytest.mark.parametrize("message, expected", [
    ("Need ceramic coating for my Creta today, can you take it?", "urgent"),
    ("Severe tooth pain since last night, can I come?", "urgent"),
    ("Urgent - wedding this weekend, need PPF", "urgent"),
    ("What are the fees for Zumba?", "casual"),
    ("Do you have parking near the gym?", "casual"),
    ("Called twice and nobody picked up. Still want details", "frustrated"),
    ("Sent 3 messages, no reply. Want a quote", "frustrated"),
    ("Hello??? anyone there???", "frustrated"),
    ("Booked online but nobody confirmed, need it TODAY", "frustrated"),   # frustrated beats urgent
])
def test_tone_labels(message, expected):
    assert mock_tone(message)["sentiment"] == expected


def test_tone_explains_itself():
    answer = mock_tone("Called twice and nobody picked up")
    assert "nobody" in answer["signals"] or "called twice" in answer["signals"]
    assert answer["reason"]


def test_tone_uses_earlier_messages():
    """'hello?' alone is casual, but after being ignored it's frustrated."""
    assert run_tone("hello?").data.sentiment == "casual"
    later = run_tone("hello?", earlier_messages=["Price for PPF?", "Still waiting for a reply"])
    assert later.data.sentiment == "frustrated"


# ----- Intake ---------------------------------------------------------------------------------
def test_intake_car_detailing():
    a = mock_intake("Hi I'm Rahul from Dwarka, need ceramic coating for my Creta this Saturday",
                    "car_detailing", DETAILING)
    assert a["customer_name"] == "Rahul"
    assert a["area"] == "Dwarka"
    assert a["service"] == "Ceramic coating"
    assert a["details"] == {"car_model": "Hyundai Creta", "preferred_day": "Saturday"}


def test_intake_hinglish_gym():
    a = mock_intake("Bhai zumba ka evening batch hai? Weight loss karna hai", "gym", GYM)
    assert a["service"] == "Zumba"
    assert a["details"] == {"batch": "evening", "goal": "weight loss"}
    assert a["language"] == "hinglish"


def test_intake_clinic():
    a = mock_intake("Severe pain, need root canal tomorrow morning", "clinic", CLINIC)
    assert a["service"] == "Root canal"
    assert a["details"] == {"preferred_day": "Tomorrow", "preferred_time": "morning", "problem": "pain"}


def test_intake_does_not_invent():
    a = mock_intake("Hello, are you open on Sundays?", "gym", GYM)
    assert a["customer_name"] is None and a["service"] is None and a["area"] is None


def test_intake_ignores_details_of_other_industries():
    a = mock_intake("Zumba for my Creta?", "gym", GYM)
    assert "car_model" not in a["details"]


def test_prompt_contains_business_info():
    prompt = build_prompt("hi", "Iron Pulse Fitness", "gym", GYM)
    assert "Iron Pulse Fitness" in prompt and "Personal training" in prompt and "batch" in prompt


# ----- Real-mode path with a fake Claude ----------------------------------------------------
class FakeClaude:
    def __init__(self, answer):
        self.answer, self.messages, self.calls = answer, self, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="tool_use", input=self.answer)],
                               usage=SimpleNamespace(input_tokens=200, output_tokens=60))


@pytest.fixture
def fake_real_ai(monkeypatch):
    """Swap the shared connector for one that 'calls' a fake Claude."""
    def use(answer):
        fake = FakeClaude(answer)
        monkeypatch.setattr(llm_module, "get_llm", lambda: LLM(client=fake, enabled=True))
        import app.agents.nodes.intake_agent as intake
        import app.agents.nodes.sentiment_agent as tone
        monkeypatch.setattr(intake, "get_llm", lambda: LLM(client=fake, enabled=True))
        monkeypatch.setattr(tone, "get_llm", lambda: LLM(client=fake, enabled=True))
        return fake
    return use


def test_real_intake_answer_is_tidied(fake_real_ai):
    fake = fake_real_ai({
        "customer_name": "Priya", "area": None, "service": "zumba",          # wrong capital letters
        "details": {"batch": "evening", "car_model": "Swift"},               # car_model not asked for a gym
        "language": "english", "summary": "Wants evening Zumba",
    })
    result = run_intake("Evening zumba please, Priya here", "Iron Pulse Fitness", "gym", GYM)
    assert result.mode == "real"
    assert result.data.service == "Zumba"                                   # matched to the real list
    assert result.data.details == {"batch": "evening"}                      # extra key removed
    assert "Iron Pulse Fitness" in fake.calls[0]["messages"][0]["content"]  # business info was sent


def test_real_tone_answer(fake_real_ai):
    fake_real_ai({"sentiment": "urgent", "confidence": "high", "reason": "Needs it today.", "signals": ["today"]})
    result = run_tone("need it today")
    assert result.mode == "real" and result.data.sentiment == "urgent"


# ----- Endpoints ----------------------------------------------------------------------------
def test_read_message_endpoint(client):
    r = client.post("/ai/read-message", json={
        "business_id": 2,
        "message": "Hi I'm Rahul from Dwarka. Sent 3 messages, no reply! Need ceramic coating on my Creta this Saturday",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["intake"]["service"] == "Ceramic coating"
    assert body["intake"]["details"]["car_model"] == "Hyundai Creta"
    assert body["tone"]["sentiment"] == "frustrated"
    assert body["tone_run"]["mode"] == "mock"


def test_read_lead_endpoint(client):
    r = client.post("/ai/read-lead/1")
    assert r.status_code == 200
    assert r.json()["tone"]["sentiment"] in ("urgent", "casual", "frustrated")


def test_read_message_unknown_business(client):
    assert client.post("/ai/read-message", json={"business_id": 999, "message": "hi"}).status_code == 404
