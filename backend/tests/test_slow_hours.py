"""
Task 33 checks: fill your empty hours (slow time slots + inviting past customers back).
"""

from datetime import date, datetime, time, timedelta, timezone

import pytest

from app.agents.llm import AIResult
from app.agents.nodes import offer_agent
from app.agents.nodes.offer_agent import OfferMessage
from app.models import Business, Lead
from app.services import slow_hours_service
from app.services.slow_hours_service import IST

GYM = 1
NOW = datetime.now(timezone.utc)


def login(client, email="gym@demo.in", password="demo1234"):
    r = client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def new_lead(db, business_id=GYM, **extra):
    """A lead with sensible defaults, overridden by whatever the test passes in."""
    defaults = dict(source="whatsapp", status="new", created_at=NOW)
    defaults.update(extra)
    lead = Lead(business_id=business_id, **defaults)
    db.add(lead)
    db.commit()
    return lead


def at_ist(weekday: int, hour: int, now: datetime = NOW) -> datetime:
    """A UTC datetime for the most recent `weekday` (0=Monday) at `hour` o'clock IST."""
    local_now = now.astimezone(IST)
    back = (local_now.weekday() - weekday) % 7
    target_date = local_now.date() - timedelta(days=back)
    local = datetime.combine(target_date, time(hour, 0), tzinfo=IST)
    return local.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# Finding the slow times
# ---------------------------------------------------------------------------
def test_slow_windows_flags_a_quiet_block(db_session):
    gym = db_session.get(Business, GYM)
    for old in db_session.query(Lead).filter(Lead.business_id == GYM).all():
        db_session.delete(old)
    db_session.commit()

    # Busy at 10am IST every day except Sunday - Sunday should be flagged slow.
    for weekday in range(6):   # Monday..Saturday
        new_lead(db_session, created_at=at_ist(weekday, 10))
        new_lead(db_session, created_at=at_ist(weekday, 10))

    windows = slow_hours_service.slow_windows(db_session, gym)
    assert any(w["day"] == "Sunday" and w["hours"] == "9am-12pm" and w["enquiries"] == 0
              for w in windows)


def test_slow_windows_needs_enough_history(db_session):
    gym = db_session.get(Business, GYM)
    for old in db_session.query(Lead).filter(Lead.business_id == GYM).all():
        db_session.delete(old)
    db_session.commit()
    for _ in range(5):   # fewer than MIN_LEADS_NEEDED (10)
        new_lead(db_session, created_at=at_ist(0, 10))
    assert slow_hours_service.slow_windows(db_session, gym) == []


# ---------------------------------------------------------------------------
# Finding past customers to invite
# ---------------------------------------------------------------------------
def test_candidates_includes_old_customers_only(db_session):
    gym = db_session.get(Business, GYM)
    for old in db_session.query(Lead).filter(Lead.business_id == GYM, Lead.status == "won").all():
        db_session.delete(old)
    db_session.commit()

    old_customer = new_lead(db_session, status="won", won_at=NOW - timedelta(days=40),
                            name="Priya", phone="+919811000001", service="Gym membership")
    recent_customer = new_lead(db_session, status="won", won_at=NOW - timedelta(days=5),
                               name="Rahul", phone="+919811000002", service="Gym membership")

    result = slow_hours_service.candidates(db_session, gym)
    ids = {c["lead_id"] for c in result}
    assert old_customer.id in ids
    assert recent_customer.id not in ids   # bought too recently - too soon to invite back


def test_candidates_excludes_recently_invited(db_session):
    gym = db_session.get(Business, GYM)
    lead = new_lead(db_session, status="won", won_at=NOW - timedelta(days=60),
                    last_slow_offer_at=NOW - timedelta(days=5),
                    name="Priya", phone="+919811000003")
    result = slow_hours_service.candidates(db_session, gym)
    assert lead.id not in {c["lead_id"] for c in result}


def test_candidates_disabled_returns_nothing(db_session):
    gym = db_session.get(Business, GYM)
    slow_hours_service.update_settings(db_session, gym, {"enabled": False})
    assert slow_hours_service.candidates(db_session, gym) == []


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
def test_settings_defaults(db_session):
    gym = db_session.get(Business, GYM)
    assert slow_hours_service.settings_for(gym) == {"enabled": True, "min_days_since_won": 30}


def test_update_settings_rejects_out_of_range(db_session):
    gym = db_session.get(Business, GYM)
    with pytest.raises(ValueError):
        slow_hours_service.update_settings(db_session, gym, {"min_days_since_won": 2})


