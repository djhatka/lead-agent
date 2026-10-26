"""
Task 23 checks: forgot password, welcome, team invites, trial reminders,
receipts, payment-failed emails, real sending (fake SMTP server) and retries.

`email_outbox` (conftest) = the list of emails the mock mailer "sent".
"""

import json
import re
import smtplib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from app.config import settings
from app.models import Email, PasswordReset, Subscription, User
from app.services import email_service, payment_gateway as gw

DAYTIME = datetime(2026, 10, 19, 6, 0, tzinfo=timezone.utc)        # 11:30am India time
NIGHT = datetime(2026, 10, 19, 18, 0, tzinfo=timezone.utc)         # 11:30pm India time


def login(client, email="gym@demo.in", password="demo1234"):
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def token_in(email: dict) -> str:
    return re.search(r"token=([A-Za-z0-9_\-]+)", email["text"]).group(1)


def of_kind(outbox, kind):
    return [e for e in outbox if e["kind"] == kind]


# ---------------------------------------------------------------------------
# Forgot password
# ---------------------------------------------------------------------------
def test_forgot_and_reset_password(raw_client, email_outbox):
    phone = login(raw_client)
    r = raw_client.post("/auth/forgot-password", json={"email": " GYM@demo.in "})
    assert r.status_code == 202 and "If that email has an account" in r.json()["message"]
    [mail] = of_kind(email_outbox, "password_reset")
    assert mail["to"] == "gym@demo.in" and "localhost:5173/reset-password?token=" in mail["text"]
    assert "60 minutes" in mail["text"]

    done = raw_client.post("/auth/reset-password", json={"token": token_in(mail), "new_password": "brand-new-pass"})
    assert done.status_code == 200 and done.json()["user"]["email"] == "gym@demo.in"   # logged in straight away
    assert raw_client.get("/auth/me", headers=phone).status_code == 401              # old logins are out
    assert raw_client.post("/auth/login", json={"email": "gym@demo.in", "password": "demo1234"}).status_code == 401
    login(raw_client, password="brand-new-pass")
    assert of_kind(email_outbox, "password_changed")                                  # "wasn't you?" notice

    again = raw_client.post("/auth/reset-password", json={"token": token_in(mail), "new_password": "another-pass"})
    assert again.status_code == 400 and "already used" in again.json()["detail"]      # works only once


def test_unknown_email_gets_the_same_answer_and_no_email(raw_client, email_outbox):
    known = raw_client.post("/auth/forgot-password", json={"email": "gym@demo.in"}).json()
    unknown = raw_client.post("/auth/forgot-password", json={"email": "nobody@nowhere.in"}).json()
    assert known == unknown
    assert [e["to"] for e in email_outbox] == ["gym@demo.in"]


def test_reset_links_are_limited_and_expire(raw_client, db_session, email_outbox):
    for _ in range(5):
        raw_client.post("/auth/forgot-password", json={"email": "gym@demo.in"})
    assert len(of_kind(email_outbox, "password_reset")) == 3                         # max 3 per hour
    for row in db_session.scalars(select(PasswordReset)):
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()
    r = raw_client.post("/auth/reset-password", json={"token": token_in(email_outbox[0]), "new_password": "brand-new-pass"})
    assert r.status_code == 400 and "expired" in r.json()["detail"]
    fake = raw_client.post("/auth/reset-password", json={"token": "x" * 43, "new_password": "brand-new-pass"})
    assert fake.status_code == 400


def test_only_the_newest_link_matters(raw_client, email_outbox):
    raw_client.post("/auth/forgot-password", json={"email": "gym@demo.in"})
    raw_client.post("/auth/forgot-password", json={"email": "gym@demo.in"})
    first, second = of_kind(email_outbox, "password_reset")
    assert raw_client.post("/auth/reset-password", json={"token": token_in(second),
                                                          "new_password": "brand-new-pass"}).status_code == 200
    old = raw_client.post("/auth/reset-password", json={"token": token_in(first), "new_password": "sneaky-pass1"})
    assert old.status_code == 400                                                     # older links die too


