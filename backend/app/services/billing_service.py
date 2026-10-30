"""
Subscriptions: free trial → choose a plan → pay → renews every month.

The one question the whole app asks: "may this business use the dashboard
right now?" → access_for(subscription) answers with a state + a friendly line:

    trial           free trial running              ✅ usable
    active          paid, renews automatically      ✅
    cancelling      cancelled, paid days left       ✅ until the end date
    payment_failed  renewal failed, Razorpay retrying  ✅ for a few grace days
    trial_ended     trial over, no plan chosen      ❌ dashboard locked
    ended           paid time over                  ❌

Even when locked, the doorbells (webhooks) keep saving enquiries, so an
owner never loses a customer while they sort out payment.

Plan limits (staff seats, social accounts, weekly review, review requests)
come from app/plans.py: check_room() and require_feature() say "upgrade".
"""

import logging
import math
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import features
from app.config import settings
from app.models import Business, Media, Payment, SocialAccount, Subscription, User
from app.plans import PLANS, TRIAL_PLAN, Plan, cheapest_with, get_plan
from app.schemas import UTCDateTime
from app.services import email_service
from app.services import payment_gateway as gw
from app.services.event_bus import bus

logger = logging.getLogger("billing")
IST = ZoneInfo("Asia/Kolkata")
USABLE = ("trial", "active", "cancelling", "payment_failed")
FEATURE_WORDS = {"weekly_review": "the weekly AI growth review",
                 "review_requests": "automatic 'please review us' messages"}
LIMIT_WORDS = {"staff_seats": "staff member", "social_accounts": "social account"}


class BillingError(Exception):
    """Something the owner should be told, e.g. 'you're already on this plan'."""


class PlanLimit(BillingError):
    """The plan doesn't include this; the message says which plan does."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)     # SQLite forgets time zones


def _day(dt: datetime) -> str:
    local = dt.astimezone(IST)
    return f"{local.day} {local:%b %Y}"                                # 5 Nov 2026


# ---------------------------------------------------------------------------
# The subscription row
# ---------------------------------------------------------------------------
def start_trial(db: Session, business: Business, now: Optional[datetime] = None) -> Subscription:
    sub = Subscription(business_id=business.id, plan=TRIAL_PLAN, status="trialing",
                       trial_ends_at=(now or _now()) + timedelta(days=settings.trial_days))
    db.add(sub)
    db.flush()
    return sub


def subscription_for(db: Session, business_id: int) -> Subscription:
    """Every business has one. Older businesses without one get a fresh trial."""
    sub = db.scalar(select(Subscription).where(Subscription.business_id == business_id))
    if sub is None:
        sub = start_trial(db, db.get(Business, business_id))
        db.commit()
    return sub


# ---------------------------------------------------------------------------
# May they use it? (plain rules, no AI)
# ---------------------------------------------------------------------------
class Access(BaseModel):
    state: str
    usable: bool
    plan: str
    plan_name: str
    price: int
    message: str
    days_left: Optional[int] = None
    ends_at: Optional[UTCDateTime] = None
    checkout_open: bool = False


def access_for(sub: Subscription, now: Optional[datetime] = None) -> Access:
    now = now or _now()
    plan = get_plan(sub.plan)
    grace = timedelta(days=settings.payment_grace_days)

    if sub.status == "trialing":
        ends = _utc(sub.trial_ends_at)
        if now < ends:
            days = math.ceil((ends - now).total_seconds() / 86400)
            state, msg = "trial", f"Free trial: {days} day{'s' if days != 1 else ''} left. Choose a plan any time."
        else:
            state, days = "trial_ended", 0
            msg = "Your free trial has ended. Choose a plan to keep using your dashboard. Your enquiries are still being saved."
    else:
        ends = _utc(sub.current_period_end) or _utc(sub.trial_ends_at)
        days = max(0, math.ceil((ends - now).total_seconds() / 86400))
        if sub.status == "active" and sub.cancel_at_period_end and now < ends:
            state, msg = "cancelling", f"Cancelled: your {plan.name} plan works until {_day(ends)}."
        elif sub.status == "active" and now < ends + grace:
            state, msg = "active", f"{plan.name} plan: renews on {_day(ends)}."
        elif sub.status == "past_due" and now < ends + grace:
            state = "payment_failed"
            msg = f"Your last payment didn't go through. Update your payment by {_day(ends + grace)} to keep your dashboard."
        elif sub.status == "cancelled" and now < ends:
            state, msg = "cancelling", f"Cancelled: your {plan.name} plan works until {_day(ends)}."
        else:
            state, days = "ended", 0
            msg = "Your plan has ended. Choose a plan to continue. Your enquiries are still being saved."

    return Access(state=state, usable=state in USABLE, plan=plan.code, plan_name=plan.name, price=plan.price,
                  message=msg, days_left=days, ends_at=ends, checkout_open=bool(sub.pending_gateway_subscription_id))


def access(db: Session, business_id: int) -> Access:
    return access_for(subscription_for(db, business_id))


def paused_business_ids(db: Session) -> set[int]:
    """Businesses whose plan isn't usable: the background jobs skip them."""
    return {b for (b,) in db.execute(select(Business.id)) if not access(db, b).usable}


