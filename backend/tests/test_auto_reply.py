"""
Task 29 checks: the instant AI first reply to new WhatsApp / Instagram enquiries.
"""

import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.agents.llm import AIResult
from app.agents.nodes import first_reply_agent
from app.agents.nodes.first_reply_agent import FirstReply
from app.models import Business, Connection, Lead, Message
from app.services import auto_reply_service, outbox
from app.services.auto_reply_service import IST

GYM, GARAGE = 1, 2
ZUMBA = "Hi! What are the fees for the evening Zumba batch? I want to join this week itself"


def login(client, email="gym@demo.in", password="demo1234"):
    r = client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def set_auto(client, headers, business_id=GYM, **body):
    r = client.put("/auto-reply/settings", params={"business_id": business_id}, json=body, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def connect(db, business_id=GYM, platform="whatsapp"):
    db.add(Connection(business_id=business_id, platform=platform, external_id=f"mock_{platform}_{business_id}",
                      display_name="+91 98100 00001", mode="mock"))
    db.commit()


def whatsapp(client, text=ZUMBA, phone="919811055555", name="Riya Arora", business_id=GYM, message_id=None):
    """A WhatsApp message arriving NOW, in the real Cloud API format."""
    payload = {"object": "whatsapp_business_account", "entry": [{"id": "1", "changes": [{"field": "messages", "value": {
        "messaging_product": "whatsapp", "metadata": {"phone_number_id": "106540352242922"},
        "contacts": [{"profile": {"name": name}, "wa_id": phone}],
        "messages": [{"from": phone, "id": message_id or f"wamid.{phone}.{time.time_ns()}",
                      "timestamp": str(int(time.time())), "type": "text", "text": {"body": text}}]}}]}]}
    r = client.post("/webhooks/whatsapp", params={"business_id": business_id}, json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def auto_replies(db, lead_id=None):
    query = select(Message).where(Message.auto_reply.is_(True))
    if lead_id:
        query = query.where(Message.lead_id == lead_id)
    return list(db.scalars(query))


@pytest.fixture(autouse=True)
def clean_outbox():
    outbox.MOCK_SENT.clear()
    yield
    outbox.MOCK_SENT.clear()


# ---------------------------------------------------------------------------
# The settings card
# ---------------------------------------------------------------------------
def test_settings_start_off_and_save(raw_client):
    gym = login(raw_client)
    start = raw_client.get("/auto-reply/settings", params={"business_id": GYM}, headers=gym).json()
    assert start["mode"] == "off" and start["opens"] == "09:00" and start["closes"] == "21:00"
    assert start["channels"] == {"whatsapp": False, "instagram": False, "facebook": False}
    assert start["recent"] == [] and start["ai_mode"] == "mock"
    saved = set_auto(raw_client, gym, mode="after_hours", opens="06:00", closes="22:30", closed_days=[6, 6],
                     note="  For emergencies call 98100 00000  ")
    assert saved["mode"] == "after_hours" and saved["opens"] == "06:00" and saved["closed_days"] == [6]
    assert saved["note"] == "For emergencies call 98100 00000"
    kept = set_auto(raw_client, gym, mode="always")                      # only what's sent changes
    assert kept["opens"] == "06:00" and kept["note"].startswith("For emergencies")


@pytest.mark.parametrize("body", [{"mode": "sometimes"}, {"opens": "9am"}, {"closes": "24:00"},
                                  {"opens": "10:00", "closes": "10:00"}, {"closed_days": [7]},
                                  {"closed_days": [0, 1, 2, 3, 4, 5, 6]}, {"note": "x" * 201}])
def test_bad_settings_are_refused(raw_client, body):
    gym = login(raw_client)
    r = raw_client.put("/auto-reply/settings", params={"business_id": GYM}, json=body, headers=gym)
    assert r.status_code == 422


def test_only_the_owner_changes_it(raw_client):
    staff = login(raw_client, "staff@demo.in")
    assert raw_client.get("/auto-reply/settings", params={"business_id": GYM}, headers=staff).status_code == 200
    assert raw_client.put("/auto-reply/settings", params={"business_id": GYM}, json={"mode": "always"},
                          headers=staff).status_code == 403
    garage = login(raw_client, "garage@demo.in")                       # someone else's business: hidden
    assert raw_client.get("/auto-reply/settings", params={"business_id": GYM}, headers=garage).status_code == 404


def test_preview_shows_the_reply_but_sends_nothing(raw_client, db_session):
    gym = login(raw_client)
    r = raw_client.post("/auto-reply/preview", params={"business_id": GYM}, json={"message": ZUMBA}, headers=gym)
    assert r.status_code == 200
    body = r.json()
    assert "Iron Pulse Fitness" in body["reply"] and "Zumba" in body["reply"]
    assert body["ai_mode"] == "mock" and body["check"] == "ok"
    assert outbox.MOCK_SENT == [] and auto_replies(db_session) == []


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------
def test_off_by_default_nothing_is_sent(client, db_session):
    connect(db_session)
    whatsapp(client)
    assert auto_replies(db_session) == [] and outbox.MOCK_SENT == []


def test_new_whatsapp_enquiry_gets_an_instant_reply(client, db_session):
    connect(db_session)
    set_auto(client, {}, mode="always", note="For emergencies call 98100 00000")
    result = whatsapp(client)
    lead_id = result["lead_ids"][0]
    [reply] = auto_replies(db_session, lead_id)
    assert reply.direction == "outbound" and reply.delivery == "sent"
    assert "Iron Pulse Fitness" in reply.text and "Riya" in reply.text and "Zumba" in reply.text
    assert reply.text.endswith("For emergencies call 98100 00000")
    assert outbox.MOCK_SENT[-1]["to"] == "+919811055555" and outbox.MOCK_SENT[-1]["text"] == reply.text

    lead = client.get(f"/leads/{lead_id}").json()
    assert lead["status"] == "new"                       # the owner still has to reply for real
    assert db_session.get(Lead, lead_id).first_response_at is None
    assert [m["auto_reply"] for m in lead["messages"]] == [False, True]
    assert lead["analysis"] is not None                  # the AI scoring still ran afterwards

    card = client.get("/auto-reply/settings", params={"business_id": GYM}).json()
    assert card["channels"]["whatsapp"] is True
    assert card["recent"][0]["lead_id"] == lead_id and card["recent"][0]["customer"] == "Riya Arora"


def test_only_once_per_enquiry(client, db_session):
    connect(db_session)
    set_auto(client, {}, mode="always")
    first = whatsapp(client, message_id="wamid.same")
    whatsapp(client, message_id="wamid.same")                        # Meta sends the same webhook twice
    whatsapp(client, text="Also, do you have parking?")              # same person, follow-up message
    lead_id = first["lead_ids"][0]
    assert len(auto_replies(db_session, lead_id)) == 1 and len(outbox.MOCK_SENT) == 1


def test_instagram_dm_gets_a_reply_too(client, db_session):
    connect(db_session, GARAGE, "instagram")
    set_auto(client, {}, business_id=GARAGE, mode="always")
    payload = {"object": "instagram", "entry": [{"id": "17841400000000002", "messaging": [{
        "sender": {"id": "6624512983309871"}, "recipient": {"id": "17841400000000002"},
        "timestamp": int(time.time() * 1000),
        "message": {"mid": f"mid.{time.time_ns()}", "text": "Saw your reel 🔥 How much for ceramic coating on a Creta?"}}]}]}
    result = client.post("/webhooks/instagram", params={"business_id": GARAGE}, json=payload).json()
    [reply] = auto_replies(db_session, result["lead_ids"][0])
    assert reply.delivery == "sent" and "Gloss Garage Detailing" in reply.text
    assert outbox.MOCK_SENT[-1] == {"platform": "instagram", "to": "6624512983309871", "text": reply.text,
                                    "business_id": GARAGE}


def test_no_reply_when_the_chat_isnt_connected(client, db_session):
    set_auto(client, {}, mode="always")
    whatsapp(client)
    assert auto_replies(db_session) == [] and outbox.MOCK_SENT == []


def test_no_reply_for_other_platforms(client, db_session):
    connect(db_session)
    set_auto(client, {}, mode="always")
    r = client.post("/webhooks/website", params={"business_id": GYM},
                    json={"name": "Asha", "phone": "9811000111", "message": "Zumba timings?"})
    assert r.status_code == 200 and auto_replies(db_session) == []


def test_after_hours_mode(client, db_session, monkeypatch):
    connect(db_session)
    set_auto(client, {}, mode="after_hours")
    monkeypatch.setattr(auto_reply_service, "is_open", lambda business, now: True)
    whatsapp(client, phone="919811000001")                            # open: the team replies themselves
    assert auto_replies(db_session) == []
    monkeypatch.setattr(auto_reply_service, "is_open", lambda business, now: False)
    monkeypatch.setattr(auto_reply_service, "back_at", lambda business, now: "tomorrow at 9 am")
    whatsapp(client, phone="919811000002")                            # closed: instant reply
    [reply] = auto_replies(db_session)
    assert "closed right now" in reply.text and "tomorrow at 9 am" in reply.text


def test_paused_plan_old_message_or_already_replied(db_session, monkeypatch):
    connect(db_session)
    business = db_session.get(Business, GYM)
    auto_reply_service.update_settings(db_session, business, {"mode": "always"})
    now = datetime.now(timezone.utc)

    def new_lead(phone, minutes_ago=0):
        lead = Lead(business_id=GYM, source="whatsapp", phone=phone, name="Kunal", first_message=ZUMBA,
                    created_at=now - timedelta(minutes=minutes_ago))
        lead.messages.append(Message(direction="inbound", text=ZUMBA, sent_at=now - timedelta(minutes=minutes_ago)))
        db_session.add(lead)
        db_session.commit()
        return lead

    old = new_lead("+919811000010", minutes_ago=180)                 # 3 hours late: not "instant" any more
    assert auto_reply_service.reply_to_new_lead(db_session, old.id, now) is None
    replied = new_lead("+919811000011")
    replied.messages.append(Message(direction="outbound", text="Hi, call you in 5 min", delivery="sent"))
    db_session.commit()
    assert auto_reply_service.reply_to_new_lead(db_session, replied.id, now) is None
    monkeypatch.setattr(auto_reply_service.billing_service, "paused_business_ids", lambda db: {GYM})
    paused = new_lead("+919811000012")
    assert auto_reply_service.reply_to_new_lead(db_session, paused.id, now) is None
    assert outbox.MOCK_SENT == []


def test_a_failed_send_is_shown_on_the_lead(db_session, monkeypatch):
    connect(db_session)
    auto_reply_service.update_settings(db_session, db_session.get(Business, GYM), {"mode": "always"})
    monkeypatch.setattr(outbox, "send_reply", lambda db, lead, text: ("failed", "Not sent: Meta is down", None))
    now = datetime.now(timezone.utc)
    lead = Lead(business_id=GYM, source="whatsapp", phone="+919811000020", first_message=ZUMBA)
    lead.messages.append(Message(direction="inbound", text=ZUMBA, sent_at=now))
    db_session.add(lead)
    db_session.commit()
    message = auto_reply_service.reply_to_new_lead(db_session, lead.id, now)
    assert message.delivery == "failed" and message.delivery_error == "Not sent: Meta is down"


# ---------------------------------------------------------------------------
# What the reply says
# ---------------------------------------------------------------------------
def test_money_or_links_from_the_ai_are_never_sent(db_session, monkeypatch):
    business = db_session.get(Business, GYM)
    auto_reply_service.update_settings(db_session, business, {"note": "Diwali offer: 20% off this week!"})
    for risky in ("Hi! Zumba is just ₹1,500 a month 💪", "Zumba fees are Rs 1500, join now",
                  "Fees 1500/- only", "Book here: https://bit.ly/zumba", "We have a special discount for you"):
        monkeypatch.setattr(first_reply_agent, "get_llm", lambda: _FakeLLM(risky))
        monkeypatch.setattr(auto_reply_service, "write_first_reply", first_reply_agent.write_first_reply)
        made = auto_reply_service.compose(business, ZUMBA, "Riya", datetime.now(timezone.utc))
        assert made["check"] == "replaced", risky
        assert "1500" not in made["text"] and "₹1" not in made["text"] and "bit.ly" not in made["text"]
        assert made["text"].endswith("Diwali offer: 20% off this week!")     # the owner's own words are kept


def test_a_good_ai_reply_is_kept_and_an_ai_crash_uses_the_safe_reply(db_session, monkeypatch):
    business = db_session.get(Business, GYM)
    good = "Hi Riya! Thanks for messaging Iron Pulse 🙏 Our team will share the Zumba details shortly. Morning or evening?"
    monkeypatch.setattr(first_reply_agent, "get_llm", lambda: _FakeLLM(good))
    made = auto_reply_service.compose(business, ZUMBA, "Riya", datetime.now(timezone.utc))
    assert made["text"] == good and made["check"] == "ok" and made["ai_mode"] == "real"

    def crash(*args):
        raise RuntimeError("boom")
    monkeypatch.setattr(auto_reply_service, "write_first_reply", crash)
    made = auto_reply_service.compose(business, ZUMBA, "Riya", datetime.now(timezone.utc))
    assert made["check"] == "ai_error" and "Iron Pulse Fitness" in made["text"]


def test_hinglish_message_gets_a_hinglish_reply(db_session):
    business = db_session.get(Business, 2)
    made = auto_reply_service.compose(business, "Bhai ceramic coating kitne ka hai? Aaj ho jayega kya?", None,
                                      datetime(2026, 10, 21, 23, 0, tzinfo=IST))
    assert "Abhi hum band hain" in made["text"] and "kis din laana" in made["text"]


def test_opening_hours(db_session):
    business = db_session.get(Business, GYM)
    auto_reply_service.update_settings(db_session, business, {"opens": "09:00", "closes": "21:00", "closed_days": [1]})
    wed = datetime(2026, 10, 21, tzinfo=IST)                                       # a Wednesday
    at = lambda day, h, m=0: wed.replace(day=21 + day, hour=h, minute=m)           # noqa: E731
    assert auto_reply_service.is_open(business, at(0, 10)) is True
    assert auto_reply_service.is_open(business, at(0, 8, 59)) is False
    assert auto_reply_service.is_open(business, at(0, 21)) is False
    assert auto_reply_service.back_at(business, at(0, 7)) == "at 9 am"
    assert auto_reply_service.back_at(business, at(0, 22)) == "tomorrow at 9 am"
    assert auto_reply_service.back_at(business, at(5, 22)) == "on Wednesday at 9 am"   # Monday night; Tuesday closed
    assert auto_reply_service.is_open(business, at(6, 12)) is False                     # Tuesday 27th: closed day

    auto_reply_service.update_settings(db_session, business, {"opens": "18:30", "closes": "02:00", "closed_days": []})
    assert auto_reply_service.is_open(business, at(0, 23)) is True                 # late-night hours past midnight
    assert auto_reply_service.is_open(business, at(1, 1, 30)) is True
    assert auto_reply_service.is_open(business, at(1, 3)) is False
    assert auto_reply_service.back_at(business, at(1, 3)) == "at 6:30 pm"


class _FakeLLM:
    """Pretends to be the real AI and always answers `reply`."""

    mode = "real"

    def __init__(self, reply):
        self.reply = reply

    def ask(self, *, schema, mock, **kwargs):
        return AIResult(data=FirstReply(reply=self.reply), mode="real", model="fake")
