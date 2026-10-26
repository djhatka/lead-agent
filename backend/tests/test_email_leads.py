"""
Task 24 checks (part 1): the email lead reader.

The emails below are realistic examples written for the tests (not copies of
real platform emails): labelled lines, HTML tables, hand-forwarded emails...
"""

from email.message import EmailMessage

import pytest
from sqlalchemy import select

from app.config import settings
from app.models import InboundEmail, Lead
from app.services import email_leads

KEY = {"X-Inbound-Key": "change-me-inbound"}


def login(client, email="gym@demo.in", password="demo1234"):
    r = client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture
def address(raw_client):
    return raw_client.get("/email-leads", headers=login(raw_client)).json()["address"]


def raw_email(to, sender="Justdial <leads@justdial.com>", subject="New enquiry from Justdial", text=None, html=None,
              message_id="<jd-1001@justdial.com>") -> bytes:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"], msg["Message-ID"] = sender, to, subject, message_id
    if text is not None:
        msg.set_content(text)
        if html:
            msg.add_alternative(html, subtype="html")
    else:
        msg.set_content(html, subtype="html")
    return msg.as_bytes()


JUSTDIAL = """Dear Iron Pulse Fitness,

You have received a new enquiry.

Caller Name : Rohan Malhotra
Mobile : +91 98101 23456
Requirement : Personal training
Area : Janakpuri, Delhi

For help call our customer care 8888888888.
"""


def deliver(client, raw: bytes, envelope_to: str = "", headers=None):
    extra = {"Content-Type": "message/rfc822", **KEY, **(headers or {})}
    if envelope_to:
        extra["X-Envelope-To"] = envelope_to
    return client.post("/webhooks/email", content=raw, headers=extra)


# ---------------------------------------------------------------------------
# The address
# ---------------------------------------------------------------------------
def test_each_business_gets_its_own_address(raw_client):
    gym = raw_client.get("/email-leads", headers=login(raw_client)).json()
    assert gym["address"].startswith("leads-") and gym["address"].endswith("@in.example.com")
    assert raw_client.get("/email-leads", headers=login(raw_client)).json()["address"] == gym["address"]   # stable
    garage = raw_client.get("/email-leads", headers=login(raw_client, "garage@demo.in")).json()
    assert garage["address"] != gym["address"]
    assert len(gym["gmail_steps"]) == 4 and "Justdial" in gym["platforms"]


def test_new_address_if_the_old_one_gets_spam(raw_client, address):
    assert raw_client.post("/email-leads/rotate", headers=login(raw_client, "staff@demo.in")).status_code == 403
    new = raw_client.post("/email-leads/rotate", headers=login(raw_client)).json()["address"]
    assert new != address
    r = deliver(raw_client, raw_email(address, text=JUSTDIAL)).json()
    assert r["new_leads"] == 0 and "Not addressed" in r["notes"][0]          # the old address stops working


def test_the_doorbell_needs_the_secret_key(raw_client, address):
    raw = raw_email(address, text=JUSTDIAL)
    assert raw_client.post("/webhooks/email", content=raw, headers={"Content-Type": "message/rfc822"}).status_code == 401
    assert deliver(raw_client, raw, headers={"X-Inbound-Key": "guess"}).status_code == 401


# ---------------------------------------------------------------------------
# Reading lead emails
# ---------------------------------------------------------------------------
def test_justdial_email_becomes_a_lead(raw_client, db_session, address):
    r = deliver(raw_client, raw_email("owner@gmail.com", text=JUSTDIAL), envelope_to=address).json()
    assert r["new_leads"] == 1 and r["ai_analysis_queued"] == 1
    lead = db_session.get(Lead, r["lead_ids"][0])
    assert lead.business_id == 1 and lead.source == "justdial"
    assert lead.name == "Rohan Malhotra" and lead.phone == "+919810123456"         # not the helpline
    assert lead.service == "Personal training" and lead.area == "Janakpuri, Delhi"
    log = db_session.scalar(select(InboundEmail))
    assert log.status == "lead" and log.lead_id == lead.id and log.platform == "justdial"

    again = deliver(raw_client, raw_email("owner@gmail.com", text=JUSTDIAL), envelope_to=address).json()
    assert again["duplicates"] == 1                                                # same email twice → once


def test_html_table_email(raw_client, db_session, address):
    html = ("<html><body><p>New lead for you on <b>Sulekha</b></p><table>"
            "<tr><td>Customer Name</td><td>Sunita Rao</td></tr>"
            "<tr><td>Mobile No</td><td>09876543210</td></tr>"
            "<tr><td>Looking for</td><td>Zumba classes</td></tr>"
            "<tr><td>Locality</td><td>Tilak Nagar</td></tr></table>"
            "<p>Helpline: 7777777777</p><style>p{color:red}</style></body></html>")
    r = deliver(raw_client, raw_email(address, sender="Sulekha <no-reply@mailer.sulekha.com>", html=html,
                                      message_id="<s-77@sulekha.com>")).json()
    lead = db_session.get(Lead, r["lead_ids"][0])
    assert (lead.source, lead.name, lead.phone, lead.service, lead.area) == (
        "sulekha", "Sunita Rao", "+919876543210", "Zumba classes", "Tilak Nagar")