# ---------------------------------------------------------------------------
# Plan limits
# ---------------------------------------------------------------------------
def plan_for(db: Session, business_id: int) -> Plan:
    return get_plan(subscription_for(db, business_id).plan)


def has_feature(db: Session, business_id: int, feature: str) -> bool:
    return bool(getattr(plan_for(db, business_id), feature))


def require_feature(db: Session, business_id: int, feature: str) -> None:
    plan = plan_for(db, business_id)
    if not getattr(plan, feature):
        better = cheapest_with(feature)
        raise PlanLimit(f"Your {plan.name} plan doesn't include {FEATURE_WORDS[feature]}. "
                        f"Upgrade to {better.name} (₹{better.price:,}/month) to get it.")


def usage(db: Session, business_id: int) -> dict[str, int]:
    staff = db.scalar(select(func.count(User.id)).where(User.business_id == business_id, User.role == "staff",
                                                        User.is_active))
    accounts = db.scalar(select(func.count(SocialAccount.id)).where(SocialAccount.business_id == business_id))
    stored = db.scalar(select(func.coalesce(func.sum(Media.size_bytes), 0)).where(Media.business_id == business_id))
    return {"staff_seats": staff, "social_accounts": accounts, "storage_mb": math.ceil(stored / (1024 * 1024))}


def check_room(db: Session, business_id: int, limit: str) -> None:
    """Before adding one more staff member / social account."""
    plan = plan_for(db, business_id)
    allowed = getattr(plan, limit)
    if usage(db, business_id)[limit] >= allowed:
        bigger = [p for p in PLANS.values() if getattr(p, limit) > allowed]
        word = LIMIT_WORDS[limit] + ("s" if allowed != 1 else "")
        tip = f" Upgrade to {bigger[0].name} for up to {getattr(bigger[0], limit)}." if bigger else ""
        raise PlanLimit(f"Your {plan.name} plan allows {allowed} {word}.{tip}")


# ---------------------------------------------------------------------------
# Paying: checkout → verify (the browser part)
# ---------------------------------------------------------------------------
class Checkout(BaseModel):
    """Everything the website needs to open Razorpay's payment window."""

    mode: str                      # "mock" (pretend) or "real"
    key_id: str                    # Razorpay checkout option "key"
    subscription_id: str           # Razorpay checkout option "subscription_id"
    plan: str
    plan_name: str
    amount: int                    # ₹ per month
    short_url: Optional[str]       # a Razorpay payment link (real mode), handy to send on WhatsApp
    business_name: str