def test_reset_lifts_the_wrong_password_lock(raw_client, email_outbox):
    from app.services import auth_service
    auth_service._failures.clear()
    for _ in range(5):
        raw_client.post("/auth/login", json={"email": "gym@demo.in", "password": "guess-guess"})
    assert raw_client.post("/auth/login", json={"email": "gym@demo.in", "password": "demo1234"}).status_code == 429
    raw_client.post("/auth/forgot-password", json={"email": "gym@demo.in"})
    raw_client.post("/auth/reset-password", json={"token": token_in(email_outbox[-1]), "new_password": "brand-new-pass"})
    login(raw_client, password="brand-new-pass")
    auth_service._failures.clear()


def test_removed_staff_get_no_reset_email(raw_client, db_session, email_outbox):
    staff = db_session.scalar(select(User).where(User.email == "staff@demo.in"))
    staff.is_active = False
    db_session.commit()
    raw_client.post("/auth/forgot-password", json={"email": "staff@demo.in"})
    assert email_outbox == []


def test_change_password_sends_a_notice(raw_client, email_outbox):
    raw_client.post("/auth/change-password", headers=login(raw_client),
                    json={"current_password": "demo1234", "new_password": "newpass123"})
    assert of_kind(email_outbox, "password_changed")[0]["to"] == "gym@demo.in"


# ---------------------------------------------------------------------------
# Welcome and team invites
# ---------------------------------------------------------------------------
def test_welcome_email_on_signup(raw_client, email_outbox):
    raw_client.post("/auth/signup", json={"name": "Priya Mehta", "email": "priya@glow.in", "password": "salon-2026",
                                          "business_name": "<b>Glow</b> Salon", "industry": "salon"})
    [mail] = of_kind(email_outbox, "welcome")
    assert mail["to"] == "priya@glow.in" and mail["subject"].startswith("Welcome to") and "Priya!" in mail["subject"]
    trial_end = (datetime.now(timezone.utc) + timedelta(days=14)).astimezone(timezone(timedelta(hours=5, minutes=30)))
    assert f"{trial_end.day} {trial_end:%B %Y}" in mail["text"]
    assert "&lt;b&gt;Glow&lt;/b&gt;" in mail["html"] and "<b>Glow</b>" not in mail["html"]     # escaped
    files = list(Path(settings.outbox_dir).glob("*-welcome.html"))
    assert len(files) == 1 and "Connect your WhatsApp" in files[0].read_text(encoding="utf-8")


def test_staff_choose_their_own_password(raw_client, email_outbox):
    owner = login(raw_client)
    r = raw_client.post("/team", headers=owner, json={"name": "Rohit Verma", "email": "rohit@ironpulse.in"})
    assert r.status_code == 201
    [mail] = of_kind(email_outbox, "staff_invite")
    assert mail["to"] == "rohit@ironpulse.in" and "added you to the team" in mail["text"] and "3 days" in mail["text"]
    assert "welcome=1" in mail["text"]
    done = raw_client.post("/auth/reset-password", json={"token": token_in(mail), "new_password": "rohit-pass-1"})
    assert done.status_code == 200 and done.json()["user"]["role"] == "staff"
    login(raw_client, "rohit@ironpulse.in", "rohit-pass-1")
    assert not of_kind(email_outbox, "password_changed")          # no scary "password changed" for a new member


def test_invite_link_lasts_three_days(raw_client, db_session, email_outbox):
    raw_client.post("/team", headers=login(raw_client), json={"name": "Rohit Verma", "email": "rohit@ironpulse.in"})
    invite = db_session.scalar(select(PasswordReset).where(PasswordReset.purpose == "invite"))
    lasts = email_service._utc(invite.expires_at) - email_service._utc(invite.created_at)
    assert timedelta(days=2, hours=23) < lasts <= timedelta(days=3)


