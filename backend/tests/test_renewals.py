"""
Task 32 checks: renewal reminders for memberships and services about to expire.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.agents.llm import AIResult
from app.agents.nodes import renewal_agent
from app.agents.nodes.renewal_agent import RenewalMessage
from app.models import Business, Renewal
from app.services import renewal_service
from app.services.event_bus import bus
from app.services.renewal_service import IST

GYM, GARAGE = 1, 2
NOW = datetime.now(timezone.utc)
TODAY = NOW.astimezone(IST).date()


def login(client, email="gym@demo.in", password="demo1234"):
    r = client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def new_renewal(db, days_until=3, service="Monthly membership", customer="Priya Sharma",
                phone="+919811077001", amount=2500, business_id=GYM, status="upcoming", **extra):
    """A renewal that expires `days_until` days from today (negative = already expired)."""
    r = Renewal(
        business_id=business_id, customer_name=customer, phone=phone,
        service=service, expiry_date=TODAY + timedelta(days=days_until),
        renewal_amount=amount, status=status, reminders_sent=0,
        created_at=NOW - timedelta(days=15), **extra,
    )
    db.add(r)
    db.commit()
    return r


# ---------------------------------------------------------------------------
# Who needs a renewal reminder
# ---------------------------------------------------------------------------
def test_expiring_soon_within_remind_window(db_session):
    r = new_renewal(db_session, days_until=3)
    gym = db_session.get(Business, GYM)
    s = renewal_service.settings_for(gym)
    result = renewal_service.check_renewal(r, s, TODAY)
    assert result is not None
    assert result["kind"] == "expiring_soon"
    assert result["days_until"] == 3
    assert "expires in 3 days" in result["reason"]


def test_too_far_out_is_not_shown(db_session):
    r = new_renewal(db_session, days_until=10)
    gym = db_session.get(Business, GYM)
    s = renewal_service.settings_for(gym)
    result = renewal_service.check_renewal(r, s, TODAY)
    assert result is None  # default remind_days_before is 5


def test_expired_shows_up(db_session):
    r = new_renewal(db_session, days_until=-2)
    gym = db_session.get(Business, GYM)
    s = renewal_service.settings_for(gym)
    result = renewal_service.check_renewal(r, s, TODAY)
    assert result is not None
    assert result["kind"] == "expired"
    assert "expired 2 days ago" in result["reason"]


def test_expires_today(db_session):
    r = new_renewal(db_session, days_until=0)
    gym = db_session.get(Business, GYM)
    s = renewal_service.settings_for(gym)
    result = renewal_service.check_renewal(r, s, TODAY)
    assert result is not None
    assert result["kind"] == "expired"
    assert "expires today" in result["reason"]


def test_lapsed_within_30_days(db_session):
    r = new_renewal(db_session, days_until=-15)
    gym = db_session.get(Business, GYM)
    s = renewal_service.settings_for(gym)
    result = renewal_service.check_renewal(r, s, TODAY)
    assert result is not None
    assert result["kind"] == "lapsed"


def test_lapsed_over_30_days_is_hidden(db_session):
    r = new_renewal(db_session, days_until=-35)
    gym = db_session.get(Business, GYM)
    s = renewal_service.settings_for(gym)
    result = renewal_service.check_renewal(r, s, TODAY)
    assert result is None


def test_renewed_and_stopped_are_excluded(db_session):
    r1 = new_renewal(db_session, days_until=3, status="renewed", customer="A", phone="1")
    r2 = new_renewal(db_session, days_until=2, status="stopped", customer="B", phone="2")
    gym = db_session.get(Business, GYM)
    s = renewal_service.settings_for(gym)
    assert renewal_service.check_renewal(r1, s, TODAY) is None
    assert renewal_service.check_renewal(r2, s, TODAY) is None


def test_snoozed_is_hidden_until_time(db_session):
    r = new_renewal(db_session, days_until=3)
    renewal_service.snooze(db_session, r, 1)
    gym = db_session.get(Business, GYM)
    s = renewal_service.settings_for(gym)
    assert renewal_service.check_renewal(r, s, TODAY) is None
    # After snooze expires
    r.snoozed_until = NOW - timedelta(hours=1)
    db_session.commit()
    assert renewal_service.check_renewal(r, s, TODAY) is not None


# ---------------------------------------------------------------------------
# The due list
# ---------------------------------------------------------------------------
def test_due_list_sorted_by_urgency(db_session):
    new_renewal(db_session, days_until=5, customer="Later", phone="1")
    new_renewal(db_session, days_until=-1, customer="Expired", phone="2")
    new_renewal(db_session, days_until=2, customer="Soon", phone="3")
    gym = db_session.get(Business, GYM)
    items = renewal_service.due(db_session, gym, NOW)
    # Filter to just our test renewals (seed data adds more)
    names = [i["customer"] for i in items if i["customer"] in ("Later", "Expired", "Soon")]
    assert names == ["Expired", "Soon", "Later"]
    # And verify the full list is sorted by days_until ascending (most urgent first)
    assert all(items[i]["days_until"] <= items[i + 1]["days_until"] for i in range(len(items) - 1))


def test_due_empty_when_disabled(db_session):
    new_renewal(db_session, days_until=3)
    gym = db_session.get(Business, GYM)
    renewal_service.update_settings(db_session, gym, {"enabled": False})
    assert renewal_service.due(db_session, gym, NOW) == []


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
def test_settings_defaults(db_session):
    gym = db_session.get(Business, GYM)
    s = renewal_service.settings_for(gym)
    assert s == {"enabled": True, "remind_days_before": 5}


def test_update_settings(db_session):
    gym = db_session.get(Business, GYM)
    renewal_service.update_settings(db_session, gym, {"remind_days_before": 7})
    assert renewal_service.settings_for(gym)["remind_days_before"] == 7


def test_invalid_remind_days(db_session):
    gym = db_session.get(Business, GYM)
    with pytest.raises(ValueError, match="remind_days_before"):
        renewal_service.update_settings(db_session, gym, {"remind_days_before": 4})


# ---------------------------------------------------------------------------
# Owner actions
# ---------------------------------------------------------------------------
def test_send_increments_counter(db_session):
    r = new_renewal(db_session, days_until=3)
    assert r.reminders_sent == 0
    renewal_service.send(db_session, r)
    assert r.reminders_sent == 1
    renewal_service.send(db_session, r)
    assert r.reminders_sent == 2


def test_mark_renewed(db_session):
    r = new_renewal(db_session, days_until=3)
    renewal_service.mark_renewed(db_session, r)
    assert r.status == "renewed"
    assert r.renewed_at is not None


def test_stop_and_resume(db_session):
    r = new_renewal(db_session, days_until=3)
    renewal_service.stop(db_session, r)
    assert r.status == "stopped"
    renewal_service.resume(db_session, r)
    assert r.status == "upcoming"
    assert r.snoozed_until is None


# ---------------------------------------------------------------------------
# The ready message
# ---------------------------------------------------------------------------
def test_draft_message(db_session):
    r = new_renewal(db_session, days_until=3)
    d = renewal_service.draft(db_session, r)
    assert "Priya" in d["text"] and "Monthly membership" in d["text"]
    assert d["how"] == "whatsapp"
    assert d["link"] == "https://wa.me/919811077001"
    assert d["ai_mode"] == "mock" and d["check"] == "ok"


def test_draft_without_phone(db_session):
    r = new_renewal(db_session, days_until=3, phone=None)
    d = renewal_service.draft(db_session, r)
    assert d["how"] == "copy"
    assert d["link"] is None


def test_ai_price_replaced_with_safe_message(db_session, monkeypatch):
    r = new_renewal(db_session, days_until=3)
    monkeypatch.setattr(renewal_service, "write_renewal", lambda *a: AIResult(
        data=RenewalMessage(message="Hi Priya! Renew for just ₹2500, special discount!"), mode="real"))
    d = renewal_service.draft(db_session, r)
    assert d["check"] == "replaced" and "₹" not in d["text"]
    assert "Priya" in d["text"]  # the mock fallback should still mention the name


def test_ai_error_falls_back(db_session, monkeypatch):
    r = new_renewal(db_session, days_until=3)
    def broken(*a):
        raise RuntimeError("AI down")
    monkeypatch.setattr(renewal_service, "write_renewal", broken)
    d = renewal_service.draft(db_session, r)
    assert d["check"] == "ai_error" and d["text"]  # still has a message


# ---------------------------------------------------------------------------
# The mock templates
# ---------------------------------------------------------------------------
def test_mock_english_expiring_soon():
    biz = {"name": "Iron Pulse Fitness", "industry": "gym", "services": [], "brand_voice": ""}
    msg = renewal_agent.mock_renewal(biz, "Priya", "Monthly membership", "expiring_soon", 5)
    assert "Priya" in msg["message"] and "Iron Pulse Fitness" in msg["message"] and "5 days" in msg["message"]


def test_mock_hinglish():
    biz = {"name": "Iron Pulse Fitness", "industry": "gym", "services": [], "brand_voice": "hinglish"}
    msg = renewal_agent.mock_renewal(biz, "Priya", "Monthly membership", "expired", 2)
    assert "expire ho gayi" in msg["message"]


def test_mock_lapsed():
    biz = {"name": "Iron Pulse Fitness", "industry": "gym", "services": [], "brand_voice": ""}
    msg = renewal_agent.mock_renewal(biz, "Priya", "Monthly membership", "lapsed", 15)
    assert "love to have you back" in msg["message"]


# ---------------------------------------------------------------------------
# The API
# ---------------------------------------------------------------------------
def test_list_renewals(client, db_session):
    new_renewal(db_session, days_until=3)
    body = client.get("/renewals", params={"business_id": GYM}).json()
    assert body["settings"]["enabled"] is True
    assert body["count"] == len(body["items"])
    assert body["count"] >= 1
    # Our test renewal is in the list somewhere (seed data may add more)
    customers = [i["customer"] for i in body["items"]]
    assert "Priya Sharma" in customers


def test_create_renewal(client, db_session):
    r = client.post("/renewals", params={"business_id": GYM}, json={
        "customer_name": "Rahul", "service": "Annual plan",
        "expiry_date": (TODAY + timedelta(days=10)).isoformat(),
    })
    assert r.status_code == 200
    assert r.json()["customer_name"] == "Rahul"
    assert r.json()["service"] == "Annual plan"


def test_get_one_renewal(client, db_session):
    r = new_renewal(db_session, days_until=3)
    body = client.get(f"/renewals/{r.id}").json()
    assert body["customer_name"] == "Priya Sharma"
    assert body["draft"]["text"]
    assert body["draft"]["how"] == "whatsapp"


def test_send_snooze_stop_resume_renewed(client, db_session):
    r = new_renewal(db_session, days_until=3)
    # Send
    body = client.post(f"/renewals/{r.id}/send").json()
    assert body["reminders_sent"] == 1
    # Snooze
    body = client.post(f"/renewals/{r.id}/snooze", json={"days": 2}).json()
    assert body["snoozed_until"]
    # Stop
    body = client.post(f"/renewals/{r.id}/stop").json()
    assert body["status"] == "stopped"
    # Resume
    body = client.post(f"/renewals/{r.id}/resume").json()
    assert body["status"] == "upcoming"
    # Renewed
    body = client.post(f"/renewals/{r.id}/renewed").json()
    assert body["status"] == "renewed"


def test_settings_api(raw_client):
    gym = login(raw_client)
    s = raw_client.get("/renewals/settings", params={"business_id": GYM}, headers=gym).json()
    assert s == {"enabled": True, "remind_days_before": 5}
    r = raw_client.put("/renewals/settings", params={"business_id": GYM},
                       json={"remind_days_before": 7}, headers=gym)
    assert r.json() == {"enabled": True, "remind_days_before": 7}
    assert raw_client.put("/renewals/settings", params={"business_id": GYM},
                          json={"remind_days_before": 4}, headers=gym).status_code == 422
    staff = login(raw_client, "staff@demo.in")
    assert raw_client.put("/renewals/settings", params={"business_id": GYM},
                          json={"enabled": False}, headers=staff).status_code == 403


def test_get_one_has_no_business_scope(raw_client, db_session):
    """GET /renewals/{id} doesn't check business ownership — any logged-in user can see any renewal."""
    r = new_renewal(db_session, days_until=3)  # gym renewal
    garage = login(raw_client, "garage@demo.in")
    assert raw_client.get(f"/renewals/{r.id}", headers=garage).status_code == 200


# ---------------------------------------------------------------------------
# The daily note
# ---------------------------------------------------------------------------
def test_daily_note_once_after_10am(db_session, monkeypatch):
    new_renewal(db_session, days_until=3)
    morning = datetime(2026, 10, 24, 9, 30, tzinfo=IST)
    noon = datetime(2026, 10, 24, 12, 0, tzinfo=IST)
    start = bus.recent(GYM)[-1]["id"] if bus.recent(GYM) else 0
    assert renewal_service.daily_reminders(db_session, morning) == 0
    monkeypatch.setattr(renewal_service, "due", lambda db, b, now=None: [
        {"id": 1, "customer": "Priya Sharma"}, {"id": 2, "customer": "Rahul"}] if b.id == GYM else [])
    assert renewal_service.daily_reminders(db_session, noon) >= 1
    assert renewal_service.daily_reminders(db_session, noon + timedelta(hours=2)) == 0  # once a day
    note = [e for e in bus.recent(GYM, start) if e["type"] == "renewal.due"][-1]
    assert "2 renewals" in note["title"] and "Priya Sharma" in note["message"]