def payments_are_manual() -> bool:
    """Live site without Razorpay keys: owners pay you by UPI or bank transfer, and you switch their plan on
    by hand (activate_manually). The pretend "mock" payment is never allowed there: it would give plans away."""
    return features.is_light() and not settings.payments_enabled


def _manual_payment_message() -> str:
    contact = settings.support_phone or settings.support_email or "us"
    return (f"Online payment isn't switched on yet. Pay by UPI or bank transfer (ask {contact} for the details) "
            f"and we'll activate your plan the same day.")


def start_checkout(db: Session, business_id: int, plan_code: str) -> Checkout:
    if plan_code not in PLANS:
        raise BillingError(f"Unknown plan '{plan_code}'")
    if payments_are_manual():
        raise BillingError(_manual_payment_message())
    sub = subscription_for(db, business_id)
    now_access = access_for(sub)
    if sub.plan == plan_code and now_access.state == "active":
        raise BillingError(f"You're already on the {PLANS[plan_code].name} plan")
    gateway = gw.get_gateway()
    try:
        created = gateway.create_subscription(plan_code, business_id)
    except gw.GatewayError as problem:
        raise BillingError(str(problem)) from problem
    sub.pending_plan, sub.pending_gateway_subscription_id = plan_code, created["id"]
    db.commit()
    plan = PLANS[plan_code]
    return Checkout(mode=gateway.mode, key_id=gateway.key_id, subscription_id=created["id"], plan=plan.code,
                    plan_name=plan.name, amount=plan.price, short_url=created.get("short_url"),
                    business_name=db.get(Business, business_id).name)


def confirm_payment(db: Session, business_id: int, payment_id: str, subscription_id: str,
                    signature: str) -> Access:
    """The browser says 'paid!': we only believe it if the signature matches.
    We check against the subscription id WE saved, not just the one sent to us."""
    sub = subscription_for(db, business_id)
    expected = sub.pending_gateway_subscription_id
    if not expected or subscription_id != expected:
        if subscription_id and subscription_id == sub.gateway_subscription_id and _paid_already(db, payment_id):
            return access_for(sub)                     # the webhook got here first: all good
        raise BillingError("No payment is in progress for this business")
    if not gw.payment_signature_ok(payment_id, expected, signature):
        raise BillingError("This payment couldn't be verified")
    _activate_pending(db, sub, payment_id)
    return access_for(sub)


def mock_pay(db: Session, business_id: int) -> Access:
    """Mock mode only: act like the owner paid in the Razorpay window."""
    if settings.payments_enabled:
        raise BillingError("Real payments are switched on: use the Razorpay checkout")
    if payments_are_manual():
        raise BillingError(_manual_payment_message())
    sub = subscription_for(db, business_id)
    if not sub.pending_gateway_subscription_id:
        raise BillingError("Choose a plan first (POST /billing/subscribe)")
    payment_id = f"pay_mock_{secrets.token_hex(6)}"
    signature = gw.sign(f"{payment_id}|{sub.pending_gateway_subscription_id}", gw.MOCK_KEY_SECRET)
    return confirm_payment(db, business_id, payment_id, sub.pending_gateway_subscription_id, signature)


def activate_manually(db: Session, business_id: int, plan_code: str, days: int = 30,
                      amount: Optional[int] = None) -> Access:
    """You (the admin) got the owner's UPI / bank payment: switch their plan on for `days` days.
    Paying again before it ends adds the days on top. Records the payment and emails a receipt."""
    if plan_code not in PLANS:
        raise BillingError(f"Unknown plan '{plan_code}'")
    if not 1 <= days <= 366:
        raise BillingError("Days must be between 1 and 366")
    sub = subscription_for(db, business_id)
    if sub.gateway_subscription_id:
        raise BillingError("This business pays through Razorpay: change its plan there, not here")
    now = _now()
    current_end = _utc(sub.current_period_end)
    base = current_end if (sub.status == "active" and current_end and current_end > now and sub.plan == plan_code) else now
    sub.plan, sub.status, sub.cancel_at_period_end = plan_code, "active", False
    sub.pending_plan = sub.pending_gateway_subscription_id = None
    sub.current_period_end = base + timedelta(days=days)
    payment = Payment(business_id=business_id, subscription_id=sub.id, gateway_payment_id=f"manual_{secrets.token_hex(6)}",
                      plan=plan_code, amount=PLANS[plan_code].price if amount is None else amount)
    db.add(payment)
    db.commit()
    plan = PLANS[plan_code]
    bus.publish(business_id, "billing.paid", "Payment received ✅",
                f"{plan.name} plan active until {_day(sub.current_period_end)}", {"plan": plan.code})
    email_service.send_receipt(db, payment, sub.current_period_end)
    return access_for(sub)