# ---------------------------------------------------------------------------
# Trial reminders (the emails that bring paying customers)
# ---------------------------------------------------------------------------
def _garage_trial(db, ends):
    sub = db.scalar(select(Subscription).where(Subscription.business_id == 2))
    sub.trial_ends_at = ends
    db.commit()


def test_trial_ending_reminder_once(db_session, email_outbox):
    _garage_trial(db_session, DAYTIME + timedelta(days=9))
    assert email_service.trial_reminders(db_session, now=DAYTIME) == 0                    # too early
    _garage_trial(db_session, DAYTIME + timedelta(days=2, hours=20))
    assert email_service.trial_reminders(db_session, now=NIGHT) == 0                      # not at night
    assert email_service.trial_reminders(db_session, now=DAYTIME) == 1
    assert email_service.trial_reminders(db_session, now=DAYTIME + timedelta(hours=3)) == 0   # never twice
    email_service.deliver_pending(db_session)
    [mail] = of_kind(email_outbox, "trial_ending")
    assert mail["to"] == "garage@demo.in" and mail["subject"] == "Your free trial ends in 3 days"
    assert "₹999/month" in mail["text"] and "/billing/plans" in mail["text"]


def test_trial_ended_email_once(db_session, email_outbox):
    _garage_trial(db_session, DAYTIME - timedelta(hours=2))
    assert email_service.trial_reminders(db_session, now=DAYTIME) == 1
    assert email_service.trial_reminders(db_session, now=DAYTIME + timedelta(days=1)) == 0
    email_service.deliver_pending(db_session)
    [mail] = of_kind(email_outbox, "trial_ended")
    assert "still saving every new enquiry" in mail["text"]


def test_paying_businesses_get_no_trial_emails(db_session):
    for sub in db_session.scalars(select(Subscription).where(Subscription.status == "active")):
        sub.trial_ends_at = DAYTIME + timedelta(days=1)
    db_session.commit()
    _garage_trial(db_session, DAYTIME + timedelta(days=30))
    assert email_service.trial_reminders(db_session, now=DAYTIME) == 0


# ---------------------------------------------------------------------------
# Receipts and payment problems
# ---------------------------------------------------------------------------
def test_receipt_after_paying(raw_client, email_outbox):
    garage = login(raw_client, "garage@demo.in")
    sub_id = raw_client.post("/billing/subscribe", json={"plan": "starter"}, headers=garage).json()["subscription_id"]
    paid = {"razorpay_payment_id": "pay_R1", "razorpay_subscription_id": sub_id,
            "razorpay_signature": gw.sign(f"pay_R1|{sub_id}", gw.MOCK_KEY_SECRET)}
    raw_client.post("/billing/verify", json=paid, headers=garage)
    raw_client.post("/billing/verify", json=paid, headers=garage)                         # browser sends twice
    [mail] = of_kind(email_outbox, "receipt")
    assert mail["to"] == "garage@demo.in" and mail["subject"] == "Payment received: ₹999 for the Starter plan"
    assert "pay_R1" in mail["text"] and "Billed by: Lead Intel" in mail["text"]


def _ring(client, event):
    body = json.dumps(event).encode()
    return client.post("/webhooks/razorpay", content=body,
                       headers={"X-Razorpay-Signature": gw.sign(body, gw.MOCK_WEBHOOK_SECRET)})


def test_renewal_receipt_and_payment_failed(raw_client, email_outbox):
    end = int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp())
    _ring(raw_client, {"event": "subscription.charged", "payload": {
        "subscription": {"entity": {"id": "sub_demo_1", "current_end": end}},
        "payment": {"entity": {"id": "pay_renew_9", "amount": 249900}}}})
    assert "₹2,499" in of_kind(email_outbox, "receipt")[0]["subject"]

    halted = {"event": "subscription.halted", "payload": {"subscription": {"entity": {"id": "sub_demo_1"}}}}
    _ring(raw_client, halted)
    _ring(raw_client, halted)                                                    # Razorpay repeats itself
    [failed] = of_kind(email_outbox, "payment_failed")
    assert failed["to"] == "gym@demo.in" and "Update payment" in failed["html"]


