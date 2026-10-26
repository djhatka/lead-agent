"""
Task 31 checks: payments and dues. Customers pay the owner's own UPI ID through a
payment page; the owner confirms; polite automatic reminders if turned on.
"""

import io
import json
import zipfile
from datetime import date, datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select

from app.models import Business, Connection, Due, Lead, Message
from app.services import account_service, dues_service, outbox
from app.services.dues_service import IST, inr
from app.services.event_bus import bus
from app.services.messenger import MockMessenger

GYM, GARAGE = 1, 2
NOON = datetime(2026, 10, 24, 12, 0, tzinfo=IST)


def login(client, email="gym@demo.in", password="demo1234"):
    r = client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def a_lead(db, business_id=GARAGE, phone="+919811066001", name="Rahul Sharma", source="whatsapp", hours_ago=30):
    lead = Lead(business_id=business_id, source=source, name=name, phone=phone, first_message="Ceramic coating price?",
                status="quoted", created_at=datetime.now(timezone.utc) - timedelta(hours=hours_ago))
    lead.messages.append(Message(direction="inbound", text="Ceramic coating price?",
                                 sent_at=datetime.now(timezone.utc) - timedelta(hours=hours_ago)))
    db.add(lead)
    db.commit()
    return lead


def new_due(db, business_id=GARAGE, lead=None, **extra):
    business = db.get(Business, business_id)
    args = {"amount": 2000, "purpose": "Advance for ceramic coating", "lead": lead,
            "customer_name": "" if lead else "Rahul Sharma", "phone": "" if lead else "+919811066002", **extra}
    return dues_service.create(db, business, **args)


def events(business_id, kind, after=0):
    return [e for e in bus.recent(business_id, after) if e["type"] == kind]


def last_event_id(business_id):
    recent = bus.recent(business_id)
    return recent[-1]["id"] if recent else 0


@pytest.fixture(autouse=True)
def clean_senders():
    outbox.MOCK_SENT.clear()
    MockMessenger.sent.clear()
    yield
    outbox.MOCK_SENT.clear()
    MockMessenger.sent.clear()


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("amount,text", [(999, "₹999"), (2000, "₹2,000"), (150000, "₹1,50,000"),
                                         (12345678, "₹1,23,45,678")])
def test_rupees_in_indian_style(amount, text):
    assert inr(amount) == text


def test_where_a_due_stands(db_session):
    today = NOON.date()
    due = new_due(db_session, due_date=today)
    assert dues_service.state(due, NOON)["label"] == "Due today"
    due.due_date = today + timedelta(days=1)
    assert dues_service.state(due, NOON)["label"] == "Due tomorrow"
    due.due_date = today + timedelta(days=5)
    assert dues_service.state(due, NOON)["label"] == "Due 29 Oct"
    due.due_date = today - timedelta(days=3)
    assert dues_service.state(due, NOON) == {"label": "Overdue by 3 days", "overdue_days": 3}
    due.due_date = None
    assert dues_service.state(due, NOON)["label"] == "Waiting for payment"


@pytest.mark.parametrize("name,hello", [("Rahul Sharma", "Hi Rahul!"), ("Mr Verma", "Hi Mr Verma!"),
                                        ("dr. anita rao", "Hi Dr. Rao!"), ("+919811066009", "Hi!")])
def test_greeting_by_name(db_session, name, hello):
    due = new_due(db_session, customer_name=name)
    assert dues_service.request_message(db_session.get(Business, GARAGE), due).startswith(hello + " ")


def test_upi_link_pays_the_owner(db_session):
    due = new_due(db_session)
    link = dues_service.upi_link(db_session.get(Business, GARAGE), due)
    assert link.startswith("upi://pay?")
    q = parse_qs(urlparse(link).query)
    assert q["pa"] == ["glossgarage.demo@okdemo"] and q["am"] == ["2000.00"] and q["cu"] == ["INR"]
    assert q["pn"] == ["Gloss Garage Detailing"] and q["tn"] == ["Advance for ceramic coating"]


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
def test_settings_and_upi_id_check(raw_client):
    garage = login(raw_client, "garage@demo.in")
    s = raw_client.get("/dues/settings", params={"business_id": GARAGE}, headers=garage).json()
    assert s == {"upi_id": "glossgarage.demo@okdemo", "payee_name": "", "auto_reminders": False, "ready": True,
                 "reminders_mode": "practice"}
    for bad in ["glossgarage", "gloss garage@okaxis", "@okaxis", "a@1bank"]:
        r = raw_client.put("/dues/settings", params={"business_id": GARAGE}, json={"upi_id": bad}, headers=garage)
        assert r.status_code == 422, bad
    r = raw_client.put("/dues/settings", params={"business_id": GARAGE},
                       json={"upi_id": " gloss.garage@okhdfcbank ", "payee_name": "Gloss Garage", "auto_reminders": True},
                       headers=garage)
    assert r.json()["upi_id"] == "gloss.garage@okhdfcbank" and r.json()["payee_name"] == "Gloss Garage"
    assert r.json()["auto_reminders"] is True


