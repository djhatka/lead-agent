"""
Task 28 checks: hot-lead alerts on the owner's own phone (WhatsApp).
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.models import Business, OwnerAlert
from app.services import alerts_service
from app.services.alerts_service import IST
from app.services.messenger import MockMessenger, PlatformMessenger, SendError, alert_messenger

URGENT = "Severe tooth pain, need root canal today. Can I get an appointment now?"


def login(client, email="clinic@demo.in", password="demo1234"):
    r = client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def set_alerts(client, headers, business_id=3, **body):
    r = client.put("/alerts/settings", params={"business_id": business_id}, json=body, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def hot_walk_in(client, headers, business_id=3, name="Meera"):
    lead = client.post("/leads", json={"business_id": business_id, "source": "walk_in", "name": name,
                                       "first_message": URGENT}, headers=headers).json()
    assert client.get(f"/leads/{lead['id']}", headers=headers).json()["analysis"]["priority"] == "hot"
    return lead


@pytest.fixture(autouse=True)
def clean_outbox():
    MockMessenger.sent.clear()
    yield
    MockMessenger.sent.clear()


# ---------------------------------------------------------------------------
# The settings card
# ---------------------------------------------------------------------------
def test_settings_start_empty_and_save(raw_client):
    clinic = login(raw_client)
    start = raw_client.get("/alerts/settings", params={"business_id": 3}, headers=clinic).json()
    assert start == {"phone": None, "hot_leads": True, "quiet_hours": False, "sender": "practice", "recent": []}
    saved = set_alerts(raw_client, clinic, phone="98111 22233", quiet_hours=True)
    assert saved["phone"] == "+919811122233" and saved["quiet_hours"] is True and saved["hot_leads"] is True
    kept = set_alerts(raw_client, clinic, hot_leads=False)                  # phone not sent → kept
    assert kept["phone"] == "+919811122233" and kept["hot_leads"] is False


def test_rules_for_the_phone(raw_client):
    clinic = login(raw_client)
    bad = raw_client.put("/alerts/settings", params={"business_id": 3}, json={"phone": "12345"}, headers=clinic)
    assert bad.status_code == 422
    business = raw_client.get("/businesses/3", headers=clinic).json()
    own_number = raw_client.put("/alerts/settings", params={"business_id": 3}, json={"phone": business["phone"]},
                                headers=clinic)
    assert own_number.status_code == 422 and "own WhatsApp number" in own_number.json()["detail"]
    staff = login(raw_client, "staff@demo.in")
    assert raw_client.put("/alerts/settings", params={"business_id": 1}, json={"hot_leads": False},
                          headers=staff).status_code == 403
    assert raw_client.get("/alerts/settings", params={"business_id": 3}, headers=staff).status_code == 404


def test_test_alert(raw_client):
    clinic = login(raw_client)
    assert raw_client.post("/alerts/test", params={"business_id": 3}, headers=clinic).status_code == 422   # no phone yet
    set_alerts(raw_client, clinic, phone="9811122233")
    alert = raw_client.post("/alerts/test", params={"business_id": 3}, headers=clinic).json()
    assert alert["status"] == "sent" and alert["sent_by"] == "practice"
    assert MockMessenger.sent[-1]["phone"] == "+919811122233" and "SmileCare" in MockMessenger.sent[-1]["text"]


# ---------------------------------------------------------------------------
# Hot leads
# ---------------------------------------------------------------------------
def test_hot_lead_alerts_the_owner_once(raw_client, db_session):
    clinic = login(raw_client)
    set_alerts(raw_client, clinic, phone="9811122233")
    lead = hot_walk_in(raw_client, clinic)
    alerts = raw_client.get("/alerts/settings", params={"business_id": 3}, headers=clinic).json()["recent"]
    assert len(alerts) == 1 and alerts[0]["lead_id"] == lead["id"] and alerts[0]["status"] == "sent"
    text = MockMessenger.sent[-1]["text"]
    assert "Meera (Walk-in)" in text and "score" in text and f"/leads/{lead['id']}" in text
    raw_client.post(f"/leads/{lead['id']}/analyze", headers=clinic)                 # re-scored: no second alert
    assert db_session.scalar(select(func.count(OwnerAlert.id)).where(OwnerAlert.lead_id == lead["id"])) == 1


def test_no_alert_without_a_phone_or_when_off(raw_client, db_session):
    clinic = login(raw_client)
    hot_walk_in(raw_client, clinic)                                                 # no phone yet
    set_alerts(raw_client, clinic, phone="9811122233", hot_leads=False)
    hot_walk_in(raw_client, clinic, name="Kiran")                                   # alerts turned off
    assert db_session.scalar(select(func.count(OwnerAlert.id))) == 0 and MockMessenger.sent == []


def test_normal_leads_dont_alert(raw_client, db_session):
    clinic = login(raw_client)
    set_alerts(raw_client, clinic, phone="9811122233")
    lead = raw_client.post("/leads", json={"business_id": 3, "source": "website", "name": "Ravi",
                                           "first_message": "What are your timings?"}, headers=clinic).json()
    assert raw_client.get(f"/leads/{lead['id']}", headers=clinic).json()["analysis"]["priority"] == "normal"
    assert db_session.scalar(select(func.count(OwnerAlert.id))) == 0


def test_quiet_hours_hold_until_8am(db_session):
    business = db_session.get(Business, 3)
    alerts_service.update_settings(db_session, business, "+919811122233", None, True, phone_given=True)
    from app.models import Lead
    lead = db_session.scalar(select(Lead).where(Lead.business_id == 3))
    night = datetime(2026, 10, 20, 23, 30, tzinfo=IST)
    alert = alerts_service.queue_hot_lead(db_session, lead, 81, now=night)
    assert alert.status == "pending" and MockMessenger.sent == []
    assert alerts_service.send_due(db_session, now=night + timedelta(hours=2)) == 0      # 1:30am: still quiet
    assert alerts_service.send_due(db_session, now=datetime(2026, 10, 21, 8, 5, tzinfo=IST)) == 1
    db_session.refresh(alert)
    assert alert.status == "sent" and len(MockMessenger.sent) == 1


def test_failed_sends_retry_then_give_up(db_session, monkeypatch):
    business = db_session.get(Business, 3)
    alerts_service.update_settings(db_session, business, "+919811122233", None, None, phone_given=True)

    def broken(self, *args, **kwargs):
        raise SendError("Meta is down")
    monkeypatch.setattr(MockMessenger, "send_whatsapp", broken)
    from app.models import Lead
    lead = db_session.scalar(select(Lead).where(Lead.business_id == 3))
    start = datetime.now(timezone.utc)
    alert = alerts_service.queue_hot_lead(db_session, lead, 90, now=start)
    assert alert.status == "pending" and alert.attempts == 1 and alert.error == "Meta is down"
    alerts_service.send_due(db_session, now=start + timedelta(minutes=1))                # too soon to retry
    assert alert.attempts == 1
    alerts_service.send_due(db_session, now=start + timedelta(minutes=3))
    alerts_service.send_due(db_session, now=start + timedelta(minutes=10))
    db_session.refresh(alert)
    assert alert.attempts == 3 and alert.status == "failed"


def test_lead_intel_number_sends_when_set_up(db_session, monkeypatch):
    assert isinstance(alert_messenger(db_session, 3)[0], MockMessenger)
    monkeypatch.setattr(settings, "alerts_whatsapp_phone_id", "1234567890")
    monkeypatch.setattr(settings, "alerts_whatsapp_token", "token")
    messenger, sender = alert_messenger(db_session, 3)
    assert isinstance(messenger, PlatformMessenger) and sender == "lead_intel"

    calls = []
    monkeypatch.setattr("app.integrations.meta.whatsapp_send_template",
                        lambda phone_id, token, to, name, language, params: calls.append((phone_id, to, name, params)) or "wamid.1")
    business = db_session.get(Business, 3)
    alerts_service.update_settings(db_session, business, "+919811122233", None, None, phone_given=True)
    alert = alerts_service.send_test(db_session, business)
    assert alert.status == "sent" and alert.sent_by == "lead_intel"
    phone_id, to, name, params = calls[0]
    assert (phone_id, to, name) == ("1234567890", "+919811122233", "hot_lead_alert")
    assert params[0] == "SmileCare Dental Clinic" and len(params) == 3                  # the template's 3 blanks


def test_paused_plan_gets_no_alerts(db_session, monkeypatch):
    business = db_session.get(Business, 3)
    alerts_service.update_settings(db_session, business, "+919811122233", None, None, phone_given=True)
    monkeypatch.setattr(alerts_service.billing_service, "paused_business_ids", lambda db: {3})
    from app.models import Lead
    lead = db_session.scalar(select(Lead).where(Lead.business_id == 3))
    alert = alerts_service.queue_hot_lead(db_session, lead, 88)
    assert alert.status == "skipped" and alert.error == "Plan ended" and MockMessenger.sent == []
