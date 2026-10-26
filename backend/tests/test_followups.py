"""
Task 30 checks: follow-up reminders for enquiries that have gone quiet.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.agents.llm import AIResult
from app.agents.nodes import followup_agent
from app.agents.nodes.followup_agent import FollowUp
from app.models import Business, Connection, Lead, Message
from app.services import followup_service, outbox
from app.services.event_bus import bus
from app.services.followup_service import IST

GYM, GARAGE = 1, 2
NOW = datetime.now(timezone.utc)


def login(client, email="gym@demo.in", password="demo1234"):
    r = client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def ago(days=0, hours=0):
    return NOW - timedelta(days=days, hours=hours)


def new_lead(db, *talk, phone="+919811077001", source="whatsapp", status="new", name="Rahul Mehta",
             service="Zumba", handle=None, business_id=GYM, **extra):
    """A lead with a conversation. talk = ("in" | "out" | "auto" | "followup", when) pairs, oldest first."""
    first = talk[0][1] if talk else ago(3)
    lead = Lead(business_id=business_id, source=source, name=name, phone=phone, handle=handle, service=service,
                first_message="Hi, what are the Zumba timings?", status=status, created_at=first,
                updated_at=NOW, **extra)
    for kind, when in talk:
        lead.messages.append(Message(direction="inbound" if kind == "in" else "outbound",
                                     text="Hi, what are the Zumba timings?" if kind == "in" else "Hello!",
                                     sent_at=when, delivery="" if kind == "in" else "sent",
                                     auto_reply=kind == "auto", followup=kind == "followup"))
    db.add(lead)
    db.commit()
    return lead


def check(db, lead, now=NOW):
    return followup_service.check_lead(lead, db.get(Business, lead.business_id), now)


def connect(db, business_id=GYM, platform="whatsapp"):
    db.add(Connection(business_id=business_id, platform=platform, external_id=f"mock_{platform}_{business_id}",
                      display_name="+91 98100 00001", mode="mock"))
    db.commit()


@pytest.fixture(autouse=True)
def clean_outbox():
    outbox.MOCK_SENT.clear()
    yield
    outbox.MOCK_SENT.clear()


# ---------------------------------------------------------------------------
# Who needs a follow-up
# ---------------------------------------------------------------------------
def test_unanswered_enquiry_shows_after_2_days(db_session):
    fresh = new_lead(db_session, ("in", ago(1)))
    old = new_lead(db_session, ("in", ago(2, 1)), phone="+919811077002")
    assert check(db_session, fresh) is None                         # only 1 day: not yet
    reminder = check(db_session, old)
    assert reminder["kind"] == "no_reply" and reminder["days"] == 2 and reminder["followups_sent"] == 0
    assert reminder["reason"] == "Asked about Zumba 2 days ago. No reply yet."
    assert reminder["customer"] == "Rahul Mehta" and reminder["source_name"] == "WhatsApp"


def test_the_instant_ai_reply_does_not_count_as_a_reply(db_session):
    lead = new_lead(db_session, ("in", ago(3)), ("auto", ago(3)))
    assert check(db_session, lead)["kind"] == "no_reply"


def test_customer_went_quiet_after_our_reply(db_session):
    lead = new_lead(db_session, ("in", ago(5)), ("out", ago(2, 2)), status="contacted")
    reminder = check(db_session, lead)
    assert reminder["kind"] == "gone_quiet" and reminder["reason"] == "You replied 2 days ago. No answer since."
    recent = new_lead(db_session, ("in", ago(5)), ("out", ago(1)), status="contacted", phone="+919811077003")
    assert check(db_session, recent) is None


def test_customer_wrote_back_and_is_waiting(db_session):
    lead = new_lead(db_session, ("in", ago(6)), ("out", ago(5)), ("in", ago(3)), status="contacted")
    assert check(db_session, lead)["kind"] == "waiting"
    assert "Still waiting for your answer" in check(db_session, lead)["reason"]


def test_called_by_phone_counts_as_a_reply(db_session):
    """Status moved to 'contacted' with no typed reply (the owner phoned): the customer went quiet."""
    lead = new_lead(db_session, ("in", ago(6)), status="contacted", first_response_at=ago(3))
    assert check(db_session, lead)["kind"] == "gone_quiet"


def test_at_most_2_follow_ups_then_we_stop(db_session):
    one = new_lead(db_session, ("in", ago(9)), ("out", ago(8)), ("followup", ago(4)), status="contacted")
    reminder = check(db_session, one)
    assert reminder["followups_sent"] == 1 and "1 follow-up already sent" in reminder["reason"]
    two = new_lead(db_session, ("in", ago(9)), ("out", ago(8)), ("followup", ago(6)), ("followup", ago(3)),
                   status="contacted", phone="+919811077004")
    assert check(db_session, two) is None


@pytest.mark.parametrize("status", ["booked", "won", "lost"])
def test_finished_enquiries_are_left_alone(db_session, status):
    lead = new_lead(db_session, ("in", ago(4)), status=status, **({"job_value": 2000} if status == "won" else {}))
    assert check(db_session, lead) is None


def test_gone_cold_after_14_days(db_session):
    assert check(db_session, new_lead(db_session, ("in", ago(15)))) is None
    assert check(db_session, new_lead(db_session, ("in", ago(13)), phone="+919811077005")) is not None


def test_owner_picks_the_number_of_days(db_session):
    lead = new_lead(db_session, ("in", ago(2, 1)))
    gym = db_session.get(Business, GYM)
    followup_service.update_settings(db_session, gym, {"after_days": 3})
    assert check(db_session, lead) is None
    followup_service.update_settings(db_session, gym, {"after_days": 1})
    assert check(db_session, lead) is not None
    followup_service.update_settings(db_session, gym, {"enabled": False})
    assert followup_service.due(db_session, gym) == []


def test_snooze_stop_and_resume(client, db_session):
    lead = new_lead(db_session, ("in", ago(3)))
    r = client.post(f"/followups/{lead.id}/snooze", json={"days": 1})
    assert r.status_code == 200 and r.json()["due"] is False and r.json()["snoozed_until"]
    assert check(db_session, lead, NOW + timedelta(days=1, hours=1)) is not None     # back tomorrow
    r = client.post(f"/followups/{lead.id}/stop")
    assert r.json()["stopped"] is True and r.json()["due"] is False
    assert lead.id not in [x["lead_id"] for x in client.get("/followups", params={"business_id": GYM}).json()["items"]]
    r = client.post(f"/followups/{lead.id}/resume")
    assert r.json()["due"] is True and r.json()["stopped"] is False


def test_customer_writing_again_starts_fresh(client, db_session):
    lead = new_lead(db_session, ("in", ago(3)), phone="+919811077006")
    followup_service.stop(db_session, lead)
    payload = {"object": "whatsapp_business_account", "entry": [{"id": "1", "changes": [{"field": "messages", "value": {
        "messaging_product": "whatsapp", "metadata": {"phone_number_id": "1"},
        "contacts": [{"profile": {"name": "Rahul Mehta"}, "wa_id": "919811077006"}],
        "messages": [{"from": "919811077006", "id": "wamid.followup.again", "timestamp": str(int(NOW.timestamp())),
                      "type": "text", "text": {"body": "Hello? Any update?"}}]}}]}]}
    assert client.post("/webhooks/whatsapp", params={"business_id": GYM}, json=payload).json()["added_to_existing"] == 1
    db_session.refresh(lead)
    assert lead.followup_stopped is False


# ---------------------------------------------------------------------------
# The ready message and how it goes out
# ---------------------------------------------------------------------------
def test_ready_message_in_the_customers_language(db_session):
    lead = new_lead(db_session, ("in", ago(3)))
    made = followup_service.draft(db_session, lead)
    assert made["text"].startswith("Hi Rahul!") and "Iron Pulse Fitness" in made["text"] and "Zumba" in made["text"]
    assert "Sorry for the late reply" in made["text"] and made["ai_mode"] == "mock" and made["check"] == "ok"
    hinglish = new_lead(db_session, ("in", ago(4)), ("out", ago(3)), status="contacted", phone="+919811077007")
    hinglish.messages[0].text = "Zumba ki timing kya hai? Fees kitni hai bhai"
    db_session.commit()
    assert "check kar rahe the" in followup_service.draft(db_session, hinglish)["text"]


def test_second_follow_up_is_a_gentle_last_check(db_session):
    lead = new_lead(db_session, ("in", ago(9)), ("out", ago(8)), ("followup", ago(4)), status="contacted")
    made = followup_service.draft(db_session, lead)
    assert made["nth"] == 2 and "last check" in made["text"]


def test_ai_price_or_link_is_replaced_with_the_safe_message(db_session, monkeypatch):
    lead = new_lead(db_session, ("in", ago(3)))
    monkeypatch.setattr(followup_agent, "write_follow_up", lambda *a: AIResult(
        data=FollowUp(message="Hi Rahul! Zumba is just ₹1500 a month, join now!"), mode="real"))
    monkeypatch.setattr(followup_service, "write_follow_up", followup_agent.write_follow_up)
    made = followup_service.draft(db_session, lead)
    assert made["check"] == "replaced" and "₹" not in made["text"] and "Iron Pulse Fitness" in made["text"]

    def broken(*a):
        raise RuntimeError("AI down")
    monkeypatch.setattr(followup_service, "write_follow_up", broken)
    made = followup_service.draft(db_session, lead)
    assert made["check"] == "ai_error" and made["text"].startswith("Hi Rahul!")


def test_how_it_can_be_sent(db_session):
    within = new_lead(db_session, ("in", ago(0, 20)), phone="919811077008")
    old = new_lead(db_session, ("in", ago(3)), phone="9811077009")
    assert followup_service.how_to_send(db_session, within)["how"] == "whatsapp"     # not connected: own phone
    connect(db_session)
    assert followup_service.how_to_send(db_session, within)["how"] == "app"          # connected + inside 24 hours
    late = followup_service.how_to_send(db_session, old)
    assert late["how"] == "whatsapp" and late["link"] == "https://wa.me/919811077009" and "24 hours" in late["note"]
    insta = new_lead(db_session, ("in", ago(3)), source="instagram", phone=None, handle="rahul.fit")
    assert followup_service.how_to_send(db_session, insta) == {
        "how": "instagram", "link": "https://ig.me/m/rahul.fit",
        "note": "Copy the message, then open their Instagram chat and paste it."}
    nobody = new_lead(db_session, ("in", ago(3)), source="website", phone=None)
    assert followup_service.how_to_send(db_session, nobody)["how"] == "copy"


def test_send_through_the_connected_account(client, db_session):
    connect(db_session)
    lead = new_lead(db_session, ("in", ago(0, 3)), phone="919811077010")
    r = client.post(f"/followups/{lead.id}/send", json={"text": "Hi Rahul, any day that suits you?", "via": "app"})
    assert r.status_code == 200 and r.json()["delivery"] == "sent" and r.json()["followup"] is True
    assert outbox.MOCK_SENT[-1]["to"] == "919811077010"
    db_session.refresh(lead)
    assert lead.status == "contacted" and lead.first_response_at is not None
    detail = client.get(f"/leads/{lead.id}").json()
    assert detail["messages"][-1]["followup"] is True


def test_sent_from_my_phone_is_noted(client, db_session):
    lead = new_lead(db_session, ("in", ago(4)), ("out", ago(3)), status="contacted")
    r = client.post(f"/followups/{lead.id}/send", json={"text": "Hi Rahul, just checking in!", "via": "phone"})
    assert r.status_code == 200 and r.json()["delivery"] == "logged" and outbox.MOCK_SENT == []
    db_session.refresh(lead)
    assert check(db_session, lead) is None                           # just followed up: quiet again for 2 days
    assert check(db_session, lead, NOW + timedelta(days=2, hours=1))["followups_sent"] == 1


def test_app_send_without_a_connection_is_refused(client, db_session):
    lead = new_lead(db_session, ("in", ago(3)))
    r = client.post(f"/followups/{lead.id}/send", json={"text": "Hello", "via": "app"})
    assert r.status_code == 400 and "isn't connected" in r.json()["detail"]
    assert len(lead.messages) == 1


def test_24_hour_rule_failure_keeps_the_reminder(client, db_session):
    connect(db_session)
    lead = new_lead(db_session, ("in", ago(3)), phone="919811077011")
    r = client.post(f"/followups/{lead.id}/send", json={"text": "Hello", "via": "app"})
    assert r.json()["delivery"] == "failed" and "24 hours" in r.json()["delivery_error"]
    db_session.refresh(lead)
    assert check(db_session, lead) is not None and lead.status == "new"


# ---------------------------------------------------------------------------
# The API and the Settings card
# ---------------------------------------------------------------------------
def test_list_and_one_lead(client, db_session):
    lead = new_lead(db_session, ("in", ago(3)))
    body = client.get("/followups", params={"business_id": GYM}).json()
    assert body["settings"] == {"enabled": True, "after_days": 2} and body["count"] == len(body["items"])
    assert lead.id in [x["lead_id"] for x in body["items"]]
    one = client.get(f"/followups/{lead.id}").json()
    assert one["due"] is True and one["reminder"]["kind"] == "no_reply"
    assert one["draft"]["how"] == "whatsapp" and one["draft"]["link"] == "https://wa.me/919811077001"
    quiet = new_lead(db_session, ("in", ago(0, 2)), phone="+919811077012")
    assert client.get(f"/followups/{quiet.id}").json()["due"] is False        # a message is still offered
    assert client.get(f"/followups/{quiet.id}").json()["draft"]["text"]


def test_settings_owner_only_and_checked(raw_client):
    gym = login(raw_client)
    assert raw_client.get("/followups/settings", params={"business_id": GYM}, headers=gym).json() == \
        {"enabled": True, "after_days": 2}
    r = raw_client.put("/followups/settings", params={"business_id": GYM}, json={"after_days": 3}, headers=gym)
    assert r.json() == {"enabled": True, "after_days": 3}
    assert raw_client.put("/followups/settings", params={"business_id": GYM}, json={"after_days": 4},
                          headers=gym).status_code == 422
    staff = login(raw_client, "staff@demo.in")
    assert raw_client.put("/followups/settings", params={"business_id": GYM}, json={"enabled": False},
                          headers=staff).status_code == 403
    assert raw_client.get("/followups", params={"business_id": GYM}, headers=staff).status_code == 200
    garage = login(raw_client, "garage@demo.in")
    assert raw_client.get("/followups", params={"business_id": GYM}, headers=garage).status_code == 404


def test_someone_elses_lead_is_hidden(raw_client, db_session):
    lead = new_lead(db_session, ("in", ago(3)))
    garage = login(raw_client, "garage@demo.in")
    assert raw_client.get(f"/followups/{lead.id}", headers=garage).status_code == 404
    assert raw_client.post(f"/followups/{lead.id}/send", json={"text": "hi", "via": "phone"},
                           headers=garage).status_code == 404


# ---------------------------------------------------------------------------
# The daily note
# ---------------------------------------------------------------------------
def test_daily_note_once_a_day_after_10am(db_session, monkeypatch):
    new_lead(db_session, ("in", ago(3)))
    morning = datetime(2026, 10, 24, 9, 30, tzinfo=IST)
    noon = datetime(2026, 10, 24, 12, 0, tzinfo=IST)
    start = bus.recent(GYM)[-1]["id"] if bus.recent(GYM) else 0
    assert followup_service.daily_reminders(db_session, morning) == 0
    monkeypatch.setattr(followup_service, "due", lambda db, b, now=None: [
        {"lead_id": 1, "customer": "Rahul Mehta"}, {"lead_id": 2, "customer": "Priya"}] if b.id == GYM else [])
    assert followup_service.daily_reminders(db_session, noon) == 1
    assert followup_service.daily_reminders(db_session, noon + timedelta(hours=2)) == 0     # once a day
    note = [e for e in bus.recent(GYM, start) if e["type"] == "followup.due"][-1]
    assert note["title"] == "📋 2 enquiries need a follow-up today" and note["message"] == "Rahul Mehta, Priya"
    assert followup_service.daily_reminders(db_session, noon + timedelta(days=1)) == 1      # next day again
    assert "reminded_on" not in followup_service.settings_for(db_session.get(Business, GYM))


def test_no_daily_note_when_paused_or_off(db_session, monkeypatch):
    noon = datetime(2026, 10, 24, 12, 0, tzinfo=IST)
    monkeypatch.setattr(followup_service, "due", lambda db, b, now=None: [{"lead_id": 1, "customer": "A"}])
    monkeypatch.setattr(followup_service.billing_service, "paused_business_ids", lambda db: {GYM})
    followup_service.update_settings(db_session, db_session.get(Business, GARAGE), {"enabled": False})
    sent = followup_service.daily_reminders(db_session, noon)
    assert sent == len(list(db_session.scalars(Business.__table__.select()))) - 2      # all but the gym and garage
