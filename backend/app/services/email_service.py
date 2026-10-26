"""
Emails: write them down first, then send.

    queue()          writes the email into the emails table ("queued").
                     A dedupe_key means "only ever once", e.g. one trial reminder
                     per business per trial: asking twice does nothing.
    deliver_pending() sends every queued email, and retries failed ones (up to
                     3 tries, a few minutes apart). Called right after a request
                     (in the background, so pages stay fast) and every minute by the scheduler.

Why the table? If the email provider has a bad minute, nothing is lost: the
scheduler simply tries again. And you (admin) can see every email at /admin/emails.

The specific emails (welcome, reset, reminders, receipts) are at the bottom.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.emails import templates
from app.models import Business, Email, Payment, Subscription, User
from app.services.mailer import MailError, get_mailer

logger = logging.getLogger("emails")
SESSION_FACTORY = SessionLocal          # tests point this at their own database
MAX_ATTEMPTS = 3
RETRY_AFTER = timedelta(minutes=5)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    return None if dt is None else (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc))


def link(path: str) -> str:
    """A link into the website (the frontend)."""
    return f"{settings.frontend_origin.rstrip('/')}/{path.lstrip('/')}"


def queue(db: Session, to: str, kind: str, content: tuple[str, str, str], business_id: Optional[int] = None,
          user_id: Optional[int] = None, dedupe_key: Optional[str] = None) -> Optional[Email]:
    if dedupe_key and db.scalar(select(Email.id).where(Email.dedupe_key == dedupe_key)):
        return None                                           # already sent (or on its way): never twice
    subject, text, html = content
    email = Email(to=to, kind=kind, subject=subject, text=text, html=html, business_id=business_id,
                  user_id=user_id, dedupe_key=dedupe_key)
    db.add(email)
    db.commit()
    return email


def _send_one(db: Session, email: Email) -> bool:
    # Claim it first (queued/failed → sending), so two senders can never both send it
    claimed = db.execute(update(Email).where(Email.id == email.id, Email.status.in_(("queued", "failed")))
                         .values(status="sending", attempts=Email.attempts + 1)).rowcount
    db.commit()
    if not claimed:
        return False
    db.refresh(email)
    try:
        get_mailer().send(email.id, email.kind, email.to, email.subject, email.text, email.html)
    except MailError as problem:
        email.status, email.error = "failed", str(problem)[:500]
        db.commit()
        logger.warning("Email %s to %s failed (try %s): %s", email.id, email.to, email.attempts, problem)
        return False
    email.status, email.error, email.sent_at = "sent", "", _now()
    db.commit()
    return True


def deliver_pending(db: Session) -> int:
    retry_before = _now() - RETRY_AFTER
    waiting = db.scalars(select(Email).where(
        (Email.status == "queued")
        | ((Email.status == "failed") & (Email.attempts < MAX_ATTEMPTS) & (Email.created_at <= retry_before))
    ).order_by(Email.id).limit(100))
    return sum(_send_one(db, email) for email in list(waiting))


def deliver_in_background() -> None:
    """For BackgroundTasks: runs right after the reply, with its own database session."""
    db = SESSION_FACTORY()
    try:
        deliver_pending(db)
    except Exception:  # noqa: BLE001 - an email problem must never crash anything; the scheduler retries
        logger.exception("Background email delivery failed")
    finally:
        db.close()


def owners_of(db: Session, business_id: int) -> list[User]:
    return list(db.scalars(select(User).where(User.business_id == business_id, User.role == "owner", User.is_active)))


# ---------------------------------------------------------------------------
# The emails
# ---------------------------------------------------------------------------
def send_welcome(db: Session, user: User, business: Business, trial_ends: datetime) -> None:
    queue(db, user.email, "welcome", templates.welcome(user.name, business.name, trial_ends, link("/")),
          business.id, user.id, dedupe_key=f"welcome:{user.id}")


def send_password_reset(db: Session, user: User, token: str) -> None:
    queue(db, user.email, "password_reset",
          templates.password_reset(user.name, link(f"/reset-password?token={token}"), settings.password_reset_minutes),
          user.business_id, user.id)


def send_password_changed(db: Session, user: User) -> None:
    queue(db, user.email, "password_changed", templates.password_changed(user.name, link("/forgot-password")),
          user.business_id, user.id)


def send_staff_invite(db: Session, staff: User, owner: User, token: str, days: int) -> None:
    business = db.get(Business, staff.business_id)
    queue(db, staff.email, "staff_invite",
          templates.staff_invite(staff.name, business.name, owner.name, link(f"/reset-password?token={token}&welcome=1"),
                                 days), business.id, staff.id, dedupe_key=f"invite:{staff.id}")


def send_receipt(db: Session, payment: Payment, until: datetime) -> None:
    from app.plans import get_plan
    business = db.get(Business, payment.business_id)
    for owner in owners_of(db, payment.business_id):
        queue(db, owner.email, "receipt",
              templates.receipt(owner.name, business.name, get_plan(payment.plan).name, payment.amount,
                                payment.gateway_payment_id, _utc(payment.paid_at) or _now(), until, link("/billing")),
              business.id, owner.id, dedupe_key=f"receipt:{payment.gateway_payment_id}:{owner.id}")


def send_payment_failed(db: Session, sub: Subscription, message: str) -> None:
    business = db.get(Business, sub.business_id)
    period = (_utc(sub.current_period_end) or _now()).date().isoformat()
    for owner in owners_of(db, sub.business_id):
        queue(db, owner.email, "payment_failed",
              templates.payment_failed(owner.name, business.name, message, link("/billing")),
              business.id, owner.id, dedupe_key=f"payment_failed:{sub.id}:{period}:{owner.id}")


def trial_reminders(db: Session, now: Optional[datetime] = None) -> int:
    """Scheduler job: 'your trial ends in 3 days' and 'your trial has ended', once each per trial.
    Only in the daytime (9am-8pm India time)."""
    now = now or _now()
    hour = now.astimezone(templates.IST).hour
    if not 9 <= hour < 20:
        return 0
    queued = 0
    soon = now + timedelta(days=settings.trial_reminder_days)
    for sub in db.scalars(select(Subscription).where(Subscription.status == "trialing")):
        ends = _utc(sub.trial_ends_at)
        business = db.get(Business, sub.business_id)
        if business is None:
            continue
        stamp = ends.date().isoformat()
        for owner in owners_of(db, sub.business_id):
            if now < ends <= soon:
                days_left = max(1, round((ends - now).total_seconds() / 86400))     # 2.9 days → "in 3 days"
                made = queue(db, owner.email, "trial_ending",
                             templates.trial_ending(owner.name, business.name, ends, days_left, link("/billing/plans")),
                             business.id, owner.id, dedupe_key=f"trial_ending:{sub.id}:{stamp}:{owner.id}")
            elif ends <= now < ends + timedelta(days=7):
                made = queue(db, owner.email, "trial_ended",
                             templates.trial_ended(owner.name, business.name, link("/billing/plans")),
                             business.id, owner.id, dedupe_key=f"trial_ended:{sub.id}:{stamp}:{owner.id}")
            else:
                made = None
            queued += made is not None
    return queued