def _paid_already(db: Session, payment_id: Optional[str]) -> bool:
    return bool(payment_id) and db.scalar(select(Payment.id).where(Payment.gateway_payment_id == payment_id)) is not None


def _record_payment(db: Session, sub: Subscription, payment_id: Optional[str],
                    amount: Optional[int]) -> Optional[Payment]:
    """Save a payment once (Razorpay may tell us twice: browser + webhook)."""
    if not payment_id or _paid_already(db, payment_id):
        return None
    plan = get_plan(sub.plan)
    payment = Payment(business_id=sub.business_id, subscription_id=sub.id, gateway_payment_id=payment_id,
                      plan=sub.plan, amount=amount if amount is not None else plan.price)
    db.add(payment)
    return payment


def _activate_pending(db: Session, sub: Subscription, payment_id: Optional[str],
                      period_end: Optional[datetime] = None, amount: Optional[int] = None) -> None:
    old_live = sub.gateway_subscription_id
    sub.plan = sub.pending_plan or sub.plan
    sub.gateway_subscription_id = sub.pending_gateway_subscription_id
    sub.pending_plan = sub.pending_gateway_subscription_id = None
    sub.status, sub.cancel_at_period_end = "active", False
    sub.current_period_end = period_end or _now() + timedelta(days=30)
    new_payment = _record_payment(db, sub, payment_id, amount)
    db.commit()
    if old_live and old_live != sub.gateway_subscription_id:           # upgrade: stop charging for the old plan
        try:
            gw.get_gateway().cancel(old_live, at_cycle_end=False)
        except gw.GatewayError as problem:
            logger.warning("Couldn't cancel old subscription %s: %s", old_live, problem)
    if new_payment:
        plan = get_plan(sub.plan)
        bus.publish(sub.business_id, "billing.paid", "Payment received ✅",
                    f"{plan.name} plan active until {_day(sub.current_period_end)}", {"plan": plan.code})
        email_service.send_receipt(db, new_payment, sub.current_period_end)


def cancel(db: Session, business_id: int) -> Access:
    sub = subscription_for(db, business_id)
    if sub.status == "trialing":
        raise BillingError("You're on the free trial: there's nothing to cancel")
    if sub.cancel_at_period_end or sub.status == "cancelled":
        raise BillingError("Already cancelled")
    if sub.gateway_subscription_id:
        try:
            gw.get_gateway().cancel(sub.gateway_subscription_id, at_cycle_end=True)
        except gw.GatewayError as problem:
            raise BillingError(str(problem)) from problem
    sub.cancel_at_period_end = True
    db.commit()
    return access_for(sub)