def test_settings_owner_only_and_private(raw_client):
    staff = login(raw_client, "staff@demo.in")
    assert raw_client.get("/dues/settings", params={"business_id": GYM}, headers=staff).status_code == 200
    assert raw_client.put("/dues/settings", params={"business_id": GYM}, json={"auto_reminders": True},
                          headers=staff).status_code == 403
    garage = login(raw_client, "garage@demo.in")
    assert raw_client.get("/dues", params={"business_id": GYM}, headers=garage).status_code == 404


def test_no_upi_id_no_payment_links(client, db_session):
    dues_service.update_settings(db_session, db_session.get(Business, GARAGE), {"upi_id": ""})
    r = client.post("/dues", params={"business_id": GARAGE}, json={"customer_name": "Rahul", "amount": 2000,
                                                                    "purpose": "Advance"})
    assert r.status_code == 422 and "UPI ID" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Making a due and the ready messages
# ---------------------------------------------------------------------------
def test_due_from_an_enquiry(client, db_session):
    lead = a_lead(db_session)
    r = client.post("/dues", params={"business_id": GARAGE}, json={
        "lead_id": lead.id, "amount": 2000, "purpose": "Advance for ceramic coating", "due_date": "2026-10-28"})
    assert r.status_code == 201
    body = r.json()
    due = body["due"]
    assert due["customer_name"] == "Rahul Sharma" and due["phone"] == "+919811066001" and due["status"] == "open"
    assert due["pay_url"].startswith("http") and "/pay/" in due["pay_url"]
    assert body["ready"]["request"] == (
        f"Hi Rahul! Here's the payment link for ₹2,000 (Advance for ceramic coating) at Gloss Garage Detailing:\n"
        f"{due['pay_url']}\nYou can pay with GPay, PhonePe, Paytm or any UPI app. Thank you 🙏")
    assert "a gentle reminder from Gloss Garage Detailing: ₹2,000" in body["ready"]["reminder"]
    assert body["ready"]["how"] == "whatsapp" and body["ready"]["link"] == "https://wa.me/919811066001"
    assert [d["id"] for d in client.get("/dues", params={"business_id": GARAGE, "lead_id": lead.id}).json()] == [due["id"]]


def test_hinglish_business_gets_hinglish_messages(db_session):
    due = new_due(db_session, business_id=GYM, purpose="Monthly membership", due_date=NOON.date())
    gym = db_session.get(Business, GYM)
    assert "ka payment link" in dues_service.request_message(gym, due)
    assert "aaj due hain" in dues_service.reminder_message(gym, due, NOON)


def test_walk_in_due_needs_a_name_and_a_sane_amount(client):
    ok = client.post("/dues", params={"business_id": GARAGE}, json={
        "customer_name": "Walk-in: Mr Verma", "phone": "9811066003", "amount": 2500, "purpose": "Interior deep clean"})
    assert ok.status_code == 201 and ok.json()["due"]["lead_id"] is None
    assert ok.json()["ready"]["link"] == "https://wa.me/919811066003"
    assert client.post("/dues", params={"business_id": GARAGE}, json={
        "amount": 2500, "purpose": "Interior deep clean"}).status_code == 422                 # no name
    for amount in (0, 2_000_000):
        assert client.post("/dues", params={"business_id": GARAGE}, json={
            "customer_name": "A", "amount": amount, "purpose": "Test"}).status_code == 422


def test_someone_elses_lead_or_due_is_hidden(raw_client, db_session):
    lead = a_lead(db_session, business_id=GYM, phone="+919811066004")
    due = new_due(db_session, business_id=GYM)
    garage = login(raw_client, "garage@demo.in")
    r = raw_client.post("/dues", params={"business_id": GARAGE}, json={"lead_id": lead.id, "amount": 100,
                                                                        "purpose": "Test"}, headers=garage)
    assert r.status_code == 404
    assert raw_client.get(f"/dues/{due.id}", headers=garage).status_code == 404
    assert raw_client.post(f"/dues/{due.id}/paid", json={"via": "cash"}, headers=garage).status_code == 404