def test_json_from_an_email_service(raw_client, db_session, address):
    postmark = {"From": "Practo <leads@practo.com>", "OriginalRecipient": address, "Subject": "New appointment request",
                "TextBody": "Patient Name: Kavita Joshi\nPhone: 9811055555\nTreatment: Root canal\n",
                "MessageID": "pm-123"}
    r = raw_client.post("/webhooks/email", json=postmark, headers=KEY).json()
    lead = db_session.get(Lead, r["lead_ids"][0])
    assert lead.source == "practo" and lead.name == "Kavita Joshi" and lead.service == "Root canal"


def test_form_post_from_an_email_service(raw_client, db_session, address):
    mailgun = {"recipient": address, "sender": "buyleads@indiamart.com", "subject": "Buy lead: Gym equipment",
               "body-plain": "Buyer Name - Arjun Mehta\nMobile Number - 98990 11223\nRequirement - Treadmill",
               "Message-Id": "<mg-9@indiamart.com>"}
    r = raw_client.post("/webhooks/email", data=mailgun, headers=KEY).json()
    lead = db_session.get(Lead, r["lead_ids"][0])
    assert (lead.source, lead.name, lead.phone) == ("indiamart", "Arjun Mehta", "+919899011223")


def test_hand_forwarded_email(raw_client, db_session, address):
    text = ("Please add this\n\n---------- Forwarded message ---------\n"
            "From: Justdial <noreply@justdial.com>\nSubject: Enquiry\n\n" + JUSTDIAL)
    r = deliver(raw_client, raw_email(address, sender="Anmol <owner@gmail.com>", subject="Fwd: Enquiry", text=text,
                                      message_id="<fwd-1@gmail.com>")).json()
    assert db_session.get(Lead, r["lead_ids"][0]).source == "justdial"


def test_customer_writes_directly(raw_client, db_session, address):
    r = deliver(raw_client, raw_email(address, sender="Priya Kapoor <priya.k@gmail.com>", subject="Membership fees?",
                                      text="Hi, what are the fees for the evening batch?\n\n> old quoted text",
                                      message_id="<direct-1@gmail.com>")).json()
    lead = db_session.get(Lead, r["lead_ids"][0])
    assert lead.source == "email" and lead.name == "Priya Kapoor"
    assert lead.details["email"] == "priya.k@gmail.com"
    assert "evening batch" in lead.first_message and "old quoted" not in lead.first_message


def test_gmail_forwarding_confirmation(raw_client, db_session, address):
    text = ("Anmol (owner@gmail.com) has requested to automatically forward mail to your email address.\n"
            "Confirmation code: 178236491\n\nTo allow, click:\n"
            "https://mail-settings.google.com/mail/vf-%5BANGjdJ-abc%5D-xyz\n")
    r = deliver(raw_client, raw_email(address, sender="Gmail Team <forwarding-noreply@google.com>",
                                      subject="(#178236491) Gmail Forwarding Confirmation", text=text,
                                      message_id="<g-1@google.com>")).json()
    assert r["new_leads"] == 0
    setup = raw_client.get("/email-leads", headers=login(raw_client)).json()
    assert setup["gmail_confirmation_code"] == "178236491"
    assert setup["gmail_confirmation_link"].startswith("https://mail-settings.google.com/mail/vf-")
    events = raw_client.get("/live/recent", params={"business_id": 1}, headers=login(raw_client)).json()
    assert any(e["type"] == "email.confirm" and e["data"]["code"] == "178236491" for e in events)


def test_unreadable_email_is_kept_for_the_owner(raw_client, address):
    r = deliver(raw_client, raw_email(address, sender="Justdial <promo@justdial.com>", subject="Boost your listing!",
                                      text="Upgrade to Platinum for more leads. Call 1800-123-4567.",
                                      message_id="<promo-1@justdial.com>")).json()
    assert r["new_leads"] == 0 and "unparsed" in r["notes"][0]
    recent = raw_client.get("/email-leads", headers=login(raw_client)).json()["recent"]
    assert recent[0]["status"] == "unparsed" and recent[0]["subject"] == "Boost your listing!"


def test_logs_are_private(raw_client, address):
    deliver(raw_client, raw_email(address, text=JUSTDIAL))
    assert raw_client.get("/email-leads", headers=login(raw_client, "garage@demo.in")).json()["recent"] == []


def test_try_it_button(raw_client, db_session):
    r = raw_client.post("/email-leads/test", headers=login(raw_client)).json()
    lead = db_session.get(Lead, r["lead_ids"][0])
    assert lead.source == "justdial" and lead.name == "Rohan Malhotra" and lead.phone == "+919810123456"


def test_reader_in_plain_words():
    found = email_leads.extract("Hi, quote for my Creta please. Call me on 98765 43210. Customer care: 9999999999")
    assert found == {"phone": "98765 43210"}                      # the customer's number, not the helpline
    assert "phone" not in email_leads.extract("Customer care: 9999999999")