# ---------------------------------------------------------------------------
# Razorpay's doorbell: renewals, failures, cancellations
# ---------------------------------------------------------------------------
def handle_webhook(db: Session, event: dict) -> str:
    name = event.get("event", "")
    payload = event.get("payload") or {}
    entity = (payload.get("subscription") or {}).get("entity") or {}
    payment = (payload.get("payment") or {}).get("entity") or {}
    gateway_id = entity.get("id")
    if not gateway_id:
        return f"ignored {name or 'event'}: no subscription in it"
    sub = db.scalar(select(Subscription).where(
        (Subscription.gateway_subscription_id == gateway_id) | (Subscription.pending_gateway_subscription_id == gateway_id)))
    if sub is None:
        return f"ignored {name}: unknown subscription {gateway_id}"

    period_end = (datetime.fromtimestamp(entity["current_end"], tz=timezone.utc)
                  if entity.get("current_end") else None)
    amount = payment["amount"] // 100 if payment.get("amount") is not None else None     # Razorpay counts paise

    if gateway_id == sub.pending_gateway_subscription_id:               # a checkout finishing
        if name in ("subscription.activated", "subscription.charged", "subscription.authenticated"):
            _activate_pending(db, sub, payment.get("id"), period_end, amount)
            return f"{name}: {sub.plan} plan active"
        return f"ignored {name} for an unfinished checkout"

    if name == "subscription.charged":                                  # the monthly renewal
        sub.status, sub.current_period_end = "active", period_end or _now() + timedelta(days=30)
        new_payment = _record_payment(db, sub, payment.get("id"), amount)
        db.commit()
        if new_payment:
            bus.publish(sub.business_id, "billing.paid", "Plan renewed ✅",
                        f"Paid until {_day(sub.current_period_end)}", {"plan": sub.plan})
            email_service.send_receipt(db, new_payment, sub.current_period_end)
        return f"{name}: renewed until {_day(sub.current_period_end)}"
    if name in ("subscription.activated", "subscription.resumed"):
        sub.status = "active"
        if period_end:
            sub.current_period_end = period_end
    elif name in ("subscription.pending", "subscription.halted"):
        sub.status = "past_due"
        bus.publish(sub.business_id, "billing.problem", "Payment failed ⚠️",
                    access_for(sub).message, {"plan": sub.plan})
        email_service.send_payment_failed(db, sub, access_for(sub).message)
    elif name in ("subscription.cancelled", "subscription.completed"):
        sub.status, sub.cancel_at_period_end = "cancelled", False
    else:
        return f"ignored {name}"
    db.commit()
    return f"{name}: status now {sub.status}"


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------
def payments(db: Session, business_id: int) -> list[Payment]:
    return list(db.scalars(select(Payment).where(Payment.business_id == business_id).order_by(Payment.id.desc())))


class BusinessBilling(BaseModel):
    business_id: int
    name: str
    plan: str
    state: str
    usable: bool
    monthly_value: int             # ₹ this business pays you per month (0 on trial)
    ends_at: Optional[UTCDateTime]


class PlatformBilling(BaseModel):
    monthly_recurring_revenue: int            # ₹/month from plans that will renew
    paid_last_30_days: int                    # ₹ actually received
    businesses: int
    by_state: dict[str, int]
    by_plan: dict[str, int]                   # paying businesses per plan
    rows: list[BusinessBilling]


def platform_overview(db: Session) -> PlatformBilling:
    """For you, the admin: how much the website earns."""
    rows = []
    for business in db.scalars(select(Business).order_by(Business.id)):
        info = access(db, business.id)
        paying = info.state in ("active", "payment_failed")
        rows.append(BusinessBilling(business_id=business.id, name=business.name, plan=info.plan, state=info.state,
                                    usable=info.usable, monthly_value=info.price if paying else 0,
                                    ends_at=info.ends_at))
    since = _now() - timedelta(days=30)
    paid = db.scalar(select(func.coalesce(func.sum(Payment.amount), 0))
                     .where(Payment.status == "paid", Payment.paid_at >= since))
    by_state: dict[str, int] = {}
    by_plan: dict[str, int] = {}
    for row in rows:
        by_state[row.state] = by_state.get(row.state, 0) + 1
        if row.monthly_value:
            by_plan[row.plan] = by_plan.get(row.plan, 0) + 1
    return PlatformBilling(monthly_recurring_revenue=sum(r.monthly_value for r in rows), paid_last_30_days=paid,
                           businesses=len(rows), by_state=by_state, by_plan=by_plan, rows=rows)
