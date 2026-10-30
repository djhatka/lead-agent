"""
Task 38 checks: phone call tracking. A tracking number per business; missed calls
flagged for a call-back; completed calls get a short AI note when a transcript
is available.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import Business, Call, TrackingNumber
from app.services import calltracking_service
from app.services.event_bus import bus

GYM = 1


def login(client, email="gym@demo.in", password="demo1234"):
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _clear(db):
    for c in db.scalars(select(Call).where(Call.business_id == GYM)):
        db.delete(c)
    for n in db.scalars(select(TrackingNumber).where(TrackingNumber.business_id == GYM)):
        db.delete(n)
    db.commit()


def events(business_id, kind, after=0):
    return [e for e in bus.recent(business_id, after) if e["type"] == kind]


def last_event_id(business_id):
    recent = bus.recent(business_id)
    return recent[-1]["id"] if recent else 0


# ---------------------------------------------------------------------------
# The tracking number
# ---------------------------------------------------------------------------
def test_mock_number_is_stable_and_free(db_session):
    _clear(db_session)
    gym = db_session.get(Business, GYM)
    a = calltracking_service.number_for(db_session, gym)
    b = calltracking_service.number_for(db_session, gym)
    assert a.id == b.id and a.number.startswith("+91 ")


# ---------------------------------------------------------------------------
# Recording a call
# ---------------------------------------------------------------------------
def test_a_new_call_starts_ringing(db_session):
    _clear(db_session)
    gym = db_session.get(Business, GYM)
    call = calltracking_service.record_call(db_session, gym, external_id="c1", from_number="+919811000001",
                                            provider_status="ringing")
    assert call.status == "ringing" and call.from_number == "+919811000001"


def test_the_same_call_updates_instead_of_duplicating(db_session):
    _clear(db_session)
    gym = db_session.get(Business, GYM)
    calltracking_service.record_call(db_session, gym, external_id="c2", from_number="+919811000002",
                                     provider_status="ringing")
    calltracking_service.record_call(db_session, gym, external_id="c2", provider_status="completed",
                                     duration_seconds=90)
    calls = list(db_session.scalars(select(Call).where(Call.business_id == GYM, Call.external_id == "c2")))
    assert len(calls) == 1 and calls[0].status == "completed" and calls[0].duration_seconds == 90


def test_a_missed_call_raises_one_alert_not_two(db_session):
    _clear(db_session)
    gym = db_session.get(Business, GYM)
    after = last_event_id(GYM)
    calltracking_service.record_call(db_session, gym, external_id="c3", from_number="+919811000003",
                                     provider_status="no-answer")
    calltracking_service.record_call(db_session, gym, external_id="c3", provider_status="no-answer")   # retried
    assert len(events(GYM, "call.missed", after)) == 1


def test_a_completed_call_with_a_transcript_gets_an_ai_note(db_session):
    _clear(db_session)
    gym = db_session.get(Business, GYM)
    call = calltracking_service.record_call(
        db_session, gym, external_id="c4", from_number="+919811000004", provider_status="completed",
        duration_seconds=120, transcript="Hi, what's the price for a monthly membership?")
    assert call.note and "pricing" in call.note.lower()


def test_a_completed_call_without_a_transcript_gets_no_note(db_session):
    _clear(db_session)
    gym = db_session.get(Business, GYM)
    call = calltracking_service.record_call(db_session, gym, external_id="c5", provider_status="completed",
                                            duration_seconds=30)
    assert call.note == ""


# ---------------------------------------------------------------------------
# The Calls page
# ---------------------------------------------------------------------------
def test_called_back_only_works_on_a_missed_call(db_session):
    _clear(db_session)
    gym = db_session.get(Business, GYM)
    missed = calltracking_service.record_call(db_session, gym, external_id="c6", provider_status="no-answer")
    calltracking_service.mark_called_back(db_session, missed)
    assert missed.called_back_at is not None
    with pytest.raises(ValueError):
        calltracking_service.mark_called_back(db_session, missed)

    completed = calltracking_service.record_call(db_session, gym, external_id="c7", provider_status="completed")
    with pytest.raises(ValueError):
        calltracking_service.mark_called_back(db_session, completed)


def test_summary_counts(db_session):
    _clear(db_session)
    gym = db_session.get(Business, GYM)
    now = datetime.now(timezone.utc)
    calltracking_service.record_call(db_session, gym, external_id="s1", provider_status="no-answer", now=now)
    calltracking_service.record_call(db_session, gym, external_id="s2", provider_status="completed",
                                     duration_seconds=60, now=now)
    yesterday = now - timedelta(days=1)
    calltracking_service.record_call(db_session, gym, external_id="s3", provider_status="completed", now=yesterday)

    s = calltracking_service.summary(db_session, GYM, now)
    assert s["total"] == 3 and s["missed_waiting"] == 1 and s["completed"] == 2 and s["today"] == 2
    assert s["mode"] == "mock"


# ---------------------------------------------------------------------------
# The endpoints
# ---------------------------------------------------------------------------
def test_number_summary_and_list_via_the_api(raw_client, db_session):
    _clear(db_session)
    headers = login(raw_client)

    r = raw_client.get("/calls/number", params={"business_id": GYM}, headers=headers)
    assert r.status_code == 200 and r.json()["mode"] == "mock" and r.json()["number"]

    r = raw_client.get("/calls/summary", params={"business_id": GYM}, headers=headers)
    assert r.status_code == 200 and r.json()["total"] == 0

    r = raw_client.post("/calls/simulate", params={"business_id": GYM, "missed": True}, headers=headers)
    assert r.status_code == 201 and r.json()["status"] == "missed"
    call_id = r.json()["id"]

    r = raw_client.get("/calls", params={"business_id": GYM, "status": "missed"}, headers=headers)
    assert r.status_code == 200 and any(c["id"] == call_id for c in r.json())

    r = raw_client.post(f"/calls/{call_id}/called-back", headers=headers)
    assert r.status_code == 200 and r.json()["called_back_at"] is not None


def test_simulate_a_completed_call_gets_a_note(raw_client, db_session):
    _clear(db_session)
    headers = login(raw_client)
    r = raw_client.post("/calls/simulate", params={"business_id": GYM}, headers=headers)
    assert r.status_code == 201
    assert r.json()["status"] == "completed" and r.json()["note"]


def test_calls_endpoint_needs_login(raw_client):
    r = raw_client.get("/calls", params={"business_id": GYM})
    assert r.status_code == 401


def test_calls_block_other_businesses(raw_client, db_session):
    headers = login(raw_client)                                 # gym owner
    r = raw_client.get("/calls", params={"business_id": 2}, headers=headers)   # the garage
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# The provider's webhook
# ---------------------------------------------------------------------------
def test_webhook_finds_the_business_by_the_tracking_number(raw_client, db_session):
    _clear(db_session)
    gym = db_session.get(Business, GYM)
    tn = calltracking_service.number_for(db_session, gym)
    to_digits = "".join(ch for ch in tn.number if ch.isdigit())

    r = raw_client.post("/webhooks/calltracking", data={
        "CallSid": "ext-123", "From": "+919811099999", "To": to_digits, "Status": "completed",
        "Duration": "75", "Transcript": "Can I book an appointment for tomorrow?",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "completed"

    call = db_session.get(Call, body["call_id"])
    assert call.business_id == GYM and call.duration_seconds == 75 and "availability" in call.note.lower()


def test_webhook_ignores_an_unknown_number(raw_client, db_session):
    r = raw_client.post("/webhooks/calltracking", data={"To": "919999999999", "Status": "ringing"})
    assert r.status_code == 200 and r.json()["ignored"] is True
