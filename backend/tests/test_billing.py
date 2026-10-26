"""
Task 20 checks: free trial, plans, Razorpay payments (mock mode), the
paywall, plan limits, and Razorpay's renewal/failure doorbell.

Demo data plans: 1 gym = Growth (paid), 2 garage = free trial, 3 clinic = Pro (paid).
"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.config import settings
from app.models import GrowthReport, Lead, Payment, Post, Subscription
from app.services import billing_service, payment_gateway as gw
from app.services.growth_service import weekly_reviews_due
from app.services.reputation_service import request_for_lead
from app.services.scheduler_service import publish_due



@pytest.fixture(autouse=True)
def mock_payments(monkeypatch):
    """Make sure no test can ever reach real Razorpay."""
    monkeypatch.setattr(settings, "razorpay_key_id", "")
    monkeypatch.setattr(settings, "razorpay_key_secret", "")
    monkeypatch.setattr(settings, "razorpay_webhook_secret", "")


def login(client, email="gym@demo.in", password="demo1234"):
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def sub_of(db, business_id) -> Subscription:
    return db.scalar(select(Subscription).where(Subscription.business_id == business_id))


def now():
    return datetime.now(timezone.utc)


def ring_razorpay(client, event: dict, secret=gw.MOCK_WEBHOOK_SECRET):
    body = json.dumps(event).encode()
    return client.post("/webhooks/razorpay", content=body,
                       headers={"X-Razorpay-Signature": gw.sign(body, secret), "Content-Type": "application/json"})


def event(name, sub_id, payment_id=None, amount_paise=None, current_end=None):
    payload = {"subscription": {"entity": {"id": sub_id, "status": "active", "current_end": current_end}}}
    if payment_id:
        payload["payment"] = {"entity": {"id": payment_id, "amount": amount_paise, "currency": "INR"}}
    return {"entity": "event", "event": name, "payload": payload}


# ---------------------------------------------------------------------------
# Price list and trial
# ---------------------------------------------------------------------------
def test_price_list_is_public(raw_client):
    plans = raw_client.get("/billing/plans").json()
    assert [p["code"] for p in plans] == ["starter", "growth", "pro"]
    assert [p["price"] for p in plans] == [999, 2499, 4999]
    assert next(p for p in plans if p["code"] == "growth")["free_trial_days"] == 14
    assert plans[0]["weekly_review"] is False and plans[1]["weekly_review"] is True


def test_signup_starts_a_free_trial(raw_client):
    r = raw_client.post("/auth/signup", json={"name": "Priya", "email": "priya@glow.in", "password": "salon-2026",
                                              "business_name": "Glow Salon", "industry": "salon"})
    headers = {"Authorization": f"Bearer {r.json()['token']}"}
    status = raw_client.get("/billing/status", headers=headers).json()
    assert status["state"] == "trial" and status["usable"] and status["days_left"] == 14
    assert status["plan"] == "growth" and status["payments_mode"] == "mock"
    assert "14 days left" in status["message"]
    assert status["limits"]["staff_seats"] == 3 and status["limits"]["storage_mb"] == 5120
    assert status["used"] == {"staff_seats": 0, "social_accounts": 0, "storage_mb": 0}


def test_trial_end_locks_dashboard_but_keeps_enquiries(raw_client, db_session):
    garage = login(raw_client, "garage@demo.in")
    assert raw_client.get("/leads", params={"business_id": 2}, headers=garage).status_code == 200
    sub_of(db_session, 2).trial_ends_at = now() - timedelta(minutes=1)
    db_session.commit()

    r = raw_client.get("/leads", params={"business_id": 2}, headers=garage)
    assert r.status_code == 402 and "free trial has ended" in r.json()["detail"]
    status = raw_client.get("/billing/status", headers=garage).json()      # billing still opens
    assert status["state"] == "trial_ended" and not status["usable"]
    assert raw_client.get("/auth/me", headers=garage).status_code == 200

    form = {"name": "Kunal", "phone": "9811077777", "message": "Ceramic coating price for Creta?"}
    saved = raw_client.post("/webhooks/website", params={"business_id": 2}, json=form).json()
    assert saved["new_leads"] == 1                                          # the customer isn't lost

    admin = login(raw_client, "admin@demo.in", "admin1234")
    assert raw_client.get("/leads", params={"business_id": 2}, headers=admin).status_code == 200


def test_old_business_without_a_plan_gets_a_trial(raw_client):
    admin = login(raw_client, "admin@demo.in", "admin1234")
    new = raw_client.post("/businesses", json={"name": "Side Shop", "industry": "salon"}, headers=admin).json()
    status = raw_client.get("/billing/status", params={"business_id": new["id"]}, headers=admin).json()
    assert status["state"] == "trial" and status["days_left"] == 14


# ---------------------------------------------------------------------------
# Paying (mock mode)
# ---------------------------------------------------------------------------
def test_choose_a_plan_and_pay(raw_client, db_session):
    garage = login(raw_client, "garage@demo.in")
    checkout = raw_client.post("/billing/subscribe", json={"plan": "starter"}, headers=garage)
    assert checkout.status_code == 200
    c = checkout.json()
    assert c["mode"] == "mock" and c["key_id"] == "rzp_test_mock" and c["subscription_id"].startswith("sub_mock_")
    assert c["amount"] == 999 and c["plan_name"] == "Starter"
    assert raw_client.get("/billing/status", headers=garage).json()["state"] == "trial"   # not paid yet

    paid = raw_client.post("/billing/mock-pay", headers=garage).json()
    assert paid["state"] == "active" and paid["plan"] == "starter" and "renews on" in paid["message"]
    history = raw_client.get("/billing/payments", headers=garage).json()
    assert len(history) == 1 and history[0]["amount"] == 999 and history[0]["status"] == "paid"
    assert sub_of(db_session, 2).gateway_subscription_id == c["subscription_id"]


def test_a_faked_payment_is_refused(raw_client):
    garage = login(raw_client, "garage@demo.in")
    sub_id = raw_client.post("/billing/subscribe", json={"plan": "growth"}, headers=garage).json()["subscription_id"]
    fake = {"razorpay_payment_id": "pay_123", "razorpay_subscription_id": sub_id, "razorpay_signature": "0" * 64}
    r = raw_client.post("/billing/verify", json=fake, headers=garage)
    assert r.status_code == 400 and "couldn't be verified" in r.json()["detail"]

    # Signed with the right secret = what Razorpay's checkout really sends
    real = dict(fake, razorpay_signature=gw.sign(f"pay_123|{sub_id}", gw.MOCK_KEY_SECRET))
    ok = raw_client.post("/billing/verify", json=real, headers=garage)
    assert ok.status_code == 200 and ok.json()["state"] == "active"
    assert raw_client.post("/billing/verify", json=real, headers=garage).status_code == 200   # repeat is harmless
    assert len(raw_client.get("/billing/payments", headers=garage).json()) == 1


def test_signature_for_another_subscription_is_refused(raw_client):
    garage = login(raw_client, "garage@demo.in")
    raw_client.post("/billing/subscribe", json={"plan": "growth"}, headers=garage)
    other = {"razorpay_payment_id": "pay_1", "razorpay_subscription_id": "sub_someone_else",
             "razorpay_signature": gw.sign("pay_1|sub_someone_else", gw.MOCK_KEY_SECRET)}
    assert raw_client.post("/billing/verify", json=other, headers=garage).status_code == 400


def test_only_the_owner_pays(raw_client):
    staff = login(raw_client, "staff@demo.in")
    assert raw_client.post("/billing/subscribe", json={"plan": "pro"}, headers=staff).status_code == 403
    assert raw_client.post("/billing/cancel", headers=staff).status_code == 403
    assert raw_client.get("/billing/status", headers=staff).status_code == 200      # but can see it
    bad = raw_client.post("/billing/subscribe", json={"plan": "platinum"}, headers=login(raw_client))
    assert bad.status_code == 422


def test_already_on_that_plan(raw_client):
    r = raw_client.post("/billing/subscribe", json={"plan": "growth"}, headers=login(raw_client))
    assert r.status_code == 400 and "already" in r.json()["detail"]


def test_upgrade_keeps_the_old_plan_until_paid(raw_client, db_session):
    gym = login(raw_client)
    raw_client.post("/billing/subscribe", json={"plan": "pro"}, headers=gym)
    status = raw_client.get("/billing/status", headers=gym).json()
    assert status["plan"] == "growth" and status["state"] == "active" and status["checkout_open"]
    assert sub_of(db_session, 1).gateway_subscription_id == "sub_demo_1"     # the paid one is untouched

    # The old subscription renews while the upgrade window is still open: still counted
    ring_razorpay(raw_client, event("subscription.charged", "sub_demo_1", "pay_renew_1", 249900,
                                    int((now() + timedelta(days=31)).timestamp())))
    assert raw_client.post("/billing/mock-pay", headers=gym).json()["plan"] == "pro"
    sub = sub_of(db_session, 1)
    assert sub.gateway_subscription_id.startswith("sub_mock_") and sub.pending_plan is None
    amounts = [p["amount"] for p in raw_client.get("/billing/payments", headers=gym).json()]
    assert amounts[:2] == [4999, 2499] and len(amounts) == 5      # 3 demo months + renewal + Pro


def test_cancel_works_until_the_paid_days_end(raw_client):
    gym = login(raw_client)
    r = raw_client.post("/billing/cancel", headers=gym).json()
    assert r["state"] == "cancelling" and r["usable"] and "works until" in r["message"]
    assert raw_client.get("/leads", params={"business_id": 1}, headers=gym).status_code == 200
    assert raw_client.post("/billing/cancel", headers=gym).status_code == 400
    trial = raw_client.post("/billing/cancel", headers=login(raw_client, "garage@demo.in"))
    assert trial.status_code == 400 and "free trial" in trial.json()["detail"]
    overview = raw_client.get("/admin/billing", headers=login(raw_client, "admin@demo.in", "admin1234")).json()
    assert overview["monthly_recurring_revenue"] == 4999        # the gym won't renew any more


# ---------------------------------------------------------------------------
# Razorpay's doorbell
# ---------------------------------------------------------------------------
def test_webhook_needs_razorpays_signature(raw_client):
    body = json.dumps(event("subscription.charged", "sub_demo_1", "pay_x", 249900)).encode()
    assert raw_client.post("/webhooks/razorpay", content=body).status_code == 400
    assert raw_client.post("/webhooks/razorpay", content=body,
                           headers={"X-Razorpay-Signature": "f" * 64}).status_code == 400
    assert ring_razorpay(raw_client, event("subscription.charged", "sub_demo_1"), secret="wrong").status_code == 400


def test_monthly_renewal(raw_client, db_session):
    new_end = int((now() + timedelta(days=50)).timestamp())
    r = ring_razorpay(raw_client, event("subscription.charged", "sub_demo_1", "pay_june", 249900, new_end))
    assert r.status_code == 200 and "renewed" in r.json()["note"]
    sub = sub_of(db_session, 1)
    assert int(billing_service._utc(sub.current_period_end).timestamp()) == new_end
    ring_razorpay(raw_client, event("subscription.charged", "sub_demo_1", "pay_june", 249900, new_end))  # sent twice
    june = list(db_session.scalars(select(Payment).where(Payment.gateway_payment_id == "pay_june")))
    assert len(june) == 1 and june[0].amount == 2499                                # paise → rupees


def test_failed_payment_gives_grace_days_then_locks(raw_client, db_session):
    gym = login(raw_client)
    ring_razorpay(raw_client, event("subscription.halted", "sub_demo_1"))
    status = raw_client.get("/billing/status", headers=gym).json()
    assert status["state"] == "payment_failed" and status["usable"]
    assert "didn't go through" in status["message"]

    sub = sub_of(db_session, 1)
    sub.current_period_end = now() - timedelta(days=settings.payment_grace_days, minutes=1)
    db_session.commit()
    assert raw_client.get("/leads", params={"business_id": 1}, headers=gym).status_code == 402

    ring_razorpay(raw_client, event("subscription.charged", "sub_demo_1", "pay_retry", 249900,
                                    int((now() + timedelta(days=30)).timestamp())))       # card updated, paid
    assert raw_client.get("/leads", params={"business_id": 1}, headers=gym).status_code == 200


def test_webhook_can_finish_a_checkout_before_the_browser(raw_client, db_session):
    garage = login(raw_client, "garage@demo.in")
    sub_id = raw_client.post("/billing/subscribe", json={"plan": "pro"}, headers=garage).json()["subscription_id"]
    end = int((now() + timedelta(days=30)).timestamp())
    note = ring_razorpay(raw_client, event("subscription.charged", sub_id, "pay_first", 499900, end)).json()["note"]
    assert "active" in note
    assert raw_client.get("/billing/status", headers=garage).json()["plan"] == "pro"
    late = {"razorpay_payment_id": "pay_first", "razorpay_subscription_id": sub_id,
            "razorpay_signature": gw.sign(f"pay_first|{sub_id}", gw.MOCK_KEY_SECRET)}
    assert raw_client.post("/billing/verify", json=late, headers=garage).status_code == 200    # browser arrives late


def test_cancelled_by_razorpay_and_unknown_events(raw_client, db_session):
    assert "status now cancelled" in ring_razorpay(raw_client, event("subscription.cancelled", "sub_demo_3")).json()["note"]
    assert sub_of(db_session, 3).status == "cancelled"
    assert "unknown subscription" in ring_razorpay(raw_client, event("subscription.charged", "sub_nobody")).json()["note"]
    assert "ignored" in ring_razorpay(raw_client, {"event": "payment.captured", "payload": {}}).json()["note"]


# ---------------------------------------------------------------------------
# Plan limits
# ---------------------------------------------------------------------------
def test_starter_plan_limits(raw_client, db_session):
    sub_of(db_session, 1).plan = "starter"                 # the gym downgrades (it has 1 staff already)
    db_session.commit()
    gym = login(raw_client)

    invite = {"name": "Rohit", "email": "rohit@gym.in", "password": "frontdesk1"}
    r = raw_client.post("/team", json=invite, headers=gym)
    assert r.status_code == 403 and r.json()["detail"] == "Your Starter plan allows 1 staff member. Upgrade to Growth for up to 3."

    account = {"business_id": 1, "platform": "youtube", "handle": "ironpulse", "display_name": "Iron Pulse"}
    r = raw_client.post("/social/accounts", json=account, headers=gym)
    assert r.status_code == 403 and "Starter plan allows 2 social accounts" in r.json()["detail"]

    r = raw_client.post("/growth/review", params={"business_id": 1}, headers=gym)
    assert r.status_code == 403 and "Upgrade to Growth (₹2,499/month)" in r.json()["detail"]

    lead = db_session.scalar(select(Lead).where(Lead.business_id == 1, Lead.phone.is_not(None)))
    assert request_for_lead(db_session, lead) is None      # no automatic review requests on Starter


def test_growth_plan_has_room(raw_client):
    gym = login(raw_client)
    invite = {"name": "Rohit", "email": "rohit@gym.in", "password": "frontdesk1"}
    assert raw_client.post("/team", json=invite, headers=gym).status_code == 201


# ---------------------------------------------------------------------------
# Background jobs respect the plan
# ---------------------------------------------------------------------------
def test_scheduled_post_not_published_after_plan_ends(db_session):
    sub_of(db_session, 2).trial_ends_at = now() - timedelta(hours=1)
    post = db_session.scalar(select(Post).where(Post.business_id == 2, Post.status == "published"))
    post.status, post.scheduled_for = "scheduled", now() - timedelta(minutes=1)
    db_session.commit()
    publish_due(db_session)
    assert post.status == "failed" and "plan has ended" in post.publish_error


def test_weekly_reviews_only_for_plans_that_include_them(db_session):
    sub_of(db_session, 1).plan = "starter"                         # gym: Starter (no weekly review)
    sub_of(db_session, 2).trial_ends_at = now() - timedelta(hours=1)  # garage: trial over
    db_session.commit()
    before = {r.business_id for r in db_session.scalars(select(GrowthReport))}
    monday = datetime(2026, 10, 19, 5, 0, tzinfo=timezone.utc)      # Monday 10:30am India time
    weekly_reviews_due(db_session, now=monday)
    after = {r.business_id for r in db_session.scalars(select(GrowthReport))}
    assert 1 not in after - before and 2 not in after - before    # skipped
    assert 3 in after                                             # the clinic (Pro) got its review


# ---------------------------------------------------------------------------
# Your money dashboard
# ---------------------------------------------------------------------------
def test_admin_money_dashboard(raw_client):
    admin = login(raw_client, "admin@demo.in", "admin1234")
    money = raw_client.get("/admin/billing", headers=admin).json()
    assert money["monthly_recurring_revenue"] == 2499 + 4999
    assert money["paid_last_30_days"] == 2499 + 4999
    assert money["by_state"] == {"active": 2, "trial": 1} and money["by_plan"] == {"growth": 1, "pro": 1}
    assert raw_client.get("/admin/billing", headers=login(raw_client)).status_code == 403


def test_access_rules_in_plain_maths(db_session):
    sub = Subscription(business_id=1, plan="growth", status="trialing", trial_ends_at=now() + timedelta(hours=30))
    assert billing_service.access_for(sub).days_left == 2
    sub.status, sub.current_period_end = "active", now() - timedelta(days=1)
    assert billing_service.access_for(sub).state == "active"         # renewal a bit late: grace days
    sub.current_period_end = now() - timedelta(days=settings.payment_grace_days + 1)
    assert billing_service.access_for(sub).state == "ended"
    sub.status, sub.current_period_end = "cancelled", now() + timedelta(days=5)
    assert billing_service.access_for(sub).state == "cancelling"