# ---------------------------------------------------------------------------
# The customer's payment page (no login)
# ---------------------------------------------------------------------------
def test_payment_page_and_ive_paid(raw_client, db_session):
    due = new_due(db_session, due_date=NOON.date())
    page = raw_client.get(f"/pay/{due.token}")
    assert page.status_code == 200 and page.headers["cache-control"] == "no-store"
    html = page.text
    assert "Gloss Garage Detailing" in html and "₹2,000" in html and "Advance for ceramic coating" in html
    assert "upi://pay?pa=glossgarage.demo@okdemo" in html and "<svg" in html and 'content="noindex' in html
    start = last_event_id(GARAGE)
    r = raw_client.post(f"/pay/{due.token}/paid", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/pay/{due.token}"
    db_session.refresh(due)
    assert due.customer_says_paid_at is not None and due.status == "open"      # the owner still confirms
    assert "Thanks! We've told Gloss Garage Detailing" in raw_client.get(f"/pay/{due.token}").text
    raw_client.post(f"/pay/{due.token}/paid")                                  # pressed twice: told once
    claimed = events(GARAGE, "payment.claimed", start)
    assert len(claimed) == 1 and claimed[0]["title"] == "💰 Rahul Sharma says they've paid ₹2,000"


def test_payment_page_when_paid_cancelled_or_unknown(raw_client, db_session):
    due = new_due(db_session)
    dues_service.mark_paid(db_session, due, "upi")
    assert "Paid. Thank you!" in raw_client.get(f"/pay/{due.token}").text
    other = new_due(db_session)
    dues_service.cancel(db_session, other)
    assert "no longer active" in raw_client.get(f"/pay/{other.token}").text
    assert raw_client.get("/pay/not-a-real-token").status_code == 404
    assert "Disallow: /pay/" in raw_client.get("/robots.txt").text


# ---------------------------------------------------------------------------
# Paid, cancelled, the list and the numbers
# ---------------------------------------------------------------------------
def test_mark_paid_counts_this_month(client, db_session):
    before = client.get("/dues/summary", params={"business_id": GARAGE}).json()
    due = new_due(db_session, amount=5000)
    start = last_event_id(GARAGE)
    r = client.post(f"/dues/{due.id}/paid", json={"via": "cash"})
    assert r.status_code == 200 and r.json()["status"] == "paid" and r.json()["paid_via"] == "cash"
    assert r.json()["label"].startswith("Paid on")
    after = client.get("/dues/summary", params={"business_id": GARAGE}).json()
    assert after["recovered_this_month"] == before["recovered_this_month"] + 5000
    assert after["paid_this_month"] == before["paid_this_month"] + 1
    assert events(GARAGE, "payment.received", start)[0]["title"] == "💰 ₹5,000 received from Rahul Sharma"
    assert client.post(f"/dues/{due.id}/paid", json={"via": "upi"}).status_code == 400   # not twice
    assert client.post(f"/dues/{due.id}/reopen").json()["status"] == "open"
    assert client.post(f"/dues/{due.id}/cancel").json()["status"] == "cancelled"
    assert client.post(f"/dues/{due.id}/cancel").status_code == 400


def test_summary_waiting_and_overdue(db_session):
    db_session.execute(Due.__table__.delete().where(Due.business_id == GARAGE))
    db_session.commit()
    today = NOON.date()
    new_due(db_session, amount=1000, due_date=today - timedelta(days=2))
    new_due(db_session, amount=3000, due_date=today + timedelta(days=2))
    paid = new_due(db_session, amount=500)
    dues_service.mark_paid(db_session, paid, "upi", now=NOON)
    claimed = new_due(db_session, amount=700)
    dues_service.customer_says_paid(db_session, claimed)
    s = dues_service.summary(db_session, GARAGE, NOON)
    assert s == {"recovered_this_month": 500, "paid_this_month": 1, "recovered_last_month": 0, "waiting": 4700,
                 "open": 3, "overdue": 1000, "overdue_count": 1, "says_paid": 1}
    order = [d.amount for d in dues_service.listing(db_session, GARAGE, "open", now=NOON)]
    assert order == [700, 1000, 3000]                 # "says paid" first, then the most overdue


# ---------------------------------------------------------------------------
# Sending the link / a reminder by hand
# ---------------------------------------------------------------------------
def test_sent_from_my_phone_goes_into_the_chat(client, db_session):
    lead = a_lead(db_session)
    due = new_due(db_session, lead=lead)
    r = client.post(f"/dues/{due.id}/send", json={"text": "Here's the link", "via": "phone", "kind": "request"})
    assert r.status_code == 200 and r.json()["delivery"] == "logged" and r.json()["due"]["reminders_sent"] == 0
    r = client.post(f"/dues/{due.id}/send", json={"text": "Gentle reminder", "via": "phone", "kind": "reminder"})
    assert r.json()["due"]["reminders_sent"] == 1 and r.json()["due"]["last_reminder_at"]
    db_session.refresh(lead)
    assert [m.text for m in lead.messages if m.direction == "outbound"] == ["Here's the link", "Gentle reminder"]


def test_send_through_the_connected_whatsapp(client, db_session):
    db_session.add(Connection(business_id=GARAGE, platform="whatsapp", external_id="mock_whatsapp_2",
                              display_name="+91 98100 00002", mode="mock"))
    db_session.commit()
    lead = a_lead(db_session, hours_ago=2, phone="919811066005")
    due = new_due(db_session, lead=lead)
    assert client.get(f"/dues/{due.id}").json()["ready"]["how"] == "app"
    r = client.post(f"/dues/{due.id}/send", json={"text": "Pay here", "via": "app"})
    assert r.json()["delivery"] == "sent" and outbox.MOCK_SENT[-1]["text"] == "Pay here"
    walk_in = new_due(db_session)
    assert client.post(f"/dues/{walk_in.id}/send", json={"text": "x", "via": "app"}).status_code == 400


# ---------------------------------------------------------------------------
# Automatic reminders
# ---------------------------------------------------------------------------
def _only(db, due):
    """Only `due` is open, so the scheduler checks are about it alone."""
    db.execute(Due.__table__.update().where(Due.id != due.id, Due.status == "open").values(status="cancelled"))
    db.commit()


def test_automatic_reminders_are_off_by_default(db_session):
    due = new_due(db_session, due_date=NOON.date())
    _only(db_session, due)
    assert dues_service.send_due_reminders(db_session, NOON) == 0


def test_automatic_reminder_schedule(db_session):
    garage = db_session.get(Business, GARAGE)
    dues_service.update_settings(db_session, garage, {"auto_reminders": True})
    lead = a_lead(db_session)
    start = NOON.date()
    due = new_due(db_session, lead=lead, due_date=start)
    _only(db_session, due)
    morning = datetime(2026, 10, 24, 9, 0, tzinfo=IST)
    assert dues_service.send_due_reminders(db_session, morning) == 0                      # before 10am
    assert dues_service.send_due_reminders(db_session, NOON) == 1                         # on the due date
    assert MockMessenger.sent[-1]["phone"] == "919811066001"
    assert dues_service.send_due_reminders(db_session, NOON + timedelta(hours=2)) == 0    # not twice a day
    assert dues_service.send_due_reminders(db_session, NOON + timedelta(days=2)) == 0     # 2nd: 3 days after
    assert dues_service.send_due_reminders(db_session, NOON + timedelta(days=3)) == 1
    assert dues_service.send_due_reminders(db_session, NOON + timedelta(days=6)) == 0     # 3rd: 7 days after
    assert dues_service.send_due_reminders(db_session, NOON + timedelta(days=7)) == 1
    assert dues_service.send_due_reminders(db_session, NOON + timedelta(days=20)) == 0    # 3 at most
    db_session.refresh(due)
    assert due.reminders_sent == 3
    db_session.refresh(lead)
    auto = [m for m in lead.messages if m.direction == "outbound"]
    assert len(auto) == 3 and auto[0].delivery == "logged" and auto[0].delivery_error == "Practice mode: not delivered"
    assert lead.status == "quoted"                                                        # automatic: status stays


def test_no_reminder_when_claimed_paused_or_no_date(db_session, monkeypatch):
    dues_service.update_settings(db_session, db_session.get(Business, GARAGE), {"auto_reminders": True})
    claimed = new_due(db_session, due_date=NOON.date())
    _only(db_session, claimed)
    dues_service.customer_says_paid(db_session, claimed)
    assert dues_service.send_due_reminders(db_session, NOON) == 0
    no_date = new_due(db_session)
    _only(db_session, no_date)
    assert dues_service.send_due_reminders(db_session, NOON) == 0
    dated = new_due(db_session, due_date=NOON.date() - timedelta(days=1))
    _only(db_session, dated)
    monkeypatch.setattr(dues_service.billing_service, "paused_business_ids", lambda db: {GARAGE})
    assert dues_service.send_due_reminders(db_session, NOON) == 0


# ---------------------------------------------------------------------------
# Demo data and the owner's data export
# ---------------------------------------------------------------------------
def test_demo_businesses_have_payments(db_session):
    for business_id in (GYM, GARAGE):
        s = dues_service.summary(db_session, business_id)
        assert s["recovered_this_month"] > 0 and s["open"] >= 4 and s["says_paid"] == 1


def test_dues_are_in_the_data_export(db_session):
    raw = account_service.export_zip(db_session, GARAGE)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        data = json.loads(z.read("all-data.json"))
        assert "customer_dues.csv" in z.namelist()
    assert len(data["customer_dues"]) == len(list(db_session.scalars(select(Due).where(Due.business_id == GARAGE))))
    assert data["customer_dues"][0]["amount_rs"] > 0
