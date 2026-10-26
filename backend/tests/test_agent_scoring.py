"""
Checks for the Scoring agent (Task 9).

The plan's test: a hot lead should score around 85,
a "just asking the price" lead should score low.
"""

from types import SimpleNamespace

import pytest

import app.agents.nodes.scoring_agent as scoring
from app.agents.llm import LLM
from app.agents.nodes.scoring_agent import LeadFacts, fixed_points, mock_intent, score_lead

HOT = LeadFacts(
    source="google", message="Hi I'm Rahul, need ceramic coating on my Creta today. Can I book a slot?",
    has_phone=True, has_name=True, service="Ceramic coating",
    details={"car_model": "Hyundai Creta", "preferred_day": "Today"},
    inbound_messages=2, sentiment="urgent", industry="car_detailing",
)
COLD = LeadFacts(
    source="instagram", message="just asking the price of zumba, maybe later",
    service="Zumba", sentiment="casual", industry="gym",
)


def test_hot_lead_scores_high():
    result = score_lead(HOT)
    assert 80 <= result.score <= 95, result.breakdown


def test_just_asking_price_scores_low():
    result = score_lead(COLD)
    assert result.score <= 30, result.breakdown


def test_score_always_between_1_and_100():
    worst = LeadFacts(source="facebook", message="for my friend, next year maybe, just checking")
    best = LeadFacts(source="referral", message="Book me, confirm the slot, sending address", has_phone=True,
                     has_name=True, service="X", details={"a": "1", "b": "2", "c": "3", "d": "4"},
                     inbound_messages=5, sentiment="urgent")
    assert 1 <= score_lead(worst).score <= 100
    assert score_lead(best).score == 100          # capped at 100


def test_breakdown_adds_up():
    result = score_lead(HOT)
    assert result.score == min(100, sum(result.breakdown.values()))
    assert result.breakdown["Source: Google (Search & Maps)"] == 20
    assert result.breakdown["Shared phone number"] == 10
    assert result.breakdown["Tone: urgent"] == 10


def test_better_sources_score_more():
    base = dict(message="price?", has_phone=True)
    referral = sum(fixed_points(LeadFacts(source="referral", **base)).values())
    google = sum(fixed_points(LeadFacts(source="google", **base)).values())
    instagram = sum(fixed_points(LeadFacts(source="instagram", **base)).values())
    assert referral > google > instagram


def test_every_platform_gets_source_points():
    from app.platforms import PLATFORMS
    for key in PLATFORMS:
        points = fixed_points(LeadFacts(source=key, message="hi"))
        assert any(k.startswith("Source:") and v > 0 for k, v in points.items()), key


def test_more_messages_more_points():
    one = sum(fixed_points(LeadFacts(source="whatsapp", message="hi", inbound_messages=1)).values())
    three = sum(fixed_points(LeadFacts(source="whatsapp", message="hi", inbound_messages=3)).values())
    assert three - one == 10


@pytest.mark.parametrize("message, intent", [
    ("Can I book an appointment for Saturday?", "high"),
    ("What is your address? I'll visit tomorrow", "high"),
    ("What are the fees?", "medium"),
    ("Just checking prices, maybe later", "low"),
    ("Asking for my friend", "low"),
])
def test_mock_intent(message, intent):
    assert mock_intent(message)["intent"] == intent


def test_reason_is_readable():
    reason = score_lead(HOT).reason
    assert "Main factors" in reason and "Source" in reason


# ----- Real-mode path with a fake Claude ----------------------------------------------------
def test_real_ai_adjustment_is_used(monkeypatch):
    answer = {"intent": "low", "adjustment": -15, "reason": "Comparing prices for later."}
    fake = SimpleNamespace(create=lambda **kw: SimpleNamespace(
        content=[SimpleNamespace(type="tool_use", input=answer)],
        usage=SimpleNamespace(input_tokens=1, output_tokens=1)))
    fake.messages = fake
    monkeypatch.setattr(scoring, "get_llm", lambda: LLM(client=fake, enabled=True))
    result = score_lead(HOT)
    assert result.ai.mode == "real"
    assert result.breakdown["AI: buying intent low"] == -15


def test_ai_cannot_go_beyond_limits(monkeypatch):
    """If the AI tries +50, the form rules reject it and the safe mock answer is used."""
    answer = {"intent": "high", "adjustment": 50, "reason": "!!!"}
    fake = SimpleNamespace(create=lambda **kw: SimpleNamespace(
        content=[SimpleNamespace(type="tool_use", input=answer)],
        usage=SimpleNamespace(input_tokens=1, output_tokens=1)))
    fake.messages = fake
    monkeypatch.setattr(scoring, "get_llm", lambda: LLM(client=fake, enabled=True))
    result = score_lead(COLD)
    assert result.ai.mode == "fallback"
    assert all(v <= 25 for v in result.breakdown.values())


# ----- Endpoints ----------------------------------------------------------------------------
def test_read_message_includes_score(client):
    body = client.post("/ai/read-message", json={
        "business_id": 2, "source": "google",
        "message": "Hi I'm Rahul, need ceramic coating on my Creta today. Can I book a slot?",
    }).json()
    assert body["score"]["score"] >= 70
    assert body["score"]["breakdown"]["Starting points"] == 10


def test_read_lead_includes_score(client):
    body = client.post("/ai/read-lead/3").json()
    assert 1 <= body["score"]["score"] <= 100