# ---------------------------------------------------------------------------
# The ready message and how to send it
# ---------------------------------------------------------------------------
def test_draft_message(db_session):
    lead = new_lead(db_session, status="won", won_at=NOW - timedelta(days=40),
                    name="Priya Sharma", phone="+919811077001", service="Gym membership")
    d = slow_hours_service.draft(db_session, lead, {"day": "Tuesday", "hours": "2pm-5pm"})
    assert "Priya" in d["text"]
    assert d["how"] == "whatsapp"
    assert d["link"] == "https://wa.me/919811077001"
    assert d["ai_mode"] == "mock" and d["check"] == "ok"


def test_draft_without_phone(db_session):
    lead = new_lead(db_session, status="won", won_at=NOW - timedelta(days=40),
                    name="Priya", phone=None)
    d = slow_hours_service.draft(db_session, lead, {"day": "Tuesday", "hours": "2pm-5pm"})
    assert d["how"] == "copy"
    assert d["link"] is None


def test_ai_price_replaced_with_safe_message(db_session, monkeypatch):
    lead = new_lead(db_session, status="won", won_at=NOW - timedelta(days=40),
                    name="Priya", phone="+919811077001")
    monkeypatch.setattr(slow_hours_service, "write_offer", lambda *a: AIResult(
        data=OfferMessage(message="Hi Priya! Come back for just ₹500 off, limited offer!"), mode="real"))
    d = slow_hours_service.draft(db_session, lead, {"day": "Tuesday", "hours": "2pm-5pm"})
    assert d["check"] == "replaced" and "₹" not in d["text"]
    assert "Priya" in d["text"]   # the mock fallback should still mention the name


def test_ai_error_falls_back(db_session, monkeypatch):
    lead = new_lead(db_session, status="won", won_at=NOW - timedelta(days=40), name="Priya")

    def broken(*a):
        raise RuntimeError("AI down")
    monkeypatch.setattr(slow_hours_service, "write_offer", broken)
    d = slow_hours_service.draft(db_session, lead, {"day": "Tuesday", "hours": "2pm-5pm"})
    assert d["check"] == "ai_error" and d["text"]   # still has a usable message


# ---------------------------------------------------------------------------
# Owner actions
# ---------------------------------------------------------------------------
def test_send_records_the_time(db_session):
    lead = new_lead(db_session, status="won", won_at=NOW - timedelta(days=40))
    assert lead.last_slow_offer_at is None
    slow_hours_service.send(db_session, lead, now=NOW)
    assert lead.last_slow_offer_at == NOW


def test_skip_also_records_the_time(db_session):
    lead = new_lead(db_session, status="won", won_at=NOW - timedelta(days=40))
    slow_hours_service.skip(db_session, lead, now=NOW)
    assert lead.last_slow_offer_at == NOW


# ---------------------------------------------------------------------------
# The mock messages (no AI needed)
# ---------------------------------------------------------------------------
def test_mock_offer_english():
    biz = {"name": "Iron Pulse Fitness", "industry": "gym", "services": [], "brand_voice": ""}
    msg = offer_agent.mock_offer(biz, "Priya", "Gym membership", "Tuesday", "2pm-5pm")
    assert "Priya" in msg["message"] and "Iron Pulse Fitness" in msg["message"]
    assert "Tuesday" in msg["message"]
    assert "₹" not in msg["message"]


def test_mock_offer_hinglish():
    biz = {"name": "Iron Pulse Fitness", "industry": "gym", "services": [], "brand_voice": "hinglish"}
    msg = offer_agent.mock_offer(biz, "Priya", "Gym membership", "Tuesday", "2pm-5pm")
    assert "khaali rehta hai" in msg["message"]


# ---------------------------------------------------------------------------
# The API
# ---------------------------------------------------------------------------
def test_overview_endpoint(client):
    r = client.get("/slow-hours", params={"business_id": GYM})
    assert r.status_code == 200
    body = r.json()
    assert "settings" in body and "slow_windows" in body and "candidates" in body


def test_settings_api(raw_client):
    gym = login(raw_client)
    s = raw_client.get("/slow-hours/settings", params={"business_id": GYM}, headers=gym).json()
    assert s == {"enabled": True, "min_days_since_won": 30}
    r = raw_client.put("/slow-hours/settings", params={"business_id": GYM},
                       json={"min_days_since_won": 45}, headers=gym)
    assert r.json() == {"enabled": True, "min_days_since_won": 45}
    assert raw_client.put("/slow-hours/settings", params={"business_id": GYM},
                          json={"min_days_since_won": 2}, headers=gym).status_code == 422
    staff = login(raw_client, "staff@demo.in")   # staff, not owner
    assert raw_client.put("/slow-hours/settings", params={"business_id": GYM},
                          json={"enabled": False}, headers=staff).status_code == 403