# ---------------------------------------------------------------------------
# Real sending (a fake SMTP server) and retries
# ---------------------------------------------------------------------------
class FakeSMTP:
    sent: list = []
    fail_with: Exception | None = None
    log: list = []

    def __init__(self, host, port, timeout=None):
        FakeSMTP.log.append(("connect", host, port))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        FakeSMTP.log.append(("starttls",))

    def login(self, user, password):
        FakeSMTP.log.append(("login", user, password))

    def send_message(self, msg):
        if FakeSMTP.fail_with:
            raise FakeSMTP.fail_with
        FakeSMTP.sent.append(msg)


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.sent, FakeSMTP.log, FakeSMTP.fail_with = [], [], None
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    for name, value in {"smtp_host": "smtp-relay.brevo.com", "smtp_port": 587, "smtp_username": "me@brevo",
                        "smtp_password": "key-123", "email_from": "Lead Agent <hello@leadagent.in>",
                        "email_reply_to": "support@leadagent.in"}.items():
        monkeypatch.setattr(settings, name, value)
    return FakeSMTP


def test_real_sending_over_smtp(raw_client, db_session, smtp):
    raw_client.post("/auth/forgot-password", json={"email": "gym@demo.in"})
    assert ("connect", "smtp-relay.brevo.com", 587) in smtp.log and ("starttls",) in smtp.log
    assert ("login", "me@brevo", "key-123") in smtp.log
    [msg] = smtp.sent
    assert msg["To"] == "gym@demo.in" and msg["From"] == "Lead Agent <hello@leadagent.in>"
    assert msg["Reply-To"] == "support@leadagent.in" and msg["Subject"] == "Reset your password"
    parts = {p.get_content_type() for p in msg.walk()}
    assert {"text/plain", "text/html"} <= parts                                   # plain + nice version
    row = db_session.scalar(select(Email).where(Email.kind == "password_reset"))
    assert row.status == "sent" and row.attempts == 1 and row.sent_at


def test_failed_sends_are_retried_then_given_up(raw_client, db_session, smtp):
    smtp.fail_with = smtplib.SMTPServerDisconnected("provider down")
    raw_client.post("/auth/forgot-password", json={"email": "gym@demo.in"})
    row = db_session.scalar(select(Email).where(Email.kind == "password_reset"))
    assert row.status == "failed" and "provider down" in row.error and row.attempts == 1
    assert email_service.deliver_pending(db_session) == 0                          # waits a few minutes first

    smtp.fail_with = None
    row.created_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    db_session.commit()
    assert email_service.deliver_pending(db_session) == 1                          # retried → sent
    assert row.status == "sent" and row.attempts == 2

    smtp.fail_with = smtplib.SMTPServerDisconnected("down again")
    raw_client.post("/auth/forgot-password", json={"email": "gym@demo.in"})
    second = db_session.scalar(select(Email).where(Email.kind == "password_reset", Email.id != row.id))
    second.created_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    db_session.commit()
    for _ in range(5):
        email_service.deliver_pending(db_session)
    assert second.status == "failed" and second.attempts == 3                    # gives up after 3 tries


# ---------------------------------------------------------------------------
# Your email log
# ---------------------------------------------------------------------------
def test_admin_email_log_and_preview(raw_client):
    raw_client.post("/auth/forgot-password", json={"email": "gym@demo.in"})
    admin = login(raw_client, "admin@demo.in", "admin1234")
    log = raw_client.get("/admin/emails", headers=admin).json()
    assert log["mode"] == "mock" and log["items"][0]["kind"] == "password_reset"
    assert log["items"][0]["status"] == "sent"
    preview = raw_client.get(f"/admin/emails/{log['items'][0]['id']}/preview", headers=admin)
    assert preview.status_code == 200 and "Choose a new password" in preview.text
    assert "script-src 'none'" in preview.headers["content-security-policy"]
    assert raw_client.get("/admin/emails", headers=login(raw_client)).status_code == 403
